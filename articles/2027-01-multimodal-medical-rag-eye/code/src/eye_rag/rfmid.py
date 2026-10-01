"""RFMiD (Retinal Fundus Multi-disease Image Dataset): download and load.

Source: the CC BY 4.0 Hugging Face mirror `ctmedtech/RFMID`, pinned to one revision.
The official host (IEEE DataPort) needs a free IEEE account; this project doesn't sign
up for anything, so it reads the mirror and checks every file against the mirror's
SHA-256 (see docs/DATA.md for what that does and doesn't prove).

The originals are PNGs of 1.5-3 MB (about 8.2 GB for the three splits). We keep a
downsized JPEG copy of each (long side 1024 px, quality 92) in data/rfmid/<split>/<id>.jpg,
which is plenty for BiomedCLIP (224 px input) and keeps data/ well under 1 GB.

    uv run python -m eye_rag.rfmid download            # all three splits
    uv run python -m eye_rag.rfmid stats               # label counts per split
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

import httpx
import numpy as np
from PIL import Image

from eye_rag.labels import CODES, DISEASE_RISK, NORMAL

REPO = "ctmedtech/RFMID"
REVISION = "16ee0cf528e9cb6ec38a6d7b1f3e4580172bc1da"  # mirror state on 2026-10-01
BASE = f"https://huggingface.co/datasets/{REPO}/resolve/{REVISION}"
TREE = f"https://huggingface.co/api/datasets/{REPO}/tree/{REVISION}"

# official split -> (label CSV, image folder) inside the mirror
SPLITS = {
    "train": ("Training_Set/Training_Set/RFMiD_Training_Labels.csv", "Training_Set/Training_Set/Training"),
    "val": ("Evaluation_Set/Evaluation_Set/RFMiD_Validation_Labels.csv", "Evaluation_Set/Evaluation_Set/Validation"),
    "test": ("Test_Set/Test_Set/RFMiD_Testing_Labels.csv", "Test_Set/Test_Set/Test"),
}
EXPECTED_SIZES = {"train": 1920, "val": 640, "test": 640}

DATA = Path("data")
LONG_SIDE = 1024
JPEG_QUALITY = 92


@dataclass(frozen=True)
class Record:
    id: str  # "<split>/<n>", unique across splits (image numbers restart per split)
    split: str
    path: Path
    labels: frozenset[str]  # condition codes; empty for a normal image
    disease_risk: int

    @property
    def label_set(self) -> frozenset[str]:
        """Labels for retrieval matching: a normal image counts as label NORMAL."""
        return self.labels if self.labels else frozenset({NORMAL})


# --------------------------------------------------------------------------- labels


def parse_labels_csv(text: str, split: str, image_dir: Path) -> list[Record]:
    """Parse an RFMiD label CSV (ID, Disease_Risk, then one 0/1 column per condition)."""
    rows = csv.DictReader(io.StringIO(text.lstrip("﻿")))
    missing = [c for c in (DISEASE_RISK, *CODES) if c not in (rows.fieldnames or [])]
    if missing:
        raise ValueError(f"label CSV is missing columns: {missing}")
    out = []
    for row in rows:
        n = row["ID"].strip()
        labels = frozenset(c for c in CODES if row[c].strip() == "1")
        risk = int(row[DISEASE_RISK])
        out.append(Record(f"{split}/{n}", split, image_dir / f"{n}.jpg", labels, risk))
    return out


def load_split(split: str, root: Path = DATA / "rfmid") -> list[Record]:
    """Records of one official split, in CSV order. Needs `download` first."""
    if split not in SPLITS:
        raise ValueError(f"unknown split {split!r}; use one of {list(SPLITS)}")
    csv_path = root / f"{split}_labels.csv"
    if not csv_path.exists():
        raise FileNotFoundError(f"{csv_path} not found: run `make download` first")
    return parse_labels_csv(csv_path.read_text(encoding="utf-8-sig"), split, root / split)


def label_matrix(records: list[Record], codes: tuple[str, ...] = CODES) -> np.ndarray:
    """(n_records, n_codes) 0/1 matrix. The code DISEASE_RISK reads the risk column."""
    y = np.zeros((len(records), len(codes)), dtype=np.int8)
    for i, r in enumerate(records):
        for j, c in enumerate(codes):
            y[i, j] = r.disease_risk if c == DISEASE_RISK else int(c in r.labels)
    return y


# --------------------------------------------------------------------------- download


def downsize(png_bytes: bytes, long_side: int = LONG_SIDE, quality: int = JPEG_QUALITY) -> bytes:
    """Re-encode an image as RGB JPEG with its long side at most `long_side` pixels."""
    im = Image.open(io.BytesIO(png_bytes)).convert("RGB")
    scale = long_side / max(im.size)
    if scale < 1:
        im = im.resize((round(im.width * scale), round(im.height * scale)), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=quality)
    return buf.getvalue()


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _tree(client: httpx.Client, folder: str) -> dict[str, dict]:
    """path -> entry (size, lfs sha256) for the files in a mirror folder (paginated API)."""
    url: str | None = f"{TREE}/{folder}"
    out = {}
    while url:
        r = client.get(url)
        r.raise_for_status()
        for e in r.json():
            if e["type"] == "file":
                out[e["path"]] = e
        url = r.links.get("next", {}).get("url")
    return out


def _fetch_one(client: httpx.Client, entry: dict, dest: Path) -> dict:
    r = client.get(f"{BASE}/{entry['path']}")
    r.raise_for_status()
    data = r.content
    expected = (entry.get("lfs") or {}).get("oid")
    got = sha256(data)
    if expected and got != expected:
        raise ValueError(f"checksum mismatch for {entry['path']}: {got} != {expected}")
    dest.write_bytes(downsize(data))
    return {"file": entry["path"], "sha256": got, "bytes": len(data)}


def download(splits: list[str], root: Path = DATA / "rfmid", workers: int = 8) -> None:
    root.mkdir(parents=True, exist_ok=True)
    with httpx.Client(follow_redirects=True, timeout=120) as client:
        for split in splits:
            csv_file, img_dir = SPLITS[split]
            r = client.get(f"{BASE}/{csv_file}")
            r.raise_for_status()
            text = r.content.decode("utf-8-sig")
            records = parse_labels_csv(text, split, root / split)
            if len(records) != EXPECTED_SIZES[split]:
                raise ValueError(f"{split}: {len(records)} rows, expected {EXPECTED_SIZES[split]}")
            (root / f"{split}_labels.csv").write_text(text, encoding="utf-8")
            (root / split).mkdir(exist_ok=True)

            tree = _tree(client, img_dir)
            todo = []
            for rec in records:
                n = rec.id.split("/")[1]
                entry = tree.get(f"{img_dir}/{n}.png")
                if entry is None:
                    raise FileNotFoundError(f"{split}: image {n}.png not in the mirror")
                if not rec.path.exists():
                    todo.append((entry, rec.path))
            print(f"{split}: {len(records)} records, {len(todo)} to download", file=sys.stderr)

            manifest_path = root / f"{split}_manifest.jsonl"
            with manifest_path.open("a") as manifest, ThreadPoolExecutor(workers) as pool:
                futures = [pool.submit(_fetch_one, client, e, d) for e, d in todo]
                for i, f in enumerate(as_completed(futures), 1):
                    manifest.write(json.dumps(f.result()) + "\n")
                    if i % 100 == 0 or i == len(futures):
                        print(f"  {split}: {i}/{len(futures)}", file=sys.stderr)


# --------------------------------------------------------------------------- stats


def stats(splits: list[str]) -> str:
    """Markdown table of label counts per split (conditions sorted by train count)."""
    recs = {s: load_split(s) for s in splits}
    counts = {s: label_matrix(r).sum(axis=0) for s, r in recs.items()}
    order = np.argsort(-counts[splits[0]], kind="stable")
    lines = ["| Code | " + " | ".join(splits) + " |", "|---|" + "---|" * len(splits)]
    lines.append("| (images) | " + " | ".join(str(len(recs[s])) for s in splits) + " |")
    lines.append("| normal (Disease_Risk = 0) | " + " | ".join(str(sum(r.disease_risk == 0 for r in recs[s])) for s in splits) + " |")
    for j in order:
        lines.append(f"| {CODES[j]} | " + " | ".join(str(int(counts[s][j])) for s in splits) + " |")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("command", choices=["download", "stats"])
    p.add_argument("--splits", nargs="+", default=list(SPLITS))
    p.add_argument("--workers", type=int, default=8)
    a = p.parse_args(argv)
    if a.command == "download":
        download(a.splits, workers=a.workers)
    else:
        print(stats(a.splits))


if __name__ == "__main__":
    main()
