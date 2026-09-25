"""Turn prediction files into the results tables for README and the article.

    uv run python -m cnh_ocr.evaluation.report --data data/synth/test \
        --reader runs/reader/*.jsonl --extractor runs/extractor/*.jsonl > docs/RESULTS.md
"""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path

from .metrics import score_transcription


def reader_rows(data: Path, files: list[Path]) -> list[str]:
    truth = {r["file_name"]: r for r in map(json.loads, (data / "metadata.jsonl").open(encoding="utf-8"))}
    rows = ["| Reader run | n | label accuracy | value recall | CER | p50 s/img | hard-set label acc |",
            "|---|---|---|---|---|---|---|"]
    for f in files:
        preds = [json.loads(line) for line in f.open(encoding="utf-8")]
        scored = [(p, score_transcription(p["transcription"], truth[p["file_name"]]["answer"]))
                  for p in preds if p["file_name"] in truth]
        if not scored:
            continue
        acc = statistics.mean(s["label_accuracy"] for _, s in scored)
        recall = statistics.mean(s["value_recall"] for _, s in scored)
        c = statistics.mean(s["cer"] for _, s in scored)
        hard = [s["label_accuracy"] for p, s in scored if truth[p["file_name"]].get("difficulty") == "hard"]
        hard_acc = f"{statistics.mean(hard):.1%}" if hard else "n/a"
        p50 = statistics.median(p["seconds"] for p, _ in scored)
        rows.append(f"| {f.stem} | {len(scored)} | {acc:.1%} | {recall:.1%} | {c:.3f} | {p50:.1f} | {hard_acc} |")
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
