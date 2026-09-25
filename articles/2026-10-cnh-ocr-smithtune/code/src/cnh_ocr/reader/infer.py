"""Run a Reader over a dataset split and save its Transcriptions.

    # zero-shot, locally on Apple Silicon
    uv run python -m cnh_ocr.reader.infer --model chandra2 --data data/synth/test --out runs/reader/chandra2-zeroshot.jsonl
    # fine-tuned
    uv run python -m cnh_ocr.reader.infer --model chandra2 --adapter runs/reader/chandra2-lora --data data/synth/test ...
    # any OpenAI-compatible server (e.g. `vllm serve datalab-to/chandra-ocr-2`)
    uv run python -m cnh_ocr.reader.infer --backend openai --base-url http://localhost:8000/v1 --model chandra2 ...
"""

from __future__ import annotations

import argparse
import base64
import json
import time
from pathlib import Path

from ..transcription import READER_PROMPT
from .models import MODELS


class MlxReader:
    def __init__(self, hf_id: str, adapter: str | None, max_tokens: int):
        from mlx_vlm import load
        from mlx_vlm.utils import load_config

        self.model, self.processor = load(hf_id, adapter_path=adapter)
        self.config = load_config(hf_id)
        self.max_tokens = max_tokens

    def __call__(self, image_path: str) -> str:
        from mlx_vlm import generate
        from mlx_vlm.prompt_utils import apply_chat_template

        prompt = apply_chat_template(self.processor, self.config, READER_PROMPT, num_images=1)
        out = generate(self.model, self.processor, prompt, image=[image_path], max_tokens=self.max_tokens, temperature=0.0)
        return out.text.strip()


class OpenAIReader:
    def __init__(self, base_url: str, model: str, max_tokens: int):
        from openai import OpenAI

        self.client, self.model = OpenAI(base_url=base_url, api_key="unused"), model
        self.max_tokens = max_tokens

    def __call__(self, image_path: str) -> str:
        b64 = base64.b64encode(Path(image_path).read_bytes()).decode()
        resp = self.client.chat.completions.create(
            model=self.model,
            temperature=0,
            max_tokens=self.max_tokens,
            messages=[{"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                {"type": "text", "text": READER_PROMPT},
            ]}],
        )
        return (resp.choices[0].message.content or "").strip()


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--model", choices=MODELS, required=True)
    p.add_argument("--data", type=Path, required=True, help="split dir containing metadata.jsonl")
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--adapter")
    p.add_argument("--backend", choices=("mlx", "openai"), default="mlx")
    p.add_argument("--base-url", default="http://localhost:8000/v1")
    p.add_argument("--limit", type=int)
    p.add_argument("--max-tokens", type=int, help="override the model's default output budget")
    args = p.parse_args()

    m = MODELS[args.model]
    max_tokens = args.max_tokens or m.max_tokens
    reader = (MlxReader(m.hf_id, args.adapter, max_tokens) if args.backend == "mlx"
              else OpenAIReader(args.base_url, m.hf_id, max_tokens))
    rows = [json.loads(line) for line in (args.data / "metadata.jsonl").open(encoding="utf-8")][: args.limit]

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as out:
        for i, row in enumerate(rows):
            t0 = time.perf_counter()
            text = reader(str(args.data / row["file_name"]))
            seconds = time.perf_counter() - t0
            out.write(json.dumps({"file_name": row["file_name"], "transcription": text, "seconds": seconds},
                                 ensure_ascii=False) + "\n")
            print(f"[{i + 1}/{len(rows)}] {row['file_name']} {seconds:.1f}s")


if __name__ == "__main__":
    main()
