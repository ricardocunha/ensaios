"""`python -m mlx_vlm.lora`, plus a fix for models whose vision tower is named `visual`.

mlx-vlm 0.7.3 doesn't freeze PaddleOCR-VL's encoder, so "LoRA" trained the whole
vision tower (see docs/upstream-issues.md). Same CLI and flags as `mlx_vlm.lora`.
"""

from __future__ import annotations

import runpy

import mlx_vlm.trainer.utils as trainer_utils

_original_freeze = trainer_utils.freeze_model


def freeze_model(model):
    _original_freeze(model)
    if hasattr(model, "visual"):
        model.visual.freeze()


trainer_utils.freeze_model = freeze_model

if __name__ == "__main__":
    runpy.run_module("mlx_vlm.lora", run_name="__main__", alter_sys=True)
