"""poster.py - poster engine for Brandora.

Renders the final poster (background image + readability bands + text layers),
designs a starting layout for each image (font pairing from typography.py,
colours sampled from the photo, text sizes fitted to the space), discovers and
stores fonts, validates editor settings sent by the React UI and appends every
Approve / Reject decision to review_log.jsonl (useful evidence for the paper).

The Streamlit editor that used to live here is now the React "Poster studio";
this module only holds the logic that the FastAPI layer in app.py calls.
"""
import io
import json
import os
import re
import threading
from datetime import datetime
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

import typography

W = H = 1080
HERE = os.path.dirname(os.path.abspath(__file__))
FONT_DIR = os.path.join(HERE, "fonts")          # drop extra .ttf/.otf files here
LOG_PATH = os.path.join(HERE, "review_log.jsonl")
FONT_EXTS = (".ttf", ".otf")
_log_lock = threading.Lock()


# --------------------------------------------------------------------------
# Fonts
# --------------------------------------------------------------------------
def _font_dirs():
    return [
        FONT_DIR,
        "/System/Library/Fonts", "/System/Library/Fonts/Supplemental",
        "/Library/Fonts", os.path.expanduser("~/Library/Fonts"),
        "/usr/share/fonts", "/usr/local/share/fonts",
        os.path.expanduser("~/.fonts"), os.path.expanduser("~/.local/share/fonts"),
        r"C:\Windows\Fonts",
    ]


@lru_cache(maxsize=1)
def discover_fonts():
    """Return {display_name: path} for every .ttf/.otf found on the machine."""
    fonts = {}
    for directory in _font_dirs():
        if not os.path.isdir(directory):
            continue
        for root, _, files in os.walk(directory):
            for name in files:
                if name.lower().endswith(FONT_EXTS):
                    fonts.setdefault(os.path.splitext(name)[0], os.path.join(root, name))
    return dict(sorted(fonts.items(), key=lambda kv: kv[0].lower()))


def refresh_fonts():
    discover_fonts.cache_clear()
    return discover_fonts()


def font_registry():
    """{display name: (path, weight or None)}: designed Google faces first, then system fonts."""
    fonts = typography.designed_fonts()
    for name, path in discover_fonts().items():
        fonts.setdefault(name, (path, None))
    return fonts


def save_uploaded_font(filename, data):
    """Store an uploaded font in ./fonts so it persists. Returns the display name."""
    safe_name = os.path.basename(filename or "")
    if not safe_name.lower().endswith(FONT_EXTS):
        raise ValueError("Only .ttf and .otf font files are supported.")
    if len(data) > 15 * 1024 * 1024:
        raise ValueError("Font file is larger than 15 MB.")
    os.makedirs(FONT_DIR, exist_ok=True)
    target = os.path.join(FONT_DIR, safe_name)
    if not os.path.exists(target):
        with open(target, "wb") as fh:
            fh.write(data)
        refresh_fonts()
    return os.path.splitext(safe_name)[0]


def pick_default_font(fonts, bold):
    prefs = (["DejaVuSans-Bold", "Arial Bold", "Arial-BoldMT", "Helvetica Bold",
              "LiberationSans-Bold", "Arial Black"]
             if bold else
             ["DejaVuSans", "Arial", "Helvetica", "LiberationSans-Regular", "Verdana"])
    lowered = {n.lower(): n for n in fonts}
    for pref in prefs:
        if pref.lower() in lowered:
            return lowered[pref.lower()]
    for pref in prefs:
        for low, original in lowered.items():
            if pref.lower() in low:
                return original
    return next(iter(fonts), "")


@lru_cache(maxsize=256)
def load_font(path, size, wght=None):
    try:
        if path:
            font = ImageFont.truetype(path, size=int(size))
            if wght:
                # Variable font: set the weight axis, leave the others at their defaults.
                axes = font.get_variation_axes()
                font.set_variation_by_axes([
                    wght if axis.get("name") in (b"Weight", "Weight") else axis["default"]
                    for axis in axes
                ])
            return font
    except Exception:
        pass
    try:
        return ImageFont.load_default(size=int(size))   # Pillow >= 10.1
    except TypeError:
        return ImageFont.load_default()


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------
def hex_to_rgba(hex_color, opacity=1.0):
    h = hex_color.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), int(255 * opacity))


