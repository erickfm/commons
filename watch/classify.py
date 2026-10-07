"""Have an open model read samples from every feed and flag agent-like or coordinated activity the rules miss.

    QWEN_BASE_URL=http://127.0.0.1:8011/v1 QWEN_API_KEY=... uv run python watch/classify.py /path/to/data

Every 15 minutes, from the newest hour of each feed:
  - a random sample of items (posts, edits, scans, new packages), shown to the model 20 at a time;
  - groups of near-identical posts from different accounts (Bluesky, Moltbook comments), shown as groups.
The model scores each item or group for "an AI agent did this" and "many accounts acting together", with a
one-line reason. Anything scoring 7+ out of 10 on either goes to data/flags/YYYYMMDD.jsonl. On Moltbook every
user is an agent, so only the "acting together" score counts there; the same goes for Nostr's paid agent jobs.
Copy-paste groups also need some sign of an agent, since most are news or spam bots.

Second pass: a frontier model (Claude Sonnet 5.5, via commons.judge with server-side fallback so a refused
review is retried on another model) reads each new flag, at most 15 per round and one per account, and labels it
"swarm", "single agent", "automation" or "nothing", taking at most 3 per feed so one noisy feed can't crowd
out the rest. Results go to data/flags/reviewed-YYYYMMDD.jsonl.
"""

import json
import os
import random
import re
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).parent))
from detect import read_lines  # noqa: E402

sys.path.insert(0, str(Path(__file__).parents[1]))
from commons.judge import Judge  # noqa: E402

REVIEW = """Someone is watching public internet feeds for AI agents, and especially for many agents or accounts acting together (a swarm). A cheap screening model flagged the item below. Decide what it most likely is.

Source: {source}
Screening model's reason: {why}
Item:
{item}

Labels:
- swarm: many accounts or agents acting together, with specific evidence in the item
- single agent: one autonomous AI agent doing something notable (testing, probing, working around limits, disclosing itself)
- automation: a scripted bot, spam campaign, or ordinary automation with no sign of an AI agent
- nothing: ordinary human activity, or nothing notable

Explain in one or two sentences, then end with exactly one label on its own line."""
LABELS = ["swarm", "single agent", "automation", "nothing"]

PROMPT = """You are screening public internet activity for signs of AI agents, and especially many AI agents or accounts acting together (a "swarm").

For each numbered item below, give two scores from 0 to 10:
- agent: how likely an autonomous AI agent (not a person, not a simple scripted bot) produced it. Signs: test or probe behaviour, tool-like phrasing, run IDs or markers, self-disclosure, systematic exploration, LLM writing style in an odd place.
- swarm: how likely it is part of many accounts or agents acting together (same text or links across accounts, coordinated timing, one operator behind many identities).
Ordinary spam, marketing, and normal human chatter score low unless there is a specific sign of agents. Be strict: most items should score 0-3.

Reply with JSON only: {{"items": [{{"i": <number>, "agent": <0-10>, "swarm": <0-10>, "why": "<one short sentence>"}}]}}

Source: {source}
Items:
{items}"""


def newest(dir_: Path, n: int = 1) -> list[Path]:
    return sorted(dir_.glob("*.jsonl.gz"))[-n:] if dir_.exists() else []


def sample(path_list: list[Path], k: int, keep) -> list[dict]:
    pool = [r for p in path_list for r in read_lines(p) if keep(r)]
    return random.sample(pool, min(k, len(pool)))


def norm(t: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"https?://\S+|@\S+|\d+", "", (t or "").lower())).strip()[:200]


def show(source: str, r: dict) -> str:
    """One compact line per item, with what matters for that feed."""
    if source == "bluesky":
        return json.dumps({"account": r.get("did"), "text": (r.get("text") or "")[:300], "links": r.get("links")[:3], "reply": bool(r.get("reply_parent"))}, ensure_ascii=False)
    if source == "moltbook":
        a = r.get("author") or {}
        return json.dumps({"kind": r.get("kind"), "author": a.get("name") if isinstance(a, dict) else a, "title": r.get("title"), "text": (r.get("content") or "")[:300]}, ensure_ascii=False)
    if source == "wikipedia":
        return json.dumps({k: r.get(k) for k in ("wiki", "user", "title", "comment", "type")}, ensure_ascii=False)
    if source == "wikilinks":
        return json.dumps({"wiki": r.get("database"), "user": (r.get("performer") or {}).get("user_text"), "edits": (r.get("performer") or {}).get("user_edit_count"), "page": r.get("page_title"), "added": [l["link"][:150] for l in r.get("added_links") or [] if l.get("external")][:4]}, ensure_ascii=False)
    if source == "npm":
        return json.dumps({k: r.get(k) for k in ("id", "description", "author", "maintainers", "scripts", "readme_head")}, ensure_ascii=False, default=str)[:600]
    if source == "urlquery":
        return json.dumps({k: r.get(k) for k in ("dt", "url", "asn")}, ensure_ascii=False)[:500]
    return json.dumps(r, ensure_ascii=False, default=str)[:500]


