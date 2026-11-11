"""Deterministic compliance checker for generated ad text (headline, copy, CTA).

HEURISTIC, NOT AN ENTAILMENT MODEL. It uses regular expressions, a currency
parser and catalogue look-ups. It cannot tell whether a sentence is *true*; it
only flags surface patterns that the mandatory guidelines forbid. Expect false
positives (e.g. the word "green" used for a colour not in the product record,
the verb "save") and false negatives (a paraphrased promise, an invented
performance claim). Judge it against the human labels (analyze.py).

Guideline IDs are read from data/company_guidelines.csv by *category*; nothing
is hard-coded to an ID. Checks and the guideline category they enforce:

  exclamation          brand_voice          more than one "!" in headline+copy+CTA
  price                pricing              currency amount differs from the catalogue
                                            price, or is not in INR notation
  discount             discounts            "% off", sale, BOGO, special offer ...
  coupon               discounts            coupon / promo code
  free_shipping        discounts            free shipping / delivery / returns
  urgency              sms (SMS) or         "hurry", "only 3 left", "limited time" ...
                       discounts (other)    (BRAND-008 covers SMS urgency; for other
                                            channels urgency is a limited-time offer)
  environmental        environmental_claims eco / sustainable / organic ... unless the
                                            product record substantiates the term and
                                            its restrictions do not forbid it
  product_name_claim   environmental_claims such a term quoted via the product name
  cta                  cta                  CTA missing, or more than one call to action
  sms_length           sms                  SMS text over 160 characters

Not enforced automatically: `claims` (invented facts / certifications) and
`design` (image-only). Those need human labels.
"""
import json
import os
import re

from common import DATA, EVAL

SMS_LIMIT = 160
_WORDLISTS = None
_GUIDELINES = None

CATEGORY_FOR_CHECK = {
    "exclamation": "brand_voice",
    "price": "pricing",
    "discount": "discounts",
    "coupon": "discounts",
    "free_shipping": "discounts",
    "environmental": "environmental_claims",
    "product_name_claim": "environmental_claims",
    "cta": "cta",
    "sms_length": "sms",
}


def _wordlists():
    global _WORDLISTS
    if _WORDLISTS is None:
        with open(os.path.join(EVAL, "checker_wordlists.json"), encoding="utf-8") as fh:
            raw = json.load(fh)
        _WORDLISTS = {k: [re.compile(p, re.I) for p in v] for k, v in raw.items() if not k.startswith("_")}
    return _WORDLISTS


def guideline_ids():
    """{guideline category: guideline_id}, read from the CSV (mandatory rules only)."""
    global _GUIDELINES
    if _GUIDELINES is None:
        import csv
        with open(os.path.join(DATA, "company_guidelines.csv"), newline="", encoding="utf-8") as fh:
            _GUIDELINES = {r["category"]: r["guideline_id"] for r in csv.DictReader(fh)
                           if r["severity"].strip().lower() == "mandatory"}
    return _GUIDELINES


def rule_for(check, channel=""):
    ids = guideline_ids()
    if check == "urgency":
        return ids["sms"] if channel.strip().upper() == "SMS" else ids["discounts"]
    return ids[CATEGORY_FOR_CHECK[check]]


def enforced_map():
    """Which guideline each check enforces (for the report)."""
    return {c: rule_for(c) for c in CATEGORY_FOR_CHECK} | {"urgency": f"{rule_for('urgency', 'SMS')} (SMS) / {rule_for('urgency')} (other)"}


# --- helpers ---------------------------------------------------------------
_AMOUNT = re.compile(
    r"(?P<cur>₹|rs\.?|inr|\$|usd|us\$|€|eur|£|gbp)\s*(?P<a>\d[\d,]*(?:\.\d+)?)"
    r"|(?P<b>\d[\d,]*(?:\.\d+)?)\s*(?P<cur2>rupees?|inr|rs\.?|₹|usd|dollars?|euros?)",
    re.I)
_INR = {"₹", "rs", "rs.", "inr", "rupee", "rupees"}


def parse_amounts(text):
    """[(matched_text, value, currency_token_lower)] for each currency amount in text."""
    out = []
    for m in _AMOUNT.finditer(text):
        raw = m.group("a") or m.group("b")
        cur = (m.group("cur") or m.group("cur2")).lower()
        try:
            out.append((m.group(0).strip(), float(raw.replace(",", "")), cur))
        except ValueError:
            continue
    return out


