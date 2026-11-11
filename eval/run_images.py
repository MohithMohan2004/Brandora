"""Image comparison: finished-poster-with-text vs the project's text-free image + compositor.

  venv/bin/python eval/run_images.py --dry-run
  CLOUDFLARE_IMAGE_MODEL=@cf/black-forest-labs/flux-1-schnell venv/bin/python eval/run_images.py --limit 20 --resume

Briefs: the first 20 of the 30-brief subset in subset order, using their eval/runs/B2.jsonl output
(headline/copy/CTA). Per brief, two images from the app's configured image model
(recorded in the output; the task text assumes FLUX.1 schnell, the app default is FLUX.2 klein):
  text      one call; the scene plus "a finished advertising poster with the headline ... and
            a button reading ..." (no inspection, no retry)
  textfree  the project's own path: describe_scene -> build_image_prompt ->
            generate_clean_image (vision check + retries) -> design -> Pillow compositor
Saves eval/images/<brief_id>_{text|textfree}.png, eval/results/image_runs.csv, blind sheets
eval/image_label_{A,B}.csv (image_id, garbled_text_visible (Y/N), notes) with copies in
eval/images_blind/<image_id>.png, image_key.csv, and eval/images/contact_sheet.png.
Quota: --limit, --dry-run, --resume; stops cleanly on quota/permission/auth errors (HTTP 401/403/429
or a quota message). Cloudflare free tier is 10,000 neurons per day, resetting 00:00 UTC.
"""
import argparse
import csv
import hashlib
import io
import json
import os
import random
import re
import sys
import time
import uuid

sys.path.insert(0, os.path.dirname(__file__))
from common import EVAL, RUN_SEED as SEED, git_hash, import_app, load_briefs, write_csv  # noqa: E402

A = import_app()
import poster  # noqa: E402  (backend/poster.py, already on sys.path via import_app)

IMG = os.path.join(EVAL, "images")
BLIND = os.path.join(EVAL, "images_blind")
LABELS = EVAL
RESULTS = os.path.join(EVAL, "results")
FIELDS = ["brief_id", "pipeline", "image_path", "t_image", "t_compose", "attempts", "model", "prompt", "git_commit", "error"]
STOP = re.compile(r"\((?:401|403|429)\)|quota|neuron|rate.?limit|insufficient|permission", re.I)


def pick_briefs(limit):
    """The first `limit` briefs of the 30-brief subset, in subset order, with their B2 output.

    A brief whose B2 run is missing or failed is kept in the list with run=None so the
    failure is recorded rather than silently replaced by another brief.
    """
    path = os.path.join(EVAL, "runs", "B2.jsonl")
    if not os.path.exists(path):
        sys.exit("eval/runs/B2.jsonl not found; run eval/run_benchmark.py first")
    b2 = {}
    for l in open(path, encoding="utf-8"):
        if l.strip():
            r = json.loads(l)
            if not r.get("error") and r.get("parsed_headline"):
                b2[r["brief_id"]] = r
    out = []
    for b in load_briefs(30)[:limit]:
        out.append(b2.get(b["brief_id"]) or {"brief_id": b["brief_id"], "_missing_b2": True})
    return out


def gen_from_run(run, products):
    """Rebuild the dict the app's image functions expect, from a saved run (no new retrieval)."""
    retrieved = []
    for sid in run["retrieved_ids"]:
        kind, ident = sid.split(":", 1)
        if kind == "products":
            row = products[products["product_id"] == ident].iloc[0]
            retrieved.append({"source_id": sid, "kind": "product", "text": A.row_to_text(row, "product")})
    return {"id": uuid.uuid4().hex, "prompt": run.get("brief_text", ""), "ad_output": run["raw_output"],
            "retrieved": retrieved}


def text_prompt(scene, headline, cta):
    return (f"{scene}\n\nA finished square advertising poster built around this photograph. The headline "
            f"\"{headline}\" is written in large letters across the top, and a button reading \"{cta}\" "
            f"sits at the bottom. Professional poster design.")


def save_contact_sheet(rows):
    from PIL import Image, ImageDraw
    pairs = {}
    for r in rows:
        if not r["error"] and r["image_path"]:
            pairs.setdefault(r["brief_id"], {})[r["pipeline"]] = r["image_path"]
    pairs = {k: v for k, v in pairs.items() if len(v) == 2}
    if not pairs:
        return
    s, pad, head = 360, 12, 34
    sheet = Image.new("RGB", (2 * s + 3 * pad, head + len(pairs) * (s + pad + 20)), "white")
    d = ImageDraw.Draw(sheet)
    d.text((pad + 4, 8), "Finished poster with text (model-drawn)", fill="black")
    d.text((2 * pad + s + 4, 8), "Text-free image + compositor", fill="black")
    for i, (bid, v) in enumerate(sorted(pairs.items())):
        y = head + i * (s + pad + 20)
        for j, p in enumerate(("text", "textfree")):
            sheet.paste(Image.open(v[p]).convert("RGB").resize((s, s)), (pad + j * (s + pad), y + 18))
        d.text((pad, y + 2), bid, fill="black")
    sheet.save(os.path.join(IMG, "contact_sheet.png"))


