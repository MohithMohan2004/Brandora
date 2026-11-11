"""Count which backend wrote generations, using only data that exists in logs/files.

  venv/bin/python eval/backend_usage.py

Sources: backend/generations/*/gen.json (writer_model recorded), eval_results/metrics.json
(earlier pilot: only an aggregate fallback rate), backend/review_log.jsonl (no writer field),
eval/runs/*.jsonl (backend + model recorded). Nothing is estimated; unrecorded = unknown.
"""
import collections
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from common import EVAL, ROOT, meta  # noqa: E402


def kind(model):
    if str(model).startswith("@cf/"):
        return "cloudflare"
    return "ollama" if model else "unknown"


def main():
    out = {"_meta": meta()}
    c, per_model, unreadable = collections.Counter(), collections.Counter(), 0
    for p in glob.glob(os.path.join(ROOT, "backend", "generations", "*", "gen.json")):
        try:
            g = json.load(open(p, encoding="utf-8"))
        except Exception:
            unreadable += 1
            continue
        m = g.get("writer_model")
        c[kind(m)] += 1
        per_model[str(m)] += 1
    out["production_saved_generations"] = {
        "source": "backend/generations/*/gen.json (field writer_model)", "total_files": sum(c.values()) + unreadable,
        "cloudflare": c["cloudflare"], "ollama": c["ollama"], "unknown": c["unknown"] + unreadable,
        "per_model": dict(per_model),
        "caveat": "the app keeps at most 60 generations on disk and prunes older ones, so earlier production generations are not in the logs; their count is unknown."}
    mp = os.path.join(ROOT, "eval_results", "metrics.json")
    if os.path.exists(mp):
        g = json.load(open(mp)).get("generation", {})
        n, rate = g.get("briefs"), g.get("writer_fallback_rate_%")
        out["earlier_pilot_eval_generation"] = {
            "source": "eval_results/metrics.json (generation section, run 2026-11-05)", "briefs": n,
            "writer_fallback_rate_%": rate,
            "interpretation": ("fallback rate is the share NOT written by the first Cloudflare writer model; 0.0 means all "
                               f"{n} briefs were written by that Cloudflare model. Per-brief model names were not saved."
                               if rate == 0.0 else "per-brief model names were not saved; split not recoverable"),
            "cloudflare": n if rate == 0.0 else None, "ollama": 0 if rate == 0.0 else None, "unknown": 0 if rate == 0.0 else n}
    rl = os.path.join(ROOT, "backend", "review_log.jsonl")
    n = sum(1 for l in open(rl, encoding="utf-8") if l.strip()) if os.path.exists(rl) else 0
    out["review_log_decisions"] = {"source": "backend/review_log.jsonl", "decisions": n, "backend_recorded": False,
                                   "unknown": n, "note": "the log stores decision, brief and texts but not the writer model"}
    runs = {}
    for cfg in ("B0", "B1", "B2", "B3"):
        p = os.path.join(EVAL, "runs", f"{cfg}.jsonl")
        if os.path.exists(p):
            rows = [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]
            runs[cfg] = dict(collections.Counter((r.get("backend", "unknown"), r.get("model", "unknown")) .__str__()
                                                 for r in rows if not r.get("error")))
            runs[cfg]["errors"] = sum(1 for r in rows if r.get("error"))
    out["benchmark_runs"] = {"source": "eval/runs/*.jsonl (backend and model recorded per row)", "by_config": runs,
                             "note": "forced to local Ollama by run_benchmark.py; not production traffic"}
    os.makedirs(os.path.join(EVAL, "results"), exist_ok=True)
    json.dump(out, open(os.path.join(EVAL, "results", "backend_usage.json"), "w", encoding="utf-8"), indent=2)
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
