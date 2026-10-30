"""evaluate.py - performance metrics for Brandora.

Measures each stage of the pipeline with standard metrics and writes
eval_results/metrics.json and eval_results/metrics.md.

  retrieval   Hit@1 / Hit@3 / Recall@k / MRR of the correct product, mandatory
              guideline coverage, query latency (local Ollama only)
  generation  format compliance, length compliance, price accuracy, invented-offer
              rate, restricted-claim mentions, citation precision, writer latency
  images      lettering-free rate, product fidelity, first-try pass rate, attempts,
              WCAG contrast of the typeset text, text/product overlap, font
              uniqueness, image-step latency
  review      approval rate, text edit rate and review time from review_log.jsonl

Run from the repo root (generation and images use Cloudflare Workers AI quota):
  venv/bin/python backend/evaluate.py                      # everything
  venv/bin/python backend/evaluate.py retrieval review     # local-only sections
  venv/bin/python backend/evaluate.py generation --n 20
"""
import argparse
import io
import json
import os
import random
import re
import statistics
import sys
import time
import uuid

import numpy as np
from PIL import Image, ImageDraw, ImageOps

import app as A
import poster
import typography

OUT_DIR = os.path.join(A.BASE_DIR, "..", "eval_results")
TONES = ["minimalist", "bold and energetic", "elegant", "playful", "warm and natural", "sleek and techy"]
OFFER_WORDS = re.compile(
    r"\b(\d+\s?% off|discount\w*|sale|coupon\w*|promo code|free shipping|limited[- ]time|"
    r"today only|hurry|last chance|buy one get one|bogo|cashback)\b", re.IGNORECASE)
STOPWORDS = {"do", "not", "claim", "or", "and", "the", "a", "an", "any", "of", "until", "verified",
             "against", "supplier", "documentation", "publish", "make", "claims", "content", "material",
             "specified", "in", "sample", "catalogue", "properties", "performance", "is", "are", "be"}


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def pct(values):
    return round(100 * sum(values) / len(values), 1) if values else None


def latency(values):
    if not values:
        return None
    v = sorted(values)
    p95 = v[min(len(v) - 1, int(round(0.95 * (len(v) - 1))))]
    return {"p50_s": round(statistics.median(v), 2), "p95_s": round(p95, 2),
            "mean_s": round(statistics.mean(v), 2), "max_s": round(v[-1], 2), "n": len(v)}


def product_rows():
    products, _ = A.load_data()
    return [row for _, row in products.iterrows()]


def banned_phrases(restriction):
    """'Do not claim genuine leather or RFID blocking.' -> [['genuine', 'leather'], ['rfid', 'blocking']]"""
    phrases = []
    for sentence in re.split(r"[.;]", restriction):
        if not re.match(r"\s*do not", sentence, re.IGNORECASE):
            continue
        body = re.sub(r"(?i)^\s*do not (claim|publish|make)\s*", "", sentence)
        for part in re.split(r"\bor\b|,|/", body):
            words = [w for w in re.findall(r"[a-z\-]+", part.lower()) if w not in STOPWORDS]
            if words:
                phrases.append(words)
    return phrases


def mentions(text, words):
    """All words of a banned phrase appear (6-letter stems, so 'waterproofing' ~ 'waterproof')."""
    low = text.lower()
    return all(w[:6] in low for w in words)


# --------------------------------------------------------------------------
# retrieval (local Ollama embeddings, no Cloudflare)
# --------------------------------------------------------------------------
def eval_retrieval(top_k=6):
    products, guidelines = A.load_data()
    mandatory = {f"guidelines:{g}" for g in guidelines.loc[
        guidelines["severity"].str.lower() == "mandatory", "guideline_id"]}
    rows = product_rows()
    queries = []
    for row in rows:
        target = f"products:{row['product_id']}"
        queries.append(("named", f"Create an Instagram ad for the {row['product_name']}.", target))
        queries.append(("descriptive",
                        f"Create an ad for a {row['category'].lower()} product made of {row['materials']} "
                        f"for {row['target_audience'].lower()}.", target))

    by_type = {}
    times, coverage = [], []
    for qtype, query, target in queries:
        t = time.perf_counter()
        retrieved = A.retrieve_context(query, products, guidelines, top_k)
        times.append(time.perf_counter() - t)
        ranked = [r["source_id"] for r in retrieved if r["kind"] == "product"]
        rank = ranked.index(target) + 1 if target in ranked else None
        by_type.setdefault(qtype, []).append(rank)
        coverage.append(mandatory <= {r["source_id"] for r in retrieved})

    def summary(ranks):
        return {"queries": len(ranks),
                "hit@1_%": pct([r == 1 for r in ranks]),
                "hit@3_%": pct([r is not None and r <= 3 for r in ranks]),
                f"recall@{top_k}_%": pct([r is not None for r in ranks]),
                "mrr": round(statistics.mean([1 / r if r else 0 for r in ranks]), 3)}

    return {
        "catalogue": {"products": len(products), "guidelines": len(guidelines)},
        "named_product_queries": summary(by_type["named"]),
        "descriptive_queries_no_product_name": summary(by_type["descriptive"]),
        "all_queries": summary(by_type["named"] + by_type["descriptive"]),
        "mandatory_guideline_coverage_%": pct(coverage),
        "query_latency": latency(times),
    }


