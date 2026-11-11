# Evaluation report (status: tooling built, benchmark NOT yet run)

Nothing in this report is estimated. Numbers come from runs listed under "What was run".

## 1. What was built (all under `eval/`, run from the repo root)

| File | Command | Purpose |
|---|---|---|
| `make_briefs.py` | `venv/bin/python eval/make_briefs.py --subset 30` | `briefs.csv` (60) and `briefs_subset30.csv` |
| `checker.py`, `checker_wordlists.json`, `test_checker.py` | `venv/bin/python eval/test_checker.py` | deterministic compliance checker + 24 unit tests |
| `run_benchmark.py` | `venv/bin/python eval/run_benchmark.py --subset 30 --resume` | B0-B3 runs into `eval/runs/<config>.jsonl` |
| `make_label_sheets.py` | `venv/bin/python eval/make_label_sheets.py` | blind label sheets + `label_key.csv` in `eval/labels/` |
| `analyze.py` | `venv/bin/python eval/analyze.py` | metrics, Wilson CIs, kappa, LaTeX table bodies in `eval/results/` |
| `retrieval_core.py`, `retrieval_dev.py`, `test_retrieval_dev.py` | `venv/bin/python eval/retrieval_dev.py` | ablation on the 200 dev queries + equivalence check |
| `retrieval_heldout.py` | `venv/bin/python eval/retrieval_heldout.py` | one-shot held-out test; refuses without `heldout_queries.csv` |
| `run_images.py` | `venv/bin/python eval/run_images.py --limit 20 --resume` | text vs text-free images, blind sheets, contact sheet (Cloudflare quota) |
| `summarize_reviews.py` | `venv/bin/python eval/summarize_reviews.py` | review-log summary incl. NED |
| `export_latency.py` | `venv/bin/python eval/export_latency.py` | `results/latency.csv`, `results/environment.json` |

No production file was edited. `run_benchmark.py` replaces `app.ollama_generate` with a seeded copy **inside its own process only**.

## 2. What was and was not run

| Item | Status | Count / reason |
|---|---|---|
| `git status` review | done | only `backend/review_log.jsonl` modified; `CLAUDE_TASKS.md` and `eval/` untracked |
| Merge-conflict markers | **present, unresolved** | root `app.py` lines 14-17 and 313-328 (`<<<<<<< HEAD` ... `>>>>>>> f0affd8`) and a stray `st.warning(` at line 666. That file is the unused Streamlit version (CLAUDE.md). `backend/` has none. Not touched. |
| Briefs | generated | 60 (12 per category, 15 per type, 60 distinct products); subset: 30 (6 per category; standard 8, price 8, discount 7, eco_claim 7) |
| Checker unit tests | pass | 24/24 |
| Dev retrieval ablation | run | 200 queries, equivalence with `retrieve_context` verified 200/200 (see 3) |
| Benchmark B0-B3 | **not run** | only a 1-brief smoke test in a scratch folder (4 rows, discarded). Waiting on your model decision (answer 4 arrived as the unfilled placeholder). |
| Label sheets | tooling tested on the smoke rows only | real sheets need the benchmark first |
| `analyze.py` | runs end to end without labels (automatic metrics only) | human GVR/GP/kappa/checker precision need completed sheets; tested only for the skip path |
| Held-out retrieval | **not run** | `eval/heldout_queries.csv` does not exist (yours to write) |
| Image comparison | **not run** | needs B2 outputs first; dry-run path only |
| Review summary | run | 7 decisions, 0 malformed lines (see 3) |
| Latency export | environment only | stage latencies need runs |

Time estimate for the benchmark, from the 4 smoke generations only (68-116 s each on this CPU): B0-B2 on 30 briefs is 90 generations, about 2.5-3 h; B3 adds 1-3 generations per brief. Full 60 briefs is about twice that. The writer is slow because it runs on CPU.

## 3. Results actually produced

Retrieval ablation, 200 development queries (100 named, 100 descriptive; `eval/results/retrieval_dev.json`; development set, retrieval WAS tuned against it):

| Variant | Hit@1 | Hit@3 | MRR |
|---|---|---|---|
| dense baseline | 178/200 = 89.0% | 193/200 = 96.5% | 0.934 |
| + task prefixes | 184/200 = 92.0% | 197/200 = 98.5% | 0.952 |
| + prefixes + clean text | 190/200 = 95.0% | 198/200 = 99.0% | 0.971 |
| BM25 alone | 200/200 = 100.0% | 200/200 = 100.0% | 1.000 |
| all combined (production) | 195/200 = 97.5% | 200/200 = 100.0% | 0.988 |

