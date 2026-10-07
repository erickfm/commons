"""Step 3c: download the confirm-pass results and add them to private_matches.jsonl
as field "label2" (items not sent to the confirm pass get label2 = null)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import HERE, PRIVATE, batch_cost, client, parse_label_v2  # noqa: E402


def main():
    ids = json.loads((HERE / "batch_ids.json").read_text())
    cl = client()
    b = cl.messages.batches.retrieve(ids["confirm"])
    print(b.processing_status, b.request_counts)
    if b.processing_status != "ended":
        return
    out, tin, tout, bad = {}, 0, 0, 0
    for r in cl.messages.batches.results(ids["confirm"]):
        if r.result.type != "succeeded":
            out[r.custom_id] = {"error2": r.result.type}
            continue
        m = r.result.message
        tin += m.usage.input_tokens
        tout += m.usage.output_tokens
        raw = next((x.text for x in m.content if x.type == "text"), "")
        lab = parse_label_v2(raw)
        bad += lab is None
        out[r.custom_id] = {"raw2": raw, "label2": lab}
    rows = [json.loads(l) for l in open(PRIVATE)]
    with open(PRIVATE, "w") as f:
        for d in rows:
            d.update(out.get(d["custom_id"], {"label2": None}))
            f.write(json.dumps(d, ensure_ascii=False) + "\n")
    cost = batch_cost(tin, tout)
    with open(HERE / "cost_log.jsonl", "a") as f:
        f.write(json.dumps({"step": f"confirm batch {ids['confirm']} n={len(out)}", "mode": "batch", "input_tokens": tin, "output_tokens": tout, "cost_usd": round(cost, 4)}) + "\n")
    print(f"confirm results {len(out)}; parse failures {bad}; cost=${cost:.3f}")


if __name__ == "__main__":
    main()
