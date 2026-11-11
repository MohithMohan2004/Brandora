"""One-shot evaluation of the CURRENT retrieval setup on the held-out queries.

  venv/bin/python eval/retrieval_heldout.py [--top-k 6]

Input eval/heldout_queries.csv (query, gold_product_id, query_type = named|descriptive),
written by a human before any tuning. Refuses to run if the file is missing, empty or
malformed. Warns if the file is newer than the retrieval code. Writes
eval/results/retrieval_heldout.json with a hash of the retrieval settings, and refuses
a second run unless --again is passed (the count is recorded). Never tune against this file.
"""
import argparse
import hashlib
import inspect
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
from common import BACKEND, EVAL, ROOT, DATA, file_sha, frac, import_app, meta, read_csv, wilson  # noqa: E402

A = import_app()
QUERIES = os.path.join(EVAL, "heldout_queries.csv")
OUT = os.path.join(EVAL, "results", "retrieval_heldout.json")


def settings_hash(top_k):
    """Hash of everything that defines the retrieval setup (code, models, constants, data)."""
    parts = {
        "code": [inspect.getsource(f) for f in (A.retrieve_context, A.bm25_scores, A.search_text, A.row_to_text, A._tokens)],
        "search_fields": list(A.SEARCH_FIELDS), "embed_model": A.EMBED_MODEL, "top_k": top_k,
        "rrf_k": 60, "products_sha": file_sha(os.path.join(DATA, "products.csv")),
        "guidelines_sha": file_sha(os.path.join(DATA, "company_guidelines.csv")),
    }
    return hashlib.sha256(json.dumps(parts, sort_keys=True).encode()).hexdigest()[:16], parts


def last_code_change():
    """Latest of: working-tree mtime of backend/app.py and its last commit time."""
    t = os.path.getmtime(os.path.join(BACKEND, "app.py"))
    try:
        c = subprocess.run(["git", "log", "-1", "--format=%ct", "--", "backend/app.py"], cwd=ROOT,
                           capture_output=True, text=True).stdout.strip()
        t = max(t, float(c)) if c else t
    except Exception:
        pass
    return t


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--top-k", type=int, default=6)
    ap.add_argument("--again", action="store_true", help="allow a repeat run (recorded in the output)")
    args = ap.parse_args()

    if not os.path.exists(QUERIES):
        sys.exit(f"REFUSING TO RUN: {QUERIES} not found. Write it first (query, gold_product_id, query_type).")
    rows = read_csv(QUERIES)
    need = {"query", "gold_product_id", "query_type"}
    if not rows or not need <= set(rows[0]):
        sys.exit(f"REFUSING TO RUN: {QUERIES} is empty or lacks columns {sorted(need)}.")
    products, guidelines = A.load_data()
    known = set(products["product_id"])
    problems = [r["gold_product_id"] for r in rows if r["gold_product_id"] not in known]
    types = {r["query_type"] for r in rows}
    if problems or not types <= {"named", "descriptive"}:
        sys.exit(f"REFUSING TO RUN: unknown gold ids {problems[:5]} or query_type values {sorted(types)}.")

    if os.path.getmtime(QUERIES) > last_code_change():
        print("WARNING: heldout_queries.csv is newer than the last change to the retrieval code. "
              "This run cannot show the queries preceded the final tuning; state who wrote them and when.")
    runs = 1
    if os.path.exists(OUT):
        runs = json.load(open(OUT)).get("run_number", 1) + 1
        if not args.again:
            sys.exit(f"REFUSING TO RUN: {OUT} exists (the held-out set is single-use). Use --again to repeat; "
                     "the count is recorded.")

    h, parts = settings_hash(args.top_k)
    per, ranks = [], {"named": [], "descriptive": []}
    for r in rows:
        retrieved = A.retrieve_context(r["query"], products, guidelines, args.top_k)
        ids = [x["source_id"] for x in retrieved if x["kind"] == "product"]
        gold = f"products:{r['gold_product_id']}"
        rank = ids.index(gold) + 1 if gold in ids else None
        ranks[r["query_type"]].append(rank)
        per.append({"query": r["query"], "gold": gold, "query_type": r["query_type"], "rank": rank, "top3": ids[:3]})

    def summ(rs):
        n = len(rs)
        h1, h3 = sum(x == 1 for x in rs), sum(x is not None and x <= 3 for x in rs)
        rk = sum(x is not None for x in rs)
        return {"n": n, "hit@1": frac(h1, n), "hit@1_ci": wilson(h1, n), "hit@3": frac(h3, n), "hit@3_ci": wilson(h3, n),
                f"recall@{args.top_k}": frac(rk, n), f"recall@{args.top_k}_ci": wilson(rk, n),
                "mrr": round(sum(1 / x for x in rs if x) / n, 3) if n else None}

    result = {"_meta": meta(top_k=args.top_k, embed_model=A.EMBED_MODEL, settings_hash=h,
                            queries_file_sha=file_sha(QUERIES), run_number=runs,
                            run_at=time.strftime("%Y-%m-%d %H:%M")),
              "named": summ(ranks["named"]), "descriptive": summ(ranks["descriptive"]),
              "all": summ(ranks["named"] + ranks["descriptive"]), "per_query": per}
    result["run_number"] = runs
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(result, open(OUT, "w", encoding="utf-8"), indent=2)
    print(f"settings hash {h}; run #{runs}")
    for k in ("named", "descriptive", "all"):
        print(k, {a: b for a, b in result[k].items() if a in ("n", "hit@1", "hit@3", "mrr")})


if __name__ == "__main__":
    main()
