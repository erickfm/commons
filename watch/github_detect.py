"""Flag groups of GitHub accounts posting near-identical text across many repos (GH Archive hourly files).

    uv run python watch/github_detect.py /path/to/gharchive/*.json.gz [--min-actors 5] [--min-repos 5]

GH Archive (https://www.gharchive.org) publishes every public GitHub event as hourly files. This reads
issue, pull request and comment bodies, strips the parts that change between copies (links, numbers,
names, repo names), and groups identical leftovers. A group with many different accounts across many
repos is either a spam/bot campaign or a fleet of agents; the printout shows samples to tell which.

Note: since 2025 GitHub's public event feed is a sample and pull request events carry no title or
body, so this sees opened issues, comments and reviews only.
"""

import argparse
import gzip
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path

TEXT_EVENTS = {
    "IssuesEvent": ("issue", "body"),
    "PullRequestEvent": ("pull_request", "body"),
    "IssueCommentEvent": ("comment", "body"),
    "PullRequestReviewCommentEvent": ("comment", "body"),
    "PullRequestReviewEvent": ("review", "body"),
    "CommitCommentEvent": ("comment", "body"),
    "DiscussionEvent": ("discussion", "body"),
}
KNOWN_BOTS = re.compile(r"\[bot\]$|^(dependabot|renovate|github-actions|codecov|sonarcloud|netlify|vercel|coderabbitai|copilot)", re.I)
AGENT_MARKS = re.compile(
    r"generated with \[?claude code|co-authored-by: claude|codex|devin|openhands|sweep|cursor agent|copilot coding agent|"
    r"jules|aider|i am an ai|as an ai (agent|assistant)|autonomous agent|this (pr|pull request) was (created|generated|opened) by",
    re.I,
)


def norm(text: str, repo: str) -> str:
    t = text.lower()
    for part in filter(None, re.split(r"[/_.-]", repo.lower())):
        if len(part) > 2:
            t = t.replace(part, " ")
    t = re.sub(r"https?://\S+|@[\w-]+|#\d+|\b[0-9a-f]{7,40}\b|\d+", " ", t)
    t = re.sub(r"[^a-z ]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def main(paths, min_actors, min_repos, min_len):
    groups = defaultdict(lambda: {"actors": set(), "repos": set(), "types": set(), "sample": None, "agentish": 0, "n": 0})
    n = 0
    for p in paths:
        with gzip.open(p, "rt") as f:
            for line in f:
                try:
                    e = json.loads(line)
                except ValueError:
                    continue
                spec = TEXT_EVENTS.get(e.get("type"))
                if not spec:
                    continue
                actor = (e.get("actor") or {}).get("login") or ""
                if KNOWN_BOTS.search(actor):
                    continue
                obj = (e.get("payload") or {}).get(spec[0]) or {}
                if e["type"] == "IssuesEvent" and (e.get("payload") or {}).get("action") != "opened":
                    continue
                body = ((obj.get("title") or "") + "\n" + (obj.get(spec[1]) or "")).strip()
                repo = (e.get("repo") or {}).get("name") or ""
                key = norm(body, repo)
                n += 1
                if len(key) < min_len:
                    continue
                g = groups[hashlib.sha1(key[:400].encode()).hexdigest()]
                g["actors"].add(actor), g["repos"].add(repo), g["types"].add(e["type"])
                g["n"] += 1
                g["agentish"] += bool(AGENT_MARKS.search(body))
                if g["sample"] is None:
                    g["sample"] = (e.get("created_at"), actor, repo, body[:500])
    print(f"read {n:,} text events from {len(paths)} files\n")
    hits = [(k, g) for k, g in groups.items() if len(g["actors"]) >= min_actors and len(g["repos"]) >= min_repos]
    for k, g in sorted(hits, key=lambda x: -len(x[1]["actors"])):
        print(f"[{len(g['actors'])} accounts, {len(g['repos'])} repos, {g['n']} posts, agent-marked {g['agentish']}] {sorted(g['types'])}")
        print(f"    accounts: {sorted(g['actors'])[:12]}")
        print(f"    repos: {sorted(g['repos'])[:6]}")
        print(f"    sample: {g['sample'][0]} {g['sample'][1]} {g['sample'][2]}\n      {g['sample'][3]!r}\n")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="+", type=Path)
    ap.add_argument("--min-actors", type=int, default=5)
    ap.add_argument("--min-repos", type=int, default=5)
    ap.add_argument("--min-len", type=int, default=80)
    a = ap.parse_args()
    main(a.paths, a.min_actors, a.min_repos, a.min_len)