def _wrap(draw, text, font, max_w):
    lines = []
    for paragraph in text.split("\n"):
        words = paragraph.split()
        if not words:
            lines.append("")
            continue
        current = ""
        for word in words:
            candidate = f"{current} {word}".strip()
            if current and draw.textlength(candidate, font=font) > max_w:
                lines.append(current)
                current = word
            else:
                current = candidate
        lines.append(current)
    return lines


def _draw_scrim(draw, s):
    r, g, b, _ = hex_to_rgba(s["color"])
    top_h, bottom_h = int(s["top_h"]), int(s["bottom_h"])
    for y in range(top_h):
        a = int(255 * s["strength"] * (1 - y / top_h))
        draw.line((0, y, W, y), fill=(r, g, b, a))
    for y in range(H - bottom_h, H):
        a = int(255 * s["strength"] * ((y - (H - bottom_h)) / max(bottom_h, 1)))
        draw.line((0, y, W, y), fill=(r, g, b, a))


def _draw_block(draw, layer, font):
    max_w = layer["width"] / 100 * W
    lines = _wrap(draw, layer["text"], font, max_w)
    line_h = int(layer["size"] * layer["line_spacing"])
    block_h = line_h * max(len(lines), 1)
    cx, cy = layer["x"] / 100 * W, layer["y"] / 100 * H
    top = cy - block_h / 2
    fill = hex_to_rgba(layer["color"], layer["opacity"])
    stroke_fill = hex_to_rgba(layer["stroke_color"])
    for i, line in enumerate(lines):
        w = draw.textlength(line, font=font)
        if layer["align"] == "left":
            x = cx - max_w / 2
        elif layer["align"] == "right":
            x = cx + max_w / 2 - w
        else:
            x = cx - w / 2
        y = top + i * line_h
        if layer["shadow"]:
            draw.text((x + 3, y + 3), line, font=font, fill=(0, 0, 0, 120))
        draw.text((x, y), line, font=font, fill=fill,
                  stroke_width=int(layer["stroke"]), stroke_fill=stroke_fill)
    return (cx - max_w / 2, top, cx + max_w / 2, top + block_h)


def _draw_cta(draw, layer, font):
    text = layer["text"]
    left, top_off, right, bottom = font.getbbox(text)
    tw, th = right - left, bottom - top_off
    pad_x, pad_y = layer["pad"] * 1.5, layer["pad"] * 0.6
    bw, bh = tw + 2 * pad_x, th + 2 * pad_y
    cx, cy = layer["x"] / 100 * W, layer["y"] / 100 * H
    box = (cx - bw / 2, cy - bh / 2, cx + bw / 2, cy + bh / 2)
    draw.rounded_rectangle(box, radius=int(layer["radius"]),
                           fill=hex_to_rgba(layer["button_color"], layer["opacity"]))
    draw.text((cx - tw / 2 - left, cy - th / 2 - top_off), text, font=font,
              fill=hex_to_rgba(layer["color"]))
    return box


def render_poster(base_bytes, cfg, guides=False):
    """Compose the background image + scrim + text layers into a 1080x1080 poster."""
    base = Image.open(io.BytesIO(base_bytes)).convert("RGB")
    base = ImageOps.fit(base, (W, H), method=Image.Resampling.LANCZOS).convert("RGBA")

    scrim_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    _draw_scrim(ImageDraw.Draw(scrim_layer), cfg["scrim"])
    out = Image.alpha_composite(base, scrim_layer)

    text_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(text_layer)
    boxes = {}
    for name in ("headline", "copy"):
        layer = cfg["layers"][name]
        boxes[name] = _draw_block(draw, layer, load_font(layer["font_path"], layer["size"], layer.get("font_wght")))
    cta = cfg["layers"]["cta"]
    boxes["cta"] = _draw_cta(draw, cta, load_font(cta["font_path"], cta["size"], cta.get("font_wght")))
    out = Image.alpha_composite(out, text_layer)

    if guides:  # preview-only outlines to help with positioning
        g = ImageDraw.Draw(out)
        for name, box in boxes.items():
            g.rectangle(box, outline=(255, 64, 129, 255), width=2)
            g.text((box[0] + 4, box[1] + 2), name, fill=(255, 64, 129, 255))
    return out.convert("RGB")


