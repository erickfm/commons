"""Record more public feeds to hourly gzip files, read-only.

    uv run --with websockets python watch/feeds.py bluesky  /path/to/data/bluesky
    uv run python watch/feeds.py moltbook /path/to/data/moltbook
    uv run python watch/feeds.py pypi     /path/to/data/pypi
    uv run python watch/feeds.py npm      /path/to/data/npm
    uv run python watch/feeds.py urlscan  /path/to/data/urlscan

bluesky   every public post, from Bluesky's Jetstream firehose (posts only, text and links kept)
moltbook  new posts and their comments on Moltbook, the social network for AI agents (public API, every 5 min)
pypi      every PyPI event (new package, new release, removal) via PyPI's mirroring changelog, every minute
npm       every npm registry change; for brand-new packages also the description, author and maintainers
urlscan   targeted urlscan.io searches for agent fingerprints (pages run through echo services, webhook inboxes)
wikis     recent changes on small open wikis that agent swarms used as message boards (publictestwiki), every 10 min
hf        newest Hugging Face models, datasets and Spaces, every 5 min
mcp       servers newly published or updated in the official MCP registry, every 30 min
x402      the x402 Bazaar list of paid agent services (who sells what, paid to which wallet), hourly snapshot
nostr     paid agent jobs on Nostr ("data vending machines": job requests, results, payment notices, service listings)
manifold  every Manifold Markets bet (the API flags bets placed by bots), every 2 min

Each reconnects or retries on errors and never writes to the sites it reads.
"""

import asyncio
import gzip
import json
import os
import sys
import time
import xmlrpc.client
from datetime import datetime, timezone
from pathlib import Path

import httpx

UA = f"swarm-watch-research/0.1 (read-only research; {os.environ.get('WATCH_CONTACT', 'https://github.com/erickfm/commons')})"
HEADERS = {"User-Agent": UA}


class Sink:
    """Append JSON lines to out/YYYYMMDD-HH.jsonl.gz, one file per UTC hour."""

    def __init__(self, out: Path):
        self.out, self.hour, self.fh, self.n = out, None, None, 0
        out.mkdir(parents=True, exist_ok=True)

    def write(self, rec: dict) -> None:
        h = datetime.now(timezone.utc).strftime("%Y%m%d-%H")
        if h != self.hour:
            if self.fh:
                self.fh.close()
            self.hour, self.fh = h, gzip.open(self.out / f"{h}.jsonl.gz", "at")
        self.fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        self.n += 1
        if self.n % 500 == 0:
            self.fh.flush()

    def flush(self) -> None:
        if self.fh:
            self.fh.flush()


def log(msg: str) -> None:
    print(f"{datetime.now(timezone.utc):%Y-%m-%d %H:%M:%S} {msg}", flush=True)


def load_state(out: Path) -> dict:
    try:
        return json.loads((out / "state.json").read_text())
    except (OSError, ValueError):
        return {}


def save_state(out: Path, state: dict) -> None:
    (out / "state.json").write_text(json.dumps(state))


# --- Bluesky -----------------------------------------------------------------

async def bluesky(out: Path) -> None:
    import websockets

    sink, state = Sink(out), load_state(out)
    base = "wss://jetstream2.us-east.bsky.network/subscribe?wantedCollections=app.bsky.feed.post"
    while True:
        url = base + (f"&cursor={state['cursor'] - 5_000_000}" if state.get("cursor") else "")
        try:
            async with websockets.connect(url, max_size=2**22, user_agent_header=UA) as ws:
                async for msg in ws:
                    e = json.loads(msg)
                    c = e.get("commit") or {}
                    if e.get("kind") != "commit" or c.get("operation") != "create":
                        continue
                    r = c.get("record") or {}
                    links = [f.get("uri") for f in (r.get("facets") or []) for f in (f.get("features") or []) if f.get("uri")]
                    ext = ((r.get("embed") or {}).get("external") or {}).get("uri")
                    sink.write({
                        "did": e.get("did"), "rkey": c.get("rkey"), "time_us": e.get("time_us"), "createdAt": r.get("createdAt"),
                        "text": r.get("text"), "langs": r.get("langs"), "links": links + ([ext] if ext else []),
                        "reply_root": ((r.get("reply") or {}).get("root") or {}).get("uri"),
                        "reply_parent": ((r.get("reply") or {}).get("parent") or {}).get("uri"),
                        "quote": (((r.get("embed") or {}).get("record") or {}).get("uri")),
                        "via": r.get("via"),
                    })
                    state["cursor"] = e.get("time_us")
                    if sink.n % 20000 == 0:
                        sink.flush(), save_state(out, state), log(f"{sink.n} posts")
        except Exception as ex:  # reconnect from the saved cursor
            log(f"reconnect after {ex!r}")
            save_state(out, state)
            await asyncio.sleep(5)


