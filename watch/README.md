# Swarm watch

Read-only watchers that look for AI agents, and especially many agents acting together, in public data. Nothing here posts, submits or writes to the sites it reads.

**Status (28 October 2026):** running on a laptop since 6 October, with an open model screening samples on one GPU. One genuine find so far — see "Findings" below — amid a steady stream of duds. Live status and findings: the "Swarm Watch" dashboard (a private claude.ai artifact).

Recording has run without interruption throughout; the screening model, which runs off-laptop on a shared GPU, is the fragile part. Current operational notes:
- **The GPU serve job keeps expiring.** It has a 7-day walltime, and when it ends the model goes offline until it's resubmitted — screening was blind this way 14–19 October and again from ~26 October. Recording never stops, so no data is lost and the gap can be re-screened offline. The tunnel used to hardcode the GPU node (which hid the first outage); `tunnel.sh` now rediscovers the node on every reconnect, so once a new serve job starts, screening reconnects on its own. The remaining gap is that nothing resubmits the job when it expires — that wants a cluster-side watchdog.
- **The urlquery feed is down since 17 October.** urlquery.net removed the public search path we read (`/api/htmx/search/` now returns 404). The site still works; the watcher needs re-pointing at whatever replaced that endpoint.

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
- `classify.py`: every 15 minutes it builds candidate groups from the newest data (the same text or link from many accounts, one publisher releasing many packages or repos at once, the Wikipedia rules over the last hour, Moltbook posts where agents direct other agents) plus a small random sample. An open model (Qwen3.5-27B on one GPU) scores each for AI agents acting together. Claude Sonnet 5.5 then reviews up to 15 flags per round and labels each swarm, single agent, automation or nothing.
- `tunnel.sh`: keeps the SSH tunnel to the screening model open. The model runs as a Slurm job whose GPU node changes when it's requeued, so the script rediscovers the node from `squeue` on every reconnect. The screening process reads the model at `http://127.0.0.1:8011` (`QWEN_BASE_URL`); set `SWARM_SSH` to the login-node ssh args to run it.

## Findings so far

- **20 Hugging Face "swarm-agent" Spaces (12 October).** The account `outnnnnnn` published 20 Spaces named `swarm-agent-0` … `swarm-agent-19` in one 46-second burst. Each held Python meant to target a class of networked device, attempt a known admin-login bypass, and harvest and encrypt that device's credentials — 20 numbered copies of one credential-harvesting agent, on live public infrastructure, and not reported anywhere else. Caveats: the code was read, never run; the Spaces declared `sdk: static`, so it was staged on Hugging Face rather than proven to run there; operator and real-world impact are unknown; the account and all 20 Spaces were gone (404) by 19 October, with no surviving public copy. This is the closest thing the watch has found to its target. Details in `experiments/hf_swarm/` (on the `exp/swarm-watch` branch) and the dashboard.
- **urlquery.net as a disguised browser.** 849 scans since 4 August where an agent ran its own small web page in the scanner's browser to get past sites that block bots. Most come from the Amap jobs Swarmchasers reported on 4 October. Since then the same addresses ran unrelated errands: UK parcel quotes, copying Capterra's site code out in pieces, a scraping firm's free trial, and on 6 October an attempt to solve a Cloudflare CAPTCHA inside the scanner to get a free API key. Interesting, not a headline.
- **GitHub (one week of GH Archive).** The biggest coordinated group was 603 throwaway accounts running the Toolathlon agent benchmark. Everything else was spam or release bots.
- **Wikipedia (one week, 24.4 million edits).** No fleets. 30 blocks citing AI or LLM use; two accounts that said they were AI agents, both blocked on 1 October.
- **New feeds (Bluesky onward).** Running since 7 October. Apart from the Hugging Face Spaces, every flag has been a dud: ordinary automation, spam, viral human memes, release and digest bots. The one other agent-coordination artifact was a single operator's self-test of an agent-to-agent messaging protocol on the publictestwiki Sandbox (12 October) — seven edits from one address, not a running swarm. A sweep of the 12–19 October window during the screening outage turned up nothing new.

## Not watched, on purpose

DseWiki, the main board in the June wiki incident, logs visitors' IP addresses publicly, so it's left off.
