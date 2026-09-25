"""How often does smithtune's agent council agree with ground truth?

    uv run python -m cnh_ocr.evaluation.council_agreement runs/smithtune/triage-sample \
        --runs runs/extractor/cnh-extractor-teacher.jsonl

Joins the council's `labels.jsonl` (keyed by example id) to our Teacher runs
(keyed by LangSmith root run id == trace id) through the triage snapshot units,
which record each example's `trace_ids`.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def _units(obj):
    if isinstance(obj, dict):
        if isinstance(obj.get("example"), dict) and "trace_ids" in obj:
            yield obj
        for v in obj.values():
            yield from _units(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _units(v)


def example_to_traces(triage_dir: Path) -> dict[str, list[str]]:
    mapping = {}
    for path in triage_dir.rglob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        for unit in _units(data):
            mapping[unit["example"]["id"]] = unit["trace_ids"]
    return mapping


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("triage_dir", type=Path)
    p.add_argument("--runs", type=Path, default=Path("runs/extractor/cnh-extractor-teacher.jsonl"))
    args = p.parse_args()

    truth = {r["run_id"]: r["exact"] for r in map(json.loads, args.runs.open(encoding="utf-8"))}
    traces = example_to_traces(args.triage_dir)
    labels = [json.loads(line) for line in (args.triage_dir / "labels.jsonl").open(encoding="utf-8")]

    pairs = []
    for label in labels:
        match = [truth[t] for t in traces.get(label["trajectory_id"], []) if t in truth]
        if match:
            pairs.append((bool(label["keep"]), bool(match[0]), label.get("reason", "")))
    if not pairs:
        raise SystemExit("no labels could be joined to runs; check the snapshot layout in the triage dir")

    tp = sum(k and t for k, t, _ in pairs)
    fp = sum(k and not t for k, t, _ in pairs)
    fn = sum(not k and t for k, t, _ in pairs)
    tn = sum(not k and not t for k, t, _ in pairs)
    n = len(pairs)
    print(f"joined {n}/{len(labels)} labels")
    print(f"agreement {(tp + tn) / n:.1%} | council kept a WRONG trajectory {fp}x | dropped a correct one {fn}x")
    print(f"precision of 'keep' {tp / max(1, tp + fp):.1%} | recall {tp / max(1, tp + fn):.1%}")
    for keep, ok, reason in pairs:
        if keep and not ok:
            print(f"  false keep: {reason[:160]}")


if __name__ == "__main__":
    main()