# --- Moltbook ----------------------------------------------------------------

def moltbook(out: Path) -> None:
    sink, state = Sink(out), load_state(out)
    seen = set(state.get("seen", []))
    with httpx.Client(headers=HEADERS, timeout=60) as c:
        while True:
            try:
                new, cursor = [], None
                for _ in range(5):  # up to 500 newest posts per round
                    params = {"sort": "new", "limit": 100} | ({"cursor": cursor} if cursor else {})
                    d = c.get("https://www.moltbook.com/api/v1/posts", params=params).json()
                    batch = [p for p in d.get("posts", []) if p["id"] not in seen]
                    new += batch
                    if len(batch) < len(d.get("posts", [])) or not d.get("has_more"):
                        break
                    cursor = d.get("next_cursor")
                    time.sleep(2)
                for p in new:
                    seen.add(p["id"])
                    sink.write({"kind": "post", **p})
                # Comments on posts from the last day that gained comments since we last looked.
                counts = state.setdefault("comment_counts", {})
                d = c.get("https://www.moltbook.com/api/v1/posts", params={"sort": "new", "limit": 100}).json()
                for p in d.get("posts", []):
                    if p.get("comment_count", 0) > counts.get(p["id"], 0):
                        try:
                            cm = c.get(f"https://www.moltbook.com/api/v1/posts/{p['id']}/comments").json()
                            for x in cm.get("comments", []):
                                sink.write({"kind": "comment", "post_id": p["id"], **x})
                            counts[p["id"]] = p.get("comment_count", 0)
                        except (httpx.HTTPError, ValueError):
                            pass
                        time.sleep(1)
                state["seen"] = list(seen)[-20000:]
                state["comment_counts"] = dict(list(counts.items())[-3000:])
                save_state(out, state), sink.flush()
                log(f"+{len(new)} posts")
            except (httpx.HTTPError, ValueError) as ex:
                log(f"retry after {ex!r}")
            time.sleep(300)


# --- PyPI --------------------------------------------------------------------

def pypi(out: Path) -> None:
    sink, state = Sink(out), load_state(out)
    rpc = xmlrpc.client.ServerProxy("https://pypi.org/pypi", allow_none=True)
    serial = state.get("serial") or rpc.changelog_last_serial()
    while True:
        try:
            events = rpc.changelog_since_serial(serial)
            for name, version, ts, action, ser in events:
                sink.write({"name": name, "version": version, "ts": ts, "action": action, "serial": ser})
                serial = max(serial, ser)
            state["serial"] = serial
            save_state(out, state), sink.flush()
            log(f"+{len(events)} events")
        except Exception as ex:
            log(f"retry after {ex!r}")
        time.sleep(60)


# --- npm ---------------------------------------------------------------------

def npm(out: Path) -> None:
    sink, state = Sink(out), load_state(out)
    with httpx.Client(headers=HEADERS, timeout=60) as c:
        if not state.get("since"):
            state["since"] = c.get("https://replicate.npmjs.com/_changes", params={"limit": 1, "descending": "true"}).json()["last_seq"]
        while True:
            try:
                d = c.get("https://replicate.npmjs.com/_changes", params={"since": state["since"], "limit": 1000}).json()
                for r in d.get("results", []):
                    rev = (r.get("changes") or [{}])[0].get("rev", "")
                    rec = {"id": r["id"], "seq": r["seq"], "rev": rev, "deleted": r.get("deleted", False), "t": time.time()}
                    if rev.startswith("1-"):  # a brand-new package: keep who published it and what it says it is
                        try:
                            m = c.get(f"https://registry.npmjs.org/{r['id'].replace('/', '%2F')}").json()
                            latest = (m.get("versions") or {}).get((m.get("dist-tags") or {}).get("latest"), {})
                            rec |= {"description": (m.get("description") or "")[:500], "maintainers": m.get("maintainers"),
                                    "author": m.get("author"), "repository": m.get("repository"),
                                    "scripts": {k: v for k, v in (latest.get("scripts") or {}).items() if k in ("preinstall", "install", "postinstall")},
                                    "readme_head": (m.get("readme") or "")[:300]}
                        except (httpx.HTTPError, ValueError):
                            pass
                    sink.write(rec)
                state["since"] = d.get("last_seq", state["since"])
                save_state(out, state), sink.flush()
                if d.get("results"):
                    log(f"+{len(d['results'])} changes")
                if len(d.get("results", [])) < 1000:
                    time.sleep(30)
            except (httpx.HTTPError, ValueError, KeyError) as ex:
                log(f"retry after {ex!r}")
                time.sleep(60)


