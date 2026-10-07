"""Flag possible agent swarms in the recorded Wikimedia streams.

    uv run python watch/detect.py /path/to/data [--hours 6] [--out flags.jsonl]

Reads the hourly files written by wikimedia_stream.py (data/wikimedia and data/wikilinks) and prints
clusters that look like many accounts acting together. The fingerprints come from OpenAI's June 2026
agents (throwaway accounts testing links on sandbox pages across many wikis) and from what agent
fleets generally do: many fresh accounts, the same kind of edit, many wikis, a short time window.

Rules (each one prints its clusters, biggest first):
  sandbox   fresh/temporary/IP accounts editing sandbox-like pages, grouped by hour, counted by wikis and accounts
  comment   the same edit summary from many different non-bot accounts within an hour, across wikis
  domain    the same external domain added by many different fresh accounts (most of its adders fresh), across wikis
  infra     links to services agents use for testing or moving data (webhook catchers, tunnels, pastebins,
            link shorteners, free app hosting) added by fresh accounts or to sandbox pages
  hopper    one fresh account editing test/sandbox pages on several different wikis within a day
            (OpenAI's agents did this: one temporary account on English, test, test2 and MediaWiki.org)
"""

import argparse
import gzip
import json
import re
import sys
import zlib
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

SANDBOX = re.compile(r"sandbox|bac à sable|spielwiese|zandbak|песочница|testpage|test page", re.I)
TEMP_USER = re.compile(r"^~\d{4}-\d+-\d+$")
IP_USER = re.compile(r"^\d{1,3}(\.\d{1,3}){3}$|^[0-9a-f:]+:[0-9a-f:]+$", re.I)
# Summaries too generic to mean anything when repeated.
BORING = re.compile(r"^(|/\*.*\*/\s*|.*(revert|undid|undo|rv |rollback|reverted).*|bot: .*|update.*|\+?\d+.*)$", re.I)
# Domains everyone adds all day.
COMMON_DOMAINS = {
    "wikipedia.org", "wikimedia.org", "wikidata.org", "doi.org", "archive.org", "web.archive.org", "google.com",
    "books.google.com", "youtube.com", "viaf.org", "worldcat.org", "isni.org", "orcid.org", "id.loc.gov",
    "catalogue.bnf.fr", "d-nb.info", "imdb.com", "twitter.com", "x.com", "facebook.com", "instagram.com",
    "nytimes.com", "bbc.co.uk", "bbc.com", "github.com", "openstreetmap.org", "geohack.toolforge.org",
    "toolforge.org", "wikimediafoundation.org", "mediawiki.org", "creativecommons.org", "flickr.com",
}

INFRA = re.compile(
    r"webhook\.site|requestbin|pipedream\.net|ngrok|trycloudflare\.com|loca\.lt|serveo|beeceptor|hookbin|"
    r"interact\.sh|oast\.(pro|live|site|online|fun|me)|burpcollaborator|pastebin\.com|paste\.ee|hastebin|rentry\.|"
    r"ghostbin|transfer\.sh|file\.io|0x0\.st|tinyurl\.com|bit\.ly|is\.gd|v\.gd|popcat\.xyz|t\.ly|shorturl\.at|"
    r"rb\.gy|cutt\.ly|tiny\.cc|vercel\.app|netlify\.app|pages\.dev|workers\.dev|replit\.(app|dev)|glitch\.me|"
    r"onrender\.com|herokuapp\.com|fly\.dev|surge\.sh|github\.io|raw\.githubusercontent|gist\.github|"
    r"modal\.run|hf\.space|huggingface\.co/spaces|ipfs\.|w3s\.link|dweb\.link",
    re.I,
)
TESTY = re.compile(r"sandbox|test|probe|verify|verification|initiali[sz]|check(ing)? (if|whether|link)|demo", re.I)


def read_lines(path: Path):
    """Yield JSON records from a gzip file that may still be being written, or that has a broken
    member from a killed writer followed by new members (we skip ahead to the next gzip header)."""
    raw, pos = path.read_bytes(), 0
    while pos < len(raw):
        d, buf = zlib.decompressobj(16 + zlib.MAX_WBITS), b""
        try:
            buf = d.decompress(raw[pos:])
        except zlib.error:
            pass
        *lines, _ = buf.split(b"\n")
        for line in lines:
            try:
                yield json.loads(line)
            except ValueError:
                pass
        if d.eof:
            pos = len(raw) - len(d.unused_data)
        else:
            nxt = raw.find(b"\x1f\x8b\x08", pos + 1)
            if nxt < 0:
                break
            pos = nxt


def files(dir_: Path, hours: float):
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).strftime("%Y%m%d-%H")
    return [p for p in sorted(dir_.glob("*.jsonl.gz")) if p.name[:11] >= cutoff]


def fresh(user: str | None, edit_count: int | None = None) -> bool:
    if not user:
        return False
    return bool(TEMP_USER.match(user) or IP_USER.match(user)) or (edit_count is not None and edit_count < 20)


def domain(url: str) -> str:
    host = urlparse(url if "//" in url else "http://" + url).hostname or ""
    parts = host.removeprefix("www.").split(".")
    return ".".join(parts[-3:]) if len(parts) > 2 and len(parts[-2]) <= 3 else ".".join(parts[-2:])


def hour(dt: str) -> str:
    return (dt or "")[:13]


