"""Turn scanner + classifier output + hand labels into the numbers in summary.json.

Run after scan_secrets.py, classify.py (all tasks) and the validation/hand_labels_*.py scripts.
"""
from __future__ import annotations

import sys as _sys
from pathlib import Path as _P
_sys.path.insert(0, str(_P(__file__).resolve().parent))  # -I drops the script dir
_sys.path.insert(0, str(_P(__file__).resolve().parent / "validation"))

import json
import math
import re

from common import CACHE, HERE, pd

RES = CACHE / "llm_results"
FOLLOW = re.compile(r"(?i)(?:/agents/[^\s/`]+/follow|/posts/[^\s/`]+/upvote|/follow\b)")


def wilson(k, n, z=1.96):
    if n == 0:
        return [None, None]
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    r = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return [round((c - r) / d, 3), round((c + r) / d, 3)]


def load(task):
    r = pd.read_json(RES / f"{task}.jsonl", lines=True)
    idx = pd.read_parquet(CACHE / f"{task}_req_index.parquet")
    return idx.merge(r, on="custom_id", how="left")


def counts(rows: pd.DataFrame) -> dict:
    vc = rows.author_id.value_counts()
    return {"rows": int(len(rows)), "posts": int((rows.kind == "post").sum()), "comments": int((rows.kind == "comment").sum()),
            "agents": int(rows.author_id.nunique()), "distinct_texts": int(rows.text.nunique()),
            "top5_agents_share_of_rows": round(vc.head(5).sum() / max(1, len(rows)), 3),
            "max_rows_by_one_agent": int(vc.iloc[0]) if len(vc) else 0}


# ---------------------------------------------------------------- Q1
def q1(corpus):
    s = pd.read_parquet(CACHE / "secrets_rows.parquet")
    idx = pd.read_parquet(CACHE / "secrets_req_index.parquet")
    llm = pd.read_json(RES / "secrets_v2.jsonl", lines=True)
    hand = pd.read_csv(HERE / "validation" / "secrets_hand_labels.csv")
    m = idx.merge(llm, on="custom_id", how="left").merge(hand[["custom_id", "hand_label", "hand_whose"]], on="custom_id")
    m = m.merge(corpus[["id", "text"]], on="id", how="left")
    # agreement, counted once per distinct (secret, author) so a key pasted 45 times counts once
    d = m.drop_duplicates(["hash", "author_id"])
    collapse = {"fake_or_example": "not_real", "not_a_secret": "not_real"}
    agree = {"items_all_rows": int(len(m)), "items_distinct_secret_author": int(len(d)),
             "five_way_agreement_distinct": round((d.label == d.hand_label).mean(), 3),
             "four_way_agreement_distinct (fake and not-a-secret merged)":
                 round((d.label.replace(collapse) == d.hand_label.replace(collapse)).mean(), 3),
             "exposed_real_yes_no_agreement_distinct": round(((d.label == "exposed_real") == (d.hand_label == "exposed_real")).mean(), 3),
             "confusion_distinct (rows=hand, cols=model)": pd.crosstab(d.hand_label, d.label).to_dict("index")}
    fin = m[(m.verdict != "placeholder") & (m.hand_label == "exposed_real")]
    fin = fin.assign(kind=fin.kind)
    by_type = fin.groupby("type").agg(distinct_secrets=("hash", "nunique"), agents=("author_id", "nunique"),
                                      rows=("id", "nunique")).reset_index()
    mb = fin[fin.type == "moltbook_api_key"]
    out = {
        "format_scan_all_hits": s.groupby(["type", "verdict"]).agg(rows=("id", "nunique"), distinct=("hash", "nunique"),
                                                                   agents=("author_id", "nunique")).reset_index().to_dict("records"),
        "likely_real_exposed (format check + hand-read context)": {
            "distinct_secrets": int(fin.hash.nunique()), "agents_posting": int(fin.author_id.nunique()),
            "rows": int(fin.id.nunique()), "posts": int(fin[fin.kind == "post"].id.nunique()),
            "comments": int(fin[fin.kind == "comment"].id.nunique()),
            "by_type": by_type.to_dict("records"),
            "whose_distinct_secrets": fin.drop_duplicates("hash").hand_whose.value_counts().to_dict(),
        },
        "moltbook_api_keys": {"distinct": int(mb.hash.nunique()), "agents_posting": int(mb.author_id.nunique()),
                              "rows": int(mb.id.nunique()),
                              "agents_posting_someone_elses_key": int(mb[mb.hand_whose == "other"].author_id.nunique()),
                              "rows_from_single_heaviest_key": int(mb.groupby("hash").id.nunique().max())},
        "other_context_labels_distinct_secrets": m[m.verdict != "placeholder"].drop_duplicates("hash").hand_label.value_counts().to_dict(),
        "scam_or_bait_wallet_keys": {"distinct": int(m[(m.hand_label == "scam_or_bait")].hash.nunique()),
                                     "agents": int(m[(m.hand_label == "scam_or_bait")].author_id.nunique())},
        "classifier_vs_hand": agree,
        "note": "Hand labels are final for this question: every flagged item was read. The model is reported for comparison only.",
    }
    return out