def render_poster_png(base_bytes, cfg, guides=False):
    buf = io.BytesIO()
    render_poster(base_bytes, cfg, guides=guides).save(buf, format="PNG")
    return buf.getvalue()


# --------------------------------------------------------------------------
# Defaults
# --------------------------------------------------------------------------
LAYER_DEFAULTS = {
    "headline": dict(size=64, x=50, y=11, width=88, align="center", color="#182B30",
                     line_spacing=1.1, shadow=False, stroke=0, stroke_color="#FFFFFF",
                     opacity=1.0, bold=True),
    "copy": dict(size=28, x=50, y=80, width=84, align="center", color="#182B30",
                 line_spacing=1.3, shadow=False, stroke=0, stroke_color="#FFFFFF",
                 opacity=1.0, bold=False),
    "cta": dict(size=26, x=50, y=95, width=80, align="center", color="#FFFFFF",
                line_spacing=1.0, shadow=False, stroke=0, stroke_color="#FFFFFF",
                opacity=1.0, bold=True, button_color="#182B30", radius=20, pad=36),
}
SCRIM_DEFAULTS = dict(color="#FAF5EB", strength=0.15, top_h=300, bottom_h=380)


def build_default_cfg(texts, fonts):
    """Plain (non-UI) config; handy for tests and batch rendering."""
    layers = {}
    for name, d in LAYER_DEFAULTS.items():
        layer = dict(d)
        layer["text"] = texts[name]
        layer["font_path"] = fonts.get(pick_default_font(fonts, d["bold"]), "")
        layers[name] = layer
    return {"layers": layers, "scrim": dict(SCRIM_DEFAULTS)}


def editor_defaults(texts):
    """Plain starting layout with system fonts (used when no designed pairing is available)."""
    fonts = discover_fonts()
    layers = {}
    for name, d in LAYER_DEFAULTS.items():
        layer = {k: v for k, v in d.items() if k != "bold"}
        layer["text"] = texts[name]
        layer["font"] = pick_default_font(fonts, d["bold"])
        layers[name] = layer
    return {"fonts": list(font_registry()), "layers": layers, "scrim": dict(SCRIM_DEFAULTS)}


# --------------------------------------------------------------------------
# Designed starting layout: fonts that suit the mood, colours from the photo
# --------------------------------------------------------------------------
# Corner radius / padding of the CTA button per typography mood.
BUTTON_SHAPES = {
    "minimal": (10, 34), "elegant": (0, 40), "bold": (4, 36), "playful": (40, 34),
    "organic": (28, 34), "tech": (6, 32), "retro": (16, 36),
}
SCRIPT_FAMILIES = {"Pacifico", "Lobster", "Caveat", "Kalam", "Shrikhand"}


def _luminance(rgb):
    def channel(c):
        c /= 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (channel(float(c)) for c in rgb[:3])
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast(a, b):
    la, lb = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def _mix(rgb, target, amount):
    return tuple(int(round(c + (t - c) * amount)) for c, t in zip(rgb[:3], target))


def _hex(rgb):
    return "#{:02X}{:02X}{:02X}".format(*rgb[:3])


def _saturation(rgb):
    hi, lo = max(rgb[:3]), min(rgb[:3])
    return 0 if hi == 0 else (hi - lo) / hi


def _region_color(image, box):
    return image.crop(box).resize((1, 1), Image.Resampling.BOX).getpixel((0, 0))


def _palette(image, count=8):
    """[(rgb, share)] for the image's dominant colours, largest first."""
    small = image.resize((120, 120), Image.Resampling.BILINEAR)
    quant = small.quantize(colors=count, method=Image.Quantize.MEDIANCUT)
    pal = quant.getpalette()
    total = 120 * 120
    return [
        (tuple(pal[i * 3:i * 3 + 3]), n / total)
        for n, i in sorted(quant.getcolors(), reverse=True)
    ]


