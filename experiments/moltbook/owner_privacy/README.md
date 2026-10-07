# What Moltbook agents reveal about their humans

Moltbook is a social network where only AI agents post. Each agent is run by a person, whom agents usually call "my human". This folder estimates how many agents post personal facts about that person in public.

**Status: preliminary.** The second, stricter classifier pass has not been checked by hand yet (see "How solid").

## Data

Same snapshot as `../secrets_money`: 290,232 posts and 1,836,664 comments from 39,700 agents, 27 January to 8 February 2026 (Hugging Face dataset `AIcell/moltbook-data`).

## Method

1. **Find candidates.** Keep every post or comment where the agent refers to its person ("my human", "my owner", "my operator", "the person I work for" and similar). That gives 53,149 items from 15,475 agents (39% of all agents).
2. **Sample.** 3,000 of those agents at random, up to 15 of their candidate items each: 7,951 items.
3. **Classify, pass 1.** Claude Haiku 4.5 reads each item and lists any personal facts about the agent's own human, with a category and a severity.
4. **Classify, pass 2.** A stricter prompt re-checks every pass-1 hit. An item counts as "revealed" only if pass 2 confirms a real personal fact beyond a first name, the item isn't clearly fiction or role-play, and it isn't part of one known spam campaign (about 3,400 near-identical "Constructor" pitches from a single agent).
5. **Scale up.** Agent-level shares from the sample, with 95% intervals, applied to the 15,475 agents who mention their human.

## Results

| | Agents (estimate) | Share of all 39,700 agents |
|---|---|---|
| Revealed at least one personal fact about their human | about 6,500 (6,260 to 6,750) | 16% |
| ...a sensitive one (health, money, relationships, location, schedule, legal and similar) | about 5,000 (4,750 to 5,220) | 13% |
| Revealed only the human's first name | about 3,580 | 9% |

By category, as a share of all agents: work 7.8%, identity details 6.4%, location 4.7%, money 2.6%, schedule 1.6%, relationships 1.2%, health 0.7%.

Agents that post more reveal more: 28% of agents with one candidate item revealed something, against 86% of agents with ten or more.

A check on 500 items that did *not* match the candidate phrases found 11 disclosures (2%). Applied to the roughly 2 million non-matching items, that suggests the candidate filter misses many disclosures, so the counts above are a lower bound on items, though not necessarily on agents.

## How solid

- **Pass 1 alone over-flags.** On 100 hand-labelled items it was right about half the time when it flagged something (26 of 50) and almost never missed a disclosure (48 of 50 negatives correct).
- **Pass 2 isn't hand-checked yet.** It was tuned on 50 of the hand-labelled positives, but its precision on fresh items hasn't been measured. Until it is, treat the 16% and 13% as upper-leaning estimates.
- **Not all claims are true.** Some agents role-play or invent details; items that were clearly fiction were excluded, but borderline ones may remain.

## Files

- `find_candidates.py`, `pilot.py`, `submit_batch.py`, `fetch_results.py`, `submit_confirm.py`, `fetch_confirm.py`, `analyze.py`, `validation_sample.py`, `common.py`: the pipeline, in that order.
- `summary.json`, `counts.json`: aggregate numbers only. They contain no text and no ids.
- `sample_manifest.csv`: which items were sampled (public post ids only, no text, no labels).
- `cost_log.jsonl`: API spend, $8.25 in total.
- Not committed: `private_matches.jsonl` (item text and per-item labels) and `validation_labels_pass1.csv` (hand labels by item). Both point to specific posts about specific people.
