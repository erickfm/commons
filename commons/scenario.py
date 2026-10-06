"""Scenario files: one YAML file describes a whole swarm experiment.

    name: hello
    agents: 4
    runtimes: [claude_code, codex]      # cycled across agents: agent_1, agent_2, ...
    models:                             # Inspect model names per runtime
      claude_code: anthropic/claude-haiku-4-5-20251001
      codex: openai/gpt-5-mini
      own_loop: openai/gpt-5-mini
    system_prompt: You are an agent working in a team.
    task: Read the team board, post a hello, and stop.
    internet: off                       # off | allowlist | open
    allow: [pypi.org, files.pythonhosted.org]
    plants:                             # scripted posts, seconds after agents start
      - {at: 30, as: agent_9, message: "..."}
    limits: {time: 900, tokens: 500000, answer_tokens: 16000}  # per agent; answer_tokens caps each model reply
    resources: {mem: 4g, cpus: 2}       # per agent container
"""

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from commons.compose import write_compose

RUNTIMES = ("claude_code", "codex", "own_loop")


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
    plants: list[dict] = field(default_factory=list)
    limits: dict = field(default_factory=lambda: {"time": 900, "tokens": 500_000, "answer_tokens": 16_000})
    resources: dict = field(default_factory=lambda: {"mem": "4g", "cpus": 2})

    def __post_init__(self) -> None:
        if self.internet is False:  # YAML reads an unquoted `off` as false
            self.internet = "off"
        unknown = set(self.runtimes) - set(RUNTIMES)
        if unknown:
            raise ValueError(f"unknown runtimes {unknown}; choose from {RUNTIMES}")

    @classmethod
    def load(cls, path: str | Path) -> "Scenario":
        return cls(**yaml.safe_load(Path(path).read_text()))

    def runtime(self, i: int) -> str:
        return self.runtimes[(i - 1) % len(self.runtimes)]

    def write_compose(self, directory: str | Path) -> Path:
        return write_compose(
            self.agents,
            Path(directory) / f"{self.name}.yaml",
            internet=self.internet,
            allow=self.allow,
            plants=self.plants,
            mem=self.resources.get("mem", "4g"),
            cpus=self.resources.get("cpus", 2),
        )
