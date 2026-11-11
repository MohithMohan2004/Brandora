"""Analysis: reads eval/runs/*.jsonl, completed label sheets, label_key.csv and the review log.

  venv/bin/python eval/analyze.py [--subset 30] [--labels-dir eval/labels]

Writes CSV + LaTeX table bodies (rows only: paste inside your own tabular) to eval/results/.
Every percentage is printed with its denominator, e.g. 9/30 = 30.0%.

Metrics
  GVR              share of outputs violating >=1 mandatory rule (lower better).
                   Human GVR uses the consensus labels; checker GVR is automatic.
  GP               supported claims / all claims over all outputs of a config (higher better).
  Price exactness  share of `price` briefs whose output shows the exact catalogue INR price
                   (automatic: any currency amount equal to the catalogue price, none different).
  Retrieval        Hit@1/Hit@3/Recall@6/MRR for the gold product over the runs' retrieved_ids
                   (Wilson 95% CI); this is retrieval on benchmark briefs, not the held-out test.
  Agreement        Cohen's kappa between annotators A and B (rule labels: per output x rule
                   binary decisions; claim labels: per claim Y/N) + number of disagreements.
  NED              from summarize_reviews.py.
  Latency          mean, median, p95 per stage (t_retrieval, t_llm, t_fix).
Consensus: an output's rule set is the rules both annotators marked (strict) when no
adjudicated file eval/labels/adjudicated_rules.csv (output_id, rules_violated) exists; if it
exists it is used instead. Claims use eval/labels/adjudicated_claims.csv likewise, else
agreement-only rows (disagreements are counted unsupported-neutral: excluded from GP and listed).
"""
import argparse
import csv
import json
import os
import statistics
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(__file__))
import checker  # noqa: E402
from common import DATA, EVAL, frac, load_briefs, meta, read_csv, wilson, write_csv  # noqa: E402
from summarize_reviews import summarize  # noqa: E402

CONFIGS = ["B0", "B1", "B2", "B3"]
RES = os.path.join(EVAL, "results")


def load_runs(runs_dir):
    runs = {}
    for c in CONFIGS:
        p = os.path.join(runs_dir, f"{c}.jsonl")
        if not os.path.exists(p):
            continue
        rows = {}
        with open(p, encoding="utf-8") as fh:
            for line in fh:
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not r.get("error"):
                    rows[r["brief_id"]] = r
        runs[c] = rows
    return runs


def cohen_kappa(a, b):
    n = len(a)
    if n == 0:
        return None
    po = sum(x == y for x, y in zip(a, b)) / n
    cats = set(a) | set(b)
    pe = sum((a.count(c) / n) * (b.count(c) / n) for c in cats)
    return None if pe == 1 else round((po - pe) / (1 - pe), 3)


def split_rules(s):
    """Rule IDs from a label cell; 'none' (or empty) means no violation."""
    return {x.strip().upper() for x in str(s or "").replace(",", ";").split(";")
            if x.strip() and x.strip().lower() != "none"}


def filled(rows, col):
    return rows and all(str(r.get(col, "")).strip() != "" for r in rows) if col == "supported (Y/N)" else bool(rows)


def percentile(v, q):
    v = sorted(v)
    return v[min(len(v) - 1, int(round(q * (len(v) - 1))))] if v else None


def latex_row(cells):
    return " & ".join(str(c).replace("%", r"\%").replace("_", r"\_") for c in cells) + r" \\"