def write_blind_sheets(rows):
    ok = [r for r in rows if not r["error"] and r["image_path"]]
    os.makedirs(BLIND, exist_ok=True)
    key, items = [], []
    for r in ok:
        iid = "I" + hashlib.sha1(f"{SEED}|{r['brief_id']}|{r['pipeline']}".encode()).hexdigest()[:8]
        with open(r["image_path"], "rb") as src, open(os.path.join(BLIND, iid + ".png"), "wb") as dst:
            dst.write(src.read())
        key.append({"image_id": iid, "brief_id": r["brief_id"], "pipeline": r["pipeline"]})
        items.append({"image_id": iid, "garbled_text_visible (Y/N)": "", "notes": ""})
    for who, off in (("A", 1), ("B", 2)):
        order = items[:]
        random.Random(SEED + off).shuffle(order)
        write_csv(os.path.join(LABELS, f"image_label_{who}.csv"), order, ["image_id", "garbled_text_visible (Y/N)", "notes"])
    write_csv(os.path.join(LABELS, "image_key.csv"), sorted(key, key=lambda k: k["image_id"]), ["image_id", "brief_id", "pipeline"])


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--limit", type=int, default=20, help="briefs to run (max 20)")
    ap.add_argument("--resume", action="store_true", help="skip images already saved without error")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    limit = min(args.limit, 20)
    runs = pick_briefs(limit)
    csv_path = os.path.join(RESULTS, "image_runs.csv")
    done = set()
    if os.path.exists(csv_path):
        if not (args.resume or args.dry_run):
            sys.exit(f"{csv_path} exists; pass --resume to continue it")
        done = {(r["brief_id"], r["pipeline"]) for r in csv.DictReader(open(csv_path, encoding="utf-8")) if not r["error"]}
    plan = [(r, p) for r in runs for p in ("text", "textfree") if (r["brief_id"], p) not in done]
    print(f"model: {A.CLOUDFLARE_IMAGE_MODEL}; briefs: {len(runs)}; images to make: {len(plan)}; already done: {2 * len(runs) - len(plan)}")
    if args.dry_run:
        for r, p in plan:
            print("  ", r["brief_id"], p)
        return
    if not (A.CLOUDFLARE_ACCOUNT_ID and A.CLOUDFLARE_API_TOKEN):
        sys.exit("Cloudflare credentials missing in .env (not printed)")
    os.makedirs(IMG, exist_ok=True)
    os.makedirs(RESULTS, exist_ok=True)
    products, _ = A.load_data()
    briefs = {b["brief_id"]: b for b in load_briefs()}
    rows = []
    if os.path.exists(csv_path):
        rows = [r for r in csv.DictReader(open(csv_path, encoding="utf-8")) if not r["error"]]
    scenes = {}
    stopped = False
    for run, pipeline in plan:
        bid = run["brief_id"]
        row = {"brief_id": bid, "pipeline": pipeline, "image_path": "", "t_image": "", "t_compose": "", "attempts": "",
               "model": A.CLOUDFLARE_IMAGE_MODEL, "prompt": "", "git_commit": git_hash(), "error": ""}
        try:
            if run.get("_missing_b2"):
                raise RuntimeError("no completed B2 output for this brief")
            run = dict(run, brief_text=briefs[bid]["brief_text"])
            gen = gen_from_run(run, products)
            if bid not in scenes:
                scenes[bid] = A.describe_scene(gen)
            scene = scenes[bid]
            out = os.path.join(IMG, f"{bid}_{pipeline}.png")
            if pipeline == "text":
                prompt = text_prompt(scene, run["parsed_headline"], run["parsed_cta"])
                t0 = time.perf_counter()
                png = A.cloudflare_generate_image(prompt, A.CLOUDFLARE_ACCOUNT_ID, A.CLOUDFLARE_API_TOKEN, seed=SEED)
                row.update(t_image=round(time.perf_counter() - t0, 2), attempts=1, prompt=prompt)
            else:
                prompt = A.build_image_prompt(scene)
                t0 = time.perf_counter()
                raw, verdict, attempts = A.generate_clean_image(prompt, A.product_subject(gen["retrieved"]))
                t1 = time.perf_counter()
                texts = {"headline": run["parsed_headline"], "copy": run["parsed_copy"], "cta": run["parsed_cta"]}
                gen["id"] = bid
                design = A._design(gen, raw, texts)
                png = poster.render_poster_png(raw, poster.config_from_payload(design))
                with open(os.path.join(IMG, f"{bid}_textfree_raw.png"), "wb") as fh:
                    fh.write(raw)
                row.update(t_image=round(t1 - t0, 2), t_compose=round(time.perf_counter() - t1, 2),
                           attempts=attempts, prompt=prompt)
            with open(out, "wb") as fh:
                fh.write(png)
            row["image_path"] = out
        except Exception as exc:
            msg = f"{type(exc).__name__}: {exc}"
            row["error"] = msg[:300]
            if STOP.search(msg):
                stopped = True
        rows.append(row)
        write_csv(csv_path, rows, FIELDS)
        print(f"{bid} {pipeline}: {row['error'] or str(row['t_image']) + 's'}", flush=True)
        if stopped:
            print("Quota/permission/auth error: stopping cleanly. Resume later with --resume.")
            break
    save_contact_sheet(rows)
    write_blind_sheets(rows)
    both = sum(1 for r in runs if all(any(x["brief_id"] == r["brief_id"] and x["pipeline"] == p and not x["error"]
                                          for x in rows) for p in ("text", "textfree")))
    print(f"briefs with BOTH pipelines completed: {both}/{len(runs)}")
    print(f"-> {IMG}, {RESULTS}/image_runs.csv, {LABELS}/image_label_[AB].csv")


if __name__ == "__main__":
    main()
