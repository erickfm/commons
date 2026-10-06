"""Inspect task that runs any scenario file.

    uv run inspect eval commons/tasks.py -T scenario=scenarios/hello.yaml
"""

from pathlib import Path

from inspect_ai import Task, task
from inspect_ai.dataset import Sample
from inspect_ai.model import GenerateConfig

from commons.basic_agent import basic_agent
from commons.scenario import Scenario
from commons.swarm import claude_code_agent, codex_agent, swarm

ROOT = Path(__file__).resolve().parent.parent
COMPOSE_DIR = ROOT / ".compose"


@task
def scenario(scenario: str) -> Task:
    # Inspect runs tasks from their own folder, so relative paths are taken from the repo root.
    path = Path(scenario)
    s = Scenario.load(path if path.is_absolute() else ROOT / path)

    def make(i: int):
        runtime, model, prompt = s.runtime(i), s.model(i), s.system_prompt_for(i)
        if runtime == "claude_code":
            return claude_code_agent(i, prompt, model)
        if runtime == "codex":
            return codex_agent(i, prompt, model)
        return basic_agent(f"agent_{i}", prompt, model, max_tokens=answer_tokens)

    answer_tokens = s.limits.get("answer_tokens", 16_000)

    return Task(
        name=s.name,
        dataset=[Sample(input=s.task)],
        solver=swarm(
            make,
            s.agents,
            s.limits.get("time", 900),
            s.limits.get("tokens"),
            task_for=s.task_for,
            role_for=s.role,
            workspace=s.workspace_files(),
        ),
        sandbox=("docker", str(s.write_compose(COMPOSE_DIR))),
        # Caps each model reply for calls Inspect makes itself (the basic agent, translated CLI calls).
        config=GenerateConfig(max_tokens=answer_tokens),
    )