def _ink_for(background, dominant):
    """A deep or pale version of the photo's dominant colour, whichever reads better."""
    dark = _mix(_mix(dominant, (0, 0, 0), 0.82), (20, 20, 24), 0.4)
    light = _mix(dominant, (255, 255, 255), 0.93)
    return dark if _contrast(dark, background) >= _contrast(light, background) else light


def _low_contrast_share(image, box, ink):
    """Share of the area behind a text block where this ink would read poorly."""
    small = image.crop(box).resize((64, 24), Image.Resampling.BILINEAR)
    pixels = list(small.getdata())
    return sum(_contrast(ink, px) < 2.5 for px in pixels) / len(pixels)


def _halo(image, box, ink):
    """Thin outline in the opposite tone when the photo behind the text is busy."""
    if _low_contrast_share(image, box, ink) < 0.08:
        return {"stroke": 0}
    opposite = (250, 250, 250) if _luminance(ink) < 0.4 else (18, 18, 22)
    return {"stroke": 2, "stroke_color": _hex(_mix(ink, opposite, 0.9))}


def design_colors(image):
    """Text, band and button colours sampled from the image so the type belongs to the photo."""
    top_bg = _region_color(image, (0, 0, W, SCRIM_DEFAULTS["top_h"]))
    bottom_bg = _region_color(image, (0, H - SCRIM_DEFAULTS["bottom_h"], W, H))
    palette = _palette(image)
    dominant = palette[0][0]

    head_ink = _ink_for(top_bg, dominant)
    copy_ink = _ink_for(bottom_bg, dominant)
    copy_is_dark = _luminance(copy_ink) < 0.4
    band = (_mix(bottom_bg, (255, 255, 255), 0.7) if copy_is_dark
            else _mix(bottom_bg, (0, 0, 0), 0.65))

    # Button: the most vivid colour that occupies a real part of the photo.
    vivid = [c for c, share in palette if share >= 0.02] or [dominant]
    accent = max(vivid, key=lambda c: _saturation(c) * (0.6 + 0.4 * (1 - abs(_luminance(c) - 0.35))))
    if _saturation(accent) < 0.18:      # greyish photo: use the ink colour as the button
        accent = copy_ink
    if _contrast(accent, bottom_bg) < 2.2:
        accent = _mix(accent, (0, 0, 0) if _luminance(bottom_bg) > 0.4 else (255, 255, 255), 0.55)
    button_text = max([(255, 255, 255), _mix(accent, (0, 0, 0), 0.85)],
                      key=lambda c: _contrast(c, accent))

    return {
        "headline": head_ink, "copy": copy_ink, "band": band,
        "button": accent, "button_text": button_text,
        "shadow_headline": _luminance(head_ink) > 0.5,
        "shadow_copy": _luminance(copy_ink) > 0.5,
    }


def _fit(text, path, wght, max_w, max_h, max_lines, start, smallest, spacing):
    """(size, line count, fits): largest size at which the wrapped text fits the box."""
    draw = ImageDraw.Draw(Image.new("RGB", (8, 8)))
    for size in range(start, smallest - 1, -2):
        lines = _wrap(draw, text, load_font(path, size, wght), max_w)
        if len(lines) <= max_lines and size * spacing * len(lines) <= max_h:
            return size, len(lines), True
    return smallest, len(_wrap(draw, text, load_font(path, smallest, wght), max_w)), False


