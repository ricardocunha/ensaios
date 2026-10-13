"""Collect the Reader and Extractor run files into one JSON for the React viewer in `viewer/` (no model, no network).

    make viewer                         # this, then the page at http://localhost:5175
    uv run python -m cnh_ocr.viewer     # only viewer/public/data.json and the image links
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from . import transcription as tx
from .evaluation.metrics import _norm
from .extractor.run import load_inputs
from .gate import CNH_ONLY_LABELS, is_cnh
from .schema import FIELD_NAMES

OUT = Path("viewer/public")
RESULTS = Path("docs/RESULTS.md")
MODEL_NAMES = {"paddleocr_vl": "PaddleOCR-VL", "chandra2": "Chandra 2", "qwen35_9b": "Qwen3.5-9B"}


@dataclass(frozen=True)
class ItemSet:
    key: str
    name: str
    data: str  # split folder under data/
    readers: tuple[str, ...] = ()  # globs under runs/reader
    extractors: tuple[str, ...] = ()  # file stems under runs/extractor


# Synthetic and BID only. Private Real Samples (ADR-0002) are never listed here.
SETS = (
    ItemSet("student", "Held-out synthetic test", "synth-v3/test", ("v2test-*.jsonl",), ("student-base", "student-tuned")),
    ItemSet("teacher", "Teacher runs (synthetic train)", "synth-v3/train", (), ("cnh-teacher-deepseek",)),
    ItemSet("bid", "BID (real CNH templates)", "bid/test", ("bid-*.jsonl",)),
    ItemSet("synth", "Synthetic test (round-1 design)", "synth/test", tuple(f"{m}-*.jsonl" for m in MODEL_NAMES)),
    ItemSet("hard", "Synthetic hard set", "synth-hard/test", ("hard-*.jsonl",)),
)


def _rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.open(encoding="utf-8") if line.strip()]


def _public(path: Path) -> Path:
    """Refuse any path inside the git-ignored `private/` folder."""
    if path.resolve().is_relative_to(Path("private").resolve()):
        raise ValueError(f"{path} is in a private folder; the viewer only reads synthetic and BID data")
    return path


_READER_RUN = re.compile(r"(paddleocr_vl|chandra2|qwen35_9b)-(zeroshot|lora-v(\d))(?:-step0*(\d+))?$")


def _reader_name(stem: str) -> str:
    """'bid-paddleocr_vl-lora-v1-step0200' -> 'PaddleOCR-VL, LoRA round 1, step 200'."""
    m = _READER_RUN.search(stem)
    if not m:
        return stem
    variant = "zero-shot" if m[2] == "zeroshot" else f"LoRA round {m[3]}"
    return f"{MODEL_NAMES[m[1]]}, {variant}" + (f", step {m[4]}" if m[4] else "")


def _reader_order(stem: str) -> tuple:
    """Zero-shot runs first, then the LoRA rounds, checkpoints before the final adapter."""
    m = _READER_RUN.search(stem)
    return (int(m[3] or 0), int(m[4] or 10**9), stem) if m else (99, 0, stem)


def _gate(text: str) -> dict:
    return {"is_cnh": is_cnh(text), "labels": sorted(CNH_ONLY_LABELS & tx.parse(text).keys())}


def _reading(stem: str, row: dict, meta: dict) -> dict:
    """One Reader run on one image, with the per-label comparison for a CNH."""
    text = row["transcription"]
    out = {"run": stem, "name": _reader_name(stem), "transcription": text, "seconds": row.get("seconds"),
           "refused": tx.NOT_A_CNH in text.upper(), "gate": _gate(text)}
    if meta["kind"] == "cnh":
        read, truth = tx.parse(text), tx.parse(meta["answer"])
        # same rule as metrics.score_transcription: a " / " split is not an error
        same = lambda a, b: _norm(a).replace(" / ", " ") == _norm(b).replace(" / ", " ")
        out["labels"] = [{"label": k, "printed": v, "read": read.get(k), "ok": same(read.get(k), v)} for k, v in truth.items()]
    return out


def _steps(messages: list[dict]) -> list[dict]:
    """Tool calls of one Trajectory, in order, each with the tool's answer."""
    results = {m["tool_call_id"]: m["content"] for m in messages if m.get("role") == "tool"}
    steps, turn = [], 0
    for m in messages:
        calls = [c for c in m["content"] if isinstance(c, dict) and c.get("type") == "tool_call"] if isinstance(m.get("content"), list) else []
        turn += bool(calls)
        steps += [{"turn": turn, "tool": c["name"], "args": c["args"], "result": results.get(c["id"])} for c in calls]
    return steps


