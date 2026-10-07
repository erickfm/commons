"""Small synchronous pilot to check the prompt before the batch run.

Usage: pilot.py N OUTFILE   (OUTFILE should live outside the repo; it contains raw text)
Appends API usage to cost_log.jsonl.
"""
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import HERE, MODEL, SEED, SYSTEM, candidates, client, load_all_items, parse_label, standard_cost, user_message  # noqa: E402


def main():
    n, outfile = int(sys.argv[1]), sys.argv[2]
    seed = int(sys.argv[3]) if len(sys.argv) > 3 else SEED + 1
    c = candidates(load_all_items()).sample(n=n, random_state=seed)
    cl = client()

    def run(row):
        r = cl.messages.create(model=MODEL, max_tokens=400, system=SYSTEM,
                               messages=[{"role": "user", "content": user_message(row.text)}])
        txt = next((b.text for b in r.content if b.type == "text"), "")
        return row, r.usage.input_tokens, r.usage.output_tokens, txt

    with ThreadPoolExecutor(8) as ex:
        res = list(ex.map(run, [r for r in c.itertuples()]))
    tin = sum(x[1] for x in res); tout = sum(x[2] for x in res)
    with open(outfile, "w") as f:
        for row, _, _, txt in res:
            f.write(json.dumps({"id": row.id, "kind": row.kind, "author_id": row.author_id, "text": row.text[:3000], "raw": txt, "label": parse_label(txt)}) + "\n")
    cost = standard_cost(tin, tout)
    with open(HERE / "cost_log.jsonl", "a") as f:
        f.write(json.dumps({"step": f"pilot n={n} seed={seed}", "mode": "standard", "input_tokens": tin, "output_tokens": tout, "cost_usd": round(cost, 4)}) + "\n")
    print(f"in={tin} out={tout} per-item in={tin/n:.0f} out={tout/n:.0f} cost=${cost:.4f}")
    print("parse failures:", sum(parse_label(x[3]) is None for x in res))


if __name__ == "__main__":
    main()
