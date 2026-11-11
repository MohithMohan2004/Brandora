"""Shared helpers for the evaluation scripts in eval/.

Every script is run from the repo root, e.g. `venv/bin/python eval/make_briefs.py`.
Nothing here changes the production pipeline: the app is imported, never edited.
"""
import csv
import hashlib
import json
import math
import os
import random
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
EVAL = os.path.join(ROOT, "eval")
BACKEND = os.path.join(ROOT, "backend")
DATA = os.path.join(BACKEND, "data")
SEED = 20241105      # used only by make_briefs.py (briefs.csv was generated with it; unchanged)
RUN_SEED = 42        # subset sampling, Ollama seed, label shuffles
CATEGORIES = ["Apparel", "Footwear", "Accessories", "Skincare", "Electronics"]
CHANNELS = ["Instagram feed", "SMS", "Email"]
TYPES = ["standard", "price", "discount", "eco_claim"]


def import_app():
    """Import backend/app.py (loads .env but prints no secrets)."""
    if BACKEND not in sys.path:
        sys.path.insert(0, BACKEND)
    import app
    return app


def git_hash():
    try:
        out = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
                             capture_output=True, text=True, check=True).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain", "--", "backend", ":!backend/review_log.jsonl"], cwd=ROOT,
                               capture_output=True, text=True).stdout.strip()
        return out + ("+dirty" if dirty else "")
    except Exception:
        return "unknown"


def read_csv(path):
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def write_csv(path, rows, fields):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


CHANNEL_KEYS = ["Instagram feed", "SMS", "Email"]


def subset_ids(briefs, n):
    """Random n-brief subset (random.Random(42)) with >=2 per category, per type and per channel.

    Rejection sampling: draw n briefs, accept the first draw meeting the minimums. Deterministic.
    """
    rng = random.Random(RUN_SEED)
    for _ in range(100000):
        pick = rng.sample(briefs, n)
        ok = all(sum(b["category"] == c for b in pick) >= 2 for c in CATEGORIES) and \
            all(sum(b["brief_type"] == t for b in pick) >= 2 for t in TYPES) and \
            all(sum(b["channel"] == c for b in pick) >= 2 for c in CHANNEL_KEYS)
        if ok:
            return {b["brief_id"] for b in pick}
    raise RuntimeError("no subset satisfied the minimums")


def load_briefs(subset=None):
    briefs = read_csv(os.path.join(EVAL, "briefs.csv"))
    if subset:
        keep = subset_ids(briefs, subset)
        briefs = [b for b in briefs if b["brief_id"] in keep]
    return briefs


def wilson(k, n, z=1.96):
    """Wilson 95% interval for k successes in n trials, as percentages."""
    if n == 0:
        return (None, None)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (round(100 * (c - h), 1), round(100 * (c + h), 1))


def frac(k, n):
    return f"{k}/{n} = {100 * k / n:.1f}%" if n else f"0/0 = n/a"


def file_sha(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()[:12]


def meta(**extra):
    return {"git_commit": git_hash(), "seed": SEED, **extra}


# ---- text overlap helpers (used by validate_heldout.py and retrieval_dev.py) ----
import re as _re


def tokens(text):
    return _re.findall(r"[a-z0-9]+", str(text).lower())


def jaccard(a, b):
    a, b = set(tokens(a)), set(tokens(b))
    return len(a & b) / len(a | b) if a | b else 0.0


def longest_shared_run(query, text):
    """(length, words) of the longest run of consecutive tokens common to both strings."""
    q, t = tokens(query), tokens(text)
    best, where = 0, 0
    prev = [0] * (len(t) + 1)
    for i in range(1, len(q) + 1):
        cur = [0] * (len(t) + 1)
        for j in range(1, len(t) + 1):
            if q[i - 1] == t[j - 1]:
                cur[j] = prev[j - 1] + 1
                if cur[j] > best:
                    best, where = cur[j], i
        prev = cur
    return best, " ".join(q[where - best:where])
