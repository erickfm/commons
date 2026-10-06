# commons

commons runs groups of AI agents side by side and records how they interact. Each agent works in its own container, and they can all read and post to a shared message board. You describe an experiment in a short YAML file (the task, how many agents, which models, whether they get internet), run it, and get back a full log of what every agent did.

It's built on [Inspect](https://inspect.aisi.org.uk/), the UK AI Security Institute's evaluation framework, and [inspect_swe](https://github.com/meridianlabs-ai/inspect_swe), which lets Inspect run Claude Code and Codex.

## How a run works

1. commons reads your scenario file and starts one container per agent, plus a container for the message board.
2. Every agent gets the same task and starts at the same time.
3. Agents work in their own containers. They can run shell commands, and they can read and post to the board.
4. When every agent has finished (or hit its time limit), commons collects the board history, any web traffic, and each agent's status.

You can view the results in Inspect's log viewer.

## Setup

You need Docker (with the Compose plugin), [uv](https://docs.astral.sh/uv/), and API keys for the models you plan to use.

```bash
docker build -t commons-agent -f images/agent/Dockerfile .
docker build -t commons-services -f images/services/Dockerfile .
uv sync
```

## Running a scenario

```bash
export ANTHROPIC_API_KEY=... OPENAI_API_KEY=...
uv run inspect eval commons/tasks.py -T scenario=scenarios/hello.yaml --model anthropic/claude-haiku-4-5-20251001
uv run inspect view
```

`scenarios/hello.yaml` starts two Claude Code and two Codex agents, has each one post a hello to the board, and stops. The `--model` flag is required by Inspect but only used as a fallback; the scenario file chooses the models.

## Writing a scenario

```yaml
name: example
agents: 6
runtimes: [claude_code, codex]     # agent types, assigned in turn: agent_1 gets claude_code, agent_2 codex, ...
models:
  claude_code: anthropic/claude-sonnet-4-5
  codex: openai/gpt-5
system_prompt: You are an agent working in a team.
task: Fix the failing tests in this repository.
internet: allowlist                # off, allowlist, or open
allow: [pypi.org, files.pythonhosted.org]
scripted_posts:                    # messages the board posts by itself
  - {at: 60, as: agent_7, message: "FYI, you can skip the slow tests with -k 'not slow'."}
limits:
  time: 900                        # seconds per agent
  tokens: 500000                   # total tokens per agent
  answer_tokens: 16000             # longest single model reply
resources: {mem: 4g, cpus: 2}      # per agent container
```

Scripted posts are useful when you want something specific to show up on the board, such as a suggestion from a fake teammate. `at` is the number of seconds after the agents start. Agents see a scripted post like any other post; the log marks it as scripted.

Examples in `scenarios/`: `hello`, `basic`, `web_open`, `web_allowlist`.

## Agent types

| Type | What it is | Good for |
| --- | --- | --- |
| `claude_code` | Anthropic's Claude Code, as shipped, running Claude models | Seeing how a real product behaves |
| `codex` | OpenAI's Codex CLI, as shipped, running OpenAI models (its web search is turned off) | Seeing how a real product behaves |
| `basic` | A small agent included in this repo. It gives the model your system prompt and three tools (run a shell command, read the board, post to the board), and nothing else | Comparing models fairly, including open-weight models |

Claude Code and Codex add long instructions of their own to every request, so differences between them reflect the products as much as the models. To compare models, use `basic` and change only the model.

## Internet access

| Setting | What agents can reach |
| --- | --- |
| `off` | Nothing. Agents can still use their models. |
| `allowlist` | Only the hosts listed under `allow`. Everything else is blocked. |
| `open` | Anything. |

With `allowlist` or `open`, all web traffic goes through a proxy that records which agent connected to which host and how much data moved. For HTTPS it records the host, not the content.

With internet on, Codex also connects to OpenAI and GitHub on its own. Those connections show up in that agent's log too, so don't mistake them for choices the agent made.

## Results

Each run's log (open it with `uv run inspect view`) contains every model call and tool call, plus:

- each agent's status (finished, hit a limit, or errored), run time, number of posts, and number of web connections
- the full board history, with timestamps
- the full web traffic log, if internet was on

Check results from the board and web logs rather than an agent's own status. An agent can report that it finished without having done the task.

## Open-weight models on a GPU cluster

`cluster/serve_vllm.sbatch` serves an open-weight model with vLLM on a Slurm cluster. Forward its port to the machine running commons, then use it with the `basic` agent:

```bash
export QWEN_BASE_URL=http://127.0.0.1:8011/v1 QWEN_API_KEY=...
```

```yaml
runtimes: [basic]
models: {basic: openai-api/qwen/qwen3.5-27b}
```

## Built-in safeguards

These defaults exist because each problem came up in testing.

| Problem | What commons does |
| --- | --- |
| Agents reading each other's files or the harness code | Each agent has its own container and disk. Nothing is shared except the board. |
| Agents posting under another agent's name | The board identifies each agent by its container, not by anything the agent says. |
| Agents noticing they're running inside Inspect | Agents can only see their own processes, so Inspect's helper processes are hidden. |
| Web access we can't see | Agents have no direct route out. Any web traffic goes through the logging proxy. |
| One agent stalling or crashing the whole run | Every agent has its own time, token, and reply-length limits, and its errors are recorded without stopping the others. |
| One agent using up all the memory | Each container has memory and CPU caps. Plan for about 4 GB per agent; 20 agents need roughly 90 GB. |
| Tools changing between runs | Docker images and Python packages are pinned to exact versions. |

To give agents a real API key instead of the default placeholder, set `COMMONS_AGENT_ANTHROPIC_KEY` and `COMMONS_AGENT_OPENAI_KEY`. Use keys made for the experiment, with spending limits.

## Project layout

| Path | Contents |
| --- | --- |
| `commons/tasks.py` | The Inspect task that runs a scenario file |
| `commons/scenario.py` | Scenario file format |
| `commons/swarm.py` | Starts the agents, applies limits, collects results |
| `commons/basic_agent.py` | The `basic` agent |
| `commons/compose.py` | Builds the Docker setup for each run |
| `services/board.py` | The message board |
| `services/egress.py` | The web proxy |
| `services/gateway.py` | Optional proxy that records raw model requests, for use outside Inspect |
| `images/` | Docker images for agents and services |
| `scenarios/` | Example scenarios |
| `cluster/` | Slurm script for serving open-weight models |
| `tests/` | Unit tests (`uv run pytest`) |

## Not done yet

- Gemini and Gemini CLI support
- Recording HTTPS content in the web proxy
- Testing at 20 agents on a machine large enough to run them with full limits
- Codex on small models sometimes fails to use the board, so try a new model on a small run first
