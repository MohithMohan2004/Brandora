"""Draw the Brandora mark at every size the web app manifest and the Android launcher need.

The mark is a "B" assembled from poster parts: a stem, a white headline block and an
indigo button block, on a flat ink tile. It says what the app makes (a laid-out ad)
instead of borrowing the generic AI sparkle. The web UI draws the same shapes as SVG
(`Logo` in frontend/src/icons.jsx), so keep the two in step. Run from the repo root:

    venv/bin/python android/tools/make_icons.py
"""
import os

from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RES = os.path.join(ROOT, "android", "app", "src", "main", "res")
PUBLIC = os.path.join(ROOT, "frontend", "public")
BIG = 1024
INK = (22, 22, 29, 255)
WHITE = (255, 255, 255, 255)
ACCENT = (124, 116, 255, 255)

# The mark on a 1024 grid, centred: stem, headline block (top), button block (bottom).
STEM = (300, 232, 400, 792)
HEAD = (458, 232, 668, 486)
BUTTON = (458, 544, 724, 792)


def _right_rounded(draw, box, fill):
    """A block with a square left edge and a fully rounded right end."""
    x0, y0, x1, y1 = box
    r = (y1 - y0) / 2
    draw.rounded_rectangle(box, radius=r, fill=fill)
    draw.rectangle((x0, y0, x0 + r, y1), fill=fill)


def mark(size, scale, accent=ACCENT, color=WHITE):
    """The mark alone on a transparent canvas, `scale` x its full size, centred."""
    layer = Image.new("RGBA", (BIG, BIG), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.rounded_rectangle(STEM, radius=24, fill=color)
    _right_rounded(d, HEAD, color)
    _right_rounded(d, BUTTON, accent)
    inner = int(BIG * scale / 0.547)   # the drawn mark spans ~55% of the grid
    out = Image.new("RGBA", (BIG, BIG), (0, 0, 0, 0))
    shrunk = layer.resize((inner, inner), Image.LANCZOS)
    out.alpha_composite(shrunk, ((BIG - inner) // 2, (BIG - inner) // 2))
    return out.resize((size, size), Image.LANCZOS) if size != BIG else out


def tile(radius_ratio=None):
    img = Image.new("RGBA", (BIG, BIG), (0, 0, 0, 0) if radius_ratio else INK)
    if radius_ratio:
        ImageDraw.Draw(img).rounded_rectangle((0, 0, BIG - 1, BIG - 1),
                                              radius=int(BIG * radius_ratio), fill=INK)
    return img


def save(img, path, size):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    img.resize((size, size), Image.LANCZOS).save(path, optimize=True)


def main():
    # Web: rounded app icon, plus a full-bleed maskable one with the mark inside the safe zone.
    web = tile(0.225)
    web.alpha_composite(mark(BIG, 0.55))
    save(web, os.path.join(PUBLIC, "icon-192.png"), 192)
    save(web, os.path.join(PUBLIC, "icon-512.png"), 512)
    maskable = tile()
    maskable.alpha_composite(mark(BIG, 0.42))
    save(maskable, os.path.join(PUBLIC, "icon-maskable-512.png"), 512)

    # Android adaptive icon: 108dp layers, the mark kept inside the 66dp safe zone.
    bg = tile()
    fg = mark(BIG, 0.36)
    mono = mark(BIG, 0.36, accent=WHITE)   # themed icons tint one colour, so no accent
    for density, px in {"mdpi": 108, "hdpi": 162, "xhdpi": 216, "xxhdpi": 324, "xxxhdpi": 432}.items():
        folder = os.path.join(RES, f"mipmap-{density}")
        save(bg, os.path.join(folder, "ic_launcher_background.png"), px)
        save(fg, os.path.join(folder, "ic_launcher_foreground.png"), px)
        save(mono, os.path.join(folder, "ic_launcher_monochrome.png"), px)
    print("icons written")


if __name__ == "__main__":
    main()
