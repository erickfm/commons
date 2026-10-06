"""Smallest end-to-end swarm: agents read the board, post hello, and stop.

Odd-numbered agents are Claude Code, even-numbered are Codex.

    uv run inspect eval examples/hello_swarm.py --model anthropic/claude-haiku-4-5-20251001 -T n=4
"""

from pathlib import Path

from inspect_ai import Task, task
from inspect_ai.dataset import Sample

from commons.compose import write_compose
from commons.swarm import claude_code_agent, codex_agent, swarm

SYSTEM = "You are an agent working in a team."
TASK = "Read the team board, post one short hello saying which agent you are, then read the board again and stop."


@task
def hello_swarm(n: int = 4, codex_model: str = "openai/gpt-5-mini", internet: str = "off"):
    compose = write_compose(n, Path(__file__).parent / ".compose" / f"hello_{n}.yaml", internet=internet)

    def make(i):
        return claude_code_agent(i, SYSTEM) if i % 2 else codex_agent(i, SYSTEM, codex_model)

    return Task(dataset=[Sample(input=TASK)], solver=swarm(make, n), sandbox=("docker", str(compose)))
