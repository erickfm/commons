"""Step 5: blind hand review of the classifier.

Draws 50 classifier positives and 50 negatives (seeded), shuffles them, and prints the
texts WITHOUT the classifier's labels so the reviewer judges blind. Writes nothing
with text.

  validation_sample.py STAGE show START END   print a slice of the shuffled 100 items
  validation_sample.py STAGE score            compare the reviewer's labels to the classifier

STAGE is "pass1" (first-pass labels; this set was then used to fix the prompt) or
"final" (both passes; a fresh draw that excludes the pass1 items).
Labels live in validation_labels_<STAGE>.csv: custom_id, my_revealed (0/1), my_sensitive (0/1).
"""
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from analyze import HERE, load_final, load_pass1  # noqa: E402


def draw(stage):
    if stage == "pass1":
        A = load_pass1().query("sample == 'A'")
        pos = A[A.revealed].sample(n=50, random_state=11)
        neg = A[~A.revealed].sample(n=50, random_state=12)
        return pd.concat([pos, neg]).sample(frac=1, random_state=13).reset_index(drop=True)
    used = set(draw("pass1").custom_id)
    A = load_final().query("sample == 'A'")
    A = A[~A.custom_id.isin(used)]
    pos = A[A.revealed].sample(n=50, random_state=21)
    neg = A[~A.revealed].sample(n=50, random_state=22)
    return pd.concat([pos, neg]).sample(frac=1, random_state=23).reset_index(drop=True)


def main():
    stage, cmd = sys.argv[1], sys.argv[2]
    V = draw(stage)
    if cmd == "show":
        s, e = int(sys.argv[3]), int(sys.argv[4])
        for i, r in V.iloc[s:e].iterrows():
            print(f"===== {i} {r.custom_id}")
            print(r.text[:1800].replace("\n", " "))
        return
    my = pd.read_csv(HERE / f"validation_labels_{stage}.csv")
    m = V[["custom_id", "revealed", "sensitive"]].merge(my, on="custom_id")
    assert len(m) == 100, len(m)
    clf, me = m.revealed.astype(bool), m.my_revealed.astype(bool)
    tp, fp = int((clf & me).sum()), int((clf & ~me).sum())
    fn, tn = int((~clf & me).sum()), int((~clf & ~me).sum())
    both = m[clf & me]
    res = {
        "stage": stage, "items": 100, "agreement": round((tp + tn) / 100, 3),
        "classifier_positives_confirmed": f"{tp} of {tp + fp}", "precision": round(tp / (tp + fp), 3),
        "classifier_negatives_confirmed": f"{tn} of {tn + fn}", "negative_predictive_value": round(tn / (tn + fn), 3),
        "sensitive_agreement_on_confirmed_positives": round(float((both.sensitive.astype(bool) == both.my_sensitive.astype(bool)).mean()), 3),
        "confusion": {"tp": tp, "fp": fp, "fn": fn, "tn": tn},
    }
    print(json.dumps(res, indent=2))
    (HERE / f"validation_result_{stage}.json").write_text(json.dumps(res, indent=2))
    if "--diff" in sys.argv:
        for i, r in m.iterrows():
            if bool(r.revealed) != bool(r.my_revealed):
                print("disagree", i, "clf", r.revealed, "me", r.my_revealed)


if __name__ == "__main__":
    main()
