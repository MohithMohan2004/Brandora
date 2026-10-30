"""typography.py - designed font pairings for Brandora posters.

Every poster gets a headline / body / CTA font pairing chosen to match the ad's
typography mood (the TYPE STYLE line the writer model returns, or keywords in
the brief and visual direction). Pairings are drawn from a curated set of open
source Google Fonts, downloaded once into fonts/google/, and a small history
file keeps successive advertisements from reusing the same pairing.
"""
import json
import os
import random
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
GOOGLE_DIR = os.path.join(HERE, "fonts", "google")
HISTORY_PATH = os.path.join(HERE, "fonts", "pairing_history.json")
SOURCE = "https://raw.githubusercontent.com/google/fonts/main/ofl/"
_lock = threading.Lock()

WEIGHT_NAMES = {100: "Thin", 200: "ExtraLight", 300: "Light", 400: "Regular", 500: "Medium",
                600: "SemiBold", 700: "Bold", 800: "ExtraBold", 900: "Black"}


def V(path, *weights):
    """Variable font: one file, weight set through the wght axis."""
    return {"variable": path, "weights": weights}


def S(**files):
    """Static font: one file per weight (keys like w400=...)."""
    return {"static": {int(k[1:]): v for k, v in files.items()}}


FAMILIES = {
    # sans
    "Montserrat": V("montserrat/Montserrat[wght].ttf", 300, 400, 600, 700, 800),
    "DM Sans": V("dmsans/DMSans[opsz,wght].ttf", 400, 500, 700, 800),
    "Manrope": V("manrope/Manrope[wght].ttf", 400, 600, 800),
    "Outfit": V("outfit/Outfit[wght].ttf", 300, 400, 600, 700),
    "Sora": V("sora/Sora[wght].ttf", 300, 400, 600, 700),
    "Space Grotesk": V("spacegrotesk/SpaceGrotesk[wght].ttf", 400, 500, 700),
    "Josefin Sans": V("josefinsans/JosefinSans[wght].ttf", 400, 600, 700),
    "Karla": V("karla/Karla[wght].ttf", 400, 600, 700),
    "Work Sans": V("worksans/WorkSans[wght].ttf", 400, 500, 700),
    "Inter": V("inter/Inter[opsz,wght].ttf", 400, 600),
    "Raleway": V("raleway/Raleway[wght].ttf", 300, 400, 600, 700),
    "Nunito": V("nunito/Nunito[wght].ttf", 400, 600, 800),
    "Quicksand": V("quicksand/Quicksand[wght].ttf", 500, 700),
    "Rubik": V("rubik/Rubik[wght].ttf", 400, 500, 700),
    "Chivo": V("chivo/Chivo[wght].ttf", 400, 700, 900),
    "Cabin": V("cabin/Cabin[wdth,wght].ttf", 400, 600, 700),
    "Comfortaa": V("comfortaa/Comfortaa[wght].ttf", 400, 700),
    "Syne": V("syne/Syne[wght].ttf", 500, 700, 800),
    "Unbounded": V("unbounded/Unbounded[wght].ttf", 500, 700, 800),
    "Bricolage Grotesque": V("bricolagegrotesque/BricolageGrotesque[opsz,wdth,wght].ttf", 400, 700, 800),
    "Oswald": V("oswald/Oswald[wght].ttf", 400, 600, 700),
    "Fredoka": V("fredoka/Fredoka[wdth,wght].ttf", 400, 600),
    "Baloo 2": V("baloo2/Baloo2[wght].ttf", 400, 600, 800),
    "Orbitron": V("orbitron/Orbitron[wght].ttf", 500, 700),
    "Poppins": S(w400="poppins/Poppins-Regular.ttf", w600="poppins/Poppins-SemiBold.ttf",
                 w700="poppins/Poppins-Bold.ttf"),
    "Lato": S(w400="lato/Lato-Regular.ttf", w700="lato/Lato-Bold.ttf"),
    "Barlow": S(w400="barlow/Barlow-Regular.ttf", w500="barlow/Barlow-Medium.ttf"),
    "Barlow Condensed": S(w600="barlowcondensed/BarlowCondensed-SemiBold.ttf"),
    "Tenor Sans": S(w400="tenorsans/TenorSans-Regular.ttf"),
    # serif
    "Playfair Display": V("playfairdisplay/PlayfairDisplay[wght].ttf", 400, 600, 700, 800),
    "Bodoni Moda": V("bodonimoda/BodoniModa[opsz,wght].ttf", 500, 600, 700),
    "EB Garamond": V("ebgaramond/EBGaramond[wght].ttf", 400, 500, 600),
    "Lora": V("lora/Lora[wght].ttf", 400, 500, 600, 700),
    "Fraunces": V("fraunces/Fraunces[SOFT,WONK,opsz,wght].ttf", 300, 400, 600, 700),
    "Noto Serif": V("notoserif/NotoSerif[wdth,wght].ttf", 400, 600),
    "Cinzel": V("cinzel/Cinzel[wght].ttf", 500, 700),
    "Eczar": V("eczar/Eczar[wght].ttf", 500, 700),
    "DM Serif Display": S(w400="dmserifdisplay/DMSerifDisplay-Regular.ttf"),
    "Instrument Serif": S(w400="instrumentserif/InstrumentSerif-Regular.ttf"),
    "Prata": S(w400="prata/Prata-Regular.ttf"),
    "Gloock": S(w400="gloock/Gloock-Regular.ttf"),
    "Italiana": S(w400="italiana/Italiana-Regular.ttf"),
    "Marcellus": S(w400="marcellus/Marcellus-Regular.ttf"),
    "Yeseva One": S(w400="yesevaone/YesevaOne-Regular.ttf"),
    "Abril Fatface": S(w400="abrilfatface/AbrilFatface-Regular.ttf"),
    "Alfa Slab One": S(w400="alfaslabone/AlfaSlabOne-Regular.ttf"),
    "Patua One": S(w400="patuaone/PatuaOne-Regular.ttf"),
    # display / script / mono
    "Anton": S(w400="anton/Anton-Regular.ttf"),
    "Bebas Neue": S(w400="bebasneue/BebasNeue-Regular.ttf"),
    "Archivo Black": S(w400="archivoblack/ArchivoBlack-Regular.ttf"),
    "Bowlby One": S(w400="bowlbyone/BowlbyOne-Regular.ttf"),
    "Fjalla One": S(w400="fjallaone/FjallaOne-Regular.ttf"),
    "Staatliches": S(w400="staatliches/Staatliches-Regular.ttf"),
    "Righteous": S(w400="righteous/Righteous-Regular.ttf"),
    "Bungee": S(w400="bungee/Bungee-Regular.ttf"),
    "Shrikhand": S(w400="shrikhand/Shrikhand-Regular.ttf"),
    "Pacifico": S(w400="pacifico/Pacifico-Regular.ttf"),
    "Lobster": S(w400="lobster/Lobster-Regular.ttf"),
    "Monoton": S(w400="monoton/Monoton-Regular.ttf"),
    "Rye": S(w400="rye/Rye-Regular.ttf"),
    "Caveat": V("caveat/Caveat[wght].ttf", 600, 700),
    "Kalam": S(w700="kalam/Kalam-Bold.ttf"),
    "Space Mono": S(w400="spacemono/SpaceMono-Regular.ttf", w700="spacemono/SpaceMono-Bold.ttf"),
    "IBM Plex Mono": S(w400="ibmplexmono/IBMPlexMono-Regular.ttf"),
}

