"""Measure Docling's OCR on the degraded scans, and whether its confidence predicts the errors.

Per page: character error rate (CER), word recall and number recall against the original
text layer, next to Docling's own page scores. Results: runs/ocr_eval.jsonl + a summary.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path

from rapidfuzz.distance import Levenshtein

from compliance_agents.mcp_server import normalize
from compliance_agents.parse import converter, item_text

NUMBER_RE = re.compile(r"(?:\d[\d.,/-]*\d|\d)%?")


def numbers(text: str) -> Counter:
    """Numeric tokens (amounts, dates, percentages, process numbers), punctuation kept."""
    return Counter(m.rstrip(".,") for m in NUMBER_RE.findall(text))


def recall(truth: Counter, got: Counter) -> float | None:
    total = sum(truth.values())
    return None if total == 0 else sum((truth & got).values()) / total


def page_metrics(truth: str, ocr: str) -> dict:
    t, o = normalize(truth), normalize(ocr)
    return {
        "chars": len(t),
        "cer": round(Levenshtein.normalized_distance(t, o), 4) if t else None,
        "word_recall": recall(Counter(t.split()), Counter(o.split())),
        "number_recall": recall(numbers(truth), numbers(ocr)),
        "numbers": sum(numbers(truth).values()),
    }


def ocr_pages(pdf: Path) -> tuple[dict[int, str], dict[int, dict]]:
    res = converter().convert(pdf)
    texts: dict[int, list[str]] = {}
    for item, _ in res.document.iterate_items():
        text = item_text(item, res.document)
        if text and item.prov:
            texts.setdefault(item.prov[0].page_no, []).append(text)
    scores = {int(p): s.model_dump() for p, s in res.confidence.pages.items()}
    return {p: "\n".join(t) for p, t in texts.items()}, scores


def spearman(xs: list[float], ys: list[float]) -> float | None:
    pairs = [(x, y) for x, y in zip(xs, ys) if x is not None and y is not None and x == x and y == y]
    if len(pairs) < 3:
        return None

    def ranks(v):
        order = sorted(range(len(v)), key=v.__getitem__)
        r = [0.0] * len(v)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
                j += 1
            for k in range(i, j + 1):
                r[order[k]] = (i + j) / 2
            i = j + 1
        return r

    rx, ry = ranks([p[0] for p in pairs]), ranks([p[1] for p in pairs])
    n = len(pairs)
    mx, my = sum(rx) / n, sum(ry) / n
    cov = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    sx = sum((a - mx) ** 2 for a in rx) ** 0.5
    sy = sum((b - my) ** 2 for b in ry) ** 0.5
    return round(cov / (sx * sy), 3) if sx and sy else None


def mean(v):
    v = [x for x in v if x is not None]
    return round(sum(v) / len(v), 4) if v else None


def summarize(rows: list[dict]) -> str:
    lines = ["| Level | Pages | CER | Word recall | Number recall | Docling ocr_score | Spearman(ocr_score, CER) |", "|---|---|---|---|---|---|---|"]
    for level in dict.fromkeys(r["level"] for r in rows):
        rs = [r for r in rows if r["level"] == level]
        lines.append(
            f"| {level} | {len(rs)} | {mean(r['cer'] for r in rs)} | {mean(r['word_recall'] for r in rs)} | "
            f"{mean(r['number_recall'] for r in rs)} | {mean(r.get('ocr_score') for r in rs)} | "
            f"{spearman([r.get('ocr_score') for r in rs], [r['cer'] for r in rs])} |"
        )
    lines.append(
        f"\nAll levels: Spearman(ocr_score, CER) = {spearman([r.get('ocr_score') for r in rows], [r['cer'] for r in rows])}, "
        f"Spearman(mean_score, CER) = {spearman([r.get('mean_score') for r in rows], [r['cer'] for r in rows])}"
    )
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--scans", type=Path, default=Path("data/scans"))
    ap.add_argument("--out", type=Path, default=Path("runs/ocr_eval.jsonl"))
    args = ap.parse_args()

    truth = json.loads((args.scans / "truth.json").read_text())
    args.out.parent.mkdir(parents=True, exist_ok=True)
    done = {(r["level"], r["doc"]) for r in map(json.loads, args.out.read_text().splitlines())} if args.out.exists() else set()
    with args.out.open("a") as f:
        for level_dir in sorted(p for p in args.scans.iterdir() if p.is_dir()):
            for pdf in sorted(level_dir.glob("*.pdf")):
                if (level_dir.name, pdf.stem) in done or pdf.stem not in truth:
                    continue
                texts, scores = ocr_pages(pdf)
                for i, t in enumerate(truth[pdf.stem], start=1):
                    row = {"level": level_dir.name, "doc": pdf.stem, "page": i, **page_metrics(t, texts.get(i, ""))}
                    s = scores.get(i, {})
                    row.update({k: s.get(k) for k in ("ocr_score", "layout_score", "mean_score", "low_score")})
                    f.write(json.dumps(row) + "\n")
                f.flush()
                print(f"{level_dir.name:>6} {pdf.stem}")
    rows = [json.loads(line) for line in args.out.read_text().splitlines()]
    rows = [r for r in rows if r["chars"] >= 200]  # skip near-empty pages (signature pages, stamps)
    print(summarize(rows))


if __name__ == "__main__":
    main()
