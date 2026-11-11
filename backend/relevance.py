"""relevance.py - how well a generated ad answers the marketer's brief.

The score shown in the app (0-100) blends up to four signals, each also 0-100:

  semantic    embeddinggemma cosine between the brief and the headline + copy + CTA.
              Raw cosines are not meaningful to a reader, so they are mapped onto
              0-100 with a window measured on this project's own outputs: unrelated
              brief/ad pairs sit around 0.26 (90th percentile 0.36), matched pairs at
              0.47-0.68. Cosine 0.25 maps to 0, 0.60 and above to 100.
  coverage    an LLM judge lists what the brief asks for (product, audience, tone,
              channel, message, specific details) and marks each met / partial /
              missed. Requests the writer deliberately left out because brand rules
              forbid them or the catalogue cannot support them ("withheld") are not
              counted against the ad: omitting an invented discount is correct.
  catalogue   how closely the best retrieved product matches the brief (the
              retrieval cosine, window 0.20-0.50). Low means the catalogue has
              nothing like what was asked for, so no copy can fully answer it.
  visual      a vision model rates the photo against the brief and the copy:
              right product, fitting setting and mood, supports the message.

Missing signals (no image yet, judge unavailable) are dropped and the weights
renormalised. This is a heuristic guide for the reviewer, not a guarantee.
"""
import json
import re

SEMANTIC_WINDOW = (0.25, 0.60)
CATALOGUE_WINDOW = (0.20, 0.50)
WEIGHTS = {"semantic": 0.30, "coverage": 0.35, "catalogue": 0.10, "visual": 0.25}
DEFAULT_THRESHOLD = 70
STATUS_POINTS = {"met": 1.0, "partial": 0.5, "missed": 0.0}
KINDS = ("product", "audience", "tone", "channel", "message", "detail")
MAX_ASPECTS = 7


def scaled(cosine, window):
    """Map a cosine onto 0-100 using a measured window; None stays None."""
    if cosine is None:
        return None
    lo, hi = window
    return round(max(0.0, min(1.0, (cosine - lo) / (hi - lo))) * 100)


def ad_text(texts):
    """The customer-facing words, in reading order."""
    return " ".join(t.strip() for t in (texts.get("headline", ""), texts.get("copy", ""),
                                        texts.get("cta", "")) if t and t.strip())


def judge_prompt(brief, texts, withheld, product=""):
    return f"""You check whether an advertisement delivers what a marketer's brief asked for.

BRIEF
{brief}

ADVERTISEMENT
Headline: {texts.get('headline', '')}
Copy: {texts.get('copy', '')}
Call to action: {texts.get('cta', '')}

CATALOGUE PRODUCT THE AD IS FOR
{product or 'Not known.'}

WHAT THE WRITER SAYS IT LEFT OUT ON PURPOSE
{withheld or 'Nothing.'}

List the distinct things the brief asks the ad to do (at most {MAX_ASPECTS}): the product,
the audience, the tone, the channel or format, the key message or benefit, and any specific
detail it requests (price, occasion, colour, imagery). Skip instructions about the output
format itself, such as "include a visual direction" or "include a call to action", and
skip optional requests ("mention the price only if useful"): they are fine either way.

For each one give:
- "aspect": 2-4 word label, e.g. "College students"
- "kind": one of {", ".join(KINDS)}
- "status": "met", "partial", "missed" or "withheld"
- "note": at most 14 words on why, quoting the ad where possible

Rules for the status:
- channel: met when the length and style suit that channel; the ad need not name it.
- product: met when the ad is clearly about the requested product, even if shortened.
- tone: judge the feel of the wording, not whether the tone word appears.
- Use "withheld" only when the ad leaves a request out because brand rules forbid it or the
catalogue does not support it (an invented discount, an unverified eco claim). Requests the
brief itself says to avoid ("do not invent a discount") are met when the ad avoids them.
Judge the words only, not any image. Reply with JSON only: {{"aspects": [...]}}"""


def _json_object(reply):
    match = re.search(r"\{.*\}", reply or "", re.DOTALL)
    if not match:
        raise ValueError("no JSON object in the reply")
    return json.loads(match.group(0))


def parse_aspects(reply):
    """Clean the judge's aspect list; raises ValueError when it is unusable."""
    aspects = []
    for item in _json_object(reply).get("aspects", [])[:MAX_ASPECTS]:
        if not isinstance(item, dict):
            continue
        status = str(item.get("status", "")).lower().strip()
        label = str(item.get("aspect", "")).strip()
        if status not in (*STATUS_POINTS, "withheld") or not label:
            continue
        kind = str(item.get("kind", "detail")).lower().strip()
        aspects.append({
            "aspect": label[:40],
            "kind": kind if kind in KINDS else "detail",
            "status": status,
            "note": str(item.get("note", "")).strip()[:140],
        })
    if not aspects:
        raise ValueError("the judge listed no aspects")
    return aspects


def coverage_score(aspects):
    counted = [STATUS_POINTS[a["status"]] for a in aspects if a["status"] in STATUS_POINTS]
    return round(100 * sum(counted) / len(counted)) if counted else None


VISUAL_QUESTION = """This photo will sit behind the words of an advertisement.

Brief: {brief}
Headline: {headline}
Copy: {copy}
Product that must be shown: {subject}

Rate the photo with whole numbers from 0 to 10 and reply with JSON only:
"subject" (the advertised product is clearly the hero of the photo),
"setting" (scene, colours and mood suit the brief's audience, tone and occasion),
"message" (the photo supports what the headline and copy say),
"note" (at most 16 words: the biggest strength or mismatch)."""


def visual_question(brief, texts, subject):
    return VISUAL_QUESTION.format(brief=brief.strip(), headline=texts.get("headline", ""),
                                  copy=texts.get("copy", ""), subject=subject or "the product")


def parse_visual(reply):
    data = _json_object(reply)
    parts = {}
    for key in ("subject", "setting", "message"):
        try:
            parts[key] = max(0, min(10, round(float(data[key]))))
        except (KeyError, TypeError, ValueError):
            raise ValueError(f"vision reply is missing {key!r}")
    score = round(10 * (0.45 * parts["subject"] + 0.30 * parts["setting"] + 0.25 * parts["message"]))
    return {"score": score, "parts": parts, "note": str(data.get("note", "")).strip()[:140]}


def overall(signals):
    """Weighted mean of the signals that are available."""
    present = {k: v for k, v in signals.items() if v is not None}
    if not present:
        return None
    total = sum(WEIGHTS[k] for k in present)
    return round(sum(WEIGHTS[k] * v for k, v in present.items()) / total)


def advice(signals, aspects):
    """One plain sentence on the weakest part, so a low score says what to do."""
    missed = [a["aspect"] for a in aspects or [] if a["status"] == "missed"]
    if signals.get("catalogue") is not None and signals["catalogue"] < 45:
        return "Your catalogue has no close match for this brief; check the product name or add it to the catalogue."
    if missed:
        return f"The copy does not yet address {', '.join(missed[:2]).lower()}. Edit the text or regenerate."
    if signals.get("visual") is not None and signals["visual"] < 55:
        return "The photo is a weak fit for the brief. Try generating the image again."
    if signals.get("semantic") is not None and signals["semantic"] < 50:
        return "The wording drifts from the brief. Name the product and audience more directly."
    return "The ad covers what the brief asks for."
