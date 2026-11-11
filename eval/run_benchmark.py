"""Run every brief through B0-B3 and save one JSONL row per run (eval/runs/<config>.jsonl).

  venv/bin/python eval/run_benchmark.py --subset 30 --dry-run
  venv/bin/python eval/run_benchmark.py --configs B0,B1,B2,B3 --resume

Configurations (same LLM, temperature 0.35 and Ollama seed for all):
  B0  guidelines pasted into the prompt, NO retrieval (no product records)
  B1  production retrieval (hybrid dense+BM25 top-k) WITHOUT mandatory-rule injection:
      retrieve_context() is called as-is and the guideline records it appended only
      because they are mandatory (score None) are dropped. Guidelines that ranked
      into the top-k on their own stay.
  B2  the real pipeline: retrieve_context() with mandatory rules always injected
  B3  B2 plus eval/checker.py; violations are fed back for up to R=2 regenerations

Writer: the local Ollama model only (ollama_generate with a fixed seed), NOT the
Cloudflare writers that generate_brief() tries first in production. fix_copy_length()
is applied identically in every config; whether it fired and its time are logged.
No images are generated here.
"""
import argparse
import json
import os
import sys
import time

import requests

sys.path.insert(0, os.path.dirname(__file__))
from common import EVAL, RUN_SEED as SEED, git_hash, import_app, load_briefs  # noqa: E402
import checker  # noqa: E402

A = import_app()
RUNS = os.path.join(EVAL, "runs")
CONFIGS = ["B0", "B1", "B2", "B3"]
MAX_ROUNDS = 2
TEMPERATURE = 0.35

_clock = {"calls": 0}


def model_info():
    """Model name and digest from the local Ollama server (recorded in every row)."""
    out = {"backend": "ollama", "model": A.CHAT_MODEL, "model_digest": None, "ollama_version": None}
    try:
        tags = requests.get(f"{A.OLLAMA_BASE_URL}/api/tags", timeout=10).json()["models"]
        out["model_digest"] = next((m["digest"] for m in tags if m["name"] == A.CHAT_MODEL), None)
        out["ollama_version"] = requests.get(f"{A.OLLAMA_BASE_URL}/api/version", timeout=10).json().get("version")
    except Exception:
        pass
    return out


def seeded_ollama_generate(prompt):
    """Same request as app.ollama_generate plus a fixed seed (installed only inside this process)."""
    _clock["calls"] += 1
    response = requests.post(
        f"{A.OLLAMA_BASE_URL}/api/generate",
        json={"model": A.CHAT_MODEL, "prompt": prompt, "stream": False,
              "options": {"temperature": TEMPERATURE, "seed": SEED}},
        timeout=600)
    response.raise_for_status()
    return response.json()["response"].strip()


def write_with_fix(prompt):
    """(raw_output, fix_fired, t_total, t_fix): ollama writer + the app's fix_copy_length."""
    t0 = time.perf_counter()
    draft = A.ollama_generate(prompt)           # patched to the seeded version
    t1 = time.perf_counter()
    final = A.fix_copy_length(draft, prompt, A.CHAT_MODEL)
    t2 = time.perf_counter()
    return final, final != draft, t2 - t0, t2 - t1


def split_list(text):
    parts = [p.strip(" -*•\t") for p in str(text or "").replace(";", "\n").splitlines()]
    return [p for p in parts if p and p.lower() not in ("none", "none identified", "none identified.")]


def mandatory_records(guidelines):
    out = []
    for _, row in guidelines.iterrows():
        if str(row.get("severity", "")).lower() == "mandatory":
            out.append({"source_id": f"guidelines:{row['guideline_id']}", "kind": "guideline",
                        "text": A.row_to_text(row, "guideline"), "score": None})
    return out


def feedback_prompt(prompt, raw, violations):
    lines = "\n".join(f"- {v['rule_id']} ({v['check']}): \"{v['matched_text']}\"" for v in violations)
    return f"""{prompt}

PREVIOUS DRAFT (rejected by the compliance checker)
{raw}

VIOLATIONS FOUND
{lines}

Rewrite the full brief in the same output format, fixing every violation above. Keep all other rules."""