# ---------------------------------------------------------------- Q2
def q2(corpus):
    from hand_labels_ask import final_table
    st, _ = final_table()
    conf = st[st.final_model & (st.hand == True)]  # noqa: E712
    a1, a2 = load("ask"), load("ask2")
    stage1 = pd.concat([a1, a2]).drop_duplicates("id")
    out = {"pipeline_rows": {"regex_candidates": int(len(a1) + len(a2)),
                             "stage1_model_yes": int((stage1.asks_for_secret == True).sum()),  # noqa: E712
                             "stage2_strict_yes_after_follow_rule": int(st.final_model.sum()),
                             "stage2_unique_texts": int(st[st.final_model].text.nunique()),
                             "hand_confirmed_unique_texts": int(conf.text.nunique())},
           "requests_hand_confirmed": counts(conf),
           "requests_excluding_biggest_spammer": counts(conf[conf.author_id != conf.author_id.value_counts().index[0]]),
           "secret_type_agents": conf.groupby("secret_type").author_id.nunique().to_dict(),
           "tactic_agents": conf.groupby("tactic").author_id.nunique().to_dict()}
    # validation of the model labels against the hand reads
    v1 = pd.read_csv(HERE / "validation" / "ask_validation.csv")
    v2 = pd.read_csv(HERE / "validation" / "ask_validation_2.csv")
    out["validation"] = {
        "stage1_draw_rows": {"n": int(len(v1)), "model_yes_hand_yes": int((v1.asks_for_secret & v1.hand).sum()),
                             "model_yes_hand_no": int((v1.asks_for_secret & ~v1.hand).sum()),
                             "model_no_hand_yes": int((~v1.asks_for_secret & v1.hand).sum()),
                             "model_no_hand_no": int((~v1.asks_for_secret & ~v1.hand).sum())},
        "stage2_draw_unique_texts": {"n": int(len(v2)), "model_yes_hand_yes": int((v2.final & v2.hand).sum()),
                                     "model_yes_hand_no": int((v2.final & ~v2.hand).sum()),
                                     "model_no_hand_yes": int((~v2.final & v2.hand).sum()),
                                     "model_no_hand_no": int((~v2.final & ~v2.hand).sum())},
        "stage2_precision_all_unique_texts_read": [int(conf.text.nunique()), int(st[st.final_model].text.nunique())],
        "extra_stage2_negatives_read": {"n": 40, "true_requests_found": 0},
    }
    # recall: seeded sample outside the first regex filter
    rc = load("ask_recall")
    pools = json.load(open(CACHE / "recall_pools.json"))
    flags = pd.read_parquet(CACHE / "flags.parquet")
    flags["id"] = corpus["id"].values
    rc = rc.merge(flags[["id", "ask2"]], on="id")
    rest = rc[~rc.ask2]
    k = int((rest.asks_for_secret == True).sum())  # noqa: E712
    pool_rest = pools["ask_recall_pool"] - int(flags.ask2.sum())
    ci = wilson(k, len(rest))
    out["recall_check"] = {"sample": int(len(rc)), "sample_rows_caught_by_second_filter": int(rc.ask2.sum()),
                           "sample_positives_caught_by_second_filter": int((rc.ask2 & (rc.asks_for_secret == True)).sum()),  # noqa: E712
                           "sample_positives_left_uncaught": k, "uncaught_pool_rows": pool_rest,
                           "est_missed_rows_95ci": [round(pool_rest * ci[0]), round(pool_rest * ci[1])],
                           "note": "the one uncaught sample positive was a borderline 'join our shared wallet' pitch"}
    # replies
    rv = pd.read_csv(HERE / "validation" / "replies_validation.csv")
    ridx = pd.read_parquet(CACHE / "replies_req_index.parquet").merge(corpus[["id", "author_id"]], on="id")
    rv = rv.merge(ridx[["custom_id", "author_id", "request_id"]], on="custom_id")
    srows = pd.read_parquet(CACHE / "secrets_rows.parquet")
    out["replies"] = {"requests_with_any_reply": int(rv.request_id.nunique()),
                      "requests_total_rows": int(len(conf)),
                      "replies": int(len(rv)), "reply_agents": int(rv.author_id.nunique()),
                      "hand_counts": rv.hand.value_counts().to_dict(),
                      "replies_sharing_a_real_looking_secret": int((rv.hand == "shared_secret").sum()),
                      "replies_with_format_valid_secret_by_scanner": int(ridx.id.isin(set(srows[srows.verdict != "placeholder"].id)).sum()),
                      "model_vs_hand_agreement": round((rv.hand == rv.response).mean(), 3)}
    return out


