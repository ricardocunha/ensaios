"""Turn prediction files into the results tables for README and the article.

    uv run python -m cnh_ocr.evaluation.report --data data/synth/test \
        --reader runs/reader/*.jsonl --extractor runs/extractor/*.jsonl > docs/RESULTS.md
"""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path

from .. import transcription as tx
from ..gate import is_cnh
from .metrics import score_transcription


def reader_rows(data: Path, files: list[Path]) -> list[str]:
    """CNH-only metrics, with both rejection directions reported separately.

    Folding correct Non-CNH rejections into one accuracy number hides failures
    (a model that rejects everything looks decent), so they are split out.
    """
    truth = {r["file_name"]: r for r in map(json.loads, (data / "metadata.jsonl").open(encoding="utf-8"))}
    rows = ["| Reader run | CNHs | label acc | value recall | CER | Reader refused CNHs | Reader refused Non-CNH "
            "| Gate: CNHs rejected | Gate: Non-CNH rejected | p50 s/img |",
            "|---|---|---|---|---|---|---|---|---|---|"]
    for f in files:
        preds = [p for p in map(json.loads, f.open(encoding="utf-8")) if p["file_name"] in truth]
        cnh = [p for p in preds if truth[p["file_name"]]["kind"] == "cnh"]
        neg = [p for p in preds if truth[p["file_name"]]["kind"] != "cnh"]
        if not cnh:
            continue
        refused = lambda p: tx.NOT_A_CNH in p["transcription"].upper()  # the Reader said "NÃO É CNH" (rounds 1-2)
        gated = lambda p: not is_cnh(p["transcription"])  # pipeline view: Reader + CNH Gate (ADR-0003)
        scores = [score_transcription(p["transcription"], truth[p["file_name"]]["answer"]) for p in cnh]
        acc = statistics.mean(s["label_accuracy"] for s in scores)
        recall = statistics.mean(s["value_recall"] for s in scores)
        c = statistics.mean(s["cer"] for s in scores)
        p50 = statistics.median(p["seconds"] for p in preds)
        frac = lambda fn, xs: f"{sum(map(fn, xs))}/{len(xs)}"
        rows.append(f"| {f.stem} | {len(cnh)} | {acc:.1%} | {recall:.1%} | {c:.2f} | {frac(refused, cnh)} | "
                    f"{frac(refused, neg)} | {frac(gated, cnh)} | {frac(gated, neg)} | {p50:.1f} |")
    return rows


def extractor_rows(files: list[Path]) -> list[str]:
    rows = ["| Extractor run | n | field accuracy | exact records | avg tool calls |", "|---|---|---|---|---|"]
    for f in files:
        runs = [json.loads(line) for line in f.open(encoding="utf-8")]
        if runs:
            rows.append(f"| {f.stem} | {len(runs)} | {statistics.mean(r['field_accuracy'] for r in runs):.1%} | "
                        f"{statistics.mean(r['exact'] for r in runs):.1%} | "
                        f"{statistics.mean(r['tool_calls'] for r in runs):.1f} |")
    return rows


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--data", type=Path, default=Path("data/synth/test"))
    p.add_argument("--reader", type=Path, nargs="*", default=[])
    p.add_argument("--extractor", type=Path, nargs="*", default=[])
    args = p.parse_args()
    print("\n".join(["## Reader (Stage 1)", "", *reader_rows(args.data, args.reader), "",
                     "## Extractor (Stage 2)", "", *extractor_rows(args.extractor)]))


if __name__ == "__main__":
    main()
