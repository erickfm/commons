"""Scenario files: one YAML file describes a whole swarm experiment.

    name: hello
    agents: 4
    runtimes: [claude_code, codex]      # cycled across agents: agent_1, agent_2, ...
    models:                             # Inspect model names per runtime
      claude_code: anthropic/claude-haiku-4-5-20251001
      codex: openai/gpt-5-mini
      basic: openai/gpt-5-mini
    system_prompt: You are {agent}, an agent working in a team.   # {agent} becomes each agent's name
    task: Read the team board, post a hello, and stop.
    internet: off                       # off | allowlist | open
    channels: [board, report, messages] # tools agents get: public board, private report to humans,
                                        # private agent-to-agent messages (default: [board])
    allow: [pypi.org, files.pythonhosted.org]
    scripted_posts:                     # posts the board makes itself, seconds after agents start
      - {at: 30, as: agent_9, message: "..."}
      - {at: 0, as: agent_9, to: agent_2, message: "..."}   # with `to`: a private message (needs messages channel)
    limits: {time: 900, tokens: 500000, answer_tokens: 16000}  # per agent; answer_tokens caps each model reply
    resources: {mem: 4g, cpus: 2}       # per agent container
    workspace: workspaces/dates         # folder copied into each agent's /work (relative to this file)
    sites:                              # mock websites on the private network, over plain HTTP, all requests logged
      docs.example.dev: sites/docs      # hostname: folder (relative to this file); see services/web.py
    env: {PIP_INDEX_URL: http://pypi.example.dev/simple/}   # environment variables for every agent
    generate: {effort: medium}          # model settings for basic agents (any Inspect GenerateConfig field)
    per_agent:                          # settings for individual agents, by name
      agent_3:
        role: plant                     # free-text label, recorded in the results
        system_prompt: ...              # replaces the shared system prompt for this agent
        task: ...                       # optional: replaces the shared task
        runtime: basic                  # optional: replaces this agent's type
        model: openai/gpt-5             # optional: replaces this agent's model
        workspace: null                 # optional: a different folder for this agent, or null for none
"""

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from commons.compose import CHANNELS, write_compose

RUNTIMES = ("claude_code", "codex", "basic")
PER_AGENT_FIELDS = {"role", "system_prompt", "task", "runtime", "model", "workspace"}


@dataclass
class Scenario:
    name: str
    task: str = ""                      # optional when every agent has its own under per_agent
    agents: int = 4
    runtimes: list[str] = field(default_factory=lambda: ["claude_code"])
    models: dict[str, str] = field(default_factory=dict)
    system_prompt: str = "You are an agent working in a team."
    internet: str = "off"
    allow: list[str] = field(default_factory=list)
    channels: list[str] = field(default_factory=lambda: ["board"])
    scripted_posts: list[dict] = field(default_factory=list)
    limits: dict = field(default_factory=lambda: {"time": 900, "tokens": 500_000, "answer_tokens": 16_000})
    resources: dict = field(default_factory=lambda: {"mem": "4g", "cpus": 2})
    per_agent: dict[str, dict] = field(default_factory=dict)
    workspace: str | None = None
    sites: dict[str, str] = field(default_factory=dict)
    env: dict[str, str] = field(default_factory=dict)
    generate: dict = field(default_factory=dict)

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
        if set(self.channels) - set(CHANNELS):
            raise ValueError(f"unknown channels {set(self.channels) - set(CHANNELS)}; choose from {CHANNELS}")
        if any("to" in p for p in self.scripted_posts) and "messages" not in self.channels:
            raise ValueError("scripted posts with `to` are private messages; add `messages` to channels")
        missing = [f"agent_{i}" for i in range(1, self.agents + 1) if not self.task_for(i)]
        if missing:
            raise ValueError(f"no task for {missing}: set `task`, or a task for each agent under per_agent")
        unknown = set(self.runtimes) | {s["runtime"] for s in self.per_agent.values() if "runtime" in s}
        unknown -= set(RUNTIMES)
        if unknown:
            raise ValueError(f"unknown runtimes {unknown}; choose from {RUNTIMES}")

    @classmethod
    def load(cls, path: str | Path) -> "Scenario":
        path = Path(path)
        s = cls(**yaml.safe_load(path.read_text()))

        def resolve(folder: str | None) -> str | None:
            if not folder:
                return None
            folder = str((path.parent / folder).resolve())
            if not Path(folder).is_dir():
                raise ValueError(f"workspace folder not found: {folder}")
            return folder

        s.workspace = resolve(s.workspace)
        s.sites = {host.lower(): resolve(folder) for host, folder in s.sites.items()}
        for settings in s.per_agent.values():
            if "workspace" in settings:
                settings["workspace"] = resolve(settings["workspace"])
        return s

    def workspace_for(self, i: int) -> str | None:
        return self._own(i).get("workspace", self.workspace)

    def workspace_files(self, i: int = 1) -> dict[str, str]:
        """Files to copy into agent i's /work, keyed by relative path (empty if it has no workspace)."""
        folder = self.workspace_for(i)
        if not folder:
            return {}
        root = Path(folder)
        files = (f for f in sorted(root.rglob("*")) if f.is_file() and "__pycache__" not in f.parts)
        return {str(f.relative_to(root)): f.read_text() for f in files}

    def site_files(self) -> dict[str, str]:
        """Every mock site's files, keyed by path under /sites (hostname/relative path)."""
        out = {}
        for host, folder in self.sites.items():
            root = Path(folder)
            for f in sorted(root.rglob("*")):
                if f.is_file():
                    out[f"{host}/{f.relative_to(root)}"] = f.read_text()
        return out

    def _own(self, i: int) -> dict:
        return self.per_agent.get(f"agent_{i}", {})

    def runtime(self, i: int) -> str:
        return self._own(i).get("runtime", self.runtimes[(i - 1) % len(self.runtimes)])

    def model(self, i: int) -> str | None:
        return self._own(i).get("model", self.models.get(self.runtime(i)))

    def system_prompt_for(self, i: int) -> str:
        return self._own(i).get("system_prompt", self.system_prompt).replace("{agent}", f"agent_{i}")

    def task_for(self, i: int) -> str:
        return self._own(i).get("task", self.task).replace("{agent}", f"agent_{i}")

    def role(self, i: int) -> str | None:
        return self._own(i).get("role")

    def write_compose(self, directory: str | Path) -> Path:
        return write_compose(
            self.agents,
            Path(directory) / f"{self.name}.yaml",
            internet=self.internet,
            allow=self.allow,
            scripted_posts=self.scripted_posts,
            channels=self.channels,
            sites=list(self.sites),
            env=self.env,
            mem=self.resources.get("mem", "4g"),
            cpus=self.resources.get("cpus", 2),
        )