def _trajectories(runs: Path) -> dict[str, list[dict]]:
    """Golden Trajectories pulled by smithtune, by LangSmith trace id."""
    out = {}
    for f in sorted((runs / "smithtune/golden/conversations").glob("*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        out[d["trace_ids"][0]] = _steps(d["example"]["inputs"]["messages"])
    return out


def _extraction(stem: str, row: dict, trajectories: dict) -> dict:
    keep = ("role", "model", "outcome", "fields", "field_accuracy", "exact", "tool_calls", "model_calls", "input_tokens", "output_tokens")
    out = {"run": stem, **{k: row.get(k) for k in keep}}
    if row.get("run_id") in trajectories:
        out["steps"] = trajectories[row["run_id"]]
    return out


def _summary(results: Path) -> dict:
    """The tables `make report` wrote, as {section: {run: {column: cell}}}; nothing is recomputed."""
    out: dict = {}
    section, header = None, None
    for line in results.read_text(encoding="utf-8").splitlines() if results.exists() else []:
        if line.startswith("## "):
            section, header = line[3:].strip(), None
        elif line.startswith("|") and section:
            cells = [c.strip() for c in line.strip("|").split("|")]
            if header is None:
                header = cells
            elif not set(cells[0]) <= {"-"}:
                out.setdefault(section, {})[cells[0]] = dict(zip(header[1:], cells[1:]))
    return out


def _items(s: ItemSet, data: Path, runs: Path, trajectories: dict) -> list[dict]:
    split = _public(data / s.data)
    if not (split / "metadata.jsonl").exists():
        return []
    files = sorted((f for g in s.readers for f in (runs / "reader").glob(g)), key=lambda f: _reader_order(f.stem))
    readers = {f.stem: {r["file_name"]: r for r in _rows(f)} for f in files}
    extractors = {e: {r["file_name"]: r for r in _rows(runs / "extractor" / f"{e}.jsonl")} for e in s.extractors}
    # The run files don't store the Extractor's input: rebuild it as the run did (default seed).
    inputs = {i["file_name"]: i for i in load_inputs(split, None, None, 0)} if any(extractors.values()) else {}
    items = []
    for meta in _rows(split / "metadata.jsonl"):
        name = meta["file_name"]
        read = [_reading(stem, rows[name], meta) for stem, rows in readers.items() if name in rows]
        extracted = [_extraction(stem, rows[name], trajectories) for stem, rows in extractors.items() if name in rows]
        if not read and not extracted:
            continue
        stem = Path(name).stem
        item = {"id": f"{s.key}/{stem}", "set": s.key, "image": f"img/{s.key}/{Path(name).name}", "kind": meta["kind"],
                "answer": meta["answer"], "readers": read,
                "tags": {k: meta[k] for k in ("difficulty", "capture", "rotation", "formato") if meta.get(k) not in (None, "")}}
        if extracted:
            given = inputs[name]
            item["extractor"] = {"input": given["transcription"], "source": given["source"], "gate": _gate(given["transcription"]),
                                 "expected": given["truth"].model_dump() if given["truth"] else None, "runs": extracted}
        items.append(item)
    return items


def build(data: Path = Path("data"), runs: Path = Path("runs"), results: Path = RESULTS) -> dict:
    """One entry per image that has at least one Reader or Extractor run."""
    trajectories = _trajectories(runs)
    sets, items = [], []
    for s in SETS:
        found = _items(s, data, runs, trajectories)
        if found:
            sets.append({"key": s.key, "name": s.name, "count": len(found), "images": str(Path(s.data) / "images")})
            items += found
    if not items:
        raise FileNotFoundError(f"no run files under {runs}/reader or {runs}/extractor: run `make zero-shot` or `make eval-reader` first")
    return {"summary": _summary(results), "fields": list(FIELD_NAMES), "gate_labels": sorted(CNH_ONLY_LABELS), "sets": sets, "items": items}


def write(built: dict, out: Path = OUT, data: Path = Path("data")) -> Path:
    """Write data.json and link each set's images next to it (both git-ignored; nothing is copied)."""
    (out / "img").mkdir(parents=True, exist_ok=True)
    (out / "data.json").write_text(json.dumps(built, ensure_ascii=False), encoding="utf-8")
    for s in built["sets"]:
        link = out / "img" / s["key"]
        if link.is_symlink():
            link.unlink()
        if not link.exists():
            link.symlink_to(_public(data / s["images"]).resolve(), target_is_directory=True)
    return out / "data.json"


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--data", type=Path, default=Path("data"))
    p.add_argument("--runs", type=Path, default=Path("runs"))
    p.add_argument("--out", type=Path, default=OUT)
    a = p.parse_args(argv)
    try:
        built = build(a.data, a.runs)
    except FileNotFoundError as e:
        sys.exit(str(e))
    path = write(built, a.out, a.data)
    print(f"{len(built['items'])} images in {len(built['sets'])} sets -> {path}", file=sys.stderr)


if __name__ == "__main__":
    main()
