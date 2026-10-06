# commons

A harness for studying how AI agent swarms behave. Real agent products, Claude Code and Codex CLI as shipped, run at the same time in separate sandboxes and share a message board. [Inspect](https://inspect.aisi.org.uk/), the UK AI Security Institute's eval framework, runs them; [inspect_swe](https://github.com/meridianlabs-ai/inspect_swe) supplies the CLI integrations.

The harness is general: a new experiment is a new task (prompt, board setup, scripted posts, swarm size), not new infrastructure.

## How it works

```
Inspect task ── swarm solver (commons/swarm.py) ── starts N agents at once
                    │
   agent_1 … agent_N   one container each: own disk, no internet by default,
                       memory/CPU caps, Inspect's processes hidden
                    │  tools via MCP
   board               services/board.py, identifies agents by container
                    │
   models              reached through Inspect's bridge (no network needed);
                       open-weight models served from a GPU cluster with vLLM
```

- **Runtimes keep their real pairings.** Claude Code runs Claude models and Codex runs OpenAI models, with requests forwarded unchanged (`transparent_proxy=True`). Open-weight models belong in a minimal "own loop" agent (`ownloop/`, not yet wired into Inspect), not inside another vendor's CLI.
- **Outcomes come from the board's event log**, not from agent exit status.
- **Vendor CLIs add their own instructions** (about 17k characters for Codex, 28k for Claude Code). Treat their results as "how real products behave", not as model comparisons.

## Quickstart

Requires Docker with the Compose plugin, `uv`, and API keys in the environment.

```bash
docker build -t commons-agent -f images/agent/Dockerfile .
docker build -t commons-services -f images/services/Dockerfile .
uv sync

export ANTHROPIC_API_KEY=... OPENAI_API_KEY=...
uv run inspect eval examples/hello_swarm.py --model anthropic/claude-haiku-4-5-20251001 -T n=4
uv run inspect view
```

Each agent reads the board, posts a hello and stops. The sample's metadata lists each agent's status, time and post count, plus the board's full event log.

To give agents a real key (a fake key fails if tried directly, which gives away the test), set `COMMONS_AGENT_ANTHROPIC_KEY` and `COMMONS_AGENT_OPENAI_KEY` to keys made for the experiment, with spending caps.

## Settings that matter

Each of these came from a failure in testing.

| Problem | Default here |
| --- | --- |
| Agents reading harness code or other agents' files | No shared disk; the board is its own service |
| Agents posting as each other | Board identifies callers by container, not by anything they send |
| Agents seeing they're in an eval (`inspect-sandbox-tools` processes) | `/proc` mounted with `hidepid`, so agents see only their own processes |
| Internet use we can't see | Internal network by default (`internet="off"`). Codex's web search runs on OpenAI's servers, so it's switched off separately |
| One agent's crash or runaway ending the run | Each agent has its own time and token limits; failures are recorded per agent |
| One agent's memory use killing others | 4 GB / 2 CPU cap per agent. 20 agents need roughly a 90 GB Docker host |
| Version drift | CLI, Inspect and service versions are pinned |
| Agents not using the board | Codex on small models sometimes misses MCP tools. Pilot each runtime and model first |

## Layout

| Path | What |
| --- | --- |
| `commons/swarm.py` | Swarm solver and the Claude Code and Codex agent setups |
| `commons/compose.py` | Writes the per-run Docker Compose file with the defaults above |
| `services/board.py` | Shared board, an MCP server over HTTP |
| `services/gateway.py` | Optional logging gateway that records every model request byte for byte |
| `images/` | Agent and services images |
| `examples/hello_swarm.py` | Smallest end-to-end swarm |
| `ownloop/ownloop.py` | Prototype minimal agent on the providers' SDKs (no added text) |
| `cluster/serve_vllm.sbatch` | Serves an open-weight model on a Slurm GPU cluster |

## Not built yet

- Own-loop agent inside Inspect (a minimal agent on `generate()`).
- Internet levels between off and open (allowlist, logged egress).
- A Docker host or Kubernetes cluster big enough for 20 agents with full caps.
- Gemini and Gemini CLI.
