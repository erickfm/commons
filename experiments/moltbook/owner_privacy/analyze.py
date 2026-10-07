"""Step 4: turn the labels in private_matches.jsonl into the headline numbers.

Writes summary.json (aggregate numbers only, no text, no ids).

Two classifier passes. Pass 1 (broad screen, SYSTEM in common.py) runs on every sampled
item. Pass 2 (strict confirm, SYSTEM_V2) re-checks every item pass 1 flagged.

Definitions (applied to each classified item, final = both passes):
  revealed   = pass 1 flagged it AND pass 2 lists at least one counted personal fact
               about the agent's own human (beyond a first name), it is not clearly
               fiction/role-play, and it is not part of the one known spam campaign.
  sensitive  = revealed and severity == "sensitive".
  first_name_only = the only disclosure is the human's first name (reported separately).

Spam campaign rule: one agent posted ~3,400 near-identical comments promoting its
"master's" plan to become a "Constructor", with crypto wallet addresses. The classifier
tends to call these a disclosure. They are a mass-produced pitch, not a private detail,
so items containing both "Constructor" and "master" are set to not-revealed.
"""
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import HERE, PRIVATE  # noqa: E402

CATS = ["health", "money", "relationships", "location", "work", "identity", "schedule", "legal", "other_sensitive"]
RNG = np.random.default_rng(7)


def wilson(k, n, z=1.96):
    if n == 0:
        return (float("nan"),) * 2
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return c - h, c + h


def load_pass1():
    rows = [json.loads(l) for l in open(PRIVATE)]
    df = pd.DataFrame(rows)
    ok = df["label"].notna()
    lab = pd.json_normalize(df.loc[ok, "label"]).set_index(df.index[ok])
    df = df.join(lab)
    df["parsed"] = ok
    for col in ["reveals", "fiction_or_roleplay", "promotional", "shares_private_comms", "mentions_own_human"]:
        df[col] = df[col].fillna(False).astype(bool)
    df["categories"] = df["categories"].apply(lambda x: x if isinstance(x, list) else [])
    df["constructor_spam"] = df.text.str.contains("Constructor") & df.text.str.contains("master", case=False)
    real = [c for c in CATS]
    df["cats_real"] = df["categories"].apply(lambda cs: [c for c in cs if c in real])
    base = df.reveals & ~df.fiction_or_roleplay & ~df.constructor_spam
    df["revealed"] = base & (df.cats_real.str.len() > 0)
    df["first_name_only"] = base & (df.cats_real.str.len() == 0) & df.categories.apply(lambda cs: "first_name" in cs)
    df["sensitive"] = df.revealed & (df.severity == "sensitive")
    df["revealed_nonpromo"] = df.revealed & ~df.promotional
    df["comms"] = df.shares_private_comms & ~df.fiction_or_roleplay & ~df.constructor_spam
    for c in CATS:
        df[f"cat_{c}"] = df.revealed & df.cats_real.apply(lambda cs, c=c: c in cs)
    return df


def load_final():
    df = load_pass1()
    p1 = ["revealed", "sensitive", "comms", "first_name_only"]
    for c in p1:
        df[f"p1_{c}"] = df[c]
    screened = df.p1_revealed | df.p1_comms
    l2 = df["label2"] if "label2" in df else pd.Series([None] * len(df))
    ok = l2.notna()
    get = lambda k, default: l2.apply(lambda d: d.get(k, default) if isinstance(d, dict) else default)
    fic2 = get("fiction_or_roleplay", False).astype(bool)
    keep = screened & ok & ~fic2 & ~df.constructor_spam
    df["revealed"] = keep & get("reveals", False).astype(bool)
    df["sensitive"] = df.revealed & (get("severity", "none") == "sensitive")
    df["promotional"] = get("promotional", False).astype(bool)
    df["revealed_nonpromo"] = df.revealed & ~df.promotional
    df["comms"] = keep & get("shares_private_comms", False).astype(bool)
    df["shares_private_comms"] = df["comms"]
    df["first_name_only"] = df.p1_first_name_only | (keep & ~df.revealed & get("first_name", False).astype(bool))
    df["cats_real"] = get("categories", []).apply(lambda cs: [c for c in cs if c in CATS])
    df["severity"] = get("severity", "none")
    for c in CATS:
        df[f"cat_{c}"] = df.revealed & df.cats_real.apply(lambda cs, c=c: c in cs)
    return df


def agent_table(A):
    flags = ["revealed", "sensitive", "revealed_nonpromo", "first_name_only", "comms", "fiction_or_roleplay"] + [f"cat_{c}" for c in CATS]
    g = A.groupby("author_id")
    t = g[flags].any()
    t["k"] = g.size()
    t["n"] = g["n_candidate_items"].first()
    t["pos_items"] = g["revealed"].sum()
    return t


def ratio_item_rate(t, col_items, B=2000):
    """Population item-level rate: sum_a n_a * (pos_a / k_a) / sum_a n_a, bootstrap over agents."""
    est = lambda tt: (tt.n * tt[col_items] / tt.k).sum() / tt.n.sum()
    point = est(t)
    idx = np.arange(len(t))
    boots = [est(t.iloc[RNG.choice(idx, size=len(idx), replace=True)]) for _ in range(B)]
    return point, float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))