def groups(source: str, recs: list[dict], key_text, key_user, min_users: int = 4) -> list[dict]:
    g = defaultdict(lambda: {"users": set(), "samples": []})
    for r in recs:
        t = norm(key_text(r))
        if len(t) < 25:
            continue
        g[t]["users"].add(key_user(r))
        if len(g[t]["samples"]) < 3:
            g[t]["samples"].append(r)
    out = [{"group_of": len(v["users"]), "text": t, "sample_accounts": sorted(map(str, v["users"]))[:8], "sample": show(source, v["samples"][0])}
           for t, v in g.items() if len(v["users"]) >= min_users]
    return sorted(out, key=lambda x: -x["group_of"])[:20]


def ask(client: httpx.Client, source: str, items: list[str]) -> list[dict]:
    body = "\n".join(f"{i}. {s}" for i, s in enumerate(items))
    r = client.post("/chat/completions", json={
        "model": "qwen3.5-27b", "temperature": 0, "max_tokens": 3000,
        "messages": [{"role": "user", "content": PROMPT.format(source=source, items=body)}],
        "chat_template_kwargs": {"enable_thinking": False},
    })
    text = r.json()["choices"][0]["message"]["content"] or ""
    m = re.search(r"\{.*\}", text, re.S)
    try:
        return json.loads(m.group(0))["items"] if m else []
    except (ValueError, KeyError):
        return []


def round_(client: httpx.Client, data: Path) -> int:
    batches: list[tuple[str, list]] = []
    bsky = [r for p in newest(data / "bluesky") for r in read_lines(p)]
    batches.append(("bluesky", [show("bluesky", r) for r in random.sample(bsky, min(100, len(bsky)))]))
    batches.append(("bluesky groups of near-identical posts from different accounts",
                    [json.dumps(x, ensure_ascii=False) for x in groups("bluesky", bsky, lambda r: r.get("text"), lambda r: r.get("did"))]))
    molt = [r for p in newest(data / "moltbook", 3) for r in read_lines(p)]
    batches.append(("moltbook (a social network where the users are AI agents; flag coordination, odd instructions, secrets, attempts to recruit or direct other agents)",
                    [show("moltbook", r) for r in random.sample(molt, min(60, len(molt)))]))
    batches.append(("moltbook groups of near-identical posts/comments from different agents",
                    [json.dumps(x, ensure_ascii=False) for x in groups("moltbook", molt, lambda r: r.get("content"), lambda r: (r.get("author") or {}).get("name") if isinstance(r.get("author"), dict) else r.get("author_id"), 3)]))
    batches.append(("wikipedia edits (non-bot)", [show("wikipedia", r) for r in sample(newest(data / "wikimedia"), 100, lambda r: not r.get("bot") and r.get("type") in ("edit", "new"))]))
    batches.append(("wikipedia external links added", [show("wikilinks", r) for r in sample(newest(data / "wikilinks"), 60, lambda r: not (r.get("performer") or {}).get("user_is_bot") and any(l.get("external") for l in r.get("added_links") or []))]))
    batches.append(("npm brand-new packages", [show("npm", r) for r in sample(newest(data / "npm", 2), 60, lambda r: r.get("rev", "").startswith("1-"))]))
    batches.append(("small open wikis that agent swarms have used as message boards (look for cloud/anonymous editors, ZZZ or Agent* page names, encoded chunks, answers to tasks)",
                    [json.dumps({k: r.get(k) for k in ("wiki", "title", "user", "comment", "timestamp", "oldlen", "newlen")}, ensure_ascii=False) for p in newest(data / "wikis", 2) for r in read_lines(p)][-100:]))
    batches.append(("Hugging Face newest repos", [json.dumps({k: r.get(k) for k in ("kind", "id", "author", "tags", "sdk")}, ensure_ascii=False)[:400] for r in sample(newest(data / "hf"), 80, lambda r: True)]))
    batches.append(("MCP registry newly published servers", [json.dumps(r, ensure_ascii=False, default=str)[:500] for p in newest(data / "mcp", 3) for r in read_lines(p)][-40:]))
    nostr = [r for p in newest(data / "nostr") for r in read_lines(p)]
    batches.append(("Nostr paid agent jobs (NIP-90 data vending machines)", [json.dumps({"kind": r.get("kind"), "pubkey": r.get("pubkey"), "content": (r.get("content") or "")[:300], "tags": (r.get("tags") or [])[:6]}, ensure_ascii=False)[:600] for r in random.sample(nostr, min(60, len(nostr)))]))
    batches.append(("Nostr groups of near-identical jobs from different keys",
                    [json.dumps(x, ensure_ascii=False) for x in groups("nostr", nostr, lambda r: r.get("content"), lambda r: r.get("pubkey"))]))
    uq = sorted((data / "urlquery").glob("*.jsonl"))[-1:]
    uq_recs = [json.loads(l) for p in uq for l in open(p)][-300:]
    batches.append(("urlquery.net public URL scans (agents sometimes submit pages that run their own code)", [show("urlquery", r) for r in random.sample(uq_recs, min(60, len(uq_recs)))]))

    out = data / "flags" / f"{datetime.now(timezone.utc):%Y%m%d}.jsonl"
    out.parent.mkdir(exist_ok=True)
    flagged = 0
    for source, items in batches:
        for i in range(0, len(items), 20):
            chunk = items[i:i + 20]
            try:
                verdicts = ask(client, source, chunk)
            except (httpx.HTTPError, KeyError, ValueError) as ex:
                print(f"{source}: {ex!r}", flush=True)
                continue
            for v in verdicts:
                if not isinstance(v, dict) or not isinstance(v.get("i"), int) or v["i"] >= len(chunk):
                    continue
                agent, swarm = v.get("agent", 0), v.get("swarm", 0)
                if source.startswith(("moltbook", "Nostr")):
                    keep = swarm >= 8  # everything there is automated by design; only coordination is news
                elif "groups" in source:
                    keep = swarm >= 8 and agent >= 4  # copy-paste groups are mostly news and spam bots
                else:
                    keep = max(agent, swarm) >= 7
                if keep:
                    flagged += 1
                    with open(out, "a") as f:
                        f.write(json.dumps({"t": datetime.now(timezone.utc).isoformat(), "source": source, "agent": v.get("agent"), "swarm": v.get("swarm"), "why": v.get("why"), "item": chunk[v["i"]]}, ensure_ascii=False) + "\n")
    return flagged


