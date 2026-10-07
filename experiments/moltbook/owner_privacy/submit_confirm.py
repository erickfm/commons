"""Step 3b: second, stricter pass ("confirm") on items the first pass flagged.

Re-classifies every first-pass item that was flagged as revealing something beyond a
first name, or as sharing private messages, using SYSTEM_V2 from common.py. Writes
batch id to batch_ids.json under "confirm".
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from analyze import load_pass1  # noqa: E402
from common import HERE, MODEL, SYSTEM_V2, client, user_message  # noqa: E402


def main():
    df = load_pass1()
    todo = df[df.revealed | df.comms]
    print("items to confirm:", len(todo), "| by sample:", todo["sample"].value_counts().to_dict())
    if "--dry" in sys.argv:
        return
    reqs = [{"custom_id": r.custom_id, "params": {"model": MODEL, "max_tokens": 600, "system": SYSTEM_V2,
             "messages": [{"role": "user", "content": user_message(r.text)}]}} for r in todo.itertuples()]
    b = client().messages.batches.create(requests=reqs)
    ids = json.loads((HERE / "batch_ids.json").read_text())
    ids["confirm"] = b.id
    ids["n_confirm"] = len(reqs)
    (HERE / "batch_ids.json").write_text(json.dumps(ids, indent=2))
    print("batch", b.id)


if __name__ == "__main__":
    main()
