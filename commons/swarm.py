"""Swarm solver: run N agents at once in their own sandboxes, sharing the board.

Each agent runs under its own time and token limits, and one agent's failure is
recorded without stopping the others. Outcomes are read from the board's event
log rather than trusted from agent exit status.
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


def claude_code_agent(i: int, system_prompt: str) -> Agent:
    """Claude Code as shipped, on Anthropic models, requests forwarded unchanged."""
    key = os.environ.get("COMMONS_AGENT_ANTHROPIC_KEY")
    return claude_code(
        sandbox=f"agent_{i}",
        user="agent",
        replace_system_prompt=system_prompt,
        transparent_proxy=True,
        mcp_servers=[BOARD],
        env={"ANTHROPIC_AUTH_TOKEN": key} if key else None,
    )


def codex_agent(i: int, system_prompt: str, model: str = "openai/gpt-5") -> Agent:
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


@solver
def swarm(
    make_agent: Callable[[int], Agent],
    n_agents: int,
    agent_time_limit: float = 900,
    agent_token_limit: int | None = 500_000,
) -> Solver:
    async def solve(state: TaskState, generate: Generate) -> TaskState:
        async def one(i: int) -> dict:
            # Inspect limits are single-use, so each agent gets its own.
            limits = [time_limit(agent_time_limit)]
            if agent_token_limit:
                limits.append(token_limit(agent_token_limit))
            start = time.time()
            try:
                _, exceeded = await run(make_agent(i), state.input_text, limits=limits)
                status = f"limit: {exceeded.type}" if exceeded else "finished"
            except Exception as e:
                status = f"error: {e!r}"[:300]
            return {"agent": f"agent_{i}", "status": status, "seconds": round(time.time() - start, 1)}

        agents = await asyncio.gather(*(one(i) for i in range(1, n_agents + 1)))
        log = (await sandbox("board").exec(["cat", "/data/board.jsonl"])).stdout
        events = [json.loads(line) for line in log.splitlines() if line.strip()]
        posts = Counter(e["agent"] for e in events if e["event"] == "post")
        for a in agents:
            a["posts"] = posts.get(a["agent"], 0)
        state.metadata.update(agents=agents, board_events=events)
        return state

    return solve
