"""Reproduce the retrieval ablation on the 200 development queries from one command.

  venv/bin/python eval/retrieval_dev.py [--top-k 6] [--check-only]

Variants: dense baseline, + task prefixes, + clean text, BM25 alone, all combined.
First verifies that the all-combined variant returns the same ranked IDs as
app.retrieve_context for every query; stops if not. Hit@1/Hit@3/Recall@k/MRR with
Wilson 95% intervals, per query type and overall. DEVELOPMENT set: the held-out set
is evaluated only by retrieval_heldout.py.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from common import DATA, EVAL, frac, longest_shared_run, meta, read_csv, wilson  # noqa: E402
import retrieval_core as R  # noqa: E402


def verify_equivalence(ranker, queries, top_k):
    products, guidelines = R.A.load_data()
    bad = []
    for qtype, q, _ in queries:
        mine = ranker.rank(q, **R.VARIANTS["all_combined"])[:top_k]
        app = [r["source_id"] for r in R.A.retrieve_context(q, products, guidelines, top_k)][:top_k]
        if mine != app:
            bad.append((q, mine, app))
    return bad


def metrics(ranks, top_k):
    n = len(ranks)
    h1 = sum(r == 1 for r in ranks)
    h3 = sum(r is not None and r <= 3 for r in ranks)
    rk = sum(r is not None and r <= top_k for r in ranks)
    return {"n": n, "hit@1": frac(h1, n), "hit@1_ci": wilson(h1, n), "hit@3": frac(h3, n), "hit@3_ci": wilson(h3, n),
            f"recall@{top_k}": frac(rk, n), f"recall@{top_k}_ci": wilson(rk, n),
            "mrr": round(sum(1 / r for r in ranks if r) / n, 3) if n else None}


def product_rank(order, target):
    products = [i for i in order if i.startswith("products:")]
    return products.index(target) + 1 if target in products else None


def write_cases(queries, per_query, path):
    """10 descriptive dev queries BM25 alone gets right at rank 1 and the dense baseline does not."""
    products = {f"products:{r['product_id']}": r for r in read_csv(os.path.join(DATA, "products.csv"))}
    fields = ("product_name", "description", "materials", "features", "target_audience", "available_colours")

    def shared(q, gold):
        best = max(((longest_shared_run(q, products[gold][f]), f) for f in fields), key=lambda x: x[0][0])
        return best[0][0], best[0][1], best[1]

    desc_idx = [i for i, (t, _, _) in enumerate(queries) if t == "descriptive"]
    runs = [shared(queries[i][1], queries[i][2])[0] for i in desc_idx]
    cases = [i for i in desc_idx if per_query["bm25_only"][i] == 1 and per_query["dense_baseline"][i] != 1]
    lines = ["# Descriptive dev queries: BM25 alone rank 1, dense baseline not rank 1", "",
             f"{len(cases)} of 100 descriptive development queries meet this condition; the first 10 in catalogue order are listed.",
             "", "Longest run of consecutive words shared with the gold product's text fields "
             "(name, description, materials, features, audience, colours), matching case-insensitively on word tokens.", ""]
    for n, i in enumerate(cases[:10], 1):
        t, q, g = queries[i]
        length, words, field = shared(q, g)
        row = products[g]
        lines += [f"{n}. **Query:** {q}",
                  f"   - Gold: `{g}` ({row['product_name']}); dense baseline rank: {per_query['dense_baseline'][i]}; BM25-alone rank: 1",
                  f"   - Longest shared run: {length} words, \"{words}\" (field: {field})", ""]
    lines += ["## Overlap of all 100 descriptive development queries with their gold product text", "",
              f"Longest shared run (words): min {min(runs)}, median {sorted(runs)[len(runs) // 2]}, max {max(runs)}; "
              f"{sum(r >= 3 for r in runs)}/100 queries share a run of 3 or more words."]
    open(path, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print(f"{len(cases)} qualifying cases; wrote {path}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--top-k", type=int, default=6)
    ap.add_argument("--check-only", action="store_true", help="only verify equivalence with retrieve_context")
    ap.add_argument("--out", default=os.path.join(EVAL, "results", "retrieval_dev.json"))
    args = ap.parse_args()
    ranker = R.Ranker()
    queries = R.dev_queries()
    bad = verify_equivalence(ranker, queries, args.top_k)
    if bad:
        for q, mine, app in bad[:3]:
            print("MISMATCH", q, mine, app)
        sys.exit(f"all_combined differs from retrieve_context on {len(bad)}/{len(queries)} queries")
    print(f"equivalence OK: all_combined == retrieve_context on {len(queries)}/{len(queries)} queries")
    if args.check_only:
        return
    results, per_query = {}, {}
    for name, flags in R.VARIANTS.items():
        by = {"named": [], "descriptive": []}
        per_query[name] = []
        for qtype, q, target in queries:
            rk = product_rank(ranker.rank(q, **flags), target)
            by[qtype].append(rk)
            per_query[name].append(rk)
        results[name] = {"named": metrics(by["named"], args.top_k), "descriptive": metrics(by["descriptive"], args.top_k),
                         "all": metrics(by["named"] + by["descriptive"], args.top_k)}
        a = results[name]["all"]
        print(f"{name:20s} all: hit@1 {a['hit@1']}  hit@3 {a['hit@3']}  mrr {a['mrr']}")
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump({"_meta": meta(top_k=args.top_k, embed_model=R.A.EMBED_MODEL, queries=len(queries),
                                 note="development set (200 queries: 100 named, 100 descriptive); see REPORT.md on tuning"),
                   "variants": results,
                   "per_query_product_rank": {"queries": [{"type": t, "query": q, "gold": g} for t, q, g in queries],
                                              "ranks": per_query}}, fh, indent=2)
    print("->", args.out)
    write_cases(queries, per_query, os.path.join(os.path.dirname(args.out), "bm25_vs_dense_cases.md"))


if __name__ == "__main__":
    main()