# --------------------------------------------------------------------------
# generation (Cloudflare writer)
# --------------------------------------------------------------------------
def sample_briefs(n, seed):
    rng = random.Random(seed)
    rows = product_rows()
    chosen = rng.sample(rows, min(n, len(rows)))
    return [(row, f"Create an Instagram ad for the {row['product_name']} aimed at "
                  f"{row['target_audience'].lower()}. Tone: {rng.choice(TONES)}. Mention the price.")
            for row in chosen]


def eval_generation(n, seed):
    products, guidelines = A.load_data()
    results, writer_t, models = [], [], []
    for row, prompt in sample_briefs(n, seed):
        retrieved = A.retrieve_context(prompt, products, guidelines)
        t = time.perf_counter()
        try:
            output, model = A.generate_brief(A.build_generation_prompt(prompt, retrieved))
        except Exception as exc:   # counted as a failure, not a crash
            results.append({"product": row["product_name"], "error": str(exc)[:200]})
            continue
        writer_t.append(time.perf_counter() - t)
        models.append(model)
        s = A.parse_ad_sections(output)
        customer_text = " ".join([s["headline"], s["copy"], s["cta"]])
        prices = [int(p.replace(",", "")) for p in re.findall(r"(?:₹|rs\.?|inr)\s?([\d,]+)", customer_text, re.I)]
        cited = set(re.findall(r"[A-Z]+-\d{3}", s["sources"]))
        retrieved_ids = {r["source_id"].split(":", 1)[1] for r in retrieved}
        banned = [" ".join(p) for p in banned_phrases(row["advertising_restrictions"])
                  if mentions(customer_text, p)]
        results.append({
            "product": row["product_name"],
            "all_sections": all(s[k] for k in ("headline", "copy", "cta", "visual_direction",
                                               "why_it_fits", "missing", "sources", "type_style")),
            "headline_ok": 0 < len(s["headline"].split()) <= 8,
            "copy_ok": 15 <= len(s["copy"].split()) <= 30,
            "cta_ok": 1 <= len(s["cta"].split()) <= 4,
            "price_mentioned": bool(prices),
            "price_correct": all(p == int(row["price_inr"]) for p in prices) if prices else None,
            "invented_offer": bool(OFFER_WORDS.search(customer_text)),
            "restricted_mentions": banned,
            "citation_precision": (len(cited & retrieved_ids) / len(cited)) if cited else None,
            "cites_product": row["product_id"] in cited,
            "type_style_valid": typography.resolve_style(s["type_style"]) == re.sub(r"[^a-z]", "", s["type_style"].lower()),
            "copy_words": len(s["copy"].split()),
        })

    ok = [r for r in results if "error" not in r]
    priced = [r["price_correct"] for r in ok if r["price_correct"] is not None]
    precisions = [r["citation_precision"] for r in ok if r["citation_precision"] is not None]
    return {
        "briefs": len(results),
        "success_rate_%": pct([("error" not in r) for r in results]),
        "format_compliance_%": pct([r["all_sections"] for r in ok]),
        "length_compliance_%": {"headline<=8_words": pct([r["headline_ok"] for r in ok]),
                                "copy_15_30_words": pct([r["copy_ok"] for r in ok]),
                                "cta<=4_words": pct([r["cta_ok"] for r in ok])},
        "copy_words_median": statistics.median([r["copy_words"] for r in ok]) if ok else None,
        "price_accuracy_%": pct(priced),
        "price_mentioned_%": pct([r["price_mentioned"] for r in ok]),
        "invented_offer_rate_%": pct([r["invented_offer"] for r in ok]),
        "restricted_claim_mention_rate_%": pct([bool(r["restricted_mentions"]) for r in ok]),
        "citation_precision_%": round(100 * statistics.mean(precisions), 1) if precisions else None,
        "cites_target_product_%": pct([r["cites_product"] for r in ok]),
        "type_style_valid_%": pct([r["type_style_valid"] for r in ok]),
        "writer_fallback_rate_%": pct([m not in A.CLOUDFLARE_TEXT_MODELS[:1] for m in models]),
        "writer_latency": latency(writer_t),
        "flagged_for_review": [{"product": r["product"], "restricted": r["restricted_mentions"]}
                               for r in ok if r["restricted_mentions"] or r["invented_offer"]],
        "failures": [r for r in results if "error" in r],
    }


