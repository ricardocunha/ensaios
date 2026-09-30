"""Turn text-layer contracts into image-only "scans" whose ground truth is known.

Real scanned contracts on PNCP are rare, and they come without a transcription. So we
take PDFs that have a text layer, keep that text as ground truth, and rasterize the pages
with increasing degradation (resolution, skew, blur, noise, JPEG artifacts).
"""

from __future__ import annotations

import argparse
import io
import json
import random
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pypdfium2 as pdfium
from PIL import Image, ImageFilter


@dataclass(frozen=True)
class Degradation:
    name: str
    dpi: int
    max_skew: float  # degrees
    blur: float  # Gaussian radius, pixels
    noise: float  # std of Gaussian noise, 0-255 scale
    jpeg_quality: int
    ink_fade: float  # 0 = none; lightens dark pixels, like a worn photocopy


LEVELS = {
    d.name: d
    for d in (
        Degradation("clean", 300, 0.0, 0.0, 0.0, 95, 0.0),
        Degradation("mild", 200, 0.8, 0.4, 6.0, 75, 0.1),
        Degradation("medium", 150, 1.8, 0.8, 12.0, 50, 0.25),
        Degradation("heavy", 110, 3.0, 1.2, 20.0, 30, 0.4),
    )
}


def degrade(img: Image.Image, d: Degradation, rng: random.Random) -> Image.Image:
    img = img.convert("L")
    if d.max_skew:
        img = img.rotate(rng.uniform(-d.max_skew, d.max_skew), resample=Image.BICUBIC, expand=True, fillcolor=255)
    if d.blur:
        img = img.filter(ImageFilter.GaussianBlur(d.blur))
    a = np.asarray(img, dtype=np.float32)
    if d.ink_fade:
        a = a + (255 - a) * d.ink_fade
    if d.noise:
        a = a + np.random.default_rng(rng.randrange(2**32)).normal(0, d.noise, a.shape)
    img = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=d.jpeg_quality)
    return Image.open(io.BytesIO(buf.getvalue()))


def page_texts(pdf: Path) -> list[str]:
    doc = pdfium.PdfDocument(pdf)
    try:
        return [doc[i].get_textpage().get_text_range() for i in range(len(doc))]
    finally:
        doc.close()


def make_scan(pdf: Path, d: Degradation, out: Path, seed: int, max_pages: int) -> Path:
    rng = random.Random(f"{seed}-{pdf.stem}-{d.name}")
    doc = pdfium.PdfDocument(pdf)
    try:
        pages = [degrade(doc[i].render(scale=d.dpi / 72).to_pil(), d, rng) for i in range(min(len(doc), max_pages))]
    finally:
        doc.close()
    dest = out / d.name / f"{pdf.stem}.pdf"
    dest.parent.mkdir(parents=True, exist_ok=True)
    pages[0].save(dest, "PDF", resolution=d.dpi, save_all=True, append_images=pages[1:])
    return dest


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--manifest", type=Path, default=Path("data/pncp/manifest.jsonl"))
    ap.add_argument("--out", type=Path, default=Path("data/scans"))
    ap.add_argument("--docs", type=int, default=20)
    ap.add_argument("--max-pages", type=int, default=6)
    ap.add_argument("--levels", nargs="+", default=list(LEVELS))
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()

    rows = [json.loads(line) for line in args.manifest.read_text().splitlines()]
    per_body: dict[str, int] = {}
    sources = []
    for r in rows:  # at most 2 contracts per public body, so no single template dominates
        if r["text_pages"] > 0 and per_body.get(r["cnpj"], 0) < 2 and len(sources) < args.docs:
            per_body[r["cnpj"]] = per_body.get(r["cnpj"], 0) + 1
            sources.append(Path(r["path"]))
    truth = {}
    for pdf in sources:
        truth[pdf.stem] = page_texts(pdf)[: args.max_pages]
        for name in args.levels:
            make_scan(pdf, LEVELS[name], args.out, args.seed, args.max_pages)
        print(f"{pdf.stem}: {len(truth[pdf.stem])} pages x {len(args.levels)} levels")
    (args.out / "truth.json").write_text(json.dumps(truth, ensure_ascii=False))


if __name__ == "__main__":
    main()