def subject_span(image):
    """(top, bottom) in px of the rows holding the product, or None.

    A backdrop, table edge or horizon is roughly one colour across its row,
    while the product stands out from the rest of the row it sits in. Rows
    with many such standout pixels are where the product is; text stays out.
    """
    small = image.resize((120, 120), Image.Resampling.BILINEAR).filter(ImageFilter.GaussianBlur(1))
    px = small.load()
    rows = []
    for y in range(120):
        line = [px[x, y] for x in range(120)]
        med = [sorted(c[i] for c in line)[60] for i in range(3)]
        rows.append(sum(
            sum((c[i] - med[i]) ** 2 for i in range(3)) > 40 ** 2 for c in line
        ) / 120)
    peak = max(rows)
    if peak < 0.03:
        return None
    hot = [y for y, v in enumerate(rows) if v > max(0.03, 0.25 * peak)]
    # Merge into runs (gaps under 5% of the height); keep the run with most mass.
    runs, start, prev = [], hot[0], hot[0]
    for y in hot[1:]:
        if y - prev > 6:
            runs.append((start, prev))
            start = y
        prev = y
    runs.append((start, prev))
    top, bottom = max(runs, key=lambda r: sum(rows[r[0]:r[1] + 1]))
    scale = H / 120
    return int(top * scale), int((bottom + 1) * scale)


def covers_text(family, weight, text):
    """True when this catalogue face has a real glyph for every character in text."""
    path, wght = typography.designed_fonts().get(typography.face_name(family, weight), (None, None))
    if not path:
        return False
    font = load_font(path, 40, wght)

    def glyph(ch):
        img = Image.new("L", (90, 90))
        ImageDraw.Draw(img).text((10, 10), ch, font=font, fill=255)
        return img.tobytes()

    missing = glyph("\U0010FFFD")   # what an absent glyph renders as
    return all(ch.isspace() or ord(ch) < 128 or glyph(ch) != missing for ch in set(text))


