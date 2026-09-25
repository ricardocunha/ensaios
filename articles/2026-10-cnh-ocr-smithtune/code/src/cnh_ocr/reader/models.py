"""The three Base OCR Models (Reader candidates). See PLAN.md §1 for why these."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BaseOcrModel:
    key: str
    hf_id: str
    params: str
    license: str
    role: str
    lora_rank: int = 16
    # Effective batch size; mlx-vlm trains at batch 1 and accumulates gradients.
    grad_accum: int = 4
    # Output budget. Chandra ignores the prompt zero-shot and emits verbose HTML with bboxes.
    max_tokens: int = 600


MODELS: dict[str, BaseOcrModel] = {
    m.key: m
    for m in (
        BaseOcrModel(
            key="chandra2",
            hf_id="datalab-to/chandra-ocr-2",
            params="~5B (Qwen3.5-4B based)",
            license="AI Pubs Open RAIL-M (modified): no commercial use above US$2M revenue/funding; share-alike",
            role="OCR specialist, best Portuguese score",
            max_tokens=3000,
        ),
        BaseOcrModel(
            key="paddleocr_vl",
            hf_id="PaddlePaddle/PaddleOCR-VL-1.6",
            params="0.9B (NaViT + ERNIE-4.5-0.3B)",
            license="Apache-2.0",
            role="tiny specialist",
            lora_rank=32,
        ),
        BaseOcrModel(
            key="qwen35_9b",
            hf_id="Qwen/Qwen3.5-9B",
            params="9B",
            license="Apache-2.0",
            role="generalist; same base as the smithtune Student",
        ),
    )
}