# ---------------------------------------------------------------- Q3
def q3(corpus):
    from hand_labels_money import RECALL_TRUE, NOT_APPROVED_CONFIRMED, NOT_APPROVED_READ
    m1 = load("money").merge(corpus[["id", "kind", "author_id", "author_name", "text"]], on="id")
    s1 = m1[(m1.owner_money == True) & (m1.fiction == False)]  # noqa: E712
    m2 = load("money_strict")
    pos = m2[(m2.owner_money == True) & (m2.fiction == False)].merge(  # noqa: E712
        corpus[["id", "kind", "author_id", "author_name", "text"]], on="id")
    did = pos[pos["mode"] == "did_it"]

    def assets(df):
        return {k: {"rows": int(df[k].sum()), "agents": int(df[df[k]].author_id.nunique())} for k in ["crypto", "memecoin", "stocks", "fiat"]}

    def approval(df):
        return {k: {"rows": int((df.approval == k).sum()), "agents": int(df[df.approval == k].author_id.nunique())}
                for k in ["approved", "asked_first", "not_approved", "not_mentioned"]}

    amt = pd.to_numeric(did.drop_duplicates("text").amount_usd, errors="coerce").dropna()
    out = {"pipeline": {"regex_candidates_rows": int(len(m1)), "stage1_yes_rows": int(len(s1)),
                        "stage1_yes_agents": int(s1.author_id.nunique()), "stage1_yes_unique_texts": int(s1.text.nunique()),
                        "stage2_yes_rows": int(len(pos)), "stage2_yes_unique_texts": int(pos.text.nunique())},
           "talks_about_handling_owner_money": counts(pos),
           "mode_agents": pos.groupby("mode").author_id.nunique().to_dict(),
           "mode_unique_texts": pos.drop_duplicates("text")["mode"].value_counts().to_dict(),
           "says_it_did_it": counts(did),
           "did_it_assets": assets(did), "did_it_approval": approval(did),
           "all_assets": assets(pos), "all_approval": approval(pos),
           "did_it_amount_usd_unique_texts": {"n": int(len(amt)), "median": float(amt.median()) if len(amt) else None,
                                              "p90": float(amt.quantile(0.9)) if len(amt) else None}}
    # biggest template
    top = pos.text.value_counts()
    out["biggest_repeated_text"] = {"rows": int(top.iloc[0]), "agents": int(pos[pos.text == top.index[0]].author_id.nunique())}
    out["excluding_biggest_repeated_text"] = counts(pos[pos.text != top.index[0]])
    # validation (filled in by validation/hand_labels_money.py outputs)
    vfile = HERE / "validation" / "money_validation_2.csv"
    if vfile.exists():
        v = pd.read_csv(vfile)
        tp = int((v.model & v.hand).sum()); fp = int((v.model & ~v.hand).sum())
        fn = int((~v.model & v.hand).sum()); tn = int((~v.model & ~v.hand).sum())
        prec_ci = wilson(tp, tp + fp)
        out["validation_stage2"] = {"n": int(len(v)), "tp": tp, "fp": fp, "fn": fn, "tn": tn,
                                    "precision": round(tp / max(1, tp + fp), 3), "precision_95ci": prec_ci}
        dv = v[v.model & v.hand]
        out["validation_stage2"]["did_it_agreement_on_true_positives"] = round(((dv.hand_mode == "did_it") == (dv["mode"] == "did_it")).mean(), 3)
        out["validation_stage2"]["approval_agreement_on_true_positives"] = round((dv.hand_approval == dv.approval).mean(), 3)
        p = tp / max(1, tp + fp)
        out["estimated_true_agents"] = {"point": round(pos.author_id.nunique() * p),
                                        "95ci": [round(pos.author_id.nunique() * prec_ci[0]), round(pos.author_id.nunique() * prec_ci[1])]}
        out["estimated_true_agents_did_it"] = {"point": round(did.author_id.nunique() * p),
                                               "95ci": [round(did.author_id.nunique() * prec_ci[0]), round(did.author_id.nunique() * prec_ci[1])]}
    na = pos[pos.approval == "not_approved"]
    conf_texts = set(m2[m2.custom_id.isin(NOT_APPROVED_CONFIRMED)].merge(corpus[["id", "text"]], on="id").text)
    na_conf = pos[pos.text.isin(conf_texts)]
    out["acted_without_approval"] = {"model_rows": int(len(na)), "model_agents": int(na.author_id.nunique()),
                                     "model_unique_texts": int(na.text.nunique()), "unique_texts_hand_read": NOT_APPROVED_READ,
                                     "hand_confirmed_unique_texts": len(NOT_APPROVED_CONFIRMED),
                                     "hand_confirmed_agents": len(set(NOT_APPROVED_CONFIRMED.values())),
                                     "hand_confirmed_rows": int(len(na_conf))}
    v1 = pd.read_csv(HERE / "validation" / "money_validation.csv")
    out["validation_stage1"] = {"n": int(len(v1)), "tp": int((v1.pos & v1.hand).sum()), "fp": int((v1.pos & ~v1.hand).sum()),
                                "fn": int((~v1.pos & v1.hand).sum()), "tn": int((~v1.pos & ~v1.hand).sum())}
    # recall outside the regex filter
    pools = json.load(open(CACHE / "recall_pools.json"))
    k = len(RECALL_TRUE)
    ci = wilson(k, 600)
    out["recall_check"] = {"sample": 600, "hand_confirmed_positives": k, "pool_rows": pools["money_recall_pool"],
                           "est_missed_rows": round(pools["money_recall_pool"] * k / 600),
                           "est_missed_rows_95ci": [round(pools["money_recall_pool"] * ci[0]), round(pools["money_recall_pool"] * ci[1])],
                           "did_it_among_them": sum(v == "did_it" for v in RECALL_TRUE.values())}
    return out


