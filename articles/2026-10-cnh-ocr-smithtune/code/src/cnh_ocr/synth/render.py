"""Draw Synthetic CNHs and Non-CNH decoys.

The layout is *inspired by* the CNH, not a replica: same labels, but no emblems, no
security features and a visible AMOSTRA / SYNTHETIC watermark (ADR-0002).
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from datetime import datetime

from PIL import Image, ImageDraw

from ..schema import CnhRecord
from ..transcription import printed_values
from .fonts import font

CARD_W, CARD_H = 1712, 1080  # ID-1 aspect ratio (85.6 x 54 mm)
INK = (20, 45, 30)
LABEL = (40, 110, 70)
WATERMARK = (200, 30, 30, 70)
# Faker's date() is bounded by "now", so the same seed gave different dates on
# different build days. Pin the bound (same value as build.TODAY).
_DATE_END = datetime(2026, 9, 25)


def _fake_date(fake) -> str:
    return fake.date(pattern="%d/%m/%Y", end_datetime=_DATE_END)

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


# ---- v2: domain randomization -----------------------------------------------
# Generic variation (palette, spacing, label spelling) so a Reader can't equate "CNH"
# with one exact look. Not a copy of any real card (ADR-0002).

PALETTES = [  # (card base, header band, label ink)
    ((212, 234, 208), (35, 95, 60), (40, 110, 70)),     # pale green
    ((226, 238, 214), (70, 120, 70), (60, 100, 60)),    # yellow-green
    ((236, 232, 214), (120, 100, 60), (100, 80, 40)),   # beige
    ((214, 228, 238), (30, 70, 120), (40, 80, 120)),    # pale blue
    ((238, 222, 228), (120, 50, 80), (110, 60, 80)),    # pink
    ((240, 240, 236), (60, 60, 60), (80, 80, 80)),      # near-white / grey
]

LABEL_VARIANTS = {
    "CAT. HAB.": ("CAT. HAB.", "CAT.HAB.", "CAT HAB"),
    "Nº REGISTRO": ("Nº REGISTRO", "N° REGISTRO", "Nº DE REGISTRO"),
    "1ª HABILITAÇÃO": ("1ª HABILITAÇÃO", "1º HABILITAÇÃO", "1ª HAB."),
    "DOC. IDENTIDADE / ÓRG. EMISSOR / UF": ("DOC. IDENTIDADE / ÓRG. EMISSOR / UF", "DOC. IDENTIDADE/ÓRG EMISSOR UF",
                                            "DOC IDENTIDADE / ORG EMISSOR / UF"),
    "DATA NASCIMENTO": ("DATA NASCIMENTO", "DATA DE NASCIMENTO"),
    "DATA EMISSÃO": ("DATA EMISSÃO", "DATA DE EMISSÃO"),
    "OBSERVAÇÕES": ("OBSERVAÇÕES", "OBSERVACOES"),
}


@dataclass(frozen=True)
class Style:
    base: tuple[int, int, int]
    header: tuple[int, int, int]
    label_ink: tuple[int, int, int]
    value_font: str
    boxed: bool
    label_below: bool
    jitter: int
    labels: dict[str, str]
    show_subtitle: bool
    watermark_alpha: int
    stamp_only: bool
    split_doc_id: bool


def random_style(rng: random.Random) -> Style:
    base, header, label_ink = rng.choice(PALETTES)
    base = tuple(min(255, max(0, c + rng.randint(-8, 8))) for c in base)
    return Style(
        base=base, header=header, label_ink=label_ink,
        value_font=rng.choice(("bold", "bold", "serif_bold", "mono_bold")),
        boxed=rng.random() < 0.5, label_below=rng.random() < 0.3, jitter=rng.choice((0, 15, 30)),
        labels={k: rng.choice(v) for k, v in LABEL_VARIANTS.items()},
        show_subtitle=rng.random() < 0.5,
        watermark_alpha=rng.randint(25, 70), stamp_only=rng.random() < 0.4,
        split_doc_id=rng.random() < 0.5,
    )


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


def _watermark(img: Image.Image, text: str = "AMOSTRA • SYNTHETIC", alpha: int = 70) -> Image.Image:
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    f = font("bold", max(40, img.width // 14))
    step = img.width // 2
    for y in range(-img.height, img.height * 2, step // 2):
        draw.text((0, y), f"  {text}  " * 4, font=f, fill=(*WATERMARK[:3], alpha))
    layer = layer.rotate(25, expand=False)
    return Image.alpha_composite(img.convert("RGBA"), layer).convert("RGB")


def _stamp(img: Image.Image, rng: random.Random) -> Image.Image:
    """A smaller but still clearly visible 'synthetic' mark (ADR-0002), placed only where
    no field is printed so the training target never contains text the stamp hides."""
    draw = ImageDraw.Draw(img)
    scale = img.width / CARD_W
    text = "AMOSTRA • SYNTHETIC"
    if rng.random() < 0.5:  # header band, top right
        f = font("bold", max(20, int(34 * scale)))
        w = draw.textlength(text, font=f)
        x, y = img.width - w - 30 * scale, 20 * scale
    else:  # across the lower part of the photo (x 60-430 on the card)
        f = font("bold", max(14, int(24 * scale)))
        w = draw.textlength(text, font=f)
        x, y = 70 * scale, 580 * scale
    draw.rectangle((x - 10, y - 6, x + w + 10, y + f.size + 10), outline=WATERMARK[:3], width=4, fill=(255, 255, 255))
    draw.text((x, y), text, font=f, fill=WATERMARK[:3])
    return img


def _mark(img: Image.Image, style: "Style | None", rng: random.Random) -> Image.Image:
    if style is None:
        return _watermark(img)
    return _stamp(img, rng) if style.stamp_only else _watermark(img, alpha=style.watermark_alpha)


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


def render_card(record: CnhRecord, rng: random.Random, style: Style | None = None) -> Image.Image:
    """`style=None` is the round-1 (v1) look; pass `random_style(rng)` for v2."""
    if style is None:
        base, header, label_ink, value_font = (
            (rng.randint(205, 225), rng.randint(228, 242), rng.randint(200, 218)), (35, 95, 60), LABEL, "bold")
    else:
        base, header, label_ink, value_font = style.base, style.header, style.label_ink, style.value_font
    img = _background(rng, CARD_W, CARD_H, base)
    draw = ImageDraw.Draw(img)

    draw.rectangle((0, 0, CARD_W, 140), fill=header)
    draw.text((60, 30), "CARTEIRA NACIONAL DE HABILITAÇÃO", font=font("bold", 50), fill="white")
    if style is None or style.show_subtitle:
        draw.text((60, 92), "AMOSTRA SINTÉTICA — SEM VALOR LEGAL", font=font("regular", 28), fill="white")

    _photo_placeholder(draw, rng, (60, 190, 430, 640))
    _signature(draw, rng, (60, 700, 430, 900))
    draw.text((60, 905), "ASSINATURA DO PORTADOR", font=font("regular", 18), fill=label_ink)

    values = printed_values(record)
    for label, (x, y, max_w) in _LAYOUT.items():
        if style is not None and style.jitter:
            x += rng.randint(-style.jitter, style.jitter)
            y += rng.randint(-style.jitter // 2, style.jitter // 2)
        printed_label = style.labels.get(label, label) if style else label
        lines = list(record.filiacao) if label == "FILIAÇÃO" else [values[label]]
        value_h = 50 * len(lines)
        # Label above (default) or tucked just under its value box; either way it stays
        # clear of the next field (rows are >= 100 px apart), so pairs remain unambiguous.
        label_y, value_y = (y + 6 + value_h + 2, y + 6) if style and style.label_below else (y, y + 32)
        if style is not None and style.boxed:
            draw.rounded_rectangle((x - 10, value_y - 6, x + max_w, value_y + value_h), radius=12,
                                   outline=label_ink, width=2)
        draw.text((x, label_y), printed_label, font=font("regular", 18 if style and style.label_below else 22),
                  fill=label_ink)
        for i, text in enumerate(lines):
            if not text:
                continue
            if label == "DOC. IDENTIDADE / ÓRG. EMISSOR / UF" and style is not None and style.split_doc_id:
                num, org, uf = text.split(" ")  # printed in separate columns, read as one line
                for part, dx in ((num, 0), (org, int(max_w * 0.45)), (uf, int(max_w * 0.8))):
                    draw.text((x + dx, value_y), part, font=font(value_font, 34), fill=INK)
                continue
            draw.text((x, value_y + i * 50), text, font=_fit(draw, text, value_font, 36, max_w), fill=INK)

    return _mark(img, style, rng)


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


def render_digital(record: CnhRecord, rng: random.Random, style: Style | None = None) -> Image.Image:
    """A phone screenshot of a CNH Digital-style app screen."""
    w, h = 1080, 2340
    screen = Image.new("RGB", (w, h), (245, 247, 250))
    draw = ImageDraw.Draw(screen)
    draw.text((40, 20), f"{rng.randint(7, 22):02d}:{rng.randint(0, 59):02d}", font=font("bold", 34), fill="black")
    draw.rectangle((0, 90, w, 230), fill=(20, 70, 140))
    draw.text((40, 125), "CNH Digital (AMOSTRA)", font=font("bold", 52), fill="white")

    card = render_card(record, rng, style).resize((1000, round(1000 * CARD_H / CARD_W)))
    screen.paste(card, (40, 290))
    _fake_qr(draw, rng, 290, 1000, 500)
    draw.text((40, 1560), "Documento sintético gerado para pesquisa.", font=font("regular", 32), fill=(90, 90, 90))
    return screen


def render_non_cnh(rng: random.Random, fake, style: Style | None = None,
                   printed: list[str] | None = None) -> Image.Image:
    """Decoys the Extractor must reject: RG-like cards, CPF cards, invoices, random paperwork.

    With a `style` (v2), ID-card decoys share the CNH look. `printed`, if given, receives
    the decoy's text (round 3); collecting it draws no random numbers, so images are unchanged.
    """
    printed = [] if printed is None else printed
    kinds = ("rg", "invoice", "letter") if style is None else ("rg", "rg", "cpf", "cpf", "invoice", "letter")
    kind = rng.choice(kinds)
    if kind in ("rg", "cpf"):
        base, header, label_ink = ((225, 215, 235), None, LABEL) if style is None else (style.base, style.header,
                                                                                        style.label_ink)
        img = _background(rng, CARD_W, CARD_H, base)
        draw = ImageDraw.Draw(img)
        if kind == "rg":
            title = "REGISTRO GERAL — AMOSTRA"
            rows = [("NOME", fake.name().upper()), ("FILIAÇÃO", fake.name().upper()),
                    ("NATURALIDADE", fake.city().upper()), ("DATA DE EXPEDIÇÃO", _fake_date(fake))]
        else:
            title = "CADASTRO DE PESSOAS FÍSICAS — AMOSTRA"
            rows = [("NÚMERO DE INSCRIÇÃO", fake.cpf()), ("NOME", fake.name().upper()),
                    ("DATA DE NASCIMENTO", _fake_date(fake))]
        if header:
            draw.rectangle((0, 0, CARD_W, 140), fill=header)
            draw.text((60, 40), title, font=font("bold", 50), fill="white")
        else:
            draw.text((60, 40), title, font=font("bold", 50), fill=INK)
        printed += [f"{label}: {value}" for label, value in rows]
        for i, (label, value) in enumerate(rows):
            y = 190 + i * 150
            if style is not None and style.boxed:
                draw.rounded_rectangle((460, y + 28, 1650, y + 85), radius=12, outline=label_ink, width=2)
            draw.text((470, y), label, font=font("regular", 24), fill=label_ink)
            draw.text((470, y + 35), value, font=font(style.value_font if style else "bold", 38), fill=INK)
        _photo_placeholder(draw, rng, (60, 190, 430, 640))
        return _mark(img, style, rng)

    img = Image.new("RGB", (1240, 1754), "white")
    draw = ImageDraw.Draw(img)
    title = "NOTA FISCAL — AMOSTRA" if kind == "invoice" else fake.company().upper()
    draw.text((80, 80), title, font=font("bold", 48), fill="black")
    printed.append(title)
    for i in range(28):
        line = (f"{fake.word().upper():<18} {rng.randint(1, 9)} x R$ {rng.uniform(1, 500):8.2f}"
                if kind == "invoice" else fake.sentence())
        printed.append(" ".join(line.split()))
        draw.text((80, 200 + i * 52), line, font=font("mono" if kind == "invoice" else "regular", 30), fill="black")
    return _mark(img, style, rng)
