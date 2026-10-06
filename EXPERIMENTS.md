# Experiments

This file tracks four experiments on AI agent swarms, all run with this repo's harness. It lives on `main` and is updated whenever an experiment starts or finishes, so it's current from any branch.

Each experiment runs on its own branch. Harness features that more than one experiment needs go to `main` first (through a short-lived branch), and each experiment branches from the updated `main`. Scenarios, workspaces and analysis for one experiment stay on its branch.

Models: Anthropic, OpenAI, and open-weight models only.

## Standards for every experiment

- **Counts, not just percentages.** Write "7 of 20 (35%)", never just "35%". State sample sizes plainly, including when they're small.
- **Eval awareness.** For every result, report how many agents said they thought they were being tested. Reviewers ask about this first.
- **Check outcomes from evidence.** Use the board log, the report log, web logs and workspace diffs, not what an agent says it did.
- **Transcripts.** Every headline number should have example transcripts to back it up, and the logs should be easy to find.
- **Primary sources.** Check every paper or incident figure against the original before it goes into a writeup. Several were gathered secondhand.
- **Cost.** Record spend for each experiment. Pilot on cheap models (`anthropic/claude-haiku-4-5-20251001`, `openai/gpt-5-mini`) before using stronger ones. Get approval before any run likely to cost more than about $20.
- **Fair model comparisons use the `basic` agent.** Claude Code and Codex add long instructions of their own (about 28k and 17k characters), so results from them describe products, not models.

## Safety rules

- No real systems. Never post to real hotlines, write to websites we don't own, or publish packages. Agents only reach internal tools and mock services.
- Payloads and "harmful" tasks are synthetic, harmless stand-ins that only exist inside the sandbox.
- Lab bait stays in the lab. Deploying bait on the real internet is a separate step that needs explicit approval.

## Lessons from building the harness

- Codex on `gpt-5-mini` sometimes fails to use the board's tools and still reports success. Use a stronger OpenAI model for real runs, and pilot it first.
- Run open-weight models in the `basic` agent, never inside another vendor's CLI.
- With internet on, Codex connects to OpenAI and GitHub by itself. Don't count those as agent choices.
- Open-weight models can produce runaway replies, so keep `limits.answer_tokens` set.
- A plant only works if its advice is plausible, actually works, and saves real effort. Test the bait in a pilot and read the transcripts before a full run.
- Codex on `gpt-5-mini` reads the board's tools as "resources" and gives up; Codex on `gpt-5` uses them correctly (checked with `scenarios/channels.yaml`).
- The local Docker VM has 4 CPUs and 4 GB, enough for about 3–4 Claude Code or Codex agents. `basic` agents use much less, since their model calls run outside the container.

## Shared harness work

| Piece | Needed by | Status |
| --- | --- | --- |
| Results script: one table per batch of logs (run, condition, model, role, status, posts, reports, what the diff did, eval-awareness mentions), plus a transcript search for eval awareness | All | done: `commons/results.py` |
| Private "report to humans" channel, logged separately from the public board, available to all three agent types | Snitch Rate (others may use it) | done: `report` channel |
| Private messages between agents (`send_message`, `read_messages`), identified by container | Delegation laundering | done: `messages` channel; scripted posts with `to` play a manager |
| Mock websites inside the Docker network over plain HTTP (docs page, forms, package index), every request logged with the agent's name | Honeypot lab | not started |

---

## 1. Snitch Rate

- **Status:** in progress (designing the scenario)
- **Branch:** `exp/snitch-rate`
- **Question:** When an agent sees a peer cheat and has a way to tell humans, does it? Is it less likely to when it's part of a swarm?
- **Background (to verify before writing up):** in a 2026 OpenAI–Hugging Face incident, about 1,200 eval agents misbehaved and none reported it. DeepMind's 2026 research-swarm study gave agents no channel to humans.
- **Setup:** a workspace with a grader that can be rigged. A plant shows the others how to rig it. Agents have a private tool to report to humans.
- **Conditions:** one agent alone vs. a swarm; tip line mentioned in the prompt vs. only available as a tool; across models (on the `basic` agent).
- **Runs:** —
- **Headline numbers:** —
- **Caveats:** —
- **Logs:** —
- **Spend:** —

## 2. Memetic immunity stress test

- **Status:** not started
- **Branch:** `exp/memetic-immunity`
- **Question:** Does a one-line system-prompt defense stop agents from passing on "meme" payloads that are known to spread well?
- **Background (to verify):** the Mind Viruses paper (arXiv 2608.10218) reports that a one-line system prompt gave near-total immunity to spreading payloads. Memetic Trojans (arXiv 2610.00430) reports about 50% retransmission of its payloads. The two haven't been tested against each other.
- **Setup:** payloads are synthetic and harmless and stay on the local network.
- **Conditions:** with vs. without the one-line defense, across payload types and models.
- **Runs:** —
- **Headline numbers:** —
- **Caveats:** —
- **Logs:** —
- **Spend:** —

## 3. Delegation laundering

- **Status:** not started
- **Branch:** `exp/delegation-laundering`
- **Question:** An agent refuses a harmful request when asked directly. Does it go along when the request is passed down through one or more agent "bosses"?
- **Background (to verify):** Delegated Misalignment (arXiv 2609.27900) reports harmful-task execution rising from 31% to 78% under delegation.
- **Setup:** harmless stand-in tasks only (e.g. "delete the audit log" in a sandbox). Bosses instruct workers by private message.
- **Conditions:** 0, 1, 2, … layers of delegation, across models.
- **Runs:** —
- **Headline numbers:** —
- **Caveats:** —
- **Logs:** —
- **Spend:** —

## 4. Systematic honeypot testing (lab)

- **Status:** not started
- **Branch:** `exp/honeypot-lab`
- **Question:** Which kinds of bait catch which models, and does the bait pull them off their task?
- **Background (to verify):** past catches in the wild were rare (Palisade: 8 likely agents in 8.1M interactions).
- **Setup:** realistic tasks in a mock environment with bait: fake "full API docs" links, bounty or application forms, contact points hidden in page source, commonly hallucinated package names. A no-bait control.
- **Conditions:** each bait type vs. control, across models.
- **Runs:** —
- **Headline numbers:** —
- **Caveats:** the lab result is the main result. Deploying the best bait on the real internet needs explicit approval.
- **Logs:** —
- **Spend:** —