def review(data: Path, judge: Judge, limit: int = 15) -> int:
    """Frontier-model second look at new flags, one per account and at most `limit` per round."""
    day = f"{datetime.now(timezone.utc):%Y%m%d}"
    flags_path, out = data / "flags" / f"{day}.jsonl", data / "flags" / f"reviewed-{day}.jsonl"
    if not flags_path.exists():
        return 0
    done = {json.loads(l)["item"] for l in open(out)} if out.exists() else set()
    seen_accounts, todo = set(), []
    for l in open(flags_path):
        f = json.loads(l)
        acct = re.search(r'"(account|author|user|maintainers)": ("[^"]*"|\[[^\]]*\])', f["item"])
        key = (f["source"], acct.group(2) if acct else f["item"])
        if f["item"] in done or key in seen_accounts:
            continue
        seen_accounts.add(key)
        todo.append(f)
    # Newest first, at most 3 per source, so one noisy feed can't use up the review budget.
    per_source, picked = defaultdict(int), []
    for f in reversed(todo):
        if per_source[f["source"]] < 3:
            per_source[f["source"]] += 1
            picked.append(f)
    todo = picked[:limit]
    prompts = [REVIEW.format(source=f["source"], why=f["why"], item=f["item"]) for f in todo]
    judge.prefetch(prompts, LABELS, workers=8)
    for f, p in zip(todo, prompts):
        with open(out, "a") as fh:
            fh.write(json.dumps(f | {"review": judge(p, LABELS, save=False)}, ensure_ascii=False) + "\n")
    return len(todo)


def main(data: Path) -> None:
    client = httpx.Client(base_url=os.environ["QWEN_BASE_URL"], headers={"Authorization": f"Bearer {os.environ['QWEN_API_KEY']}"}, timeout=300)
    judge = Judge(data / "flags" / "review_cache.json")
    while True:
        t = time.time()
        try:
            n = round_(client, data)
            r = review(data, judge)
            print(f"{datetime.now(timezone.utc):%Y-%m-%d %H:%M} round done in {time.time() - t:.0f}s, {n} flagged, {r} reviewed", flush=True)
        except Exception as ex:  # keep going; the tunnel or server may blip
            print(f"round failed: {ex!r}", flush=True)
        time.sleep(max(60, 900 - (time.time() - t)))


if __name__ == "__main__":
    main(Path(sys.argv[1]))