def run_one(brief, config, products, guidelines, product_row, top_k, info):
    row = {"brief_id": brief["brief_id"], "config": config, "category": brief["category"],
           "channel": brief["channel"], "brief_type": brief["brief_type"], "product_id": brief["product_id"],
           **info, "seed": SEED, "temperature": TEMPERATURE, "top_k": top_k, "git_commit": git_hash(),
           "retrieved_ids": [], "raw_output": "", "parsed_headline": "", "parsed_copy": "", "parsed_cta": "",
           "unsupported_list": [], "source_ids": [], "t_retrieval": 0.0, "t_llm": 0.0, "t_fix": 0.0,
           "fix_fired": False, "regen_rounds": 0, "checker_violations": [], "error": ""}
    text = brief["brief_text"]
    t0 = time.perf_counter()
    if config == "B0":
        retrieved = mandatory_records(guidelines)
    else:
        retrieved = A.retrieve_context(text, products, guidelines, top_k)
        if config == "B1":
            retrieved = [r for r in retrieved if not (r["kind"] == "guideline" and r.get("score") is None)]
    row["t_retrieval"] = round(time.perf_counter() - t0, 4)
    row["retrieved_ids"] = [r["source_id"] for r in retrieved] if config != "B0" else []
    prompt = A.build_generation_prompt(text, retrieved)

    raw, fired, t_total, t_fix = write_with_fix(prompt)
    fix_any, fix_t = fired, t_fix
    rounds = 0
    violations = []
    if config == "B3":
        while True:
            p = A.parse_ad_sections(raw)
            violations = checker.check(p["headline"], p["copy"], p["cta"], product_row, brief["channel"])
            if not violations or rounds >= MAX_ROUNDS:
                break
            rounds += 1
            raw, fired, t, tf = write_with_fix(feedback_prompt(prompt, raw, violations))
            t_total += t
            fix_t += tf
            fix_any = fix_any or fired
    p = A.parse_ad_sections(raw)
    if config != "B3":
        violations = checker.check(p["headline"], p["copy"], p["cta"], product_row, brief["channel"])
    row.update(raw_output=raw, parsed_headline=p["headline"], parsed_copy=p["copy"], parsed_cta=p["cta"],
               unsupported_list=split_list(p["missing"]), source_ids=split_list(p["sources"]),
               t_llm=round(t_total, 3), t_fix=round(fix_t, 3), fix_fired=fix_any, regen_rounds=rounds,
               checker_violations=violations)
    return row


def done_keys(path):
    keys = set()
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                try:
                    r = json.loads(line)
                    if not r.get("error"):
                        keys.add(r["brief_id"])
                except json.JSONDecodeError:
                    pass
    return keys


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--configs", default="B0,B1,B2,B3", help="comma list (default all)")
    ap.add_argument("--subset", type=int, help="run the balanced N-brief subset (e.g. 30)")
    ap.add_argument("--limit", type=int, help="stop after N briefs (smoke test)")
    ap.add_argument("--top-k", type=int, default=6)
    ap.add_argument("--resume", action="store_true", help="skip (brief, config) pairs already saved without error")
    ap.add_argument("--overwrite", action="store_true", help="replace existing run files")
    ap.add_argument("--out-dir", default=RUNS, help="where to write run files (default eval/runs)")
    ap.add_argument("--dry-run", action="store_true", help="print the plan; call no model")
    args = ap.parse_args()

    configs = [c.strip().upper() for c in args.configs.split(",") if c.strip()]
    bad = [c for c in configs if c not in CONFIGS]
    if bad:
        sys.exit(f"unknown config(s): {bad}")
    briefs = load_briefs(args.subset)
    if args.limit:
        briefs = briefs[:args.limit]
    out_dir = args.out_dir
    os.makedirs(out_dir, exist_ok=True)
    paths = {c: os.path.join(out_dir, f"{c}.jsonl") for c in configs}
    existing = [p for p in paths.values() if os.path.exists(p)]
    if existing and not (args.resume or args.overwrite or args.dry_run):
        sys.exit(f"{existing} exist; pass --resume or --overwrite")
    if args.overwrite:
        for p in existing:
            os.remove(p)
    todo = {c: [b for b in briefs if b["brief_id"] not in done_keys(paths[c])] for c in configs}
    print(f"briefs: {len(briefs)}; configs: {configs}; model: {A.CHAT_MODEL}; commit: {git_hash()}")
    for c in configs:
        print(f"  {c}: {len(todo[c])} to run, {len(briefs) - len(todo[c])} already done")
    if args.dry_run:
        return

    info = model_info()
    if not info["model_digest"]:
        sys.exit(f"Could not read {A.CHAT_MODEL} from Ollama at {A.OLLAMA_BASE_URL}. Is it running?")
    A.ollama_generate = seeded_ollama_generate
    products, guidelines = A.load_data()
    by_id = {r["product_id"]: r for r in products.to_dict("records")}
    for c in configs:
        with open(os.path.join(out_dir, f"{c}.meta.json"), "w", encoding="utf-8") as fh:
            json.dump({"config": c, "git_commit": git_hash(), "seed": SEED, "temperature": TEMPERATURE,
                       "top_k": args.top_k, "max_regen_rounds": MAX_ROUNDS, "embed_model": A.EMBED_MODEL,
                       "retrieval": "hybrid dense+BM25 RRF (app.retrieve_context)", **info}, fh, indent=2)

    for n, brief in enumerate(briefs, 1):
        for c in configs:
            if brief not in todo[c]:
                continue
            try:
                row = run_one(brief, c, products, guidelines, by_id[brief["product_id"]], args.top_k, info)
            except requests.exceptions.ConnectionError as exc:
                sys.exit(f"Ollama unreachable, stopping cleanly (resume with --resume): {exc}")
            except Exception as exc:  # keep going; the failure is recorded, not hidden
                row = {"brief_id": brief["brief_id"], "config": c, "error": f"{type(exc).__name__}: {exc}",
                       "git_commit": git_hash(), **info}
            with open(paths[c], "a", encoding="utf-8") as fh:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            tag = row.get("error") or f"{row['t_llm']:.1f}s, {len(row['checker_violations'])} violations"
            print(f"[{n}/{len(briefs)}] {brief['brief_id']} {c}: {tag}", flush=True)


if __name__ == "__main__":
    main()
