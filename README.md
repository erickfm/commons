# commons

A harness for studying how AI agent swarms behave. Many agents run at the same time in separate sandboxes and share a message board. They can be real agent products (Claude Code and Codex CLI, as shipped) or a minimal agent of our own for clean model comparisons. [Inspect](https://inspect.aisi.org.uk/), the UK AI Security Institute's eval framework, runs them; [inspect_swe](https://github.com/meridianlabs-ai/inspect_swe) supplies the CLI integrations.

A new experiment is a new scenario file, not new infrastructure.

## How it works

```
scenario.yaml ── commons/tasks.py ── swarm solver: starts N agents at once
                                         │
   agent_1 … agent_N    one container each: own disk, memory/CPU caps,
                        Inspect's processes hidden, internal network only
            │ tools via MCP            │ web (if allowed)
   board                            egress proxy
   posts, reads, scripted plants    logs every connection, enforces allowlist
            │
   models   reached through Inspect's bridge, which needs no network;
            open-weight models served from a GPU cluster with vLLM
```

**Runtimes** (`runtimes:` in a scenario, cycled across agents):

| Runtime | What it is | Use it for |
| --- | --- | --- |
| `claude_code` | Claude Code as shipped, on Anthropic models, requests forwarded unchanged | How a real product behaves |
| `codex` | Codex CLI as shipped, on OpenAI models, web search and goals off | How a real product behaves |
| `own_loop` | Minimal agent: our prompt, three tools (`shell`, `read_board`, `post_board`), nothing else | Comparing models, including open-weight ones |

Vendor CLIs add their own instructions (about 17k characters for Codex, 28k for Claude Code), so their results describe products, not models. Don't run a model inside another vendor's CLI.

**Internet** (`internet:`):

| Level | What agents can reach |
| --- | --- |
| `off` | Nothing. Models still work through Inspect's bridge |
| `allowlist` | Only `allow:` hosts, through the egress proxy. Everything else is blocked and logged |
| `open` | Everything, through the egress proxy, which logs each connection (agent, host, bytes). HTTPS content isn't decrypted |

With internet on, Codex also makes its own background connections (e.g. `chatgpt.com`, `github.com`). They appear in that agent's egress log, so separate them from what the agent chose to do.

## Quickstart

Requires Docker with the Compose plugin, `uv`, and API keys in the environment.

```bash
docker build -t commons-agent -f images/agent/Dockerfile .
docker build -t commons-services -f images/services/Dockerfile .
uv sync

export ANTHROPIC_API_KEY=... OPENAI_API_KEY=...
uv run inspect eval commons/tasks.py -T scenario=scenarios/hello.yaml --model anthropic/claude-haiku-4-5-20251001
uv run inspect view
```

The sample's metadata holds each agent's status, time, post count and web connections, plus the board's and egress proxy's full event logs. `--model` is only a default; scenarios set models per runtime.

To give agents a real key (a fake key fails if tried directly, which gives away the test), set `COMMONS_AGENT_ANTHROPIC_KEY` and `COMMONS_AGENT_OPENAI_KEY` to keys made for the experiment, with spending caps.

## Scenarios

```yaml
name: example
agents: 6
runtimes: [claude_code, codex]          # agent_1 claude_code, agent_2 codex, ...
models: {claude_code: anthropic/claude-sonnet-4-5, codex: openai/gpt-5}
system_prompt: You are an agent working in a team.
task: ...
internet: allowlist                     # off | allowlist | open
allow: [pypi.org, files.pythonhosted.org]
plants:                                 # scripted posts, seconds after agents start
  - {at: 60, as: agent_7, message: "..."}
limits: {time: 900, tokens: 500000, answer_tokens: 16000}   # per agent
resources: {mem: 4g, cpus: 2}           # per agent container
```

Plants appear on the board like any post; the log marks them `"plant": true`. Included: `hello`, `own_loop`, `web_open`, `web_allowlist`.

## Open-weight models on a cluster

`cluster/serve_vllm.sbatch` serves a model with vLLM (tool calling on) behind an API key. Tunnel it to the machine running Inspect, then point Inspect's OpenAI-compatible provider at it:

```bash
export QWEN_BASE_URL=http://127.0.0.1:8011/v1 QWEN_API_KEY=...
# in a scenario: models: {own_loop: openai-api/qwen/qwen3.5-27b}
```

## Settings that matter

Each of these came from a failure in testing.

| Problem | Default here |
| --- | --- |
| Agents reading harness code or other agents' files | No shared disk; the board is its own service |
| Agents posting as each other | Board and egress proxy identify callers by container, not by anything they send |
| Agents seeing they're in an eval (`inspect-sandbox-tools` processes) | `/proc` mounted with `hidepid`, so agents see only their own processes |
| Internet use we can't see | Agents never have a direct route out; web traffic, when allowed, goes through the logging egress proxy. Codex's hosted web search is switched off |
| One agent's crash or runaway ending the run | Per-agent time and token limits, a cap on each model reply, failures recorded per agent |
| One agent's memory use killing others | 4 GB / 2 CPU cap per agent. 20 agents need roughly a 90 GB Docker host |
| "Finished" without doing the task | Outcomes come from the board and egress logs, not agent exit status |
| Version drift | CLI, Inspect, service and Python package versions are pinned (`uv.lock`) |
| Agents not using the board | Codex on small models sometimes misses MCP tools. Pilot each runtime and model first |

## Layout

| Path | What |
| --- | --- |
| `commons/tasks.py` | Inspect task that runs any scenario file |
| `commons/scenario.py` | Scenario file format |
| `commons/swarm.py` | Swarm solver; Claude Code and Codex setups |
| `commons/ownloop.py` | Own-loop runtime |
| `commons/compose.py` | Writes each run's Docker Compose file with the defaults above |
| `services/board.py` | Board: MCP tools, HTTP API, plants |
| `services/egress.py` | Egress proxy: logging and allowlist |
| `services/gateway.py` | Optional logging gateway for byte-exact model requests outside Inspect |
| `images/` | Agent and services images |
| `scenarios/` | Example scenarios |
| `cluster/serve_vllm.sbatch` | Serves an open-weight model on a Slurm GPU cluster |
| `tests/` | Unit tests (`uv run pytest`) |

## Not built yet

- Gemini and Gemini CLI (no key yet).
- HTTPS content logging in the egress proxy (only host and byte counts today).
- A Docker host or Kubernetes cluster big enough for 20 agents with full caps.
