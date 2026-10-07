"""Step 1: count posts/comments where an agent talks about its own human.

Prints corpus-level counts and writes counts.json (numbers only, no text).
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import HERE, candidates, load_all_items  # noqa: E402


def main():
    allt = load_all_items()
    c = candidates(allt)
    per = c.groupby("author_id").size().sort_values(ascending=False)
    out = {
        "items_total": int(len(allt)),
        "posts_total": int((allt.kind == "post").sum()),
        "comments_total": int((allt.kind == "comment").sum()),
        "agents_total": int(allt.author_id.nunique()),
        "items_mentioning_human_raw": int(allt.mention.sum()),
        "candidate_items_dedup": int(len(c)),
        "candidate_posts": int((c.kind == "post").sum()),
        "candidate_comments": int((c.kind == "comment").sum()),
        "agents_mentioning_human": int(c.author_id.nunique()),
        "candidate_items_per_agent_median": float(per.median()),
        "candidate_items_per_agent_max": int(per.max()),
        "top10_agents_share_of_candidate_items": round(float(per.head(10).sum() / len(c)), 4),
    }
    print(json.dumps(out, indent=2))
    (HERE / "counts.json").write_text(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
