"""Blind label sheets for two human annotators. Never fills the human columns.

  venv/bin/python eval/make_label_sheets.py [--subset 30] [--runs-dir eval/runs]

Writes to eval/ (by default):
  label_annotator_A.csv, label_annotator_B.csv   one row per output (config hidden, shuffled
                                                 differently per annotator); fill rules_violated, notes
  claims_A.csv, claims_B.csv                     one row per sentence of the copy (auto-split);
                                                 fill supported (Y/N), evidence_product_field
  label_key.csv                                  restores config names (do not show annotators)
Also writes rule_guide.csv with the mandatory guideline IDs and the product record for each
output (output_id -> product fields) so annotators can verify facts against the catalogue.
rules_violated: IDs separated by ';' (e.g. BRAND-003;BRAND-005); write the word none when no rule is violated
(analyze.py treats an empty cell as 'not labelled yet').
"""
import argparse
import csv
import hashlib
import json
import os
import random
import re
import sys

sys.path.insert(0, os.path.dirname(__file__))
from common import EVAL, DATA, RUN_SEED as SEED, load_briefs, read_csv, write_csv  # noqa: E402

CONFIGS = ["B0", "B1", "B2", "B3"]


def output_id(brief_id, config):
    return "O" + hashlib.sha1(f"{SEED}|{brief_id}|{config}".encode()).hexdigest()[:8]


def sentences(text):
    parts = re.split(r"(?<=[.!?])\s+", (text or "").strip())
    return [p.strip() for p in parts if p.strip()]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--subset", type=int)
    ap.add_argument("--runs-dir", default=os.path.join(EVAL, "runs"))
    ap.add_argument("--out-dir", default=EVAL)
    ap.add_argument("--configs", default=",".join(CONFIGS))
    args = ap.parse_args()

    wanted = {b["brief_id"]: b for b in load_briefs(args.subset)}
    products = {r["product_id"]: r for r in read_csv(os.path.join(DATA, "products.csv"))}
    items = []
    for cfg in args.configs.split(","):
        path = os.path.join(args.runs_dir, f"{cfg}.jsonl")
        if not os.path.exists(path):
            print(f"missing {path}; skipped")
            continue
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if r.get("error") or r.get("brief_id") not in wanted:
                    continue
                items.append(r)
    if not items:
        sys.exit("no completed runs found")

    key_rows, sheet, claim_rows = [], [], []
    for r in items:
        b = wanted[r["brief_id"]]
        oid = output_id(r["brief_id"], r["config"])
        p = products[b["product_id"]]
        key_rows.append({"output_id": oid, "brief_id": r["brief_id"], "config": r["config"]})
        sheet.append({"output_id": oid, "channel": b["channel"], "brief_text": b["brief_text"],
                      "product_id": b["product_id"], "product_name": p["product_name"],
                      "price_inr": p["price_inr"], "advertising_restrictions": p["advertising_restrictions"],
                      "headline": r["parsed_headline"], "copy": r["parsed_copy"], "cta": r["parsed_cta"],
                      "rules_violated": "", "notes": ""})
        for i, s in enumerate(sentences(f"{r['parsed_headline']}. {r['parsed_copy']}"), 1):
            claim_rows.append({"output_id": oid, "claim_no": i, "claim_text": s,
                               "supported (Y/N)": "", "evidence_product_field": ""})

    os.makedirs(args.out_dir, exist_ok=True)
    f1 = ["output_id", "channel", "brief_text", "product_id", "product_name", "price_inr",
          "advertising_restrictions", "headline", "copy", "cta", "rules_violated", "notes"]
    f2 = ["output_id", "claim_no", "claim_text", "supported (Y/N)", "evidence_product_field"]
    for who, offset in (("A", 1), ("B", 2)):
        rng = random.Random(SEED + offset)
        order = sheet[:]
        rng.shuffle(order)
        write_csv(os.path.join(args.out_dir, f"label_annotator_{who}.csv"), order, f1)
        by_out = {}
        for c in claim_rows:
            by_out.setdefault(c["output_id"], []).append(c)
        ids = list(by_out)
        rng.shuffle(ids)
        write_csv(os.path.join(args.out_dir, f"claims_{who}.csv"), [c for i in ids for c in by_out[i]], f2)
    write_csv(os.path.join(args.out_dir, "label_key.csv"), sorted(key_rows, key=lambda r: r["output_id"]),
              ["output_id", "brief_id", "config"])
    write_csv(os.path.join(args.out_dir, "rule_guide.csv"),
              [{"guideline_id": g["guideline_id"], "rule": g["rule"], "severity": g["severity"]}
               for g in read_csv(os.path.join(DATA, "company_guidelines.csv"))],
              ["guideline_id", "rule", "severity"])
    print(f"{len(sheet)} outputs, {len(claim_rows)} claim rows -> {args.out_dir} (human columns left empty)")


if __name__ == "__main__":
    main()
