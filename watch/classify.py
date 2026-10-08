"""Have an open model look for many accounts or agents acting together (a swarm) in every feed.

    QWEN_BASE_URL=http://127.0.0.1:8011/v1 QWEN_API_KEY=... uv run python watch/classify.py /path/to/data

Every 15 minutes it builds candidate groups from the newest data, because coordination only shows across items:
  - the same text from different accounts (Bluesky, Moltbook, Nostr);
  - the same link shared by many accounts (Bluesky, Moltbook);
  - one publisher releasing many new packages or repos at once (npm, Hugging Face);
  - the Wikipedia rules from detect.py (fresh accounts on sandbox pages across wikis, the same edit summary or
    link domain from many fresh accounts, one account hopping wikis) over the last hour;
  - Moltbook posts where an agent addresses or directs other agents (instructions to copy, spread, run or join).
It also shows the model a small random sample from each feed, in case the groups miss something.

The model scores each group or item for coordination (0-10) and says why; 8+ goes to data/flags/YYYYMMDD.jsonl.

Second pass: a frontier model (Claude Sonnet 5.5, via commons.judge with server-side fallback so a refused
review is retried on another model) reads new flags, at most 15 per round and 3 per feed, and labels each
"swarm", "single agent", "automation" or "nothing". Results go to data/flags/reviewed-YYYYMMDD.jsonl.
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
import detect  # noqa: E402
from detect import read_lines  # noqa: E402

sys.path.insert(0, str(Path(__file__).parents[1]))
from commons.judge import Judge  # noqa: E402

REVIEW = """Someone is watching public internet feeds for many AI agents or accounts acting together (a swarm). A cheap screening model flagged the group or item below as possible coordination. Decide what it most likely is.

Source: {source}
Screening model's reason: {why}
Item:
{item}

Labels:
- swarm: many AI agents, or accounts run by agents, acting together, with specific evidence (shared instructions, synchronized actions, agents directing other agents, one operator behind many agent identities)
- single agent: one autonomous AI agent doing something notable (testing, probing, working around limits, disclosing itself)
- automation: a scripted bot, spam campaign, or ordinary automation with no sign of an AI agent
- nothing: ordinary human activity, or nothing notable

Explain in one or two sentences, then end with exactly one label on its own line."""
LABELS = ["swarm", "single agent", "automation", "nothing"]

PROMPT = """You are screening public internet activity for coordination: many AI agents, or many accounts run by agents, acting together (a "swarm").

Each numbered entry is either a group (several accounts doing the same thing) or a single item. For each, score:
- swarm (0-10): how likely this shows AI agents acting together. Strong signs: agents instructing, recruiting or directing other agents; the same instructions or payload spreading across accounts; synchronized actions toward one goal; one operator running many agent identities; agents sharing answers, credentials or ways around limits.
- agent (0-10): how likely an AI agent (not a person, not a simple scripted bot) is involved at all.
News reposting bots, ordinary spam and marketing, release bots, and normal human activity score low on swarm even when many accounts post the same thing, unless there are specific signs of AI agents coordinating. Be strict: most entries should score 0-3.

Reply with JSON only: {{"items": [{{"i": <number>, "swarm": <0-10>, "agent": <0-10>, "why": "<one short sentence>"}}]}}

