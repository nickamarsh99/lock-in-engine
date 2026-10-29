"""Brand assets shared with the engine page: themes, fonts, and Pillow painting."""
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent.parent
FONTS = ROOT / "brand" / "fonts"
BRAND = json.loads((ROOT / "brand" / "brand.json").read_text())
THEMES = BRAND["themes"]


def rgb(hex_color):
    n = int(hex_color.lstrip("#"), 16)
    return (n >> 16, (n >> 8) & 255, n & 255)


def font(name, size):
    return ImageFont.truetype(str(FONTS / name), size)


def theme_for(key=None, pillar=None):
    if key in THEMES:
        return THEMES[key]
    return THEMES[BRAND["pillarTheme"].get(str(pillar), "dawn")]


def paint_background(theme, w, h, sun_scale=1.0):
    """Vertical gradient, a glowing sun, and fine grain, matching the carousel slides."""
    stops = theme["stops"]
    line = Image.new("RGB", (1, h))
    px = line.load()
    for y in range(h):
        t = y / (h - 1)
        for (o1, c1), (o2, c2) in zip(stops, stops[1:]):
            if o1 <= t <= o2:
                k = (t - o1) / ((o2 - o1) or 1)
                a, b = rgb(c1), rgb(c2)
                px[0, y] = tuple(round(a[i] + (b[i] - a[i]) * k) for i in range(3))
                break
    img = line.resize((w, h))

    sun = theme["sun"]
    if not sun["r"]:
        noise = Image.effect_noise((w, h), 48).convert("RGB")
        return Image.blend(img, ImageChops.overlay(img, noise), 0.1)
    cx, cy = sun["x"] * w, sun["y"] * h
    r = sun["r"] * (w / 1080) * sun_scale
    # Same falloff as the page's canvas glow: 50% at the disk edge, 14% at 40%, gone at 4.4x radius.
    yy, xx = np.mgrid[0:h, 0:w]
    d = np.hypot(xx - cx, yy - cy)
    r0, r1 = r * 0.85, r * 4.4
    t = np.clip((d - r0) / (r1 - r0), 0, 1)
    alpha = np.where(t < 0.4, 0.5 + (0.14 - 0.5) * t / 0.4, 0.14 * (1 - (t - 0.4) / 0.6))
    glow = Image.fromarray((alpha * 255).astype("uint8"), "L")
    img.paste(Image.new("RGB", (w, h), rgb(sun["c"])), (0, 0), glow)
    disk = Image.new("L", (w, h), 0)
    ImageDraw.Draw(disk).ellipse((cx - r, cy - r, cx + r, cy + r), fill=255)
    img.paste(Image.new("RGB", (w, h), rgb(sun["c"])), (0, 0), disk.filter(ImageFilter.GaussianBlur(1.2)))

    noise = Image.effect_noise((w, h), 48).convert("RGB")
    return Image.blend(img, ImageChops.overlay(img, noise), 0.08)


def wrap(draw, text, fnt, max_w):
    words, lines, cur = text.split(), [], ""
    for word in words:
        test = f"{cur} {word}".strip()
        if draw.textlength(test, font=fnt) > max_w and cur:
            lines.append(cur)
            cur = word
        else:
            cur = test
    if cur:
        lines.append(cur)
    return lines


def end_card(path, handle, theme, line="Follow for more", sub="Faith. Real food. Created rhythms.", w=1080, h=1920):
    img = paint_background(theme, w, h)
    d = ImageDraw.Draw(img)
    m = 96
    eyebrow = font("Barlow-Bold.ttf", 34)
    d.text((m, 640), "ONE FELLOW MAN AT A TIME", font=eyebrow, fill=rgb(theme["accent"]))
    big = font("BarlowCondensed-ExtraBold.ttf", 150)
    y = 700
    for ln in wrap(d, line.upper(), big, w - 2 * m):
        d.text((m, y), ln, font=big, fill=rgb(theme["fg"]))
        y += 140
    d.text((m, y + 30), handle, font=font("BarlowCondensed-ExtraBold.ttf", 96), fill=rgb(theme["accent"]))
    d.text((m, y + 160), sub, font=font("Newsreader-Italic.ttf", 54), fill=rgb(theme["fg"]))
    img.save(path)
    return path
