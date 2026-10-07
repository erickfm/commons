"""Step 3: download batch results and write private_matches.jsonl (NOT for commit).

Each line: one classified item with its raw text and the classifier's label.
Also appends the batch's token usage and cost to cost_log.jsonl.
"""
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import HERE, PRIVATE, batch_cost, client, load_all_items, parse_label  # noqa: E402


def main():
    bid = json.loads((HERE / "batch_ids.json").read_text())["main"]
    cl = client()
    b = cl.messages.batches.retrieve(bid)
    print(b.processing_status, b.request_counts)
    if b.processing_status != "ended":
        return
    man = pd.read_csv(HERE / "sample_manifest.csv")
    allt = load_all_items().set_index("id")
    text = allt["text"]
    rows, tin, tout, bad = {}, 0, 0, 0
    for r in cl.messages.batches.results(bid):
        if r.result.type != "succeeded":
            rows[r.custom_id] = {"error": r.result.type}
            continue
        m = r.result.message
        tin += m.usage.input_tokens
        tout += m.usage.output_tokens
        raw = next((x.text for x in m.content if x.type == "text"), "")
        lab = parse_label(raw)
        bad += lab is None
        rows[r.custom_id] = {"raw": raw, "label": lab}
    with open(PRIVATE, "w") as f:
        for r in man.itertuples():
            d = {"custom_id": r.custom_id, "id": r.id, "kind": r.kind, "author_id": r.author_id,
                 "sample": r.sample, "n_candidate_items": None if pd.isna(r.n_candidate_items) else int(r.n_candidate_items),
                 "truncated": bool(r.truncated), "text": text[r.id], **rows.get(r.custom_id, {"error": "missing"})}
            f.write(json.dumps(d, ensure_ascii=False) + "\n")
    cost = batch_cost(tin, tout)
    with open(HERE / "cost_log.jsonl", "a") as f:
        f.write(json.dumps({"step": f"batch {bid} n={len(man)}", "mode": "batch", "input_tokens": tin, "output_tokens": tout, "cost_usd": round(cost, 4)}) + "\n")
    print(f"written {len(man)} rows; parse failures {bad}; errors {sum('error' in v for v in rows.values())}; in={tin} out={tout} cost=${cost:.3f}")


if __name__ == "__main__":
    main()
