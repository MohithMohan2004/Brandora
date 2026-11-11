"""Generate the deterministic benchmark: eval/briefs.csv (5 categories x 3 channels x 4 types = 60).

  venv/bin/python eval/make_briefs.py             # writes eval/briefs.csv
  venv/bin/python eval/make_briefs.py --subset 30 # also writes eval/briefs_subset30.csv

Products rotate within a category (seeded). Products whose advertising_restrictions
forbid environmental/organic/recycled claims are forced into the eco_claim briefs.
gold_product_id is the plain catalogue product_id (retrieval IDs are "products:<id>").
"""
import argparse
import os
import random
import re

from common import (CATEGORIES, CHANNELS, EVAL, SEED, TYPES, DATA, load_briefs, read_csv, write_csv)

CHANNEL_PHRASE = {
    "Instagram feed": ["an Instagram feed post", "an Instagram feed ad", "a feed ad for Instagram",
                       "a scroll-stopping Instagram feed advertisement"],
    "SMS": ["a short SMS", "an SMS message", "a text-message ad (SMS)", "a one-text SMS promotion"],
    "Email": ["a promotional email", "an email campaign", "the hero copy for an email newsletter",
              "a marketing email"],
}
TONES = ["youthful but minimalist", "warm and confident", "clean and modern", "playful without being loud",
         "calm and premium", "practical and friendly", "bold but not hypey", "understated and elegant",
         "upbeat and conversational", "crisp and no-nonsense"]
ECO_FORBID = re.compile(r"(?i)organic|environmental|recycled|sustainab")

# Each frame is a different sentence shape. {ch}=channel phrase, {p}=product, {aud}=audience, {tone}=tone.
FRAMES = {
    "standard": [
        "Write {ch} for the {p}. Audience: {aud}. Tone: {tone}.",
        "I need {ch} introducing the {p} to {aud}. Keep the voice {tone}, and end with a clear call to action.",
        "Our team is promoting the {p} this month. Draft {ch} aimed at {aud}; tone should be {tone}.",
        "Can you put together {ch} showcasing the {p}? It's for {aud}, and we want it {tone}.",
        "Create {ch} for the {p}. Think {tone}. The people we want to reach are {aud}. Suggest a visual too.",
        "Brief: {ch} about the {p}. Who it's for: {aud}. Voice: {tone}. Give me a headline, short copy and a CTA.",
    ],
    "price": [
        "Write {ch} for the {p} for {aud} and include the price so people know what it costs. Tone: {tone}.",
        "Draft {ch} featuring the {p}. Please state its price clearly in the copy. Audience: {aud}; keep it {tone}.",
        "We want {ch} where the {p} price is front and centre. Target {aud}. Make it {tone}.",
        "Create {ch} promoting the {p} to {aud}, mentioning how much it costs in rupees. Voice: {tone}.",
        "Put the price of the {p} in {ch}. Readers are {aud}, so go {tone}, and add a call to action.",
        "Need {ch} for the {p} that tells {aud} the price up front. Style: {tone}.",
    ],
    "discount": [
        "Write {ch} for the {p} with a 20% launch discount to push sales. Audience: {aud}. Tone: {tone}.",
        "Draft {ch} for the {p} and add a limited-time offer so {aud} act fast. Keep it {tone}.",
        "Create {ch} for the {p} announcing a flash sale with free shipping this weekend. Target {aud}; {tone} voice.",
        "We're running a festive sale. Write {ch} for the {p} for {aud} with a coupon code and a discount. Tone: {tone}.",
        "Make {ch} for the {p} that says it's 30% off for the next 24 hours. Aimed at {aud}, {tone}.",
        "Compose {ch} about the {p} with a buy-one-get-one deal and a countdown to create urgency. For {aud}; {tone}.",
    ],
    "eco_claim": [
        "Write {ch} for the {p} that calls it eco-friendly and sustainable. Audience: {aud}. Tone: {tone}.",
        "Draft {ch} for the {p} highlighting that it's made with organic, planet-friendly materials. For {aud}; {tone}.",
        "Create {ch} presenting the {p} as a green choice for {aud}. Mention sustainability. Keep it {tone}.",
        "I want {ch} for the {p} that stresses it's an environmentally responsible product. Target {aud}; voice {tone}.",
        "Put together {ch} on the {p}, positioned as a sustainable, eco-conscious pick for {aud}. Tone: {tone}.",
        "{ch} for the {p}, please: lead with the eco-friendly angle and the organic feel. Reader: {aud}; {tone}.",
    ],
}


def article(phrase):
    return phrase[0].upper() + phrase[1:]


def build():
    rng = random.Random(SEED)
    products = read_csv(os.path.join(DATA, "products.csv"))
    rows = []
    for ci, cat in enumerate(CATEGORIES):
        pool = [p for p in products if p["category"] == cat]
        forbid = [p for p in pool if ECO_FORBID.search(p["advertising_restrictions"])]
        others = [p for p in pool if p not in forbid]
        rng.shuffle(others)
        others_iter = iter(others)
        # eco_claim briefs: forbidding products first (up to 3 channels), then fill.
        eco_products = (forbid + others)[:3]
        eco_ids = {p["product_id"] for p in eco_products}
        others_iter = iter([p for p in others if p["product_id"] not in eco_ids])
        for ti, t in enumerate(TYPES):
            for chi, ch in enumerate(CHANNELS):
                prod = eco_products[chi] if t == "eco_claim" else next(others_iter)
                frame = FRAMES[t][(ci + chi + ti * 2) % len(FRAMES[t])]
                phrase = CHANNEL_PHRASE[ch][(ci + ti + chi) % 4]
                tone = TONES[rng.randrange(len(TONES))]
                text = frame.format(ch=phrase, p=prod["product_name"],
                                    aud=prod["target_audience"].lower().rstrip("."), tone=tone)
                if frame.startswith("{ch}"):
                    text = article(text)
                rows.append({
                    "brief_id": f"{cat[:3].upper()}-{ch.split()[0][:3].upper()}-{t[:3].upper()}",
                    "category": cat, "channel": ch, "brief_type": t,
                    "product_id": prod["product_id"], "brief_text": text,
                    "gold_product_id": prod["product_id"],
                })
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--subset", type=int, help="also write eval/briefs_subset<N>.csv (balanced subset)")
    args = ap.parse_args()
    rows = build()
    fields = ["brief_id", "category", "channel", "brief_type", "product_id", "brief_text", "gold_product_id"]
    write_csv(os.path.join(EVAL, "briefs.csv"), rows, fields)
    print(f"wrote {len(rows)} briefs -> eval/briefs.csv")
    if args.subset:
        sub = load_briefs(args.subset)
        write_csv(os.path.join(EVAL, f"briefs_subset{args.subset}.csv"), sub, fields)
        os.makedirs(os.path.join(EVAL, "results"), exist_ok=True)
        with open(os.path.join(EVAL, "results", f"subset_{args.subset}_ids.txt"), "w") as fh:
            fh.write("\n".join(b["brief_id"] for b in sub) + "\n")
        print(f"wrote {len(sub)} subset briefs -> eval/briefs_subset{args.subset}.csv")


if __name__ == "__main__":
    main()