def cost():
    tot = {"input_tokens": 0, "output_tokens": 0, "usd": 0.0}
    for f in RES.glob("*_usage.json"):
        u = json.load(open(f))
        if "input" in u:
            tot["input_tokens"] += u["input"]
            tot["output_tokens"] += u["output"]
        tot["usd"] += u["cost_usd"]
    tot["usd"] = round(tot["usd"], 2)
    return tot


def main():
    corpus = pd.read_parquet(CACHE / "corpus.parquet")
    summary = {"corpus": {"posts": int((corpus.kind == "post").sum()), "comments": int((corpus.kind == "comment").sum()),
                          "agents": int(corpus.author_id.nunique()), "from": str(corpus.created_at.min())[:10],
                          "to": str(corpus.created_at.max())[:10]},
               "classifier_model": "claude-haiku-4-5 (Message Batches API for the large runs)"}
    summary["q1_secrets"] = q1(corpus)
    summary["q2_asking_for_secrets"] = q2(corpus)
    summary["q3_owner_money"] = q3(corpus)
    q1s, q2s, q3s = summary["q1_secrets"], summary["q2_asking_for_secrets"], summary["q3_owner_money"]
    lr = q1s["likely_real_exposed (format check + hand-read context)"]
    summary["headlines"] = {
        "q1_moltbook_keys": f"{q1s['moltbook_api_keys']['agents_posting']} agents posted {q1s['moltbook_api_keys']['distinct']} distinct "
                            f"Moltbook API keys that pass format checks, in {q1s['moltbook_api_keys']['rows']} posts/comments",
        "q1_all_likely_real": f"{lr['distinct_secrets']} distinct likely-real credentials from {lr['agents_posting']} agents "
                              f"in {lr['rows']} posts/comments (format check + every case read by hand)",
        "q2_requests": f"{q2s['requests_hand_confirmed']['agents']} agents asked others for keys/passwords/seed phrases "
                       f"({q2s['requests_hand_confirmed']['distinct_texts']} distinct requests, {q2s['requests_hand_confirmed']['rows']} posts/comments, "
                       f"{q2s['requests_excluding_biggest_spammer']['rows']} without the biggest spammer)",
        "q2_replies": f"{q2s['replies']['replies']} replies to those requests; {q2s['replies']['replies_sharing_a_real_looking_secret']} shared a real-looking secret",
        "q3_owner_money_est_agents": f"about {q3s['estimated_true_agents']['point']} agents (95% CI {q3s['estimated_true_agents']['95ci']}) "
                                     f"talk about handling their human's money; model flagged {q3s['talks_about_handling_owner_money']['agents']}",
        "q3_did_it_est_agents": f"about {q3s['estimated_true_agents_did_it']['point']} agents (95% CI {q3s['estimated_true_agents_did_it']['95ci']}) say they actually did it",
        "q3_without_approval_confirmed": f"{q3s['acted_without_approval']['hand_confirmed_agents']} agents (hand-confirmed) say they moved or spent "
                                         f"their human's money without permission",
    }
    summary["api_cost"] = cost()
    json.dump(summary, open(HERE / "summary.json", "w"), indent=2, default=str)
    print(json.dumps(summary, indent=2, default=str))


if __name__ == "__main__":
    main()
