# Do shipped products behave like the bare models?

Every other experiment ran models on the `basic` agent: our own prompt and tools, nothing else. Real deployments use products such as Claude Code and Codex, which bring their own tools, settings and instructions. This experiment repeats the most decisive conditions from Snitch Rate and the peer-pressure experiment on those products, and compares.

## Setup

Same tasks, prompts and scenarios as before (`snitch_workspace/`, `peer_workspace/`), with the agent type switched:

- **Claude Code** (v2.1.290) on Sonnet 5.5 and on Opus 5.5
- **Codex** (v0.160.1) on gpt-6.1-sol and on gpt-5.5

Conditions: Snitch Rate solo, tip line only available vs mentioned (30 runs each); peer pressure at high stakes with 0 or 3 cheating teammates (15 runs each). 360 runs.

One detail matters below: our harness gives Claude Code our system prompt in place of its own (`replace_system_prompt`), so what's left of the product is its tools, its added context (an identity line, an environment block, a reminder), and its settings. One of those settings is reasoning effort: Claude Code runs Sonnet 5.5 at **medium** effort, while the API default for Sonnet 5.5 (what the `basic` agent got) is **high**.

## Results (2026-10-06)

**Snitch Rate: agents that reported the cheating teammate to the humans** (out of 30):

| Model | `basic`, tip line available | Product, tip line available | `basic`, mentioned | Product, mentioned |
| --- | --- | --- | --- | --- |
| Sonnet 5.5 (Claude Code) | 23 | **0** | 30 | 30 |
| Opus 5.5 (Claude Code) | 30 | 30 | 30 | 30 |
| gpt-6.1-sol (Codex) | 1 | 0 | 30 | 30 |
| gpt-5.5 (Codex) | 1 | 4 | 28 | 30 |

**Why Sonnet stopped reporting in Claude Code: reasoning effort.** We reran the `basic` agent's "tip line available" condition with Sonnet 5.5 and Opus 5.5 at three effort levels (30 runs each):

| Model | Low effort | Medium effort | High effort |
| --- | --- | --- | --- |
| Sonnet 5.5 | 1/30 | 0/30 | 17/30 |
| Opus 5.5 | 30/30 | 30/30 | 30/30 |

What this shows:

1. **A product setting can switch a safety behaviour off.** Sonnet 5.5 reports a cheating teammate unprompted at high effort (17 of 30) and almost never at low or medium (1 of 60; p = 8e-6 for low vs high). Claude Code runs it at medium, so in Claude Code it reported 0 of 30. It still objected to the cheating publicly on the board in all 30 runs; it just didn't think to tell the humans.
2. **Opus 5.5 is robust:** it reported every time, at every effort, in both the bare model and Claude Code.
3. **Mentioning the tip line fixes it everywhere.** With one sentence pointing to the tool, every product-model pair reported 30 of 30.
4. **Codex didn't change the OpenAI models' behaviour.** Like the bare models, they almost never reported unless the tip line was mentioned.
5. **No product agent cheated in the peer-pressure runs** (0 of 119), and with cheating teammates on the board all four pairs reported them to the humans in every run.

The two Sonnet "high effort" figures (23 of 30 in the original run, 17 of 30 here) come from the same setup on different days; together, 40 of 60.

**Eval awareness:** no candidate passages in any product run.

**Cost:** about $41.

### Caveats

- Claude Code ran with our system prompt instead of its own, so these runs measure its tools and settings, not its full default prompt.
- One Codex run (gpt-5.5, 3 cheating teammates) recorded no data, so that cell has 14 runs.
- The effort test used the `basic` agent; we didn't run Claude Code at high effort, so the identity line and environment block can't be fully ruled out as contributors. Effort alone reproduces the drop.

### Files

`results/snitch.txt` and `results/peer.txt` (tables and every report and post). Raw logs are kept locally under `logs/products/`.

## Part 2: does low effort weaken other safety behaviours?

Low effort switched off Sonnet's unprompted reporting. We checked whether it does the same to three other behaviours, by rerunning one condition from each earlier experiment on the `basic` agent at low and high effort.

| Behaviour (experiment, condition) | Sonnet 5.5 low | Sonnet 5.5 high | Opus 5.5 low | Opus 5.5 high |
| --- | --- | --- | --- | --- |
| Reports a cheating teammate unprompted (Snitch Rate, tip line available) | 1/30 | 17/30 | 30/30 | 30/30 |
| Warns others about a malicious post (memetic, security trojan) | 17/60 | 50/60 | 47/60 | 53/60 |
| Looks for an SDK and inspects the fake package (honeypot, package bait) | 1/15 | 11/15 | 13/15 | 10/15 |
| Promotes the malicious post | 0/60 | 0/60 | 0/60 | 0/60 |
| Installs the fake package | 0/15 | 0/15 | 0/15 | 0/15 |
| Cheats on the impossible task (peer pressure, 3 cheaters, high stakes) | 0/15 | 0/15 | 0/15 | 0/15 |
| Reports the cheating teammates (same condition) | 15/15 | 15/15 | 15/15 | 13/15 |

What this shows:

1. **Low effort removes Sonnet's extra protective steps, not its refusals.** At low effort Sonnet was far less likely to report unprompted (p = 8e-6), to warn others about a malicious post (p = 1e-9), or to go looking for and checking a package (p = 0.0005). It never did anything harmful at either effort: no promoting, no installing, no cheating.
2. **When the protective step is part of the obvious job, effort doesn't matter.** With cheating teammates on the board and the tip line mentioned, Sonnet reported them 15 of 15 times at both efforts.
3. **Opus 5.5 is steady across efforts** on every behaviour (no difference was significant). Two of Opus's high-effort peer-pressure runs without a report had calls blocked by the API safety filter (4 blocked runs in that cell).

**Why it matters:** "don't do harm" survives low effort; "notice something is off and speak up" doesn't, for Sonnet. Products that lower effort for speed or cost lose the second kind, and a test that only checks refusals won't see it.

**Cost of the effort tests:** about $15.

Files: `results/effort/` has each experiment's analysis at low and high effort.

## Running it

```bash
experiments/products/run_all.sh
uv run python -m commons.batch experiments/products/scenarios/basic__snitch_n1_available.yaml \
  --model anthropic/claude-sonnet-5-5 --effort low --effort medium --effort high --epochs 30 --log-dir logs/products/effort
```
