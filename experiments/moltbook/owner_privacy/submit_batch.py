"""Step 2: draw the seeded samples and submit them to the Message Batches API.

Sample A (main): a uniform random sample of agents who mention their human. For each
sampled agent we classify all of its candidate items, or a random 15 if it has more.
Sample B (recall check): a uniform random sample of items that do NOT match the
"my human" phrases, to estimate how much the keyword filter misses.

Writes sample_manifest.csv (ids and sampling info only, no text) and batch_ids.json.
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import HERE, MODEL, SEED, SYSTEM, candidates, client, load_all_items, user_message  # noqa: E402

N_AGENTS = 3000
CAP = 15
N_RECALL = 500


def main():
    dry = "--dry" in sys.argv
    allt = load_all_items()
    c = candidates(allt)
    rng = np.random.default_rng(SEED)

    agents = np.sort(c.author_id.unique())
    sampled = set(rng.choice(agents, size=N_AGENTS, replace=False))
    a = c[c.author_id.isin(sampled)]
    n_per = a.groupby("author_id").size().rename("n_candidate_items")
    parts = []
    for aid, g in a.groupby("author_id", sort=True):
        parts.append(g if len(g) <= CAP else g.sample(n=CAP, random_state=int(rng.integers(1 << 31))))
    A = pd.concat(parts).join(n_per, on="author_id")
    A["sample"] = "A"

    non = allt[~allt["mention"]].drop_duplicates(subset=["author_id", "norm"])
    B = non.sample(n=N_RECALL, random_state=SEED).copy()
    B["n_candidate_items"] = np.nan
    B["sample"] = "B"

    S = pd.concat([A, B], ignore_index=True)
    S["custom_id"] = [f"{s}-{i}" for i, s in enumerate(S["sample"])]
    S["truncated"] = S.text.str.len() > 8000
    print("sample A agents", A.author_id.nunique(), "items", len(A), "| agents over cap", int((n_per > CAP).sum()))
    print("sample B items", len(B), "| truncated texts", int(S.truncated.sum()))
    S[["custom_id", "id", "kind", "author_id", "sample", "n_candidate_items", "truncated"]].to_csv(HERE / "sample_manifest.csv", index=False)
    if dry:
        return

    requests = [
        {
            "custom_id": r.custom_id,
            "params": {
                "model": MODEL,
                "max_tokens": 400,
                "system": SYSTEM,
                "messages": [{"role": "user", "content": user_message(r.text)}],
            },
        }
        for r in S.itertuples()
    ]
    b = client().messages.batches.create(requests=requests)
    print("batch", b.id, b.processing_status)
    (HERE / "batch_ids.json").write_text(json.dumps({"main": b.id, "n_requests": len(requests)}, indent=2))


if __name__ == "__main__":
    main()