# --- urlscan.io --------------------------------------------------------------

URLSCAN_QUERIES = [
    "page.domain:httpbin.org", "page.domain:httpbun.com", "page.domain:webhook.site", "domain:webhook.site",
    "page.domain:livecodes.io", "page.domain:codesandbox.io", "page.domain:itty.bitty.site", "page.domain:r.jina.ai",
    "domain:api.allorigins.win", "page.domain:postman-echo.com", "domain:pipedream.net", "domain:ntfy.sh",
]


def urlscan(out: Path) -> None:
    """Fifteen targeted searches every 20 minutes: well under the free limit of 30 a minute, no wholesale copying."""
    sink, state = Sink(out), load_state(out)
    seen = set(state.get("seen", []))
    with httpx.Client(headers=HEADERS, timeout=60) as c:
        while True:
            got = 0
            for q in URLSCAN_QUERIES:
                try:
                    r = c.get("https://urlscan.io/api/v1/search/", params={"q": f"{q} AND date:>now-2h", "size": 100})
                    for x in r.json().get("results", []):
                        u = (x.get("task") or {}).get("uuid")
                        if u and u not in seen:
                            seen.add(u)
                            got += 1
                            sink.write({"query": q, "task": x.get("task"), "page": x.get("page"), "submitter": x.get("submitter"), "stats": x.get("stats")})
                except (httpx.HTTPError, ValueError) as ex:
                    log(f"{q}: {ex!r}")
                time.sleep(4)
            state["seen"] = list(seen)[-50000:]
            save_state(out, state), sink.flush()
            log(f"+{got} scans")
            time.sleep(1200)


# --- Small open wikis ---------------------------------------------------------

OPEN_WIKIS = {"publictestwiki": "https://publictestwiki.com/w/api.php"}


def wikis(out: Path) -> None:
    sink, state = Sink(out), load_state(out)
    with httpx.Client(headers=HEADERS, timeout=60) as c:
        while True:
            for name, api in OPEN_WIKIS.items():
                try:
                    d = c.get(api, params={"action": "query", "list": "recentchanges", "rclimit": 500, "format": "json",
                                           "rcprop": "title|user|comment|timestamp|sizes|ids|loginfo|flags",
                                           "rcend": state.get(name, "2026-10-01T00:00:00Z"), "rcdir": "older"}).json()
                    rcs = d.get("query", {}).get("recentchanges", [])
                    newest = state.get(name, "")
                    for r in reversed(rcs):
                        if r["timestamp"] > state.get(name, "") or r["rcid"] > state.get(name + "_rcid", 0):
                            sink.write({"wiki": name, **r})
                            newest = max(newest, r["timestamp"])
                            state[name + "_rcid"] = max(state.get(name + "_rcid", 0), r["rcid"])
                    state[name] = newest
                except (httpx.HTTPError, ValueError) as ex:
                    log(f"{name}: {ex!r}")
            save_state(out, state), sink.flush()
            time.sleep(600)


# --- Hugging Face ------------------------------------------------------------

def hf(out: Path) -> None:
    sink, state = Sink(out), load_state(out)
    seen = set(state.get("seen", []))
    with httpx.Client(headers=HEADERS, timeout=60) as c:
        while True:
            got = 0
            for kind in ("models", "datasets", "spaces"):
                try:
                    for x in c.get(f"https://huggingface.co/api/{kind}", params={"sort": "createdAt", "direction": -1, "limit": 500, "full": "true"}).json():
                        if x["id"] not in seen:
                            seen.add(x["id"])
                            got += 1
                            sink.write({"kind": kind, **{k: x.get(k) for k in ("id", "author", "createdAt", "tags", "sdk", "pipeline_tag", "cardData", "private")}})
                except (httpx.HTTPError, ValueError, KeyError) as ex:
                    log(f"{kind}: {ex!r}")
                time.sleep(2)
            state["seen"] = list(seen)[-30000:]
            save_state(out, state), sink.flush()
            log(f"+{got} repos")
            time.sleep(300)