# --------------------------------------------------------------------------
# images + layout (Cloudflare image, vision and writer models)
# --------------------------------------------------------------------------
def text_blocks(cfg):
    """(top, bottom, layer) of the headline and copy blocks as rendered."""
    draw = ImageDraw.Draw(Image.new("RGB", (8, 8)))
    blocks = []
    for name in ("headline", "copy"):
        layer = cfg["layers"][name]
        font = poster.load_font(layer["font_path"], layer["size"], layer.get("font_wght"))
        lines = len(poster._wrap(draw, layer["text"], font, layer["width"] / 100 * poster.W))
        h = layer["size"] * layer["line_spacing"] * lines
        cy = layer["y"] / 100 * poster.H
        blocks.append((cy - h / 2, cy + h / 2, layer))
    return blocks


def block_contrast(base, cfg, top, bottom, layer):
    """WCAG contrast of the text colour against the median background behind it (band included)."""
    scrim = Image.new("RGBA", (poster.W, poster.H), (0, 0, 0, 0))
    poster._draw_scrim(ImageDraw.Draw(scrim), cfg["scrim"])
    bg = Image.alpha_composite(base.convert("RGBA"), scrim).convert("RGB")
    half = layer["width"] / 200 * poster.W
    cx = layer["x"] / 100 * poster.W
    region = np.asarray(bg.crop((int(cx - half), int(max(0, top)), int(cx + half), int(min(poster.H, bottom)))))
    median = tuple(int(c) for c in np.median(region.reshape(-1, 3), axis=0))
    return poster._contrast(poster.hex_to_rgba(layer["color"]), median)


def ask_vision(image_bytes, question):
    image = Image.open(io.BytesIO(image_bytes)).convert("RGB").resize((512, 512))
    buf = io.BytesIO()
    image.save(buf, format="JPEG", quality=85)
    url = "data:image/jpeg;base64," + __import__("base64").b64encode(buf.getvalue()).decode()
    reply = A.cloudflare_chat(A.VISION_MODEL, [{"type": "text", "text": question},
                                               {"type": "image_url", "image_url": {"url": url}}],
                              max_tokens=10, temperature=0)
    return reply.strip().lower().startswith("yes")