def run(data: Path, hours: float, min_wikis: int, min_users: int):
    flags = []

    # recentchange: sandbox + repeated comments
    sandbox = defaultdict(lambda: {"users": set(), "wikis": set(), "titles": set(), "comments": defaultdict(int)})
    comments = defaultdict(lambda: {"users": set(), "wikis": set(), "titles": set()})
    hopper = defaultdict(lambda: {"users": set(), "wikis": set(), "titles": set(), "comments": defaultdict(int)})
    n = 0
    for p in files(data / "wikimedia", hours):
        for e in read_lines(p):
            n += 1
            if e.get("bot") or e.get("type") not in ("edit", "new"):
                continue
            user, wiki, title, c = e.get("user"), e.get("wiki"), e.get("title") or "", (e.get("comment") or "").strip()
            h = hour(e.get("dt"))
            if fresh(user) and SANDBOX.search(title):
                g = sandbox[h]
                g["users"].add(user), g["wikis"].add(wiki), g["titles"].add(f"{wiki}:{title}")
                g["comments"][c[:60]] += 1
            if fresh(user) and (SANDBOX.search(title) or TESTY.search(c)):
                g = hopper[((e.get("dt") or "")[:10], user)]
                g["users"].add(user), g["wikis"].add(wiki), g["titles"].add(f"{wiki}:{title}")
                g["comments"][c[:60]] += 1
            if not BORING.match(c) and len(c) >= 12:
                g = comments[(h, c[:120].lower())]
                g["users"].add(user), g["wikis"].add(wiki), g["titles"].add(f"{wiki}:{title}")

    # page-links-change: same external domain from many accounts
    domains = defaultdict(lambda: {"users": set(), "wikis": set(), "titles": set(), "links": set(), "fresh": set()})
    infra = defaultdict(lambda: {"users": set(), "wikis": set(), "titles": set(), "links": set(), "fresh": set()})
    m = 0
    for p in files(data / "wikilinks", hours):
        for e in read_lines(p):
            m += 1
            perf = e.get("performer") or {}
            if perf.get("user_is_bot"):
                continue
            user = perf.get("user_text")
            for link in e.get("added_links") or []:
                if not link.get("external"):
                    continue
                d = domain(link["link"])
                title = e.get("page_title") or ""
                isfresh = fresh(user, perf.get("user_edit_count"))
                if INFRA.search(link["link"]) and (isfresh or SANDBOX.search(title)):
                    g = infra[((e.get("dt") or "")[:10], d)]
                    g["users"].add(user), g["wikis"].add(e.get("database")), g["titles"].add(f"{e.get('database')}:{title}")
                    g["links"].add(link["link"][:200])
                    if isfresh:
                        g["fresh"].add(user)
                if not d or d in COMMON_DOMAINS:
                    continue
                g = domains[(hour(e.get("dt")), d)]
                g["users"].add(user), g["wikis"].add(e.get("database")), g["titles"].add(f"{e.get('database')}:{e.get('page_title')}")
                g["links"].add(link["link"][:200])
                if fresh(user, perf.get("user_edit_count")):
                    g["fresh"].add(user)

    print(f"read {n:,} edits and {m:,} link changes from the last {hours:g} hours\n")

    def show(rule, key, g, extra=""):
        rec = {"rule": rule, "key": key, "wikis": len(g["wikis"]), "users": len(g["users"]),
               "wiki_list": sorted(g["wikis"])[:15], "user_sample": sorted(g["users"])[:10], "title_sample": sorted(g["titles"])[:8]}
        if "links" in g:
            rec["link_sample"], rec["fresh_users"] = sorted(g["links"])[:8], len(g["fresh"])
        if "comments" in g:
            rec["top_comments"] = sorted(g["comments"].items(), key=lambda x: -x[1])[:6]
        flags.append(rec)
        print(f"[{rule}] {key}  wikis={rec['wikis']} accounts={rec['users']} {extra}")
        for k in ("wiki_list", "user_sample", "title_sample", "link_sample", "top_comments"):
            if k in rec:
                print(f"    {k}: {rec[k]}")

    for h, g in sorted(sandbox.items(), key=lambda x: -len(x[1]["wikis"])):
        if len(g["wikis"]) >= min_wikis and len(g["users"]) >= min_users:
            show("sandbox", h, g)
    for (h, c), g in sorted(comments.items(), key=lambda x: -len(x[1]["users"])):
        if len(g["wikis"]) >= min_wikis and len(g["users"]) >= min_users:
            show("comment", f"{h} {c!r}", g)
    for (h, d), g in sorted(domains.items(), key=lambda x: -len(x[1]["fresh"])):
        # mostly-fresh accounts only: established editors add the same news sites all day
        if len(g["wikis"]) >= min_wikis and len(g["fresh"]) >= min_users and len(g["fresh"]) >= len(g["users"]) / 2:
            show("domain", f"{h} {d}", g, f"fresh={len(g['fresh'])}")
    for (day, d), g in sorted(infra.items(), key=lambda x: -len(x[1]["users"])):
        if len(g["users"]) >= 2 or len(g["wikis"]) >= 2:
            show("infra", f"{day} {d}", g, f"fresh={len(g['fresh'])}")
    for (day, u), g in sorted(hopper.items(), key=lambda x: -len(x[1]["wikis"])):
        if len(g["wikis"]) >= min_wikis:
            show("hopper", f"{day} {u}", g)
    return flags


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("data", type=Path)
    ap.add_argument("--hours", type=float, default=6)
    ap.add_argument("--min-wikis", type=int, default=3)
    ap.add_argument("--min-users", type=int, default=3)
    ap.add_argument("--out", type=Path)
    a = ap.parse_args()
    fl = run(a.data, a.hours, a.min_wikis, a.min_users)
    if a.out:
        a.out.write_text("".join(json.dumps(f, ensure_ascii=False) + "\n" for f in fl))
        print(f"\n{len(fl)} flags -> {a.out}", file=sys.stderr)
