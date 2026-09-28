"""Make clean renders look like real-world captures (phone photos, screenshots)."""

from __future__ import annotations

import io
import random
from typing import Literal

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter

Difficulty = Literal["clean", "normal", "hard"]

_STRENGTH = {"clean": 0.0, "normal": 1.0, "hard": 2.0}


def _perspective_coeffs(src, dst):
    matrix = []
    for (x, y), (u, v) in zip(dst, src):
        matrix.append([x, y, 1, 0, 0, 0, -u * x, -u * y])
        matrix.append([0, 0, 0, x, y, 1, -v * x, -v * y])
    a = np.array(matrix, dtype=float)
    b = np.array(src, dtype=float).reshape(8)
    return np.linalg.solve(a, b).tolist()


def _table_background(rng: random.Random, w: int, h: int) -> Image.Image:
    base = np.array([rng.randint(60, 200) for _ in range(3)], dtype=float)
    noise = np.random.default_rng(rng.randint(0, 2**31)).normal(0, 12, (h, w, 1))
    return Image.fromarray(np.clip(base + noise, 0, 255).astype("uint8"))


def phone_photo(card: Image.Image, rng: random.Random, difficulty: Difficulty) -> Image.Image:
    s = _STRENGTH[difficulty]
    if s == 0:
        return _jpeg(card.convert("RGB"), 95)

    w, h = card.size
    pad = int(0.18 * w)
    canvas = _table_background(rng, w + 2 * pad, h + 2 * pad)
    canvas.paste(card, (pad, pad))

    j = 0.05 * s * w  # corner jitter in pixels
    src = [(pad, pad), (pad + w, pad), (pad + w, pad + h), (pad, pad + h)]
    dst = [(x + rng.uniform(-j, j), y + rng.uniform(-j, j)) for x, y in src]
    table = canvas.getpixel((2, 2))
    img = canvas.transform(canvas.size, Image.Transform.PERSPECTIVE, _perspective_coeffs(src, dst),
                           Image.Resampling.BICUBIC, fillcolor=table)
    img = img.rotate(rng.uniform(-6, 6) * s, resample=Image.Resampling.BICUBIC, fillcolor=table)

    # Uneven lighting: a soft gradient shadow across the card.
    grad = np.linspace(1.0, 1.0 - 0.25 * s * rng.random(), img.width)[None, :, None]
    if rng.random() < 0.5:
        grad = grad[:, ::-1]
    img = Image.fromarray(np.clip(np.asarray(img, dtype=float) * grad, 0, 255).astype("uint8"))

    img = ImageEnhance.Brightness(img).enhance(rng.uniform(1 - 0.15 * s, 1 + 0.1 * s))
    img = ImageEnhance.Contrast(img).enhance(rng.uniform(1 - 0.2 * s, 1 + 0.1 * s))
    img = img.filter(ImageFilter.GaussianBlur(rng.uniform(0, 0.9 * s)))
    img.thumbnail((1400, 1400))
    return _jpeg(img, rng.randint(int(85 - 20 * s), 92))


def screenshot(screen: Image.Image, rng: random.Random, difficulty: Difficulty) -> Image.Image:
    s = _STRENGTH[difficulty]
    img = screen.copy()
    img.thumbnail((int(1080 - 250 * s * rng.random()), 2400))
    return _jpeg(img, rng.randint(int(92 - 15 * s), 95))


def _jpeg(img: Image.Image, quality: int) -> Image.Image:
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality)
    buf.seek(0)
    return Image.open(buf).convert("RGB")


def scan(card: Image.Image, rng: random.Random, difficulty: Difficulty) -> Image.Image:
    """A flatbed scan: light paper background, small tilt, faded colors, mild blur."""
    s = _STRENGTH[difficulty]
    w, h = card.size
    pad = int(rng.uniform(0.02, 0.12) * w)
    shade = rng.randint(225, 250)
    canvas = Image.new("RGB", (w + 2 * pad, h + 2 * pad), (shade, shade, shade - rng.randint(0, 6)))
    canvas.paste(card, (pad + rng.randint(-pad // 2, pad // 2), pad + rng.randint(-pad // 2, pad // 2)))
    img = canvas.rotate(rng.uniform(-3, 3), resample=Image.Resampling.BICUBIC, fillcolor=(shade,) * 3)
    img = ImageEnhance.Color(img).enhance(rng.uniform(0.5, 1.0))  # faded print
    img = ImageEnhance.Contrast(img).enhance(rng.uniform(0.8, 1.05))
    img = img.filter(ImageFilter.GaussianBlur(rng.uniform(0, 0.6 + 0.4 * s)))
    img.thumbnail((rng.choice((900, 1100, 1400)),) * 2)
    return _jpeg(img, rng.randint(int(85 - 15 * s), 95))


def quarter_turn(img: Image.Image, rng: random.Random) -> tuple[Image.Image, int]:
    """Rotate by 90/180/270 degrees: scanned and photographed IDs are often sideways or upside down."""
    angle = rng.choice((90, 180, 270))
    return img.rotate(angle, expand=True), angle
