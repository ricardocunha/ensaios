"""Collect the run files into one JSON for the React viewer in `viewer/` (no model, no scores recomputed).

    make viewer                         # this, then the page at http://localhost:5174
    uv run python -m eye_rag.viewer     # only viewer/public/data.json and the image link

Research demo, not a medical device.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from eye_rag.explain import RUNS, _recorded, _rows
from eye_rag.labels import CONDITIONS, NORMAL_DESCRIPTION
from eye_rag.rfmid import DATA, load_split
from eye_rag.vlm import NORMAL_LABEL

OUT = Path("viewer/public")
ARMS = ("zero_shot", "retrieval", "shuffled")


def _image(record_id: str) -> str:
    """URL of an image under the page's `rfmid/` link, from a "<split>/<n>" id."""
    return f"rfmid/{record_id}.jpg"


def _shown(labels: Sequence[str]) -> list[str]:
    return sorted(_recorded(labels))


def _arm(row: dict, explanation: dict | None) -> dict:
    cases = []
    true_labels = row.get("true_case_labels") or [None] * len(row["case_ids"])
    for case_id, labels, real in zip(row["case_ids"], row["case_labels"], true_labels):
        case = {"id": case_id, "image": _image(case_id), "labels": _shown(labels)}
        if real is not None:
            case["true_labels"] = _shown(real)
        cases.append(case)
    out = {"labels": row["labels"], "rationale": row["rationale"], "cited_cases": row["cited_cases"], "cases": cases}
    if explanation:
        out["explanation"] = {k: explanation[k] for k in ("findings", "verified", "attempts", "first_problems", "problems")}
    return out


def _summary(runs: Path, split: str) -> dict:
    """The headline numbers already written by `make m2-score` and `make explain-score`, if present."""
    out: dict = {}
    three = runs / f"m2_three_arms_{split}.json"
    if three.exists():
        out["macro_f1_frequent"] = {k: v["macro_f1_frequent"] for k, v in json.loads(three.read_text())["summary"].items()}
    scores = runs / f"m2_explain_{split}.json"
    if scores.exists():
        s = json.loads(scores.read_text())
        if "macro_f1_same_images" in s:
            out.setdefault("macro_f1_frequent", {})["vlm_shuffled"] = s["macro_f1_same_images"]["shuffled"]["macro_f1_frequent"]
        out["answer_changed"] = s["faithfulness"].get("answer_changed")
        out["verified"] = {a: e.get("verified_after_retries") for a, e in s["explanations"].items()}
    return out


def build(runs: Path = RUNS, split: str = "test", root: Path = DATA / "rfmid") -> dict:
    """One entry per image that has a retrieval-arm diagnosis; the other arms are added when present."""
    truth = {r.id: sorted(r.labels) or [NORMAL_LABEL] for r in load_split(split, root)}
    rows = {a: {r["id"]: r for r in _rows(runs / f"m2_vlm_{split}_{a}.jsonl")} for a in ARMS}
    explained = {a: {r["id"]: r for r in _rows(runs / f"m2_explain_{split}_{a}.jsonl")} for a in ("retrieval", "shuffled")}
    if not rows["retrieval"]:
        raise FileNotFoundError(f"no {runs}/m2_vlm_{split}_retrieval.jsonl: run `make vlm-retrieval` first")
    cases = []
    for record_id in sorted(rows["retrieval"], key=lambda x: int(x.split("/")[1])):
        arms = {a: _arm(rows[a][record_id], explained.get(a, {}).get(record_id)) for a in ARMS if record_id in rows[a]}
        cases.append({"id": record_id, "image": _image(record_id), "truth": truth[record_id], "arms": arms})
    conditions = {c.code: {"name": c.name, "description": c.description} for c in CONDITIONS}
    conditions[NORMAL_LABEL] = {"name": "normal fundus", "description": NORMAL_DESCRIPTION}
    return {"split": split, "summary": _summary(runs, split), "conditions": conditions, "cases": cases}


def write(data: dict, out: Path = OUT, root: Path = DATA / "rfmid") -> Path:
    """Write data.json and link the images next to it (both git-ignored; nothing is copied)."""
    out.mkdir(parents=True, exist_ok=True)
    (out / "data.json").write_text(json.dumps(data, ensure_ascii=False))
    link = out / "rfmid"
    if link.is_symlink():
        link.unlink()
    if not link.exists():
        link.symlink_to(root.resolve(), target_is_directory=True)
    return out / "data.json"


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--split", default="test", choices=["val", "test"])
    p.add_argument("--runs", type=Path, default=RUNS)
    p.add_argument("--out", type=Path, default=OUT)
    a = p.parse_args(argv)
    data = build(a.runs, a.split)
    path = write(data, a.out)
    print(f"{len(data['cases'])} images -> {path}", file=sys.stderr)


if __name__ == "__main__":
    main()