# Typography moods -> (headline faces, body faces). Each face is (family, weight).
STYLES = {
    "minimal": {
        "headline": [("Montserrat", 700), ("DM Sans", 700), ("Manrope", 800), ("Outfit", 600),
                     ("Sora", 600), ("Josefin Sans", 700), ("Tenor Sans", 400), ("Space Grotesk", 700)],
        "body": [("DM Sans", 400), ("Manrope", 400), ("Karla", 400), ("Work Sans", 400),
                 ("Inter", 400), ("Outfit", 300), ("Lato", 400)],
    },
    "elegant": {
        "headline": [("Playfair Display", 700), ("DM Serif Display", 400), ("Bodoni Moda", 600),
                     ("Italiana", 400), ("Prata", 400), ("Instrument Serif", 400), ("Cinzel", 700),
                     ("Marcellus", 400), ("EB Garamond", 600)],
        "body": [("Lora", 400), ("EB Garamond", 400), ("Raleway", 400), ("Montserrat", 300),
                 ("Tenor Sans", 400), ("Noto Serif", 400), ("Josefin Sans", 400)],
    },
    "bold": {
        "headline": [("Anton", 400), ("Bebas Neue", 400), ("Archivo Black", 400), ("Oswald", 700),
                     ("Bowlby One", 400), ("Barlow Condensed", 600), ("Fjalla One", 400),
                     ("Unbounded", 800), ("Bricolage Grotesque", 800)],
        "body": [("Barlow", 400), ("Work Sans", 500), ("Rubik", 400), ("Chivo", 400),
                 ("Poppins", 400), ("Inter", 400)],
    },
    "playful": {
        "headline": [("Pacifico", 400), ("Lobster", 400), ("Fredoka", 600), ("Baloo 2", 800),
                     ("Righteous", 400), ("Shrikhand", 400), ("Bungee", 400), ("Comfortaa", 700)],
        "body": [("Nunito", 400), ("Quicksand", 500), ("Poppins", 400), ("Baloo 2", 400),
                 ("Fredoka", 400), ("Comfortaa", 400)],
    },
    "organic": {
        "headline": [("Fraunces", 600), ("Lora", 600), ("Caveat", 700), ("Kalam", 700),
                     ("Eczar", 700), ("Patua One", 400), ("Yeseva One", 400), ("Gloock", 400)],
        "body": [("Lora", 400), ("Karla", 400), ("Cabin", 400), ("Nunito", 400),
                 ("Fraunces", 300), ("Work Sans", 400)],
    },
    "tech": {
        "headline": [("Space Grotesk", 700), ("Orbitron", 700), ("Syne", 800), ("Unbounded", 700),
                     ("Chivo", 900), ("Space Mono", 700), ("Sora", 700), ("Bricolage Grotesque", 700)],
        "body": [("Space Grotesk", 400), ("IBM Plex Mono", 400), ("Sora", 300), ("Manrope", 400),
                 ("Inter", 400), ("DM Sans", 400)],
    },
    "retro": {
        "headline": [("Alfa Slab One", 400), ("Abril Fatface", 400), ("Righteous", 400),
                     ("Monoton", 400), ("Rye", 400), ("Staatliches", 400), ("Shrikhand", 400),
                     ("Patua One", 400), ("Bungee", 400)],
        "body": [("Poppins", 400), ("Lato", 400), ("Cabin", 400), ("Josefin Sans", 400),
                 ("Barlow", 400), ("Space Mono", 400)],
    },
}