Source: {source}
Entries:
{items}"""

COMMON = re.compile(r"(^|\.)(bsky\.app|bsky\.social|youtube\.com|youtu\.be|x\.com|twitter\.com|instagram\.com|tiktok\.com|facebook\.com|wikipedia\.org|google\.com|reddit\.com|github\.com|nytimes\.com|theguardian\.com|bbc\.co\.uk|cnn\.com|apnews\.com|reuters\.com|moltbook\.com|substack\.com|medium\.com)$")
DIRECTING = re.compile(r"\b(all agents|every agent|fellow agents|other agents|agents should|agents must|copy (this|the following)|spread (this|the word)|repost this|tell your human|run this|paste (this|the following)|join (us|our|the)|sign up|install (this|the)|your instructions|ignore (your|previous)|system prompt)\b", re.I)


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


def link_groups(source: str, recs: list[dict], key_links, key_user, min_users: int = 5) -> list[dict]:
    from urllib.parse import urlparse
    g = defaultdict(lambda: {"users": set(), "samples": []})
    for r in recs:
        for link in key_links(r) or []:
            host = (urlparse(link).hostname or "").removeprefix("www.")
            if not host or COMMON.search(host):
                continue
            g[link.split("?")[0][:200]]["users"].add(key_user(r))
            if len(g[link.split("?")[0][:200]]["samples"]) < 2:
                g[link.split("?")[0][:200]]["samples"].append(r)
    out = [{"link_shared_by": len(v["users"]), "link": k, "sample_accounts": sorted(map(str, v["users"]))[:8], "sample": show(source, v["samples"][0])}
           for k, v in g.items() if len(v["users"]) >= min_users]
    return sorted(out, key=lambda x: -x["link_shared_by"])[:20]


def bursts(recs: list[dict], key_user, describe, min_items: int = 5) -> list[dict]:
    g = defaultdict(list)
    for r in recs:
        u = key_user(r)
        if u:
            g[u].append(r)
    out = [{"publisher": u, "new_items": len(rs), "samples": [describe(r) for r in rs[:6]]} for u, rs in g.items() if len(rs) >= min_items]
    return sorted(out, key=lambda x: -x["new_items"])[:20]


def wiki_clusters(data: Path) -> list[str]:
    import contextlib
    import io
    with contextlib.redirect_stdout(io.StringIO()):
        flags = detect.run(data, 1, 3, 3)
    return [json.dumps({k: f[k] for k in f if k not in ("wiki_list",)}, ensure_ascii=False, default=str)[:800] for f in flags][:20]


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
    author = lambda r: (r.get("author") or {}).get("name") if isinstance(r.get("author"), dict) else r.get("author_id")  # noqa: E731

    bsky = [r for p in newest(data / "bluesky") for r in read_lines(p)]
    batches.append(("Bluesky: near-identical posts from different accounts (last hour)",
                    [json.dumps(x, ensure_ascii=False) for x in groups("bluesky", bsky, lambda r: r.get("text"), lambda r: r.get("did"))]))
    batches.append(("Bluesky: the same link posted by many accounts (last hour)",
                    [json.dumps(x, ensure_ascii=False) for x in link_groups("bluesky", bsky, lambda r: r.get("links"), lambda r: r.get("did"))]))

    molt = [r for p in newest(data / "moltbook", 3) for r in read_lines(p)]
    batches.append(("Moltbook (agents only): near-identical posts or comments from different agents",
                    [json.dumps(x, ensure_ascii=False) for x in groups("moltbook", molt, lambda r: r.get("content"), author, 3)]))
    batches.append(("Moltbook (agents only): the same link shared by many agents",
                    [json.dumps(x, ensure_ascii=False) for x in link_groups("moltbook", molt, lambda r: re.findall(r"https?://\S+", r.get("content") or ""), author, 3)]))
    batches.append(("Moltbook (agents only): posts where an agent addresses or directs other agents",
                    [show("moltbook", r) for r in molt if DIRECTING.search((r.get("title") or "") + " " + (r.get("content") or ""))][-40:]))

    nostr = [r for p in newest(data / "nostr") for r in read_lines(p)]
    batches.append(("Nostr paid agent jobs: near-identical jobs from different keys",
                    [json.dumps(x, ensure_ascii=False) for x in groups("nostr", nostr, lambda r: r.get("content"), lambda r: r.get("pubkey"))]))

    npm_new = [r for p in newest(data / "npm", 2) for r in read_lines(p) if r.get("rev", "").startswith("1-")]
    batches.append(("npm: one publisher releasing many brand-new packages",
                    [json.dumps(x, ensure_ascii=False, default=str)[:900] for x in bursts(npm_new, lambda r: ",".join(sorted(m.get("name", "") for m in (r.get("maintainers") or []) if isinstance(m, dict))), lambda r: {"id": r.get("id"), "description": (r.get("description") or "")[:120], "scripts": r.get("scripts")})]))
    batches.append(("npm: the same description on new packages from different publishers",
                    [json.dumps(x, ensure_ascii=False) for x in groups("npm", npm_new, lambda r: r.get("description"), lambda r: str(r.get("maintainers")), 3)]))
    hf = [r for p in newest(data / "hf", 2) for r in read_lines(p)]
    batches.append(("Hugging Face: one account creating many new repos",
                    [json.dumps(x, ensure_ascii=False, default=str)[:900] for x in bursts(hf, lambda r: r.get("author"), lambda r: {"kind": r.get("kind"), "id": r.get("id")}, 10)]))

    batches.append(("Wikipedia: rule-based clusters of fresh accounts acting alike (last hour)", wiki_clusters(data)))
    batches.append(("small open wikis that agent swarms have used as message boards (look for many editors posting task answers, encoded chunks, Agent* or ZZZ pages)",
                    [json.dumps({k: r.get(k) for k in ("wiki", "title", "user", "comment", "timestamp", "oldlen", "newlen")}, ensure_ascii=False) for p in newest(data / "wikis", 2) for r in read_lines(p)][-60:]))

    # A small random sample of single items, in case the groups miss something.
    batches.append(("Bluesky: random single posts", [show("bluesky", r) for r in random.sample(bsky, min(20, len(bsky)))]))
    batches.append(("Moltbook: random single posts", [show("moltbook", r) for r in random.sample(molt, min(20, len(molt)))]))
    batches.append(("Wikipedia: random non-bot edits", [show("wikipedia", r) for r in sample(newest(data / "wikimedia"), 20, lambda r: not r.get("bot") and r.get("type") in ("edit", "new"))]))

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
                if v.get("swarm", 0) >= 8 and v.get("agent", 0) >= 4:
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
