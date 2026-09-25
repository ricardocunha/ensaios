"""Draw Synthetic CNHs and Non-CNH decoys.

The layout is deliberately *inspired by* the CNH, not a replica. It has the same
labels and a similar field arrangement, but no national emblems, no security
features and a visible AMOSTRA / SYNTHETIC watermark. It is good enough to
teach a reader model where fields live, and useless as a forgery template.
"""

from __future__ import annotations

import math
import random

from PIL import Image, ImageDraw

from ..schema import CnhRecord
from ..transcription import printed_values
from .fonts import font

CARD_W, CARD_H = 1712, 1080  # ID-1 aspect ratio (85.6 x 54 mm)
INK = (20, 45, 30)
LABEL = (40, 110, 70)
WATERMARK = (200, 30, 30, 70)

# label -> (x, y, max_width) in card pixels
_LAYOUT: dict[str, tuple[int, int, int]] = {
    "NOME": (470, 190, 1190),
    "DOC. IDENTIDADE / ÓRG. EMISSOR / UF": (470, 290, 1190),
    "CPF": (470, 390, 560),
    "DATA NASCIMENTO": (1080, 390, 580),
    "FILIAÇÃO": (470, 490, 1190),
    "PERMISSÃO": (470, 670, 300),
    "ACC": (800, 670, 300),
    "CAT. HAB.": (1130, 670, 300),
    "Nº REGISTRO": (470, 770, 400),
    "VALIDADE": (900, 770, 350),
    "1ª HABILITAÇÃO": (1280, 770, 380),
    "OBSERVAÇÕES": (470, 870, 1190),
    "LOCAL": (60, 970, 980),
    "DATA EMISSÃO": (1080, 970, 580),
}


def _fit(draw: ImageDraw.ImageDraw, text: str, style: str, size: int, max_w: int):
    while size > 14 and draw.textlength(text, font=font(style, size)) > max_w:
        size -= 2
    return font(style, size)


def _background(rng: random.Random, w: int, h: int, base: tuple[int, int, int]) -> Image.Image:
    img = Image.new("RGB", (w, h), base)
    draw = ImageDraw.Draw(img)
    # Generic wavy line pattern (not a copy of any real security print).
    for k in range(0, h, 18):
        phase = rng.random() * math.tau
        pts = [(x, k + 6 * math.sin(x / 55 + phase)) for x in range(0, w + 20, 20)]
        draw.line(pts, fill=tuple(max(0, c - 18) for c in base), width=1)
    return img


