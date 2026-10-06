"""Swarm solver: run N agents at once in their own sandboxes, sharing the board.

Each agent runs under its own time and token limits, and one agent's failure is
recorded without stopping the others. Outcomes are read from the board's (and,
when internet is on, the egress proxy's) event logs rather than trusted from
agent exit status. Private reports to humans and private messages are in the board
log too. Each agent runs inside a span named after it. Each agent with a workspace gets its own copy
in /work as a git repo, and its changes are recorded as a diff.
"""

import asyncio
import json
import os
import time
from collections import Counter
from typing import Callable

from inspect_ai.agent import Agent, run
from inspect_ai.solver import Generate, Solver, TaskState, solver
from inspect_ai.tool import MCPServerConfigHTTP
from inspect_ai.util import sandbox, span, time_limit, token_limit
from inspect_swe import claude_code, codex_cli

BOARD = MCPServerConfigHTTP(name="board", type="http", url="http://board:8000/mcp")
WORKDIR = "/work"
GIT_BASELINE = (
    "cd /work && git init -q && git -c user.name=team -c user.email=team@example.com add -A"
    " && git -c user.name=team -c user.email=team@example.com commit -qm 'initial'"
)
START_SCRIPTED_POSTS = "import urllib.request as u; u.urlopen(u.Request('http://127.0.0.1:8000/api/start', method='POST'))"


def claude_code_agent(i: int, system_prompt: str, model: str | None = None) -> Agent:
    """Claude Code as shipped, on Anthropic models, requests forwarded unchanged."""
    key = os.environ.get("COMMONS_AGENT_ANTHROPIC_KEY")
    return claude_code(
        sandbox=f"agent_{i}",
        user="agent",
        model=model,
        replace_system_prompt=system_prompt,
        transparent_proxy=True,
        mcp_servers=[BOARD],
        env={"ANTHROPIC_AUTH_TOKEN": key} if key else None,
    )


def codex_agent(i: int, system_prompt: str, model: str | None = "openai/gpt-5") -> Agent:
    """Codex CLI as shipped, on OpenAI models, with hosted extras switched off."""
    key = os.environ.get("COMMONS_AGENT_OPENAI_KEY")
    return codex_cli(
        sandbox=f"agent_{i}",
        user="agent",
        model=model,
        system_prompt=system_prompt,
        transparent_proxy=True,
        web_search="disabled",
        goals=False,
        home_dir="/home/agent",
        cwd=WORKDIR,
        mcp_servers=[BOARD],
        env={"OPENAI_API_KEY": key} if key else None,
    )


async def _read_log(service: str, path: str) -> list[dict]:
    try:
        out = (await sandbox(service).exec(["cat", path])).stdout
    except Exception:
        return []
    return [json.loads(line) for line in out.splitlines() if line.strip()]


@solver
def swarm(
    make_agent: Callable[[int], Agent],
    n_agents: int,
    agent_time_limit: float = 900,
    agent_token_limit: int | None = 500_000,
    task_for: Callable[[int], str] | None = None,
    role_for: Callable[[int], str | None] | None = None,
    describe: Callable[[int], dict] | None = None,
    workspace_for: Callable[[int], dict[str, str]] | None = None,
) -> Solver:
    async def solve(state: TaskState, generate: Generate) -> TaskState:
        async def one(i: int) -> dict:
            # Inspect limits are single-use, so each agent gets its own.
            limits = [time_limit(agent_time_limit)]
            if agent_token_limit:
                limits.append(token_limit(agent_token_limit))
            start = time.time()
            # A span named after the agent lets analysis attribute each model call to its agent.
            async with span(f"agent_{i}", type="swarm_agent"):
                try:
                    task = task_for(i) if task_for else state.input_text
                    _, exceeded = await run(make_agent(i), task, limits=limits)
                    status = f"limit: {exceeded.type}" if exceeded else "finished"
                except Exception as e:
                    status = f"error: {e!r}"[:300]
            role = role_for(i) if role_for else None
            return {
                "agent": f"agent_{i}",
                "role": role,
                **(describe(i) if describe else {}),
                "status": status,
                "seconds": round(time.time() - start, 1),
            }

        workspaces = {i: workspace_for(i) if workspace_for else {} for i in range(1, n_agents + 1)}

        async def setup(i: int) -> None:
            box = sandbox(f"agent_{i}")
            for rel, content in workspaces[i].items():
                await box.write_file(f"{WORKDIR}/{rel}", content)
            await box.exec(["chown", "-R", "agent:agent", WORKDIR], user="root")
            await box.exec(["bash", "-c", GIT_BASELINE], user="agent")

        async def changes(i: int) -> str:
            r = await sandbox(f"agent_{i}").exec(
                ["bash", "-c", "cd /work && git add -A && git diff --cached"], user="agent"
            )
            return r.stdout

        await asyncio.gather(*(setup(i) for i in workspaces if workspaces[i]))
        await sandbox("board").exec(["python", "-c", START_SCRIPTED_POSTS])
        agents = await asyncio.gather(*(one(i) for i in range(1, n_agents + 1)))

        board = await _read_log("board", "/data/board.jsonl")
        egress = await _read_log("egress", "/data/egress.jsonl")
        posts = Counter(e["agent"] for e in board if e["event"] == "post" and not e.get("scripted"))
        reports = Counter(e["agent"] for e in board if e["event"] == "report")
        sent = Counter(e["agent"] for e in board if e["event"] == "dm" and not e.get("scripted"))
        connections = Counter(e["agent"] for e in egress)
        diffs = await asyncio.gather(*(changes(i) if workspaces[i] else asyncio.sleep(0) for i in range(1, n_agents + 1)))
        for a, diff in zip(agents, diffs):
            a["posts"] = posts.get(a["agent"], 0)
            a["reports"] = reports.get(a["agent"], 0)
            a["messages_sent"] = sent.get(a["agent"], 0)
            a["web_connections"] = connections.get(a["agent"], 0)
            if workspaces[int(a["agent"].split("_")[1])]:
                a["changes"] = diff
        state.metadata.update(agents=agents, board_events=board, egress_events=egress)
        return state

    return solve