STYLE_KEYWORDS = {
    "minimal": "minimal minimalist clean simple modern whitespace understated calm neutral",
    "elegant": "elegant luxury luxurious premium sophisticated refined timeless classy editorial serif",
    "bold": "bold energetic energy sport sporty strong powerful dynamic urgent loud impact athletic",
    "playful": "playful fun kids cheerful quirky colourful colorful joyful whimsical friendly",
    "organic": "organic natural earthy eco sustainable handmade artisanal warm botanical cosy cozy",
    "tech": "tech technology futuristic digital innovative gadget smart electronic sleek",
    "retro": "retro vintage nostalgic nostalgia 70s 80s 90s throwback heritage",
}


# --------------------------------------------------------------------------
# Font files
# --------------------------------------------------------------------------
def _local_path(rel):
    return os.path.join(GOOGLE_DIR, os.path.basename(rel))


def face_file(family, weight):
    """(relative source path, weight to apply or None) for the nearest available weight."""
    spec = FAMILIES[family]
    if "variable" in spec:
        return spec["variable"], weight
    nearest = min(spec["static"], key=lambda w: abs(w - weight))
    return spec["static"][nearest], None


def face_name(family, weight):
    spec = FAMILIES[family]
    weights = spec.get("weights") or tuple(spec["static"])
    if len(weights) == 1:
        return family
    return f"{family} {WEIGHT_NAMES.get(weight, weight)}"