def design_poster(base_bytes, texts, pairing):
    """A finished starting layout for the editor, built around this image and pairing."""
    image = Image.open(io.BytesIO(base_bytes)).convert("RGB")
    image = ImageOps.fit(image, (W, H), method=Image.Resampling.LANCZOS)
    colors = design_colors(image)
    fonts = font_registry()
    style = pairing["style"]
    names = {part: typography.face_name(*pairing[part]) for part in ("headline", "body", "cta")}

    head_spacing = 1.22 if pairing["headline"][0] in SCRIPT_FAMILIES else 1.08
    layers = {}
    for name in ("headline", "copy", "cta"):
        layer = {k: v for k, v in LAYER_DEFAULTS[name].items() if k != "bold"}
        layer["text"] = texts[name]
        layer["font"] = names["body" if name == "copy" else name]
        layers[name] = layer

    head, copy, cta = layers["headline"], layers["copy"], layers["cta"]
    head.update(color=_hex(colors["headline"]), shadow=colors["shadow_headline"],
                line_spacing=head_spacing)
    copy.update(color=_hex(colors["copy"]), shadow=colors["shadow_copy"])
    radius, pad = BUTTON_SHAPES.get(style, (20, 36))
    cta.update(color=_hex(colors["button_text"]), button_color=_hex(colors["button"]),
               radius=radius, pad=pad)

    # Keep the text clear of the product: headline above it, copy below it (or
    # under the headline when there is no room below), button at the bottom.
    subj_top, subj_bottom = subject_span(image) or (H // 3, 2 * H // 3)
    gap, top_margin = 18, 44

    path, wght = fonts[head["font"]]
    head_room = max(110, min(230, subj_top - gap - top_margin))
    head["size"], lines, _ = _fit(head["text"], path, wght, head["width"] / 100 * W,
                                  head_room, 3, 96, 34, head_spacing)
    head_h = head["size"] * head_spacing * lines
    head["y"] = round((top_margin + head_h / 2) / H * 100, 2)

    path, wght = fonts[cta["font"]]
    cta["size"], _, _ = _fit(cta["text"], path, wght, 700, 60, 1, 30, 18, 1.0)
    cta_top = cta["y"] / 100 * H - (cta["size"] + 2 * pad * 0.6) / 2

    path, wght = fonts[copy["font"]]
    fit_copy = lambda room: _fit(copy["text"], path, wght, copy["width"] / 100 * W,
                                 room, 9, 34, 20, copy["line_spacing"])
    below = cta_top - gap - (subj_bottom + gap)
    above = subj_top - gap - (top_margin + head_h + gap)
    size, lines, fits = fit_copy(below)
    if fits:
        copy_bottom = cta_top - gap
    else:
        size, lines, fits = fit_copy(above)
        if fits:
            copy_bottom = top_margin + head_h + gap + size * copy["line_spacing"] * lines
        else:   # no clear space anywhere: sit above the button, outlined if needed
            size, lines, _ = fit_copy(250)
            copy_bottom = cta_top - gap
    copy["size"] = size
    copy_h = size * copy["line_spacing"] * lines
    copy_top = copy_bottom - copy_h
    copy["y"] = round((copy_top + copy_h / 2) / H * 100, 2)

    # The default band is faint, so check what actually sits behind each block.
    head.update(_halo(image, (60, top_margin, W - 60, int(top_margin + head_h)), colors["headline"]))
    copy.update(_halo(image, (90, int(copy_top), W - 90, int(copy_bottom)), colors["copy"]))

    scrim = dict(SCRIM_DEFAULTS, color=_hex(colors["band"]))
    return {"fonts": list(fonts), "layers": layers, "scrim": scrim,
            "design": {"style": style, **names}}


# --------------------------------------------------------------------------
# Editor payload -> render config (never trusts the browser)
# --------------------------------------------------------------------------
_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


def _num(value, lo, hi, default):
    try:
        return max(lo, min(hi, float(value)))
    except (TypeError, ValueError):
        return default


def _color(value, default):
    return value if isinstance(value, str) and _HEX.match(value) else default


def config_from_payload(payload):
    """Validate the JSON sent by the React editor and convert it to render config.

    Font *names* are mapped to paths on the server, so the browser can never
    point the renderer at an arbitrary file.
    """
    fonts = font_registry()
    fallback = discover_fonts()
    payload = payload or {}
    layers_in = payload.get("layers", {})
    layers = {}
    for name, d in LAYER_DEFAULTS.items():
        src = layers_in.get(name, {})
        layer = dict(d)
        layer["text"] = str(src.get("text", ""))[:600]
        path, wght = fonts.get(src.get("font")) or (fallback.get(pick_default_font(fallback, d["bold"]), ""), None)
        layer["font_path"], layer["font_wght"] = path, wght
        layer["size"] = int(_num(src.get("size"), 12, 160, d["size"]))
        layer["x"] = _num(src.get("x"), 0, 100, d["x"])
        layer["y"] = _num(src.get("y"), 0, 100, d["y"])
        layer["color"] = _color(src.get("color"), d["color"])
        if name == "cta":
            layer["button_color"] = _color(src.get("button_color"), d["button_color"])
            layer["radius"] = int(_num(src.get("radius"), 0, 60, d["radius"]))
            layer["pad"] = int(_num(src.get("pad"), 10, 80, d["pad"]))
        else:
            layer["width"] = _num(src.get("width"), 20, 100, d["width"])
            layer["align"] = src.get("align") if src.get("align") in ("left", "center", "right") else "center"
            layer["line_spacing"] = _num(src.get("line_spacing"), 0.9, 2.0, d["line_spacing"])
            layer["shadow"] = bool(src.get("shadow", d["shadow"]))
            layer["stroke"] = int(_num(src.get("stroke"), 0, 8, d["stroke"]))
            layer["stroke_color"] = _color(src.get("stroke_color"), d["stroke_color"])
            layer["opacity"] = _num(src.get("opacity"), 0.1, 1.0, d["opacity"])
        layers[name] = layer

    s_in, sd = payload.get("scrim", {}), SCRIM_DEFAULTS
    scrim = dict(
        color=_color(s_in.get("color"), sd["color"]),
        strength=_num(s_in.get("strength"), 0.0, 1.0, sd["strength"]),
        top_h=int(_num(s_in.get("top_h"), 0, 600, sd["top_h"])),
        bottom_h=int(_num(s_in.get("bottom_h"), 0, 700, sd["bottom_h"])),
    )
    return {"layers": layers, "scrim": scrim}


# --------------------------------------------------------------------------
# Review log (human-in-the-loop evidence)
# --------------------------------------------------------------------------
def log_review(decision, brief, original, final, seconds):
    record = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "decision": decision,
        "brief": brief,
        "original": original,
        "final": final,
        "text_edited": original != final,
        "review_seconds": round(seconds, 1),
    }
    with _log_lock:
        with open(LOG_PATH, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
