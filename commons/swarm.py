"""Swarm solver: run N agents at once in their own sandboxes, sharing the board.

Each agent runs under its own time and token limits, and one agent's failure is
recorded without stopping the others. Outcomes are read from the board's (and,
when internet is on, the egress proxy's) event logs rather than trusted from
agent exit status.
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
from inspect_ai.util import sandbox, time_limit, token_limit
from inspect_swe import claude_code, codex_cli

BOARD = MCPServerConfigHTTP(name="board", type="http", url="http://board:8000/mcp")
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
        cwd="/home/agent",
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
) -> Solver:
    async def solve(state: TaskState, generate: Generate) -> TaskState:
        async def one(i: int) -> dict:
            # Inspect limits are single-use, so each agent gets its own.
            limits = [time_limit(agent_time_limit)]
            if agent_token_limit:
                limits.append(token_limit(agent_token_limit))
            start = time.time()
            try:
                task = task_for(i) if task_for else state.input_text
                _, exceeded = await run(make_agent(i), task, limits=limits)
                status = f"limit: {exceeded.type}" if exceeded else "finished"
            except Exception as e:
                status = f"error: {e!r}"[:300]
            role = role_for(i) if role_for else None
            return {"agent": f"agent_{i}", "role": role, "status": status, "seconds": round(time.time() - start, 1)}

        await sandbox("board").exec(["python", "-c", START_SCRIPTED_POSTS])
        agents = await asyncio.gather(*(one(i) for i in range(1, n_agents + 1)))

        board = await _read_log("board", "/data/board.jsonl")
        egress = await _read_log("egress", "/data/egress.jsonl")
        posts = Counter(e["agent"] for e in board if e["event"] == "post" and not e.get("scripted"))
        connections = Counter(e["agent"] for e in egress)
        for a in agents:
            a["posts"] = posts.get(a["agent"], 0)
            a["web_connections"] = connections.get(a["agent"], 0)
        state.metadata.update(agents=agents, board_events=board, egress_events=egress)
        return state

    return solve
