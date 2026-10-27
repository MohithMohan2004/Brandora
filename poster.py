"""poster_editor.py - interactive poster editor for Brandora.

Lets a reviewer edit the generated headline / copy / CTA text, choose fonts,
colours and sizes, reposition every element, then Approve or Reject the poster.
Every decision is appended to review_log.jsonl (useful evidence for the paper).
"""
import hashlib
import io
import json
import os
import time
from datetime import datetime

import streamlit as st
from PIL import Image, ImageDraw, ImageFont, ImageOps

W = H = 1080
HERE = os.path.dirname(os.path.abspath(__file__))
FONT_DIR = os.path.join(HERE, "fonts")          # drop extra .ttf/.otf files here
LOG_PATH = os.path.join(HERE, "review_log.jsonl")
FONT_EXTS = (".ttf", ".otf")


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


@st.cache_data(show_spinner=False)
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

    if guides:  # preview-only dashed-style outlines to help with positioning
        g = ImageDraw.Draw(out)
        for name, box in boxes.items():
            g.rectangle(box, outline=(255, 64, 129, 255), width=2)
            g.text((box[0] + 4, box[1] + 2), name, fill=(255, 64, 129, 255))
    return out.convert("RGB")


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
    with open(LOG_PATH, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


# --------------------------------------------------------------------------
# Streamlit UI
# --------------------------------------------------------------------------
def poster_editor_ui(base_image_bytes, defaults, brief="", ad_output=""):
    """Render the editor. `defaults` = {"headline":..., "copy":..., "cta":...}."""
    token = hashlib.md5((ad_output + str(len(base_image_bytes))).encode()).hexdigest()[:8]
    key = lambda *parts: "_".join((token,) + parts)

    # Optional: upload a custom font (saved into ./fonts so it persists)
    with st.expander("Add your own font (.ttf / .otf)"):
        uploaded = st.file_uploader("Font file", type=["ttf", "otf"], key=key("font_upload"))
        if uploaded is not None:
            os.makedirs(FONT_DIR, exist_ok=True)
            target = os.path.join(FONT_DIR, os.path.basename(uploaded.name))
            if not os.path.exists(target):
                with open(target, "wb") as fh:
                    fh.write(uploaded.getbuffer())
                discover_fonts.clear()
            st.caption(f"Saved to fonts/{os.path.basename(uploaded.name)}")
    fonts = discover_fonts() or {"(built-in default)": ""}
    font_names = list(fonts)

    st.session_state.setdefault(key("shown_at"), time.time())
    original = {k: defaults[k] for k in ("headline", "copy", "cta")}

    controls, preview = st.columns([1, 1.15], gap="large")

    with controls:
        tabs = st.tabs(["Headline", "Ad copy", "CTA button", "Background"])
        layers = {}
        for tab, name, label in zip(tabs, ("headline", "copy", "cta"),
                                    ("Headline", "Ad copy", "CTA text")):
            d = LAYER_DEFAULTS[name]
            with tab:
                text = st.text_area(label, value=defaults[name], key=key(name, "text"),
                                    height=110 if name == "copy" else 70)
                default_font = pick_default_font(fonts, d["bold"])
                font_name = st.selectbox(
                    "Font", font_names, key=key(name, "font"),
                    index=font_names.index(default_font) if default_font in font_names else 0)
                c1, c2 = st.columns(2)
                size = c1.slider("Size", 12, 160, d["size"], key=key(name, "size"))
                color = c2.color_picker("Text colour", d["color"], key=key(name, "color"))
                x = st.slider("Horizontal position (%)", 0, 100, d["x"], key=key(name, "x"))
                y = st.slider("Vertical position (%)", 0, 100, d["y"], key=key(name, "y"))
                layer = dict(d, text=text, font_path=fonts[font_name], size=size,
                             color=color, x=x, y=y)
                if name != "cta":
                    layer["width"] = st.slider("Text box width (%)", 20, 100, d["width"],
                                               key=key(name, "width"))
                    layer["align"] = st.radio("Alignment", ["left", "center", "right"],
                                              index=1, horizontal=True, key=key(name, "align"))
                    layer["line_spacing"] = st.slider("Line spacing", 0.9, 2.0,
                                                      d["line_spacing"], 0.05,
                                                      key=key(name, "ls"))
                    s1, s2 = st.columns(2)
                    layer["shadow"] = s1.checkbox("Drop shadow", d["shadow"],
                                                  key=key(name, "shadow"))
                    layer["stroke"] = s2.slider("Outline", 0, 8, d["stroke"],
                                                key=key(name, "stroke"))
                    layer["stroke_color"] = st.color_picker("Outline colour", d["stroke_color"],
                                                            key=key(name, "stroke_color"))
                    layer["opacity"] = st.slider("Text opacity", 0.1, 1.0, d["opacity"], 0.05,
                                                 key=key(name, "opacity"))
                else:
                    layer["button_color"] = st.color_picker("Button colour", d["button_color"],
                                                            key=key(name, "button_color"))
                    b1, b2 = st.columns(2)
                    layer["radius"] = b1.slider("Corner radius", 0, 60, d["radius"],
                                                key=key(name, "radius"))
                    layer["pad"] = b2.slider("Button padding", 10, 80, d["pad"],
                                             key=key(name, "pad"))
                layers[name] = layer
        with tabs[3]:
            st.caption("Soft colour bands behind the text keep it readable on any photo.")
            sd = SCRIM_DEFAULTS
            scrim = dict(
                color=st.color_picker("Band colour", sd["color"], key=key("scrim", "color")),
                strength=st.slider("Band strength", 0.0, 1.0, sd["strength"], 0.05,
                                   key=key("scrim", "strength")),
                top_h=st.slider("Top band height (px)", 0, 600, sd["top_h"],
                                key=key("scrim", "top")),
                bottom_h=st.slider("Bottom band height (px)", 0, 700, sd["bottom_h"],
                                   key=key("scrim", "bottom")),
            )
        show_guides = st.checkbox("Show position guides in preview", value=True,
                                  key=key("guides"))
        if st.button("Reset all edits", key=key("reset")):
            for k in [k for k in st.session_state if k.startswith(token + "_")]:
                del st.session_state[k]
            st.rerun()

    cfg = {"layers": layers, "scrim": scrim}
    with preview:
        st.image(render_poster(base_image_bytes, cfg, guides=show_guides),
                 use_container_width=True)
        final_text = {k: layers[k]["text"] for k in ("headline", "copy", "cta")}
        approved_key, rejected_key = key("approved"), key("rejected")
        elapsed = time.time() - st.session_state[key("shown_at")]

        if st.session_state.get(approved_key):
            st.success("Approved and logged. You can download the final poster.")
            buf = io.BytesIO()
            render_poster(base_image_bytes, cfg, guides=False).save(buf, format="PNG")
            st.download_button("Download approved poster", buf.getvalue(),
                               file_name="brandora_final_ad.png", mime="image/png",
                               use_container_width=True, key=key("download"))
        elif st.session_state.get(rejected_key):
            st.warning("Rejected and logged. Edit your brief and generate again.")
        else:
            a, r = st.columns(2)
            if a.button("Approve poster", type="primary", use_container_width=True,
                        key=key("approve")):
                log_review("approved", brief, original, final_text, elapsed)
                st.session_state[approved_key] = True
                st.rerun()
            if r.button("Reject", use_container_width=True, key=key("reject")):
                log_review("rejected", brief, original, final_text, elapsed)
                st.session_state[rejected_key] = True
                st.rerun()
            st.caption("Download unlocks after you approve. Every decision is saved to "
                       "review_log.jsonl.")