def _watermark(img: Image.Image, text: str = "AMOSTRA • SYNTHETIC") -> Image.Image:
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    f = font("bold", max(40, img.width // 14))
    step = img.width // 2
    for y in range(-img.height, img.height * 2, step // 2):
        draw.text((0, y), f"  {text}  " * 4, font=f, fill=WATERMARK)
    layer = layer.rotate(25, expand=False)
    return Image.alpha_composite(img.convert("RGBA"), layer).convert("RGB")


def _photo_placeholder(draw: ImageDraw.ImageDraw, rng: random.Random, box) -> None:
    x0, y0, x1, y1 = box
    shade = rng.randint(150, 200)
    draw.rectangle(box, fill=(shade, shade, shade + 5), outline=INK, width=2)
    cx, w = (x0 + x1) // 2, x1 - x0
    draw.ellipse((cx - w // 5, y0 + 60, cx + w // 5, y0 + 60 + w // 2.4), fill=(shade - 50,) * 3)
    draw.pieslice((x0 + 30, y1 - w // 2, x1 - 30, y1 + w // 3), 180, 360, fill=(shade - 50,) * 3)


def _signature(draw: ImageDraw.ImageDraw, rng: random.Random, box) -> None:
    x0, y0, x1, y1 = box
    pts, x = [], x0 + 20
    while x < x1 - 20:
        pts.append((x, (y0 + y1) / 2 + rng.randint(-35, 35)))
        x += rng.randint(12, 30)
    draw.line(pts, fill=(15, 30, 90), width=4, joint="curve")


def render_card(record: CnhRecord, rng: random.Random) -> Image.Image:
    base = (rng.randint(205, 225), rng.randint(228, 242), rng.randint(200, 218))
    img = _background(rng, CARD_W, CARD_H, base)
    draw = ImageDraw.Draw(img)

    draw.rectangle((0, 0, CARD_W, 140), fill=(35, 95, 60))
    draw.text((60, 30), "CARTEIRA NACIONAL DE HABILITAÇÃO", font=font("bold", 50), fill="white")
    draw.text((60, 92), "AMOSTRA SINTÉTICA — SEM VALOR LEGAL", font=font("regular", 28), fill="white")

    _photo_placeholder(draw, rng, (60, 190, 430, 640))
    _signature(draw, rng, (60, 700, 430, 900))
    draw.text((60, 905), "ASSINATURA DO PORTADOR", font=font("regular", 18), fill=LABEL)

    values = printed_values(record)
    for label, (x, y, max_w) in _LAYOUT.items():
        draw.text((x, y), label, font=font("regular", 22), fill=LABEL)
        value = values[label]
        if label == "FILIAÇÃO":
            for i, parent in enumerate(record.filiacao):
                draw.text((x, y + 32 + i * 50), parent, font=_fit(draw, parent, "bold", 36, max_w), fill=INK)
        elif value:
            draw.text((x, y + 32), value, font=_fit(draw, value, "bold", 36, max_w), fill=INK)

    return _watermark(img)


def _fake_qr(draw: ImageDraw.ImageDraw, rng: random.Random, x: int, y: int, size: int) -> None:
    """A random block pattern that looks like a QR code but encodes nothing."""
    n = 29
    cell = size // n
    draw.rectangle((x, y, x + size, y + size), fill="white")
    for i in range(n):
        for j in range(n):
            if rng.random() < 0.45:
                draw.rectangle((x + i * cell, y + j * cell, x + (i + 1) * cell, y + (j + 1) * cell), fill="black")
    for fx, fy in ((0, 0), (n - 7, 0), (0, n - 7)):
        px, py = x + fx * cell, y + fy * cell
        draw.rectangle((px, py, px + 7 * cell, py + 7 * cell), fill="black")
        draw.rectangle((px + cell, py + cell, px + 6 * cell, py + 6 * cell), fill="white")
        draw.rectangle((px + 2 * cell, py + 2 * cell, px + 5 * cell, py + 5 * cell), fill="black")


def render_digital(record: CnhRecord, rng: random.Random) -> Image.Image:
    """A phone screenshot of a CNH Digital-style app screen."""
    w, h = 1080, 2340
    screen = Image.new("RGB", (w, h), (245, 247, 250))
    draw = ImageDraw.Draw(screen)
    draw.text((40, 20), f"{rng.randint(7, 22):02d}:{rng.randint(0, 59):02d}", font=font("bold", 34), fill="black")
    draw.rectangle((0, 90, w, 230), fill=(20, 70, 140))
    draw.text((40, 125), "CNH Digital (AMOSTRA)", font=font("bold", 52), fill="white")

    card = render_card(record, rng).resize((1000, round(1000 * CARD_H / CARD_W)))
    screen.paste(card, (40, 290))
    _fake_qr(draw, rng, 290, 1000, 500)
    draw.text((40, 1560), "Documento sintético gerado para pesquisa.", font=font("regular", 32), fill=(90, 90, 90))
    return screen


def render_non_cnh(rng: random.Random, fake) -> Image.Image:
    """Decoys the Extractor must reject: RG-like cards, invoices, random paperwork."""
    kind = rng.choice(("rg", "invoice", "letter"))
    if kind == "rg":
        img = _background(rng, CARD_W, CARD_H, (225, 215, 235))
        draw = ImageDraw.Draw(img)
        draw.text((60, 40), "REGISTRO GERAL — AMOSTRA", font=font("bold", 50), fill=INK)
        rows = [("NOME", fake.name().upper()), ("FILIAÇÃO", fake.name().upper()),
                ("NATURALIDADE", fake.city().upper()), ("DATA DE EXPEDIÇÃO", fake.date(pattern="%d/%m/%Y"))]
        for i, (label, value) in enumerate(rows):
            draw.text((470, 190 + i * 150), label, font=font("regular", 24), fill=LABEL)
            draw.text((470, 225 + i * 150), value, font=font("bold", 38), fill=INK)
        _photo_placeholder(draw, rng, (60, 190, 430, 640))
        return _watermark(img)

    img = Image.new("RGB", (1240, 1754), "white")
    draw = ImageDraw.Draw(img)
    title = "NOTA FISCAL — AMOSTRA" if kind == "invoice" else fake.company().upper()
    draw.text((80, 80), title, font=font("bold", 48), fill="black")
    for i in range(28):
        line = (f"{fake.word().upper():<18} {rng.randint(1, 9)} x R$ {rng.uniform(1, 500):8.2f}"
                if kind == "invoice" else fake.sentence())
        draw.text((80, 200 + i * 52), line, font=font("mono" if kind == "invoice" else "regular", 30), fill="black")
    return _watermark(img)