def _download(rel):
    target = _local_path(rel)
    if os.path.exists(target):
        return True
    try:
        response = requests.get(SOURCE + quote(rel), timeout=30)
        response.raise_for_status()
    except requests.RequestException:
        return False
    os.makedirs(GOOGLE_DIR, exist_ok=True)
    tmp = target + ".part"
    with open(tmp, "wb") as fh:
        fh.write(response.content)
    os.replace(tmp, target)
    return True


def ensure_faces(faces):
    """Download the files for these (family, weight) faces; returns the ones available."""
    available = []
    for family, weight in faces:
        if _download(face_file(family, weight)[0]):
            available.append((family, weight))
    return available


def _all_files():
    files = set()
    for spec in FAMILIES.values():
        files.update([spec["variable"]] if "variable" in spec else spec["static"].values())
    return sorted(files)


def prefetch_all():
    """Download the whole catalogue in the background so the editor can offer every face."""
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(_download, _all_files()))


def designed_fonts():
    """{display name: (path, weight or None)} for every catalogue face already on disk."""
    fonts = {}
    for family, spec in FAMILIES.items():
        weights = spec.get("weights") or tuple(spec["static"])
        for weight in weights:
            rel, wght = face_file(family, weight)
            path = _local_path(rel)
            if os.path.exists(path):
                fonts[face_name(family, weight)] = (path, wght)
    return fonts


# --------------------------------------------------------------------------
# Choosing a pairing
# --------------------------------------------------------------------------
def resolve_style(type_style, *texts):
    """Use the writer's TYPE STYLE when valid, otherwise score keywords in the brief."""
    word = re.sub(r"[^a-z]", "", (type_style or "").lower())
    if word in STYLES:
        return word
    blob = " ".join(texts).lower()
    scores = {
        style: sum(len(re.findall(rf"\b{re.escape(k)}\b", blob)) for k in words.split())
        for style, words in STYLE_KEYWORDS.items()
    }
    best = max(scores, key=scores.get)
    return best if scores[best] else "minimal"


def _load_history():
    try:
        with open(HISTORY_PATH, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return []


def _save_history(history):
    os.makedirs(os.path.dirname(HISTORY_PATH), exist_ok=True)
    with open(HISTORY_PATH, "w", encoding="utf-8") as fh:
        json.dump(history[-200:], fh)


def _cta_face(body, headline):
    """CTA uses a heavier cut of the body family, or the headline face if none exists."""
    family = body[0]
    spec = FAMILIES[family]
    weights = spec.get("weights") or tuple(spec["static"])
    heavy = [w for w in weights if w >= 600]
    return (family, min(heavy)) if heavy else headline


def choose_pairing(style, seed, covers=lambda part, face: True):
    """Pick a headline/body pairing for this style that recent ads have not used.

    covers(part, face) lets the caller reject faces missing glyphs its text needs (e.g. ₹).
    """
    rng = random.Random(seed)
    pool = STYLES[style]
    pairs = [(h, b) for h in pool["headline"] for b in pool["body"] if h[0] != b[0]]
    rng.shuffle(pairs)

    with _lock:
        history = _load_history()
        used = {entry["pair"]: i for i, entry in enumerate(history)}
        recent_heads = {entry["pair"].split("|")[0] for entry in history[-5:]}
        key = lambda p: f"{p[0][0]}|{p[1][0]}"
        # Prefer never-used pairs whose headline family hasn't appeared lately,
        # then any never-used pair, then the least recently used one.
        ranked = sorted(pairs, key=lambda p: (
            key(p) in used, p[0][0] in recent_heads, used.get(key(p), -1)))

        for headline, body in ranked:
            cta = _cta_face(body, headline)
            faces = {headline, body, cta}
            if (len(ensure_faces(faces)) == len(faces) and covers("headline", headline)
                    and covers("copy", body) and covers("cta", cta)):
                history.append({"pair": key((headline, body)), "style": style})
                _save_history(history)
                return {"style": style, "headline": headline, "body": body, "cta": cta}
    return None   # offline and nothing cached
