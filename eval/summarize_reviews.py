"""Summarize review_log.jsonl: decisions, approval rate, edit rates, review time, NED.

  venv/bin/python eval/summarize_reviews.py [path ...]   (default: backend/review_log.jsonl)

NED = Levenshtein(original, final) / max(len(original), len(final)), where each text is
"headline | copy | cta". Reported for edited reviews only (text_edited true or texts differ).
Malformed lines are skipped and counted. Proportions carry Wilson 95% intervals.
"""
import argparse
import json
import os
import statistics
import sys

sys.path.insert(0, os.path.dirname(__file__))
from common import ROOT, EVAL, frac, meta, wilson  # noqa: E402


def levenshtein(a, b):
    if a == b:
        return 0
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def text_of(d):
    d = d or {}
    return " | ".join(str(d.get(k, "")) for k in ("headline", "copy", "cta"))


def ned(original, final):
    a, b = text_of(original), text_of(final)
    m = max(len(a), len(b))
    return levenshtein(a, b) / m if m else 0.0


def summarize(paths):
    rows, skipped, files = [], 0, 0
    for path in paths:
        if not os.path.exists(path):
            print(f"missing: {path}")
            continue
        files += 1
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                try:
                    r = json.loads(line)
                    if r.get("decision") not in ("approved", "rejected"):
                        raise ValueError
                    rows.append(r)
                except (json.JSONDecodeError, ValueError, AttributeError):
                    skipped += 1
    n = len(rows)
    approved = [r for r in rows if r["decision"] == "approved"]
    edited = [r for r in rows if r.get("text_edited") or text_of(r.get("original")) != text_of(r.get("final"))]
    approved_clean = [r for r in approved if r not in edited]
    secs = [float(r["review_seconds"]) for r in rows if isinstance(r.get("review_seconds"), (int, float))]
    neds = [ned(r.get("original"), r.get("final")) for r in edited]
    out = {
        "files": files, "decisions": n, "malformed_lines_skipped": skipped,
        "approved": frac(len(approved), n), "approved_95ci": wilson(len(approved), n),
        "text_edited": frac(len(edited), n), "text_edited_95ci": wilson(len(edited), n),
        "approved_without_edits": frac(len(approved_clean), n),
        "approved_without_edits_95ci": wilson(len(approved_clean), n),
        "review_seconds_median": round(statistics.median(secs), 1) if secs else None,
        "review_seconds_mean": round(statistics.mean(secs), 1) if secs else None,
        "review_seconds_n": len(secs),
        "ned_edited_n": len(neds),
        "ned_mean": round(statistics.mean(neds), 3) if neds else None,
        "ned_median": round(statistics.median(neds), 3) if neds else None,
        "ned_each": [round(x, 3) for x in neds],
    }
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="*", default=[os.path.join(ROOT, "backend", "review_log.jsonl")])
    ap.add_argument("--out", default=os.path.join(EVAL, "results", "review_summary.json"))
    args = ap.parse_args()
    out = summarize(args.paths)
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump({"_meta": meta(inputs=args.paths), **out}, fh, indent=2)
    for k, v in out.items():
        if k != "ned_each":
            print(f"{k}: {v}")
    print(f"-> {args.out}")


if __name__ == "__main__":
    main()
