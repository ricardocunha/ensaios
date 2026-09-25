"""LoRA-fine-tune a Reader on Apple Silicon with mlx-vlm.

    uv run python -m cnh_ocr.reader.train_mlx --model paddleocr_vl --data data/synth --epochs 1
    uv run python -m cnh_ocr.reader.train_mlx --model qwen35_9b --data data/synth --epochs 1 --qlora

The dataset is the imagefolder written by `cnh_ocr.synth.build`; mlx-vlm turns
its `question` / `answer` columns into a one-turn chat around the image.
"""

from __future__ import annotations

import argparse
import shlex
import subprocess
import sys
from pathlib import Path

from .models import MODELS


def quantize_command(hf_id: str, path: Path) -> list[str]:
    """4-bit base weights for QLoRA, needed for the 9B models on a 48 GB Mac."""
    return [sys.executable, "-m", "mlx_vlm.convert", "--hf-path", hf_id, "--mlx-path", str(path),
            "-q", "--q-bits", "4"]


def command(args: argparse.Namespace, model_path: str) -> list[str]:
    m = MODELS[args.model]
    out = args.out or Path("runs/reader") / f"{m.key}-lora"
    return [
        sys.executable, "-m", "cnh_ocr.reader.mlx_lora",  # mlx_vlm.lora + vision-freeze fix
        "--model-path", model_path,
        "--dataset", str(args.data),
        "--split", "train",
        "--epochs", str(args.epochs),
        "--batch-size", "1",  # batch > 1 breaks PaddleOCR-VL's vision encoder in mlx-vlm 0.7.3
        "--gradient-accumulation-steps", str(m.grad_accum),
        "--learning-rate", str(args.learning_rate),
        "--lora-rank", str(m.lora_rank),
        "--lora-alpha", str(m.lora_rank * 2),
        "--lora-dropout", "0.05",
        "--max-seq-length", "2048",
        "--grad-checkpoint",
        "--train-on-completions",
        "--steps-per-report", "10",
        "--steps-per-save", "200",
        "--output-path", str(out),
    ]


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--model", choices=MODELS, required=True)
    p.add_argument("--data", type=Path, default=Path("data/synth"))
    p.add_argument("--epochs", type=int, default=1)
    p.add_argument("--learning-rate", type=float, default=1e-4)
    p.add_argument("--out", type=Path)
    p.add_argument("--qlora", action="store_true", help="train on a 4-bit copy of the base model")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    cmds, model_path = [], MODELS[args.model].hf_id
    if args.qlora:
        q_path = Path("runs/models") / f"{args.model}-4bit"
        if not q_path.exists():
            cmds.append(quantize_command(model_path, q_path))
        model_path = str(q_path)
    cmds.append(command(args, model_path))
    for cmd in cmds:
        print(shlex.join(cmd))
        if not args.dry_run:
            subprocess.run(cmd, check=True)


if __name__ == "__main__":
    main()