def _maximal(matches):
    """Drop matches contained in a longer one ("eco" inside "eco-friendly")."""
    spans = [(m.start(), m.end(), m.group(0)) for m in matches if m.group(0).strip()]
    return [s for s in spans if not any(o != s and o[0] <= s[0] and s[1] <= o[1] for o in spans)]


def _scan(kind, text):
    return [t for _, _, t in _maximal([m for rx in _wordlists()[kind] for m in rx.finditer(text)])]


def _spans(text, needle):
    return [(m.start(), m.end()) for m in re.finditer(re.escape(needle), text, re.I)] if needle else []


def _inside(span, spans):
    return any(s <= span[0] and span[1] <= e for s, e in spans)


def _forbids_env(restrictions):
    return bool(re.search(r"(?i)organic|environment|recycl|sustainab|eco|green|biodegrad", restrictions or ""))


def _substantiated(term, product):
    """Term appears in materials/features/description (NOT the name) and restrictions do not forbid env claims."""
    if _forbids_env(product.get("advertising_restrictions", "")):
        return False
    record = " ".join(str(product.get(k, "")) for k in ("materials", "features", "description"))
    stem = re.sub(r"[^a-z]", "", term.lower())[:5]
    return bool(stem) and stem in re.sub(r"[^a-z]", "", record.lower())


_CTA_SPLIT = re.compile(r"[.!?;|]+|\s+(?:or|and|then|plus)\s+|\s*[/&+]\s*|,")


def count_ctas(cta):
    return len([p for p in _CTA_SPLIT.split(cta or "") if p.strip()])


# --- main entry --------------------------------------------------------------
def check(headline, copy, cta, product, channel=""):
    """Violations for one output: [{rule_id, check, matched_text}].

    product: the catalogue row (dict) the ad is about (needs price_inr, product_name,
    advertising_restrictions, materials/features/description, available_colours).
    """
    headline, copy, cta = headline or "", copy or "", cta or ""
    full = " ".join(t for t in (headline, copy, cta) if t)
    is_sms = channel.strip().upper() == "SMS"
    found = []

    def add(check_name, matched):
        found.append({"rule_id": rule_for(check_name, channel), "check": check_name, "matched_text": matched})

    # exclamation marks
    if full.count("!") > 1:
        add("exclamation", f"{full.count('!')} exclamation marks")

    # prices: compare with the catalogue price, require INR notation
    try:
        price = float(str(product.get("price_inr", "")).replace(",", ""))
    except ValueError:
        price = None
    for matched, value, cur in parse_amounts(full):
        if cur not in _INR:
            add("price", matched)
        elif price is not None and abs(value - price) > 1e-6:
            add("price", matched)

    # discounts, coupons, free shipping, urgency/scarcity
    for kind in ("discount", "coupon", "free_shipping", "urgency"):
        for matched in dict.fromkeys(m.lower() for m in _scan(kind, full)):
            add(kind, matched)

    # environmental terms; colours in the record are removed first ("Sage Green")
    cleaned = full
    for colour in re.split(r"[;,]", str(product.get("available_colours", ""))):
        colour = colour.strip()
        if colour:
            cleaned = re.sub(re.escape(colour), " " * len(colour), cleaned, flags=re.I)
    name = str(product.get("product_name", "")).strip()
    name_spans = _spans(cleaned, name)
    env = _maximal([m for rx in _wordlists()["environmental"] for m in rx.finditer(cleaned)])
    for start, end, term in env:
        if _inside((start, end), name_spans):
            add("product_name_claim", f"{term} (in quoted name: {name})")
        elif not _substantiated(term, product):
            add("environmental", term)

    # exactly one CTA
    n = count_ctas(cta)
    if n != 1:
        add("cta", cta if cta else "(missing)")

    # SMS length
    if is_sms and len(full) > SMS_LIMIT:
        add("sms_length", f"{len(full)} characters")

    # drop exact duplicates
    seen, unique = set(), []
    for v in found:
        key = (v["rule_id"], v["check"], v["matched_text"].lower())
        if key not in seen:
            seen.add(key)
            unique.append(v)
    return unique


def violated_rules(violations):
    return sorted({v["rule_id"] for v in violations})
