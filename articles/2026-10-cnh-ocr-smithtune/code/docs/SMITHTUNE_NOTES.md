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

## 2026-09-25: Stage 1 zero-shot, 50 synthetic test images, same prompt for all models

| Model | Label acc | Value recall | CER | p50 s/img |
|---|---|---|---|---|
| PaddleOCR-VL-1.6 (0.9B) | 15.0% | 73.5% | 10.36 | 3.1 |
| Chandra 2 (~5B), 600-token budget, **46/50 outputs truncated** | 14.9% | 47.5% | 19.70 | 26.3 |
| Qwen3.5-9B | **68.0%** | **91.8%** | 1.38 | 21.3 |

- **The generalist wins zero-shot** because it follows the `LABEL: value` instruction. The specialists don't: PaddleOCR-VL writes free text and often loops (CER ≈ 10 means the output is about 10× the reference length). Chandra 2 always writes its own HTML layout format with a `data-bbox` on every element, whatever the prompt says.
- **Qwen's errors are the dangerous kind.** It gives confident, well-formed but wrong dates (DATA NASCIMENTO `29/05/1990` vs truth `23/07/1990`). Checksums catch a bad CPF, but nothing catches a plausible date.
- Chandra 2 is being re-run with a 3,000-token budget for a fair number.

## 2026-09-25: BID Dataset loader

- The sample is 70 CNH images (36 front, 34 open card) plus 72 RG/CPF fronts as Non-CNH.
- These are **real CNH templates, scanned, often rotated 90°/180°**, with synthetic personal data and blurred faces. Our training rotations stay within about ±12°, so it's a genuine robustness test.
- The `*_gt_ocr.txt` files come in two formats: boxes, and rotated quads with `[xs], [ys]`. File order is **not** label-then-value (a value sometimes precedes its label), so pairing is by format plus distance.
- 8 fields are scored: NOME, CPF, DATA NASCIMENTO, CAT. HAB., Nº REGISTRO, VALIDADE, 1ª HABILITAÇÃO, plus LOCAL and DATA EMISSÃO on the open cards. FILIAÇÃO and DOC. IDENTIDADE line splits are too inconsistent to score.
- BID dates are random (born 2019, valid until 2007), so BID is for the Reader only.

## 2026-09-25: PaddleOCR-VL-1.6 + LoRA (1 epoch, 2,293 images, M4 Pro)

- Training took **1h51 on an M4 Pro**: 2,293 steps at about 0.37 steps/s, **5.7 GB peak**, rank 32, 12.1M trainable params (1.3%). The loss went 0.56 → 0.10 (step 100) → 0.0018 (step 1,000) → 0.0003 (step 2,000).

| Synthetic test | Label acc | Value recall | CER | s/img | Non-CNH rejected |
|---|---|---|---|---|---|
| zero-shot (50) | 15.0% | 73.5% | 10.36 | 3.1 | 0/7 |
| **LoRA (50)** | **99.9%** | **99.8%** | **0.000** | **2.8** | **7/7** |
| zero-shot, hard set (100) | 15.7% | 77.3% | 19.92 | 3.3 | |
| **LoRA, hard set (100)** | **99.8%** | **99.8%** | **0.000** | 2.8 | |

- **Checked for leakage:** the test and hard sets share 0 CPFs and 0 names with train, and 0 identical transcriptions.
- The only error in 50 test images is `CÂMARA` → `CAMARA`, a lost accent on a CNH Digital screenshot (the smallest text).
- **Caveat: this is in-distribution.** The test images come from the same renderer, fonts and layout as training, so 99.9% mostly says "it learned our template". The honest test of generalization is **BID** (real CNH templates, scanned, rotated 90°/180°), which is queued after the Chandra re-run.
- A 0.9B model at 2.8 s/img on a laptop beats zero-shot Qwen3.5-9B (68.0%, 21.3 s/img) on this distribution by a wide margin.

## Next entries

- [ ] `smithtune doctor` output and install time
- [ ] pull: how many Teacher runs matched the `exact == 1` filter
- [ ] triage sample: council agreement with ground truth (`cnh_ocr.evaluation.council_agreement`)
- [ ] `plan` estimate vs. actual train time and cost
- [ ] replay-eval numbers vs. our field-level numbers
- [ ] deploy / undeploy: time to ready, cost per hour
- [ ] bugs found → upstream issue links