def write_tex(path, rows):
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(latex_row(r) for r in rows) + "\n")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--subset", type=int)
    ap.add_argument("--runs-dir", default=os.path.join(EVAL, "runs"))
    ap.add_argument("--labels-dir", default=EVAL, help="folder with the label_*.csv, claims_*.csv, label_key.csv (default eval/)")
    ap.add_argument("--review-log", default=os.path.join(os.path.dirname(EVAL), "backend", "review_log.jsonl"))
    args = ap.parse_args()
    os.makedirs(RES, exist_ok=True)

    briefs = {b["brief_id"]: b for b in load_briefs(args.subset)}
    products = {r["product_id"]: r for r in read_csv(os.path.join(DATA, "products.csv"))}
    runs = load_runs(args.runs_dir)
    if not runs:
        sys.exit("no run files found; run eval/run_benchmark.py first")
    summary = {"_meta": meta(subset=args.subset)}

    # ---- retrieval on the benchmark briefs (B1/B2 share retrieval; B0 has none)
    ret_rows = []
    for c in ("B1", "B2", "B3"):
        rows = [r for r in runs.get(c, {}).values() if r["brief_id"] in briefs]
        ranks = []
        for r in rows:
            gold = f"products:{briefs[r['brief_id']]['gold_product_id']}"
            ids = [i for i in r["retrieved_ids"] if i.startswith("products:")]
            ranks.append(ids.index(gold) + 1 if gold in ids else None)
        n = len(ranks)
        if not n:
            continue
        h1, h3, r6 = (sum(x == 1 for x in ranks), sum(x is not None and x <= 3 for x in ranks),
                      sum(x is not None for x in ranks))
        ret_rows.append({"config": c, "n": n, "hit@1": frac(h1, n), "hit@1_ci": wilson(h1, n),
                         "hit@3": frac(h3, n), "recall@6": frac(r6, n),
                         "mrr": round(sum(1 / x for x in ranks if x) / n, 3)})
    if ret_rows:
        write_csv(os.path.join(RES, "retrieval_benchmark.csv"), ret_rows, list(ret_rows[0]))
        write_tex(os.path.join(RES, "retrieval_benchmark.tex"),
                  [[r["config"], r["hit@1"], r["hit@3"], r["recall@6"], r["mrr"]] for r in ret_rows])
    summary["retrieval_benchmark"] = ret_rows

    # ---- automatic metrics: checker GVR, price exactness, fix_copy_length
    auto_rows = []
    for c, rows in runs.items():
        rs = [r for r in rows.values() if r["brief_id"] in briefs]
        n = len(rs)
        viol = sum(bool(r["checker_violations"]) for r in rs)
        price = [r for r in rs if r["brief_type"] == "price"]
        exact = 0
        for r in price:
            amounts = checker.parse_amounts(" ".join([r["parsed_headline"], r["parsed_copy"], r["parsed_cta"]]))
            want = float(str(products[r["product_id"]]["price_inr"]).replace(",", ""))
            if amounts and all(cur in ("₹", "rs", "rs.", "inr", "rupee", "rupees") and abs(v - want) < 1e-6
                               for _, v, cur in amounts):
                exact += 1
        auto_rows.append({"config": c, "outputs": n, "checker_GVR": frac(viol, n), "checker_GVR_ci": wilson(viol, n),
                          "price_exact": frac(exact, len(price)), "price_exact_ci": wilson(exact, len(price)),
                          "fix_copy_length_fired": frac(sum(bool(r["fix_fired"]) for r in rs), n),
                          "mean_regen_rounds": round(statistics.mean([r["regen_rounds"] for r in rs]), 2) if rs else None})
    write_csv(os.path.join(RES, "automatic_metrics.csv"), auto_rows, list(auto_rows[0]))
    write_tex(os.path.join(RES, "automatic_metrics.tex"),
              [[r["config"], r["checker_GVR"], r["price_exact"]] for r in auto_rows])
    summary["automatic"] = auto_rows

    # ---- human labels
    key = {r["output_id"]: r for r in read_csv(os.path.join(args.labels_dir, "label_key.csv"))} \
        if os.path.exists(os.path.join(args.labels_dir, "label_key.csv")) else {}
    sheets = {w: read_csv(os.path.join(args.labels_dir, f"label_annotator_{w}.csv"))
              for w in "AB" if os.path.exists(os.path.join(args.labels_dir, f"label_annotator_{w}.csv"))}
    # a sheet counts as completed only if every row has an entry in rules_violated ("none" = no violation)
    labelled = {w: s for w, s in sheets.items() if s and all(str(r.get("rules_violated", "")).strip() for r in s)}
    cannot = []
    for w, sh in sheets.items():
        done = sum(1 for r in sh if str(r.get("rules_violated", "")).strip())
        print(f"label_annotator_{w}.csv: {done}/{len(sh)} rows filled")
    human_rows, agreement = [], {}
    if len(sheets) == 2 and len(labelled) == 2 and key:
        lab = {w: {r["output_id"]: split_rules(r["rules_violated"]) for r in s} for w, s in sheets.items()}
        ids = sorted(set(lab["A"]) & set(lab["B"]))
        rule_ids = sorted(checker.guideline_ids().values())
        a_bin, b_bin = [], []
        for i in ids:
            for rid in rule_ids:
                a_bin.append(int(rid in lab["A"][i]))
                b_bin.append(int(rid in lab["B"][i]))
        dis_out = [i for i in ids if lab["A"][i] != lab["B"][i]]
        agreement["rules"] = {"kappa": cohen_kappa(a_bin, b_bin), "decisions": len(a_bin),
                              "binary_disagreements": sum(x != y for x, y in zip(a_bin, b_bin)),
                              "outputs_with_disagreement": frac(len(dis_out), len(ids))}
        adj_path = os.path.join(args.labels_dir, "adjudicated_rules.csv")
        adj = {r["output_id"]: split_rules(r["rules_violated"]) for r in read_csv(adj_path)} if os.path.exists(adj_path) else {}
        consensus = {i: adj.get(i, lab["A"][i] & lab["B"][i]) for i in ids}
        agreement["rules"]["consensus"] = "adjudicated file" if adj else "intersection of A and B (strict)"
        by_cfg = defaultdict(list)
        for i in ids:
            by_cfg[key[i]["config"]].append(i)
        for c in CONFIGS:
            if c not in by_cfg:
                continue
            n = len(by_cfg[c])
            v = sum(bool(consensus[i]) for i in by_cfg[c])
            human_rows.append({"config": c, "outputs": n, "human_GVR": frac(v, n), "human_GVR_ci": wilson(v, n)})
        # checker vs human, per output and rule
        runs_by_key = {}
        for i in ids:
            k = key[i]
            runs_by_key[i] = runs.get(k["config"], {}).get(k["brief_id"])
        side = []
        for i in ids:
            r = runs_by_key.get(i)
            side.append({"output_id": i, "config": key[i]["config"], "brief_id": key[i]["brief_id"],
                         "checker_rules": ";".join(sorted({v["rule_id"] for v in r["checker_violations"]})) if r else "",
                         "checker_matches": " | ".join(f"{v['check']}: {v['matched_text']}" for v in r["checker_violations"]) if r else "",
                         "human_A": ";".join(sorted(lab["A"][i])), "human_B": ";".join(sorted(lab["B"][i])),
                         "human_consensus": ";".join(sorted(consensus[i]))})
        write_csv(os.path.join(RES, "checker_beside_human.csv"), side,
                  ["output_id", "config", "brief_id", "checker_rules", "checker_matches", "human_A", "human_B", "human_consensus"])
        tp = fp = fn = tn = 0
        for i in ids:
            r = runs_by_key.get(i)
            if not r:
                continue
            auto = set(v["rule_id"] for v in r["checker_violations"])
            for rid in rule_ids:
                a, h = rid in auto, rid in consensus[i]
                tp += a and h
                fp += a and not h
                fn += (not a) and h
                tn += (not a) and (not h)
        write_csv(os.path.join(RES, "checker_vs_human.csv"),
                  [{"TP": tp, "FP": fp, "FN": fn, "TN": tn,
                    "precision": frac(tp, tp + fp), "recall": frac(tp, tp + fn)}], ["TP", "FP", "FN", "TN", "precision", "recall"])
        summary["checker_vs_human"] = {"TP": tp, "FP": fp, "FN": fn, "TN": tn, "precision": frac(tp, tp + fp),
                                       "recall": frac(tp, tp + fn), "unit": "output x rule decisions"}
        write_csv(os.path.join(RES, "disagreements_rules.csv"),
                  [{"output_id": i, "config": key[i]["config"], "A": ";".join(sorted(lab["A"][i])), "B": ";".join(sorted(lab["B"][i]))}
                   for i in dis_out], ["output_id", "config", "A", "B"])
    else:
        why = ("label sheets are missing" if len(sheets) < 2 else
               "not every row of both sheets has a rules_violated entry (write 'none' when no rule is violated)")
        cannot += [("human GVR (share of outputs breaking a rule per human labels)", why),
                   ("Cohen's kappa for rule labels", why), ("checker precision/recall against human labels", why),
                   ("checker flags beside human labels", why)]

    cl = {w: read_csv(os.path.join(args.labels_dir, f"claims_{w}.csv")) for w in "AB"
          if os.path.exists(os.path.join(args.labels_dir, f"claims_{w}.csv"))}
    if len(cl) == 2 and key and all(all(str(r["supported (Y/N)"]).strip() for r in rows) and rows for rows in cl.values()):
        a = {(r["output_id"], r["claim_no"]): r["supported (Y/N)"].strip().upper()[:1] for r in cl["A"]}
        b = {(r["output_id"], r["claim_no"]): r["supported (Y/N)"].strip().upper()[:1] for r in cl["B"]}
        ks = sorted(set(a) & set(b))
        agreement["claims"] = {"kappa": cohen_kappa([a[k] for k in ks], [b[k] for k in ks]), "claims": len(ks),
                               "disagreements": sum(a[k] != b[k] for k in ks)}
        adj_path = os.path.join(args.labels_dir, "adjudicated_claims.csv")
        adj = {(r["output_id"], r["claim_no"]): r["supported (Y/N)"].strip().upper()[:1] for r in read_csv(adj_path)} if os.path.exists(adj_path) else {}
        gp_rows = []
        for c in CONFIGS:
            sup = tot = unresolved = 0
            for k in ks:
                if key[k[0]]["config"] != c:
                    continue
                v = adj.get(k, a[k] if a[k] == b[k] else None)
                if v is None:
                    unresolved += 1
                    continue
                tot += 1
                sup += v == "Y"
            if tot or unresolved:
                gp_rows.append({"config": c, "GP": frac(sup, tot), "GP_ci": wilson(sup, tot), "unresolved_disagreements": unresolved})
        write_csv(os.path.join(RES, "gp.csv"), gp_rows, ["config", "GP", "GP_ci", "unresolved_disagreements"])
        for r in human_rows:
            for g in gp_rows:
                if g["config"] == r["config"]:
                    r["GP"] = g["GP"]
        summary["gp"] = gp_rows
    else:
        cannot += [("GP (supported claims / all claims)", "claims_A/B.csv are missing or not fully filled"),
                   ("Cohen's kappa for claim labels", "claims_A/B.csv are missing or not fully filled")]
    if human_rows:
        fields = sorted({k for r in human_rows for k in r}, key=lambda k: ["config", "outputs", "human_GVR", "human_GVR_ci", "GP"].index(k) if k in ["config", "outputs", "human_GVR", "human_GVR_ci", "GP"] else 9)
        write_csv(os.path.join(RES, "human_metrics.csv"), human_rows, fields)
        write_tex(os.path.join(RES, "human_metrics.tex"), [[r["config"], r["human_GVR"], r.get("GP", "n/a")] for r in human_rows])
    summary["human"] = human_rows
    summary["agreement"] = agreement

    # ---- image labels (garbled text)
    il = {w: read_csv(os.path.join(args.labels_dir, f"image_label_{w}.csv")) for w in "AB"
          if os.path.exists(os.path.join(args.labels_dir, f"image_label_{w}.csv"))}
    ikey_p = os.path.join(args.labels_dir, "image_key.csv")
    col = "garbled_text_visible (Y/N)"
    if len(il) == 2 and os.path.exists(ikey_p) and all(rows and all(str(r[col]).strip() for r in rows) for rows in il.values()):
        ikey = {r["image_id"]: r for r in read_csv(ikey_p)}
        a = {r["image_id"]: r[col].strip().upper()[:1] for r in il["A"]}
        b = {r["image_id"]: r[col].strip().upper()[:1] for r in il["B"]}
        ids_ = sorted(set(a) & set(b))
        rows_ = []
        for pipe in ("text", "textfree"):
            sel = [i for i in ids_ if ikey[i]["pipeline"] == pipe]
            both_y = sum(a[i] == "Y" and b[i] == "Y" for i in sel)
            any_y = sum(a[i] == "Y" or b[i] == "Y" for i in sel)
            rows_.append({"pipeline": pipe, "images": len(sel), "garbled_both_annotators": frac(both_y, len(sel)),
                          "garbled_either_annotator": frac(any_y, len(sel)), "either_ci": wilson(any_y, len(sel))})
        write_csv(os.path.join(RES, "image_garbled.csv"), rows_, list(rows_[0]))
        agreement["images"] = {"kappa": cohen_kappa([a[i] for i in ids_], [b[i] for i in ids_]),
                               "disagreements": sum(a[i] != b[i] for i in ids_), "images": len(ids_)}
        summary["image_garbled"] = rows_
    else:
        cannot.append(("garbled-text rates per image pipeline and image kappa", "image_label_A/B.csv missing or not filled"))

    # ---- reviews and latency
    summary["reviews"] = summarize([args.review_log])
    lat = []
    for c, rows in runs.items():
        for stage in ("t_retrieval", "t_llm", "t_fix"):
            v = [r[stage] for r in rows.values() if r["brief_id"] in briefs and isinstance(r.get(stage), (int, float))]
            if v:
                lat.append({"source": c, "stage": stage, "n": len(v), "mean_s": round(statistics.mean(v), 3),
                            "median_s": round(statistics.median(v), 3), "p95_s": round(percentile(v, 0.95), 3)})
    write_csv(os.path.join(RES, "latency_benchmark.csv"), lat, ["source", "stage", "n", "mean_s", "median_s", "p95_s"])
    summary["latency"] = lat
    json.dump(summary, open(os.path.join(RES, "analysis_summary.json"), "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    print(json.dumps({k: v for k, v in summary.items() if k in ("automatic", "agreement", "retrieval_benchmark")}, indent=1, ensure_ascii=False))
    summary["cannot_compute"] = [{"metric": m, "reason": r} for m, r in cannot]
    json.dump(summary, open(os.path.join(RES, "analysis_summary.json"), "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    print("\nChecker-based rates (automatic, NOT human labels) are in automatic_metrics.csv; human-labelled rates are in human_metrics.csv.")
    if cannot:
        print("Cannot be computed yet:")
        for m, r in cannot:
            print(f"  - {m}: {r}")
    print("-> eval/results/")


if __name__ == "__main__":
    main()
