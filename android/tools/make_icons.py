"""Draw the Brandora mark (white four-point sparkle on an indigo gradient) at every
size the web app manifest and the Android launcher need. Run from the repo root:

    venv/bin/python android/tools/make_icons.py
"""
import os

from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RES = os.path.join(ROOT, "android", "app", "src", "main", "res")
PUBLIC = os.path.join(ROOT, "frontend", "public")
BIG = 1024
STOPS = [(0.0, (139, 123, 255)), (0.55, (79, 70, 229)), (1.0, (55, 48, 163))]


def gradient(size):
    """Diagonal three-stop gradient, top-left to bottom-right."""
    img = Image.new("RGB", (size, size))
    px = img.load()
    for y in range(size):
        for x in range(size):
            t = (x + y) / (2 * (size - 1))
            for (t0, c0), (t1, c1) in zip(STOPS, STOPS[1:]):
                if t <= t1:
                    k = (t - t0) / (t1 - t0)
                    px[x, y] = tuple(round(a + (b - a) * k) for a, b in zip(c0, c1))
                    break
    return img


def sparkle(size, scale):
    """White four-point star with concave sides, centred, `scale` of the canvas wide."""
    layer = Image.new("L", (size, size), 0)
    c, r = size / 2, size * scale / 2
    pull = r * 0.13   # how far the sides bow in towards the centre
    tips = [(c, c - r), (c + r, c), (c, c + r), (c - r, c)]
    controls = [(c + pull, c - pull), (c + pull, c + pull), (c - pull, c + pull), (c - pull, c - pull)]
    points = []
    for i, (p0, ctrl) in enumerate(zip(tips, controls)):
        p1 = tips[(i + 1) % 4]
        for s in range(48):
            t = s / 48
            points.append(((1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * ctrl[0] + t * t * p1[0],
                           (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * ctrl[1] + t * t * p1[1]))
    ImageDraw.Draw(layer).polygon(points, fill=255)
    return layer


def rounded(img, radius_ratio):
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, img.size[0] - 1, img.size[1] - 1],
                                           radius=int(img.size[0] * radius_ratio), fill=255)
    out = Image.new("RGBA", img.size, (0, 0, 0, 0))
    out.paste(img, (0, 0), mask)
    return out


def save(img, path, size):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    img.resize((size, size), Image.LANCZOS).save(path, optimize=True)


def main():
    bg = gradient(BIG)

    # Web: rounded app icon, plus a full-bleed maskable one with the mark inside the safe zone.
    web = bg.convert("RGBA")
    web.paste((255, 255, 255, 255), (0, 0), sparkle(BIG, 0.62))
    save(rounded(web, 0.225), os.path.join(PUBLIC, "icon-192.png"), 192)
    save(rounded(web, 0.225), os.path.join(PUBLIC, "icon-512.png"), 512)
    maskable = bg.convert("RGBA")
    maskable.paste((255, 255, 255, 255), (0, 0), sparkle(BIG, 0.46))
    save(maskable, os.path.join(PUBLIC, "icon-maskable-512.png"), 512)

    # Android adaptive icon: 108dp layers, the mark kept inside the 66dp safe zone.
    fg = Image.new("RGBA", (BIG, BIG), (0, 0, 0, 0))
    fg.paste((255, 255, 255, 255), (0, 0), sparkle(BIG, 0.40))
    mono = fg.copy()
    for density, px in {"mdpi": 108, "hdpi": 162, "xhdpi": 216, "xxhdpi": 324, "xxxhdpi": 432}.items():
        folder = os.path.join(RES, f"mipmap-{density}")
        save(bg, os.path.join(folder, "ic_launcher_background.png"), px)
        save(fg, os.path.join(folder, "ic_launcher_foreground.png"), px)
        save(mono, os.path.join(folder, "ic_launcher_monochrome.png"), px)
    print("icons written")


if __name__ == "__main__":
    main()
