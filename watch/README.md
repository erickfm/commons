# Swarm watch

Read-only watchers that look for AI agents, and especially many agents acting together, in public data. Nothing here posts, submits or writes to the sites it reads.

**Status (7 October 2026):** running on a laptop since 6 October, with an open model screening samples on one GPU. No new swarm found. Live status and findings: the "Swarm Watch" dashboard (a private claude.ai artifact).

## What's recorded

| Feed | Script | What it keeps |
|---|---|---|
| Wikipedia and sister sites | `wikimedia_stream.py` | every edit, and every link added (two live streams); also replays the last week |
| urlquery.net | `urlquery_watch.py`, `urlquery_agents.py` | the public list of new URL scans; scans where an agent ran its own page in the scanner's browser, decoded |
| Bluesky | `feeds.py bluesky` | every public post |
| Moltbook | `feeds.py moltbook` | new posts and comments on the social network for AI agents |
| PyPI, npm | `feeds.py pypi`, `feeds.py npm` | every new package and release; for new npm packages, who published it and any install scripts |
| urlscan.io | `feeds.py urlscan` | 12 targeted searches for agent fingerprints every 20 minutes |
| Open wikis | `feeds.py wikis` | recent changes on publictestwiki, one of the wikis agents used as a message board |
| Hugging Face | `feeds.py hf` | new models, datasets and Spaces |
| MCP registry | `feeds.py mcp` | newly published agent tool servers |
| x402 Bazaar | `feeds.py x402` | hourly list of paid services agents buy from |
| Nostr | `feeds.py nostr` | paid agent jobs and results on three public relays |
| Manifold | `feeds.py manifold` | every bet; the API marks bot bets |

Data goes to hourly gzip files outside the repo. Sites ask automated readers to say who they are, so every request carries a user agent with a contact; set `WATCH_CONTACT` to change it.

## Finding things

- `detect.py`: rules over the Wikipedia streams (throwaway accounts on sandbox pages across wikis, the same edit summary or link domain from many fresh accounts, one fresh account hopping across wikis). Tuned on the 46 edits Wikimedia attributed to OpenAI's agents.
- `github_detect.py`: groups GH Archive issues and comments that are near-identical across many accounts and repos.
- `classify.py`: every 15 minutes an open model (Qwen3.5-27B on one GPU) scores random samples from every feed, plus groups of near-identical posts, for "an agent did this" and "many accounts acting together". Claude Sonnet 5.5 then reviews up to 15 flags per round and labels each swarm, single agent, automation or nothing.

## Findings so far (6–7 October 2026)

- **urlquery.net as a disguised browser.** 849 scans since 4 August where an agent ran its own small web page in the scanner's browser to get past sites that block bots. Most come from the Amap jobs Swarmchasers reported on 4 October. Since then the same addresses ran unrelated errands: UK parcel quotes, copying Capterra's site code out in pieces, a scraping firm's free trial, and on 6 October an attempt to solve a Cloudflare CAPTCHA inside the scanner to get a free API key. Interesting, not a headline.
- **GitHub (one week of GH Archive).** The biggest coordinated group was 603 throwaway accounts running the Toolathlon agent benchmark. Everything else was spam or release bots.
- **Wikipedia (one week, 24.4 million edits).** No fleets. 30 blocks citing AI or LLM use; two accounts that said they were AI agents, both blocked on 1 October.
- **New feeds (Bluesky onward).** Running since 7 October. Every flag reviewed so far is ordinary automation.

## Not watched, on purpose

DseWiki, the main board in the June wiki incident, logs visitors' IP addresses publicly, so it's left off.
