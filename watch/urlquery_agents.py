"""Find urlquery.net scans that look like an agent using the scanner as a remote browser, and list what they targeted.

    uv run python watch/urlquery_agents.py /path/to/data/urlquery-hits 2026-09-01 2026-10-08

The trick: an agent that can't reach a site (blocked, rate-limited, behind anti-bot checks) submits a URL to a
public scanner. The scanner's real browser loads it and the result is public. Agents wrap their own small web
page in an echo service (httpbin.org/base64/<page>, httpbun, itty.bitty.site, codesandbox, livecodes...), so the
scanner runs the agent's script, which then loads the target or sends what it finds to a webhook inbox.

This searches urlquery's public index (read-only, a few requests with pauses), decodes the embedded pages, and
writes one JSON line per scan with the target sites found inside. It never opens the target or inbox URLs.
"""

import base64
import json
import re
import sys
import time
import urllib.parse
from collections import Counter, defaultdict
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).parent))
import urlquery_watch as uq  # noqa: E402

RELAYS = [
    "httpbin.org", "httpbun.com", "itty.bitty.site", "codesandbox.io", "livecodes.io", "href.li", "postman-echo.com",
    "api.allorigins.win", "translate.goog", "webhook.site", "spoo.me", "httpbin.ceshiren.com", "httpbin.konghq.com",
]
CALLBACKS = ["webhook.site", "pipedream.net", "requestcatcher.com", "requestbin.net", "beeceptor.com", "interact.sh"]
NOISE = {"www.w3.org", "httpbin.org", "httpbun.com", "webhook.site", "example.com", "g.alicdn.com"}


def decode(url: str) -> str:
    """The page an agent packed into the URL, if any (base64 path, data param, or itty.bitty fragment)."""
    url = url or ""
    # Some loaders run code kept in the #fragment, so decode that part too.
    frag = urllib.parse.unquote(url.split("#", 1)[1]) if "#" in url else ""
    m = re.search(r"/base64/([^?#\s]+)", url)
    if m:
        s = urllib.parse.unquote(m.group(1)).replace("-", "+").replace("_", "/")
        try:
            return base64.b64decode(s + "=" * (-len(s) % 4)).decode("utf-8", "replace") + "\n" + frag
        except ValueError:
            return frag
    return urllib.parse.unquote(urllib.parse.unquote(url))


def targets(page: str) -> list[str]:
    hosts = re.findall(r"https?(?::|%3A)(?://|%2F%2F)([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})", page)
    return sorted({h.lower() for h in hosts} - NOISE)


def main(out: Path, start: str, end: str) -> None:
    out.mkdir(parents=True, exist_ok=True)
    rows: dict[str, dict] = {}
    queries = [f"url.domain:{d}" for d in RELAYS] + [f"http.url.domain:{d}" for d in CALLBACKS]
    with httpx.Client(headers=uq.HEADERS, timeout=120) as client:
        for q in queries:
            n = 0
            for off in range(0, 3000, 100):
                got = uq.fetch(client, f"({q}) AND date:[{start} TO {end}]", off, 100)
                for r in got:
                    r.setdefault("matched", []).append(q)
                    rows.setdefault(r["id"], r)
                n += len(got)
                time.sleep(4)
                if len(got) < 90:
                    break
            print(f"{q}: {n}", flush=True)
    by_target: dict[str, list] = defaultdict(list)
    with open(out / "agent_scans.jsonl", "w") as f:
        for r in sorted(rows.values(), key=lambda r: r["dt"] or ""):
            page = decode(r["url"])
            t = re.search(r"<title>(.*?)</title>", page)
            r["page_title"] = t.group(1)[:80] if t else None
            r["targets"] = targets(page)
            r["callback"] = bool(re.search("|".join(map(re.escape, CALLBACKS)), page))
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
            for h in r["targets"] or ["(none found)"]:
                by_target[h].append(r["dt"])
    print(f"\n{len(rows)} scans. Targets (scans, first, last):")
    for h, ds in sorted(by_target.items(), key=lambda x: -len(x[1]))[:60]:
        print(f"  {len(ds):5d}  {min(ds)}  {max(ds)}  {h}")
    print("\nby day:", sorted(Counter((r["dt"] or "")[:10] for r in rows.values()).items()))


if __name__ == "__main__":
    main(Path(sys.argv[1]), sys.argv[2], sys.argv[3])
