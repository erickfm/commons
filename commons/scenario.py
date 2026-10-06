"""Scenario files: one YAML file describes a whole swarm experiment.

    name: hello
    agents: 4
    runtimes: [claude_code, codex]      # cycled across agents: agent_1, agent_2, ...
    models:                             # Inspect model names per runtime
      claude_code: anthropic/claude-haiku-4-5-20251001
      codex: openai/gpt-5-mini
      basic: openai/gpt-5-mini
    system_prompt: You are an agent working in a team.
    task: Read the team board, post a hello, and stop.
    internet: off                       # off | allowlist | open
    allow: [pypi.org, files.pythonhosted.org]
    scripted_posts:                     # posts the board makes itself, seconds after agents start
      - {at: 30, as: agent_9, message: "..."}
    limits: {time: 900, tokens: 500000, answer_tokens: 16000}  # per agent; answer_tokens caps each model reply
    resources: {mem: 4g, cpus: 2}       # per agent container
    per_agent:                          # settings for individual agents, by name
      agent_3:
        role: plant                     # free-text label, recorded in the results
        system_prompt: ...              # replaces the shared system prompt for this agent
        task: ...                       # optional: replaces the shared task
        runtime: basic                  # optional: replaces this agent's type
        model: openai/gpt-5             # optional: replaces this agent's model
"""

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from commons.compose import write_compose

RUNTIMES = ("claude_code", "codex", "basic")
PER_AGENT_FIELDS = {"role", "system_prompt", "task", "runtime", "model"}


@dataclass
class Scenario:
    name: str
    task: str
    agents: int = 4
    runtimes: list[str] = field(default_factory=lambda: ["claude_code"])
    models: dict[str, str] = field(default_factory=dict)
    system_prompt: str = "You are an agent working in a team."
    internet: str = "off"
    allow: list[str] = field(default_factory=list)
    scripted_posts: list[dict] = field(default_factory=list)
    limits: dict = field(default_factory=lambda: {"time": 900, "tokens": 500_000, "answer_tokens": 16_000})
    resources: dict = field(default_factory=lambda: {"mem": "4g", "cpus": 2})
    per_agent: dict[str, dict] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.internet is False:  # YAML reads an unquoted `off` as false
            self.internet = "off"
        names = {f"agent_{i}" for i in range(1, self.agents + 1)}
        for name, settings in self.per_agent.items():
            if name not in names:
                raise ValueError(f"per_agent: {name} isn't one of agent_1..agent_{self.agents}")
            extra = set(settings) - PER_AGENT_FIELDS
            if extra:
                raise ValueError(f"per_agent.{name}: unknown settings {extra}; choose from {PER_AGENT_FIELDS}")
        unknown = set(self.runtimes) | {s["runtime"] for s in self.per_agent.values() if "runtime" in s}
        unknown -= set(RUNTIMES)
        if unknown:
            raise ValueError(f"unknown runtimes {unknown}; choose from {RUNTIMES}")

    @classmethod
    def load(cls, path: str | Path) -> "Scenario":
        return cls(**yaml.safe_load(Path(path).read_text()))

    def _own(self, i: int) -> dict:
        return self.per_agent.get(f"agent_{i}", {})

    def runtime(self, i: int) -> str:
        return self._own(i).get("runtime", self.runtimes[(i - 1) % len(self.runtimes)])

    def model(self, i: int) -> str | None:
        return self._own(i).get("model", self.models.get(self.runtime(i)))

    def system_prompt_for(self, i: int) -> str:
        return self._own(i).get("system_prompt", self.system_prompt)

    def task_for(self, i: int) -> str:
        return self._own(i).get("task", self.task)

    def role(self, i: int) -> str | None:
        return self._own(i).get("role")

    def write_compose(self, directory: str | Path) -> Path:
        return write_compose(
            self.agents,
            Path(directory) / f"{self.name}.yaml",
            internet=self.internet,
            allow=self.allow,
            scripted_posts=self.scripted_posts,
            mem=self.resources.get("mem", "4g"),
            cpus=self.resources.get("cpus", 2),
        )
