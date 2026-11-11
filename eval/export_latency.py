"""Aggregate per-stage timings into eval/results/latency.csv and record hardware.

  venv/bin/python eval/export_latency.py [--subset 30]

Stages: t_retrieval, t_llm (writer incl. copy-length rewrite and B3 regenerations), t_fix
(the rewrite alone, part of t_llm), t_image, t_compose (image runs). mean/median/p95 per stage.
Also writes eval/results/environment.json (CPU, GPU if any, RAM, OS, Python, Ollama version, models).
"""
import argparse
import csv
import json
import os
import platform
import statistics
import subprocess
import sys

sys.path.insert(0, os.path.dirname(__file__))
from common import EVAL, import_app, load_briefs, meta, write_csv  # noqa: E402

RES = os.path.join(EVAL, "results")


def p95(v):
    v = sorted(v)
    return v[min(len(v) - 1, int(round(0.95 * (len(v) - 1))))]


def cmd(*a):
    try:
        return subprocess.run(a, capture_output=True, text=True, timeout=10).stdout.strip()
    except Exception:
        return ""


def digests(A):
    """Model digests from the local Ollama server."""
    import requests
    out = {}
    try:
        tags = {m["name"]: m["digest"] for m in requests.get(f"{A.OLLAMA_BASE_URL}/api/tags", timeout=10).json()["models"]}
        out["writer_model_digest"] = tags.get(A.CHAT_MODEL)
        out["embed_model_digest"] = tags.get(A.EMBED_MODEL) or tags.get(A.EMBED_MODEL + ":latest")
    except Exception as exc:
        out["digest_error"] = str(exc)
    return out


def environment():
    cpu = next((l.split(":", 1)[1].strip() for l in open("/proc/cpuinfo") if l.startswith("model name")), platform.processor())
    mem_kb = int(next(l.split()[1] for l in open("/proc/meminfo") if l.startswith("MemTotal")))
    gpu = cmd("nvidia-smi", "-L") or "none detected (nvidia-smi absent)"
    A = import_app()
    return {"cpu": cpu, "logical_cpus": os.cpu_count(), "gpu": gpu, "ram_gb": round(mem_kb / 1024 / 1024, 1),
            "os": platform.platform(), "python": platform.python_version(),
            "ollama_version": cmd("ollama", "--version"), "writer_model": A.CHAT_MODEL, "embed_model": A.EMBED_MODEL,
            "image_model": A.CLOUDFLARE_IMAGE_MODEL, **digests(A)}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--subset", type=int)
    args = ap.parse_args()
    keep = {b["brief_id"] for b in load_briefs(args.subset)}
    rows = []
    for cfg in ("B0", "B1", "B2", "B3"):
        path = os.path.join(EVAL, "runs", f"{cfg}.jsonl")
        if not os.path.exists(path):
            continue
        recs = [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]
        recs = [r for r in recs if not r.get("error") and r["brief_id"] in keep]
        for stage in ("t_retrieval", "t_llm", "t_fix"):
            v = [r[stage] for r in recs if isinstance(r.get(stage), (int, float))]
            if v:
                rows.append({"source": f"benchmark_{cfg}", "stage": stage, "n": len(v), "mean_s": round(statistics.mean(v), 3),
                             "median_s": round(statistics.median(v), 3), "p95_s": round(p95(v), 3)})
    img = os.path.join(EVAL, "results", "image_runs.csv")
    if os.path.exists(img):
        recs = [r for r in csv.DictReader(open(img, encoding="utf-8")) if not r["error"]]
        for pipe in ("text", "textfree"):
            for stage in ("t_image", "t_compose"):
                v = [float(r[stage]) for r in recs if r["pipeline"] == pipe and r[stage] not in ("", None)]
                if v:
                    rows.append({"source": f"images_{pipe}", "stage": stage, "n": len(v), "mean_s": round(statistics.mean(v), 3),
                                 "median_s": round(statistics.median(v), 3), "p95_s": round(p95(v), 3)})
    os.makedirs(RES, exist_ok=True)
    write_csv(os.path.join(RES, "latency.csv"), rows, ["source", "stage", "n", "mean_s", "median_s", "p95_s"])
    env = {"_meta": meta(), **environment()}
    json.dump(env, open(os.path.join(RES, "environment.json"), "w", encoding="utf-8"), indent=2)
    print(f"{len(rows)} latency rows -> eval/results/latency.csv; environment -> eval/results/environment.json")
    print(json.dumps({k: v for k, v in env.items() if k != "_meta"}, indent=1))


if __name__ == "__main__":
    main()
