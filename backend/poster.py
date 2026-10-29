"""poster.py - poster engine for Brandora.

Renders the final poster (background image + readability bands + text layers),
discovers and stores fonts, validates editor settings sent by the React UI and
appends every Approve / Reject decision to review_log.jsonl (useful evidence
for the paper).

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

from PIL import Image, ImageDraw, ImageFont, ImageOps

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


def load_font(path, size):
    try:
        if path:
            return ImageFont.truetype(path, size=int(size))
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
        boxes[name] = _draw_block(draw, layer, load_font(layer["font_path"], layer["size"]))
    cta = cfg["layers"]["cta"]
    boxes["cta"] = _draw_cta(draw, cta, load_font(cta["font_path"], cta["size"]))
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
SCRIM_DEFAULTS = dict(color="#FAF5EB", strength=0.75, top_h=300, bottom_h=380)


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
    """Everything the React editor needs to start: fonts, layer and band defaults."""
    fonts = discover_fonts()
    names = list(fonts)
    layers = {}
    for name, d in LAYER_DEFAULTS.items():
        layer = {k: v for k, v in d.items() if k != "bold"}
        layer["text"] = texts[name]
        layer["font"] = pick_default_font(fonts, d["bold"])
        layers[name] = layer
    return {"fonts": names, "layers": layers, "scrim": dict(SCRIM_DEFAULTS)}


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
    fonts = discover_fonts()
    payload = payload or {}
    layers_in = payload.get("layers", {})
    layers = {}
    for name, d in LAYER_DEFAULTS.items():
        src = layers_in.get(name, {})
        layer = dict(d)
        layer["text"] = str(src.get("text", ""))[:600]
        layer["font_path"] = fonts.get(
            src.get("font"), fonts.get(pick_default_font(fonts, d["bold"]), "")
        )
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
