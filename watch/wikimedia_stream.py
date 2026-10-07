"""Record one of Wikimedia's public live streams to hourly gzip files.

    uv run python watch/wikimedia_stream.py /path/to/data/wikimedia                       # every edit on every wiki
    uv run python watch/wikimedia_stream.py /path/to/data/wikilinks page-links-change     # links added or removed by edits
    uv run python watch/wikimedia_stream.py /path/to/backfill recentchange 2026-09-29T00:00:00Z 2026-10-07T01:00:00Z
        # history: Wikimedia keeps about a week; files are bucketed by event time and it stops at the end time

Read-only: it only reads https://stream.wikimedia.org/v2/stream/<name>, public feeds published
for researchers. Reconnects automatically and resumes from the last event it saw.
"""

import gzip
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

URL = "https://stream.wikimedia.org/v2/stream/"
CONTACT = os.environ.get("WATCH_CONTACT", "https://github.com/erickfm/commons")  # sites ask bots for a way to reach the operator
HEADERS = {"User-Agent": f"swarm-watch-research/0.1 (read-only research; {CONTACT})", "Accept": "text/event-stream"}
KEEP = ("type", "namespace", "title", "comment", "timestamp", "user", "bot", "minor", "patrolled", "server_name", "wiki", "length", "revision", "log_type", "log_action")


def main(out_dir: str, stream: str = "recentchange", since: str | None = None, until: str | None = None) -> None:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    last_id, hour, fh, n, past = None, None, None, 0, 0
    handles: dict[str, gzip.GzipFile] = {}  # backfill: events from different datacenters arrive interleaved
    while True:
        headers = dict(HEADERS)
        if last_id:
            headers["Last-Event-ID"] = last_id
        url = URL + stream + (f"?since={since}" if since and not last_id else "")
        try:
            with httpx.stream("GET", url, headers=headers, timeout=httpx.Timeout(30, read=120)) as r:
                for line in r.iter_lines():
                    if line.startswith("id:"):
                        last_id = line[3:].strip()
                    if not line.startswith("data:"):
                        continue
                    try:
                        e = json.loads(line[5:])
                    except ValueError:
                        continue
                    if stream == "recentchange":
                        rec = {k: e.get(k) for k in KEEP}
                    else:
                        rec = {k: v for k, v in e.items() if k not in ("meta", "$schema")}
                    rec["dt"] = e.get("meta", {}).get("dt")
                    if since:  # backfill: bucket by event time, stop once events are steadily past `until`
                        if until and (rec["dt"] or "") >= until:
                            past += 1
                            if past >= 5000:
                                for h in handles.values():
                                    h.close()
                                print(f"reached {until}, {n} events", flush=True)
                                return
                            continue
                        past = 0
                        now = (rec["dt"] or "")[:13].replace("-", "").replace("T", "-")
                        if now not in handles:
                            handles[now] = gzip.open(out / f"{now}.jsonl.gz", "at")
                        fh = handles[now]
                    elif (now := datetime.now(timezone.utc).strftime("%Y%m%d-%H")) != hour:
                        if fh:
                            fh.close()
                        hour, fh = now, gzip.open(out / f"{now}.jsonl.gz", "at")
                    fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    n += 1
                    if n % 2000 == 0:
                        for h in handles.values() or [fh]:
                            h.flush()
                    if n % 50000 == 0:
                        print(f"{datetime.now(timezone.utc).isoformat()} {n} events", flush=True)
        except Exception as ex:  # network hiccups: wait and resume from last_id
            print(f"reconnect after error: {ex!r}", flush=True)
            time.sleep(5)


if __name__ == "__main__":
    main(*sys.argv[1:5])