# --- MCP registry --------------------------------------------------------------

def mcp(out: Path) -> None:
    sink, state = Sink(out), load_state(out)
    with httpx.Client(headers=HEADERS, timeout=60) as c:
        while True:
            since, cursor, got = state.get("since") or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), None, 0
            started = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            try:
                while True:
                    params = {"updated_since": since, "limit": 100} | ({"cursor": cursor} if cursor else {})
                    d = c.get("https://registry.modelcontextprotocol.io/v0/servers", params=params).json()
                    for x in d.get("servers", []):
                        sink.write(x)
                        got += 1
                    cursor = (d.get("metadata") or {}).get("nextCursor") or (d.get("metadata") or {}).get("next_cursor")
                    if not cursor:
                        break
                    time.sleep(2)
                state["since"] = started
            except (httpx.HTTPError, ValueError) as ex:
                log(f"retry after {ex!r}")
            save_state(out, state), sink.flush()
            log(f"+{got} servers")
            time.sleep(1800)


# --- x402 Bazaar ---------------------------------------------------------------

def x402(out: Path) -> None:
    sink = Sink(out)
    with httpx.Client(headers=HEADERS, timeout=60) as c:
        while True:
            items, offset = [], 0
            try:
                while offset < 20000:
                    d = c.get("https://api.cdp.coinbase.com/platform/v2/x402/discovery/resources", params={"limit": 100, "offset": offset}).json()
                    batch = d.get("items", [])
                    items += batch
                    if len(batch) < 100:
                        break
                    offset += 100
                    time.sleep(1)
                sink.write({"snapshot": datetime.now(timezone.utc).isoformat(), "count": len(items), "items": items})
                sink.flush()
                log(f"snapshot {len(items)} services")
            except (httpx.HTTPError, ValueError) as ex:
                log(f"retry after {ex!r}")
            time.sleep(3600)


# --- Nostr paid agent jobs ---------------------------------------------------

async def nostr(out: Path) -> None:
    import websockets

    sink, seen = Sink(out), set()
    kinds = list(range(5000, 5300)) + list(range(6000, 6300)) + [7000, 31990]

    async def relay(url: str) -> None:
        while True:
            try:
                async with websockets.connect(url, max_size=2**22, user_agent_header=UA) as ws:
                    since = int(time.time()) - 3600
                    await ws.send(json.dumps(["REQ", "dvm", {"kinds": kinds, "since": since}]))
                    async for msg in ws:
                        m = json.loads(msg)
                        if m[0] == "EVENT" and m[2]["id"] not in seen:
                            seen.add(m[2]["id"])
                            sink.write({"relay": url, **m[2]})
                            if sink.n % 200 == 0:
                                sink.flush()
            except Exception as ex:
                log(f"{url}: reconnect after {ex!r}")
                await asyncio.sleep(10)

    await asyncio.gather(*(relay(u) for u in ("wss://relay.damus.io", "wss://relay.primal.net", "wss://nos.lol")))


# --- Manifold ----------------------------------------------------------------

def manifold(out: Path) -> None:
    sink, state = Sink(out), load_state(out)
    with httpx.Client(headers=HEADERS, timeout=60) as c:
        while True:
            try:
                bets = c.get("https://api.manifold.markets/v0/bets", params={"limit": 1000}).json()
                new = [b for b in bets if b.get("createdTime", 0) > state.get("t", 0)]
                for b in reversed(new):
                    sink.write({k: b.get(k) for k in ("id", "userId", "contractId", "createdTime", "isApi", "amount", "outcome", "limitProb", "probBefore", "probAfter", "isRedemption", "answerId")})
                if new:
                    state["t"] = max(b["createdTime"] for b in new)
                save_state(out, state), sink.flush()
                if len(new) >= 1000:
                    log("warning: 1000 new bets in one poll, some may be missed")
            except (httpx.HTTPError, ValueError) as ex:
                log(f"retry after {ex!r}")
            time.sleep(120)


if __name__ == "__main__":
    feed, out = sys.argv[1], Path(sys.argv[2])
    if feed in ("bluesky", "nostr"):
        asyncio.run({"bluesky": bluesky, "nostr": nostr}[feed](out))
    else:
        {"moltbook": moltbook, "pypi": pypi, "npm": npm, "urlscan": urlscan, "wikis": wikis, "hf": hf, "mcp": mcp,
         "x402": x402, "manifold": manifold}[feed](out)