def eval_images(n, seed):
    products, guidelines = A.load_data()
    typography._save_history = lambda history: None   # don't use up real pairing history
    rows, step_t, pairs = [], [], []
    for row, prompt in sample_briefs(n, seed + 1):
        try:
            retrieved = A.retrieve_context(prompt, products, guidelines)
            output, _ = A.generate_brief(A.build_generation_prompt(prompt, retrieved))
            gen = {"id": uuid.uuid4().hex, "prompt": prompt, "ad_output": output, "retrieved": retrieved}
            t = time.perf_counter()
            scene = A.describe_scene(gen)
            image_bytes, verdict, attempts = A.generate_clean_image(A.build_image_prompt(scene))
            design = A._design(gen, image_bytes)
            step_t.append(time.perf_counter() - t)
            fidelity = ask_vision(image_bytes, f"Is the main subject of this photo a {row['product_name']} "
                                               f"({row['category'].lower()})? Answer yes or no.")
        except Exception as exc:
            rows.append({"product": row["product_name"], "error": str(exc)[:200]})
            continue

        cfg = poster.config_from_payload(design)
        base = ImageOps.fit(Image.open(io.BytesIO(image_bytes)).convert("RGB"), (poster.W, poster.H))
        span = poster.subject_span(base)
        blocks = text_blocks(cfg)
        overlap = sum(max(0, min(b, span[1]) - max(t, span[0])) for t, b, _ in blocks) if span else 0
        contrasts = [block_contrast(base, cfg, t, b, layer) for t, b, layer in blocks]
        pairs.append(f"{design['design']['headline']}|{design['design']['body']}")
        rows.append({
            "product": row["product_name"], "attempts": attempts,
            "lettering_free": not (verdict or {}).get("lettering", False),
            "tidy": not (verdict or {}).get("cluttered", False),
            "product_fidelity": fidelity,
            "text_overlaps_product": overlap > 0,
            "headline_contrast": round(contrasts[0], 2), "copy_contrast": round(contrasts[1], 2),
            "style": design["design"]["style"],
        })

    ok = [r for r in rows if "error" not in r]
    return {
        "posters": len(rows),
        "success_rate_%": pct([("error" not in r) for r in rows]),
        "lettering_free_rate_%": pct([r["lettering_free"] for r in ok]),
        "tidy_composition_rate_%": pct([r["tidy"] for r in ok]),
        "product_fidelity_%": pct([r["product_fidelity"] for r in ok]),
        "first_try_pass_rate_%": pct([r["attempts"] == 1 for r in ok]),
        "mean_attempts": round(statistics.mean([r["attempts"] for r in ok]), 2) if ok else None,
        "text_product_overlap_rate_%": pct([r["text_overlaps_product"] for r in ok]),
        "wcag_headline_large_text_AA_3:1_%": pct([r["headline_contrast"] >= 3 for r in ok]),
        "wcag_copy_AA_4.5:1_%": pct([r["copy_contrast"] >= 4.5 for r in ok]),
        "contrast_median": {"headline": statistics.median([r["headline_contrast"] for r in ok]) if ok else None,
                            "copy": statistics.median([r["copy_contrast"] for r in ok]) if ok else None},
        "font_pairing_uniqueness_%": round(100 * len(set(pairs)) / len(pairs), 1) if pairs else None,
        "image_step_latency": latency(step_t),
        "per_poster": rows,
    }


# --------------------------------------------------------------------------
# human review log
# --------------------------------------------------------------------------
def eval_review():
    try:
        with open(poster.LOG_PATH, encoding="utf-8") as fh:
            records = [json.loads(line) for line in fh if line.strip()]
    except OSError:
        records = []
    if not records:
        return {"decisions": 0}
    seconds = [r["review_seconds"] for r in records]
    return {
        "decisions": len(records),
        "approval_rate_%": pct([r["decision"] == "approved" for r in records]),
        "text_edit_rate_%": pct([r["text_edited"] for r in records]),
        "approved_without_edits_%": pct([r["decision"] == "approved" and not r["text_edited"] for r in records]),
        "review_time_s": {"median": statistics.median(seconds), "mean": round(statistics.mean(seconds), 1)},
    }


# --------------------------------------------------------------------------
# report
# --------------------------------------------------------------------------
def to_markdown(metrics):
    lines = ["# Brandora performance metrics", "", f"Run: {metrics['run_at']}", ""]
    for section, values in metrics.items():
        if not isinstance(values, dict):
            continue
        lines += [f"## {section}", "", "| Metric | Value |", "|---|---|"]
        for key, value in values.items():
            if key in ("per_poster", "flagged_for_review", "failures"):
                continue
            if isinstance(value, dict):
                value = ", ".join(f"{k}: {v}" for k, v in value.items())
            lines.append(f"| {key} | {value} |")
        lines.append("")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("sections", nargs="*", default=["retrieval", "generation", "images", "review"])
    parser.add_argument("--n", type=int, default=15, help="briefs for the generation section")
    parser.add_argument("--images", type=int, default=8, help="posters for the images section")
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()

    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, "metrics.json")
    try:
        with open(path, encoding="utf-8") as fh:
            metrics = json.load(fh)        # keep sections from earlier runs
    except (OSError, ValueError):
        metrics = {}
    runners = {"retrieval": eval_retrieval, "review": eval_review,
               "generation": lambda: eval_generation(args.n, args.seed),
               "images": lambda: eval_images(args.images, args.seed)}
    for section in args.sections:
        print(f"Evaluating {section}...", file=sys.stderr, flush=True)
        metrics[section] = runners[section]()
        metrics[section]["evaluated_at"] = time.strftime("%Y-%m-%d %H:%M")
    metrics["run_at"] = time.strftime("%Y-%m-%d %H:%M")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(metrics, fh, indent=2, ensure_ascii=False)
    with open(os.path.join(OUT_DIR, "metrics.md"), "w", encoding="utf-8") as fh:
        fh.write(to_markdown(metrics))
    print(json.dumps({k: v for k, v in metrics.items() if k in args.sections}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