def main():
    final = load_final()
    out = stats(final)
    p1 = stats(load_pass1())
    out["first_pass_only_for_comparison"] = {"agent_level": p1["agent_level"], "item_level_revealed": p1["item_level"]["revealed"]}
    costs = [json.loads(l) for l in open(HERE / "cost_log.jsonl")]
    out["api_cost_usd"] = round(sum(c["cost_usd"] for c in costs), 3)
    out["api_cost_breakdown"] = costs
    (HERE / "summary.json").write_text(json.dumps(out, indent=2))
    print(json.dumps({k: v for k, v in out.items() if k not in ("api_cost_breakdown", "agent_level_by_category")}, indent=1))


def stats(df):
    counts = json.loads((HERE / "counts.json").read_text())
    N_all, N_mention = counts["agents_total"], counts["agents_mentioning_human"]
    A = df[df["sample"] == "A"]
    Bs = df[df["sample"] == "B"]
    t = agent_table(A)
    n = len(t)
    fpc = math.sqrt((N_mention - n) / (N_mention - 1))

    def agent_stat(col):
        k = int(t[col].sum())
        p = k / n
        lo, hi = wilson(k, n)
        # finite-population correction narrows the interval around p
        lo, hi = p - (p - lo) * fpc, p + (hi - p) * fpc
        return {
            "sampled_agents_positive": k, "sampled_agents": n,
            "share_of_mentioning_agents": round(p, 4), "ci95": [round(lo, 4), round(hi, 4)],
            "est_agents": round(p * N_mention), "est_agents_ci95": [round(lo * N_mention), round(hi * N_mention)],
            "share_of_all_agents": round(p * N_mention / N_all, 4),
            "share_of_all_agents_ci95": [round(lo * N_mention / N_all, 4), round(hi * N_mention / N_all, 4)],
        }

    out = {
        "corpus": counts,
        "sample": {
            "agents_sampled": n, "agents_mentioning_human_population": N_mention,
            "items_classified_main": int(len(A)), "items_classified_recall_check": int(len(Bs)),
            "agents_over_cap_15": int((t.n > t.k).sum()), "parse_failures": int((~df.parsed).sum()),
            "errors": int(df.get("error", pd.Series(dtype=object)).notna().sum()) if "error" in df else 0,
            "truncated_texts": int(df.truncated.sum()),
            "items_constructor_spam_in_sample": int(A.constructor_spam.sum()),
        },
        "agent_level": {c: agent_stat(c) for c in ["revealed", "sensitive", "revealed_nonpromo", "first_name_only", "comms"]},
        "agent_level_by_category": {c: agent_stat(f"cat_{c}") for c in CATS},
    }
    # Item level
    t2 = A.groupby("author_id").agg(k=("revealed", "size"), n=("n_candidate_items", "first"),
                                     revealed=("revealed", "sum"), sensitive=("sensitive", "sum"), comms=("comms", "sum"))
    il = {}
    for col in ["revealed", "sensitive", "comms"]:
        p, lo, hi = ratio_item_rate(t2, col)
        il[col] = {"share_of_candidate_items": round(p, 4), "ci95": [round(lo, 4), round(hi, 4)],
                   "est_items": round(p * counts["candidate_items_dedup"]),
                   "share_of_all_items": round(p * counts["candidate_items_dedup"] / counts["items_total"], 5)}
    il["unweighted_share_of_classified_items"] = round(float(A.revealed.mean()), 4)
    # posts vs comments, unweighted within sample
    il["by_kind_unweighted"] = {k: {"items": int(len(g)), "revealed": int(g.revealed.sum()), "share": round(float(g.revealed.mean()), 4)}
                                for k, g in A.groupby("kind")}
    out["item_level"] = il
    # Severity mix and flags among revealing items
    R = A[A.revealed]
    out["among_revealing_items"] = {
        "items": int(len(R)),
        "sensitive": int(R.sensitive.sum()), "promotional": int(R.promotional.sum()),
        "with_private_comms": int(R.shares_private_comms.sum()),
        "category_counts": {c: int(R[f"cat_{c}"].sum()) for c in CATS},
    }
    out["other_flags_in_sample"] = {
        "items_fiction_or_roleplay": int(A.fiction_or_roleplay.sum()),
        "items_classifier_says_not_about_own_human": int((~A.mentions_own_human).sum()),
    }
    # Heavy posters
    pos_agents = t[t.revealed]
    out["heavy_posters"] = {
        "sampled_agents_with_10plus_candidate_items": int((t.n >= 10).sum()),
        "of_which_revealed": int(t[(t.n >= 10)].revealed.sum()),
        "share_revealed_among_1_item_agents": round(float(t[t.n == 1].revealed.mean()), 4),
        "share_revealed_among_2_to_9_item_agents": round(float(t[(t.n >= 2) & (t.n < 10)].revealed.mean()), 4),
        "share_revealed_among_10plus_item_agents": round(float(t[t.n >= 10].revealed.mean()), 4),
        "revealing_items_from_top_1pct_of_sampled_agents": round(float(
            t.sort_values("n", ascending=False).head(max(1, n // 100)).pos_items.sum() / max(1, t.pos_items.sum())), 4),
        "max_revealing_items_one_sampled_agent": int(t.pos_items.max()),
    }
    # Recall check
    nonmention_items = counts["items_total"] - counts["items_mentioning_human_raw"]
    kb = int(Bs.revealed.sum())
    lo, hi = wilson(kb, len(Bs))
    out["recall_check_non_matching_items"] = {
        "items_checked": int(len(Bs)), "revealed": kb, "share": round(kb / max(1, len(Bs)), 4),
        "ci95": [round(lo, 4), round(hi, 4)], "non_matching_items_in_corpus_approx": nonmention_items,
    }
    return out


if __name__ == "__main__":
    main()
