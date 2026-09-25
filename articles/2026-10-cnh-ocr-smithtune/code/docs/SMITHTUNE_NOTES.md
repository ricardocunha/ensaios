# smithtune field notes

A running log kept while testing smithtune. It becomes the review section of the article. Include dates, commands, surprises, time and cost.

## 2026-09-25: reading the source (v0.1.0, released 2026-09-24)

- **Multimodal trajectories are filtered out on purpose.** `triage_source.py::multimodal_types()` detects `image`, `image_url`, `input_image`, audio, video, `file`/`document` and PDF mime types. `triage.py` then drops those trajectories before judging ("Filtered before judging: multimodal content"), and `dataset_workflow.py` rejects them when freezing splits. So an OCR model can't be trained through smithtune today. → ADR-0001.
- **The base models are a fixed allowlist.**
  - Fireworks: `qwen3p8-27b` (the default), `kimi-k3`, `deepseek-v4-flash-0731`, `muse-glimmer-30b`.
  - Baseten: `Qwen/Qwen3.8-27B`, `Qwen/Qwen3.5-9B`, `moonshotai/Kimi-K3`, `zai-org/GLM-5.3-Flash`.
  - Each model has a pinned tokenizer revision and a hand-written chat-template "renderer". That explains why "any HF model" isn't possible: the renderer has to reproduce the model's chat template exactly.
- **Training is LoRA SFT** (`--lora-rank`, `--lora-alpha`). The split is about 80/10/10.
- **Evaluation is a replay.** Given the recorded context, predict the next assistant action; tool calls are *not* executed. An LLM judge scores agreement (`teacher_agreement`, `trajectory_teacher_agreement`).
- **Triage council:** there is no default rubric. `triage` refuses to run without `--rubric` or `--rule`. The bundled skill says an agent-name filter or "no errors" is *not* a quality signal.
- **Safety rails:** every paid step (`triage`, `train`, `evaluate`, `deploy`, `undeploy`) needs `--confirm`, and without it smithtune only previews. You must run `acknowledge-data-rights` first.
- Fireworks' own API can fine-tune Qwen3-VL-8B on images directly; smithtune just doesn't expose it (yet).

## 2026-09-25: Stage 1 spike (zero-shot PaddleOCR-VL-1.6 on M4 Pro, mlx-vlm 0.7.3)

- 4 images, 4–8 s per image. Value recall is 91.8% (it *reads* the text), but label accuracy is only 17.9% (it ignores the `LABEL: value` format).
- Failure modes:
  - multi-column rows lose the label-to-value pairing (`Nº REGISTRO VALIDADE 1º HABILITAÇÃO 34627740679 12/10/2027 02/11/2009`)
  - it sometimes drops a value
  - once it looped, repeating the same blocks
- n=4 is an anecdote, not a result. The full zero-shot run is `make zero-shot`.

## 2026-09-25: first PaddleOCR-VL LoRA attempt on the Mac (mlx-vlm 0.7.3)

Two upstream bugs, both worth reporting to `Blaizzy/mlx-vlm`:

1. **"LoRA" trained the whole vision tower.** `trainer/utils.py::freeze_model` freezes encoders by attribute name (`vision_model`, `vision_tower`, `aligner`, …). PaddleOCR-VL names its encoder `visual`, so it was never frozen. The log said `trainable 451M / 905M (49.8%)`, and the run hit a Metal OOM (`kIOGPUCommandBufferCallbackErrorOutOfMemory`). Fix: `src/cnh_ocr/reader/mlx_lora.py` also freezes `model.visual`. After the fix: 12.1M trainable (1.3%), 5.6 GB peak, about 2.7 s per step, and the loss went 0.56 → 0.12 in 5 steps.
2. **`--batch-size > 1` crashes PaddleOCR-VL.** `vision.py::_patch_embed` expects 5-D pixel values and gets 4-D (`not enough values to unpack (expected 5, got 4)`). Workaround: batch 1 with `--gradient-accumulation-steps 4`.

A 5-step adapter already produces the `LABEL: value` format (with some fields misplaced), so the format problem looks cheap to fix. The full run is 1 epoch on 2,293 images.

Also: the dataset build was interrupted by a session restart, and the generator isn't resumable mid-split. The train split is therefore **2,293 images** instead of 3,000. Validation and test use fixed per-split seeds, so they're unaffected.

## Next entries

- [ ] `smithtune doctor` output and install time
- [ ] pull: how many Teacher runs matched the `exact == 1` filter
- [ ] triage sample: council agreement with ground truth (`cnh_ocr.evaluation.council_agreement`)
- [ ] `plan` estimate vs. actual train time and cost
- [ ] replay-eval numbers vs. our field-level numbers
- [ ] deploy / undeploy: time to ready, cost per hour
- [ ] bugs found → upstream issue links
