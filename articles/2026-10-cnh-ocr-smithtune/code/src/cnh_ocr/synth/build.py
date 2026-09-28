"""Build the Synthetic CNH dataset as an HF `imagefolder`.

    uv run python -m cnh_ocr.synth.build --out data/synth --train 3000 --validation 300 --test 300
    uv run python -m cnh_ocr.synth.build --out data/synth-hard --test 100 --difficulty hard
    # round 2: domain-randomized, 8 parallel shards
    uv run python -m cnh_ocr.synth.build --style v2 --shards 8 --out data/synth-v2 --train 2293 --test 300

Each split gets `images/*.jpg` and a `metadata.jsonl` with the columns
`question` / `answer` (what mlx-vlm and TRL train on), plus ground truth for eval.
"""

from __future__ import annotations

import argparse
import json
import random
from concurrent.futures import ProcessPoolExecutor
from datetime import date
from pathlib import Path

from faker import Faker

from .. import transcription
from .augment import Difficulty, phone_photo, quarter_turn, scan, screenshot
from .records import random_record
from .render import random_style, render_card, render_digital, render_non_cnh

NON_CNH_RATE = 0.10
V2_NON_CNH_RATE = 0.15
V2_SCAN_RATE = 0.4       # physical cards captured on a flatbed instead of a phone
V2_QUARTER_TURN = 0.25   # sideways / upside-down captures
TODAY = date(2026, 9, 25)  # pinned so the dataset is reproducible


def _difficulty(rng: random.Random, forced: Difficulty | None) -> Difficulty:
    if forced:
        return forced
    return rng.choices(("clean", "normal", "hard"), weights=(15, 70, 15))[0]


def build_split(out: Path, split: str, n: int, seed: int, forced: Difficulty | None) -> None:
    rng = random.Random(seed)
    fake = Faker("pt_BR")
    fake.seed_instance(seed)
    images = out / split / "images"
    images.mkdir(parents=True, exist_ok=True)

    with (out / split / "metadata.jsonl").open("w", encoding="utf-8") as meta:
        for i in range(n):
            difficulty = _difficulty(rng, forced)
            row = {"file_name": f"images/{split}-{i:05d}.jpg", "question": transcription.READER_PROMPT,
                   "difficulty": difficulty}
            if rng.random() < NON_CNH_RATE:
                img = phone_photo(render_non_cnh(rng, fake), rng, difficulty)
                row |= {"answer": transcription.NOT_A_CNH, "kind": "non_cnh", "formato": "", "record": ""}
            else:
                record = random_record(rng, fake, TODAY)
                if record.formato == "digital":
                    img = screenshot(render_digital(record, rng), rng, difficulty)
                else:
                    img = phone_photo(render_card(record, rng), rng, difficulty)
                row |= {"answer": transcription.from_record(record), "kind": "cnh",
                        "formato": record.formato, "record": record.model_dump_json()}
            img.save(out / split / row["file_name"], quality=90)
            meta.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"{split}: {n} images -> {out / split}")


def _v2_item(rng: random.Random, fake: Faker, difficulty: Difficulty, always_transcribe: bool = False) -> tuple:
    """v2 images. With `always_transcribe` (v3), decoys are transcribed instead of refused;
    the random draws are identical, so v2 and v3 images are pixel-identical."""
    style = random_style(rng)
    capture = "scan" if rng.random() < V2_SCAN_RATE else "phone"
    shoot = scan if capture == "scan" else phone_photo
    if rng.random() < V2_NON_CNH_RATE:
        printed: list[str] = []
        img = shoot(render_non_cnh(rng, fake, style, printed), rng, difficulty)
        answer = "\n".join(printed) if always_transcribe else transcription.NOT_A_CNH
        fields = {"answer": answer, "kind": "non_cnh", "formato": "", "record": ""}
    else:
        record = random_record(rng, fake, TODAY)
        if record.formato == "digital":
            capture, img = "screenshot", screenshot(render_digital(record, rng, style), rng, difficulty)
        else:
            img = shoot(render_card(record, rng, style), rng, difficulty)
        fields = {"answer": transcription.from_record(record), "kind": "cnh", "formato": record.formato,
                  "record": record.model_dump_json()}
    rotation = 0
    if capture != "screenshot" and rng.random() < V2_QUARTER_TURN:
        img, rotation = quarter_turn(img, rng)
    return img, fields | {"capture": capture, "rotation": rotation}


def build_shard(out: Path, split: str, n: int, seed: int, forced: Difficulty | None, shard: int,
                style: str = "v2") -> Path:
    """One v2 shard: its own seed and file prefix, so shards run in parallel and resume independently."""
    rng = random.Random(seed * 100 + shard)
    fake = Faker("pt_BR")
    fake.seed_instance(seed * 100 + shard)
    (out / split / "images").mkdir(parents=True, exist_ok=True)
    part = out / split / f"metadata.shard{shard:02d}.jsonl"
    with part.open("w", encoding="utf-8") as meta:
        for i in range(n):
            difficulty = _difficulty(rng, forced)
            img, fields = _v2_item(rng, fake, difficulty, always_transcribe=style == "v3")
            name = f"images/{split}-s{shard:02d}-{i:05d}.jpg"
            img.save(out / split / name, quality=90)
            prompt = transcription.PROMPTS["v3" if style == "v3" else "v1"]
            meta.write(json.dumps({"file_name": name, "question": prompt,
                                   "difficulty": difficulty} | fields, ensure_ascii=False) + "\n")
    return part


def build_split_v2(out: Path, split: str, n: int, seed: int, forced: Difficulty | None, shards: int,
                   style: str = "v2") -> None:
    sizes = [n // shards + (k < n % shards) for k in range(shards)]
    with ProcessPoolExecutor(shards) as pool:
        parts = list(pool.map(build_shard, *zip(*[(out, split, sz, seed, forced, k, style)
                                                  for k, sz in enumerate(sizes)])))
    with (out / split / "metadata.jsonl").open("w", encoding="utf-8") as meta:
        for part in parts:
            meta.write(part.read_text(encoding="utf-8"))
            part.unlink()
    print(f"{split}: {n} images ({shards} shards, {style}) -> {out / split}")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--out", type=Path, default=Path("data/synth"))
    p.add_argument("--train", type=int, default=0)
    p.add_argument("--validation", type=int, default=0)
    p.add_argument("--test", type=int, default=0)
    p.add_argument("--difficulty", choices=("clean", "normal", "hard"))
    p.add_argument("--seed", type=int, default=2026)
    p.add_argument("--style", choices=("v1", "v2", "v3"), default="v1",
                   help="v1 = round-1 look; v2 = domain-randomized (palettes, layouts, scans, rotations); "
                        "v3 = v2 images, but the Reader always transcribes (decoys too)")
    p.add_argument("--shards", type=int, default=8, help="parallel workers (v2 only)")
    args = p.parse_args()
    for offset, split in enumerate(("train", "validation", "test")):
        n = getattr(args, split)
        if n and args.style == "v1":
            build_split(args.out, split, n, args.seed * 10 + offset, args.difficulty)
        elif n:
            build_split_v2(args.out, split, n, args.seed * 10 + offset + 500, args.difficulty, args.shards, args.style)


if __name__ == "__main__":
    main()
