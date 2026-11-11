"""Check eval/heldout_queries.csv against the independence rules. Exit code 0 = pass.

  venv/bin/python eval/validate_heldout.py

Rules: exactly 50 rows (25 named + 25 descriptive); each category 5 named + 5 descriptive;
50 distinct gold IDs that exist in the catalogue; named queries contain the exact product
name; descriptive queries do not contain it; a descriptive query shares no run of 3+
consecutive words with any text field of its gold product (name, description, materials,
features, target_audience, available_colours); no query has token Jaccard > 0.5 with any of
the 200 development queries. It does not run any retrieval.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from common import DATA, EVAL, jaccard, longest_shared_run, read_csv  # noqa: E402
import retrieval_core as R  # noqa: E402  (only for the dev query texts; no retrieval is run)

FIELDS = ("product_name", "description", "materials", "features", "target_audience", "available_colours")


def main():
    rows = read_csv(os.path.join(EVAL, "heldout_queries.csv"))
    products = {r["product_id"]: r for r in read_csv(os.path.join(DATA, "products.csv"))}
    dev = [q for _, q, _ in R.dev_queries()]
    problems = []
    if list(rows[0]) != ["query", "gold_product_id", "query_type"]:
        problems.append(f"columns are {list(rows[0])}")
    if len(rows) != 50:
        problems.append(f"{len(rows)} rows, need 50")
    types = [r["query_type"] for r in rows]
    if types.count("named") != 25 or types.count("descriptive") != 25:
        problems.append(f"type counts named={types.count('named')} descriptive={types.count('descriptive')}")
    ids = [r["gold_product_id"] for r in rows]
    if len(set(ids)) != len(ids):
        problems.append("gold product IDs are not all different")
    for cat in sorted({p["category"] for p in products.values()}):
        for t in ("named", "descriptive"):
            n = sum(1 for r in rows if r["query_type"] == t and products.get(r["gold_product_id"], {}).get("category") == cat)
            if n != 5:
                problems.append(f"{cat} {t}: {n} queries, need 5")
    longest = []
    for i, r in enumerate(rows, 2):
        p = products.get(r["gold_product_id"])
        if not p:
            problems.append(f"line {i}: unknown gold id {r['gold_product_id']}")
            continue
        q, name = r["query"], p["product_name"]
        if r["query_type"] == "named" and name not in q:
            problems.append(f"line {i}: named query lacks exact name '{name}'")
        if r["query_type"] == "descriptive":
            if name.lower() in q.lower():
                problems.append(f"line {i}: descriptive query contains the product name")
            run = max((longest_shared_run(q, p[f]) for f in FIELDS), key=lambda x: x[0])
            longest.append(run[0])
            if run[0] >= 3:
                problems.append(f"line {i} ({r['gold_product_id']}): shares a {run[0]}-word run '{run[1]}' with the product text")
        worst = max(((jaccard(q, d), d) for d in dev), key=lambda x: x[0])
        if worst[0] > 0.5:
            problems.append(f"line {i}: Jaccard {worst[0]:.2f} with dev query '{worst[1]}'")
    print(f"rows={len(rows)} named={types.count('named')} descriptive={types.count('descriptive')} "
          f"distinct_gold={len(set(ids))} max_shared_run_descriptive={max(longest) if longest else None}")
    if problems:
        print("FAILED:")
        for p in problems:
            print("  -", p)
        sys.exit(1)
    print("PASS")


if __name__ == "__main__":
    main()
