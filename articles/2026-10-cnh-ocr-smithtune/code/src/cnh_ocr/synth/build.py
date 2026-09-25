"""Build the Synthetic CNH dataset as an HF `imagefolder`.

    uv run python -m cnh_ocr.synth.build --out data/synth --train 3000 --validation 300 --test 300
    uv run python -m cnh_ocr.synth.build --out data/synth-hard --test 100 --difficulty hard

Each split gets `images/*.jpg` and a `metadata.jsonl` with the columns
`question` / `answer` (what mlx-vlm and TRL train on), plus ground truth for eval.
"""

from __future__ import annotations

import argparse
import json
import random
from datetime import date
from pathlib import Path

from faker import Faker

from .. import transcription
from .augment import Difficulty, phone_photo, screenshot
from .records import random_record
from .render import render_card, render_digital, render_non_cnh

NON_CNH_RATE = 0.10
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


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--out", type=Path, default=Path("data/synth"))
    p.add_argument("--train", type=int, default=0)
    p.add_argument("--validation", type=int, default=0)
    p.add_argument("--test", type=int, default=0)
    p.add_argument("--difficulty", choices=("clean", "normal", "hard"))
    p.add_argument("--seed", type=int, default=2026)
    args = p.parse_args()
    for offset, split in enumerate(("train", "validation", "test")):
        n = getattr(args, split)
        if n:
            build_split(args.out, split, n, args.seed * 10 + offset, args.difficulty)


if __name__ == "__main__":
    main()
