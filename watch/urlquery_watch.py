"""Record urlquery.net's public list of recent URL scans.

    uv run python watch/urlquery_watch.py live /path/to/data/urlquery            # poll every 5 minutes, forever
    uv run python watch/urlquery_watch.py backfill /path/to/data/urlquery 2026-09-28 2026-10-06

urlquery.net is a public URL scanner: anyone (or any agent) can submit a link, and the results are
public. Agent fleets have shown up here because agents use scanners to fetch pages they can't reach
directly. This reads only the public search listing, one request at a time with pauses, and stores
date, URL, report id, IP, network and detection counts. It never submits anything.
"""

import html
import json
import os
import re
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import httpx

SEARCH = "https://urlquery.net/api/htmx/search/"
HEADERS = {
    "User-Agent": f"swarm-watch-research/0.1 (read-only research; {os.environ.get('WATCH_CONTACT', 'https://github.com/erickfm/commons')})",
    "HX-Request": "true",
    "HX-Current-URL": "https://urlquery.net/search",
}
ROW = re.compile(r"<tr.*?</tr>", re.S)


def parse(page: str) -> list[dict]:
    rows = []
    for r in ROW.findall(page):
        rid = re.search(r'href="/report/([0-9a-f-]{36})"', r)
        if not rid:
            continue
        url = re.search(r'href="/report/[0-9a-f-]{36}"[^>]*>([^<]*)</a>', r)
        when = re.search(r">(\d{4}-\d\d-\d\d \d\d:\d\d)<", r)
        ip = re.search(r'search\?q=ip\.addr:([^"]+)"', r)
        asn = re.search(r'title="(#\d+[^"]*)"', r)
        country = re.search(r'flags/(\w+)\.png', r)
        det = dict(re.findall(r"<span>(UQ|IDS|TDS)</span>\s*<span[^>]*>(\d+)</span>", r))
        rows.append({
            "id": rid.group(1), "dt": when.group(1) if when else None, "url": html.unescape(url.group(1)) if url else None,
            "ip": ip.group(1) if ip else None, "asn": html.unescape(asn.group(1)) if asn else None,
            "country": country.group(1) if country else None, "det": {k: int(v) for k, v in det.items()},
        })
    return rows


def fetch(client: httpx.Client, q: str, offset: int, limit: int = 100) -> list[dict]:
    for attempt in range(5):
        try:
            r = client.get(SEARCH, params={"q": q, "limit": limit, "offset": offset, "view": "list", "type": "reports"})
            if r.status_code == 204:
                return []
            r.raise_for_status()
            return parse(r.text)
        except httpx.HTTPError as ex:
            print(f"retry after {ex!r}", flush=True)
            time.sleep(30 * (attempt + 1))
    return []


def save(out: Path, rows: list[dict], seen: set[str]) -> int:
    new = [r for r in rows if r["id"] not in seen]
    by_day: dict[str, list[dict]] = {}
    for r in new:
        seen.add(r["id"])
        by_day.setdefault((r["dt"] or "unknown")[:10], []).append(r)
    for day, rs in by_day.items():
        with open(out / f"{day}.jsonl", "a") as f:
            f.writelines(json.dumps(r, ensure_ascii=False) + "\n" for r in rs)
    return len(new)


def load_seen(out: Path) -> set[str]:
    seen = set()
    for p in out.glob("*.jsonl"):
        for line in open(p):
            try:
                seen.add(json.loads(line)["id"])
            except (ValueError, KeyError):
                pass
    return seen


def live(out: Path) -> None:
    seen = load_seen(out)
    with httpx.Client(headers=HEADERS, timeout=60) as client:
        while True:
            today = datetime.now(timezone.utc).date()
            q = f"date:[{today - timedelta(days=1)} TO {today + timedelta(days=1)}]"
            got = 0
            for off in (0, 100):  # ~10-15 scans a minute, so two pages cover 5 minutes with room to spare
                got += save(out, fetch(client, q, off), seen)
                time.sleep(3)
            print(f"{datetime.now(timezone.utc):%Y-%m-%d %H:%M} +{got}", flush=True)
            time.sleep(300)


def backfill(out: Path, start: str, end: str) -> None:
    seen = load_seen(out)
    d, last = date.fromisoformat(start), date.fromisoformat(end)
    with httpx.Client(headers=HEADERS, timeout=60) as client:
        while d <= last:
            off, total = 0, 0
            while True:
                rows = fetch(client, f"date:[{d} TO {d}]", off)
                if not rows:
                    break
                total += save(out, rows, seen)
                off += len(rows)
                time.sleep(3)
            print(f"{d}: {total} new scans ({off} listed)", flush=True)
            d += timedelta(days=1)


if __name__ == "__main__":
    mode, out = sys.argv[1], Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    live(out) if mode == "live" else backfill(out, sys.argv[3], sys.argv[4])