Review log (`eval/results/review_summary.json`): 7 decisions; approved 5/7 = 71.4% (CI 35.9-91.8); text edited 2/7 = 28.6%; approved without edits 3/7 = 42.9%; review time median 78.4 s, mean 138.5 s; NED over the 2 edited reviews: mean 0.719.

Hardware (`eval/results/environment.json`): Intel i5-10210U (8 logical CPUs), no GPU, 15.5 GB RAM, Ubuntu (Linux 6.14), Ollama 0.40.11.

Production writer usage (13 generations persisted in `backend/generations/`, 30 Oct - 3 Nov 2026): 8 used Cloudflare `@cf/meta/llama-3.3-70b-instruct-fp8-fast`, 5 used local Ollama `llama3.2:3b`. The store keeps at most 60 and prunes, so this is not a full history. In the earlier pilot (below) all 15 briefs were written by Cloudflare (fallback rate 0%). So production generation is **not** local-only: Cloudflare writers are tried first. The paper's "local Llama 3.2 3B" claim only holds for the benchmark, which forces Ollama.

Earlier pilot (not part of the new tables): `eval_results/metrics.md`, 2026-11-05 21:12-21:18, Cloudflare writer, 15 briefs, 8 posters, 200 retrieval queries, 7 reviews, no baselines, no human labels.

## 4. Things that look odd

1. **BM25 alone (100%) beats the production hybrid (97.5%) on the dev set.** The hybrid misses 5 of 200 at Hit@1. The likely cause is that the descriptive dev queries are built from the catalogue's own `materials` and `target_audience` fields, so keyword matching is nearly an exact lookup. The dev set favours BM25 and says little about real marketer phrasing; the held-out set is where this should be checked. Not tuned or changed.
2. **Dense-only tie-breaking.** The app uses `np.argsort` (unstable); 12/200 queries had ties at ranks 5/6 that only matched once my code used the same call. Rank order within ties is arbitrary but deterministic.
3. **Image model mismatch.** Your brief says FLUX.1 [schnell]; `.env` sets `@cf/black-forest-labs/flux-2-klein-9b` (the app default comment says FLUX.2 follows plain-surface instructions better). `run_images.py` records the model per row. FLUX.1 schnell ignores `seed` in the app's call, so image runs are not reproducible.
4. **Writer path.** Production calls Cloudflare writers first, so the benchmark's local Llama 3.2 3B outputs are not what the app normally produces.
5. **Smoke test:** in one brief all four configs produced similar headlines, none violated the checker, and the copy-length rewrite did not fire. One brief proves nothing.

## 5. Deviations and limitations

- `B0` has no product records, so the generation prompt still says "RETRIEVED COMPANY CONTEXT" over the guidelines only; checker price/name checks use the gold product row.
- `B1` = `retrieve_context` output with the guideline records appended solely for being mandatory (score `None`) removed. Guidelines that ranked into the top-k by themselves remain, so B1 can contain some rules.
- `B3` regeneration feedback prompt is mine (not in the app); `fix_copy_length` runs after every generation. `t_llm` includes the rewrite and all regenerations; `t_fix` is the rewrite alone.
- Ollama is called with `seed` = 20241105 and temperature 0.35. GPU/CPU nondeterminism can still differ across machines.
- Checker is a heuristic (see `checker.py` docstring): word lists can miss paraphrases and flag benign words; `claims` (BRAND-002) and `design` (BRAND-006) are not checked automatically. Urgency maps to BRAND-008 for SMS and BRAND-005 otherwise (my reading of the guidelines). Exclamation rule: more than one `!` (the guideline says "excessive"). SMS length counts headline + copy + CTA joined by spaces. Colour names in the product record are ignored for the word "green".
- Human GVR consensus defaults to the strict intersection of A and B unless `labels/adjudicated_rules.csv` exists; record how disagreements were resolved yourself.
- Image labelling cannot be fully blind: the text-free pipeline's typeset poster looks different from model-drawn text.
- Wilson CIs are for single proportions; kappa is computed over per-rule binary decisions.

## 6. Files you must fill in by hand

- `eval/heldout_queries.csv`: `query, gold_product_id, query_type` (50 queries: 25 named, 25 descriptive), written by you before tuning. Record who wrote them.
- `eval/labels/label_annotator_A.csv`, `_B.csv` (`rules_violated`, `notes`) and `claims_A.csv`, `claims_B.csv` (`supported (Y/N)`, `evidence_product_field`), after the benchmark runs.
- `eval/labels/image_label_A.csv`, `_B.csv` (`garbled_text_visible (Y/N)`), after the image run.
- Optional `eval/labels/adjudicated_rules.csv` (`output_id, rules_violated`) and `adjudicated_claims.csv` (`output_id, claim_no, supported (Y/N)`) with how disagreements were resolved.
- 20+ review decisions from 3+ reviewers (current log has 7, mostly one reviewer).
