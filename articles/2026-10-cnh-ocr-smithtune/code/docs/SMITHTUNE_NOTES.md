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
- **Chandra 2 re-run with a 3,000-token budget:** 0/50 outputs truncated. Value recall is **86.0%** (was 47.5% at 600 tokens), label accuracy still 14.9%, CER 30.9, **51.0 s/img**. The HTML layout output is the cost.
- Metric note: about 14% label accuracy is the floor. Blank fields (PERMISSÃO, ACC) match even when the format is ignored, which is why both specialists sit near 15%.

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

## 2026-09-25: BID (real CNH templates): the synthetic-to-real gap

142 images: 70 CNH (36 front, 34 open card) and 72 RG/CPF fronts (Non-CNH).

| PaddleOCR-VL on BID | CNH label acc (all 70) | Real CNHs wrongly rejected | Non-CNH rejected | Label acc / value recall on accepted CNHs |
|---|---|---|---|---|
| zero-shot | 0.0% | 0/70 | 0/72 | 0.0% / low |
| LoRA (final, step 2,293) | ~28% (front 14.6%, open 43.4%) | **48/70** | **72/72** | **82.8% / 96.3%** (n=22) |

- **Reading transferred; gatekeeping overfit.** On synthetic data the model hits 99.9%. On real CNH templates it calls 48 of 70 genuine CNHs "NÃO É CNH". It learned "a CNH looks like *my* renderer's card". When it does accept a card, it reads it almost perfectly.
- Most of the remaining misses are label text copied from the real card (`CAT.HA8`, `CAT.HAB.`), so CAT. HAB. only scores 3/22 even though the value is right.
- The aggregate 64.8% "label accuracy" in `report.py` is misleading on BID, because the 72 correct rejections count as perfect. Report CNH-only numbers and the rejection matrix separately.
- **All three on BID (CNH-only metrics; rejections reported separately):**

  | Model | CNH label acc (70) | Value recall | Real CNHs wrongly rejected | Non-CNH rejected | p50 s/img |
  |---|---|---|---|---|---|
  | PaddleOCR-VL zero-shot | 0.0% | 80.8% | 0/70 | 0/72 | 1.2 |
  | PaddleOCR-VL + LoRA | 28.6% | 34.0% | 48/70 | 72/72 | 0.6 |
  | **Qwen3.5-9B zero-shot** | **41.8%** | **85.4%** | 5/70 | 59/72 | 7.1 |

  **On real CNH templates, zero-shot Qwen beats our fine-tuned model.** That's the reverse of the synthetic result (99.9% vs 68.0%). Qwen rejects real RG/CPF well (59/72) but only 3/7 of our synthetic decoys, which says our decoys are unrealistic too.
- **Checkpoints:** step 200 is a degenerate "reject almost everything" phase. On synthetic data it gets 28.9% label accuracy and 14.2% value recall, and on BID it rejects 70/70 real CNHs. By step 1,000 synthetic is solved (99.9%), but BID still wrongly rejects 49/70 (29.6% CNH acc). The final step gives 48/70 (28.6%). The real-template rejection is flat from step 1,000 to the end. **Early stopping doesn't help; the training data has to change.** Probable fixes:
  - domain randomization in the generator (colors, layout jitter, label spelling variants)
  - 90°/180°/270° rotations
  - keeping the Non-CNH rate but making the decoys more CNH-like
  - accent- and punctuation-tolerant label parsing, which also helps the Extractor

## 2026-09-28: round 2 setup (domain randomization)

**Hypothesis.** The round-1 Reader learned "CNH = my renderer's look". Varying the look should keep the reading skill and fix the rejection of real CNHs.

**Controls.** Same model (PaddleOCR-VL-1.6), same LoRA hyperparameters (rank 32, lr 1e-4, batch 1 × grad-accum 4, 1 epoch), same **2,293** training images. Only the data distribution changes.

**Data changes (`--style v2`).** Six palettes, three value-font families, layout jitter, boxed fields in 50% of cards, labels below the box in 30%, printed label variants (`CAT.HAB.`, `N° REGISTRO`, `1º HABILITAÇÃO`…), ID number / órgão / UF in separate columns, 40% flatbed scans, 25% quarter turns (90/180/270), and CNH-like decoys (RG and CPF cards in the same palettes), with the Non-CNH rate at 15%. The watermark is lighter, or a corner stamp placed only where no field is printed. Build time: **59 s** with 10 shards, vs about 45 min single-process in round 1.

**Leakage guard.** From BID I used only the coarse properties I'd observed while writing the loader (green-ish cards, boxed fields, scans, upside-down images, `CAT.HAB.` spelling). I did no tuning against BID scores, and BID is evaluated once per round.

**Scoring change.** Label parsing is now tolerant (accents, punctuation, known variants, fuzzy OCR slips). Round-1 runs were re-scored with CNH-only metrics:

| Round 1, re-scored | Set | CNH label acc | Value recall | CNHs wrongly rejected | Non-CNH rejected |
|---|---|---|---|---|---|
| PaddleOCR-VL zero-shot | synth (43 CNH) | 17.4% | 85.5% | 0/43 | 0/7 |
| Chandra 2 zero-shot (3k) | synth | 17.3% | 100.0% | 0/43 | 0/7 |
| Qwen3.5-9B zero-shot | synth | 72.4% | 99.8% | 0/43 | 3/7 |
| PaddleOCR-VL LoRA v1 | synth | 99.8% | 99.8% | 0/43 | 7/7 |
| PaddleOCR-VL zero-shot | BID (70 CNH) | 0.0% | 80.8% | 0/70 | 0/72 |
| Qwen3.5-9B zero-shot | BID | 48.2% | 85.4% | 5/70 | 59/72 |
| PaddleOCR-VL LoRA v1 | BID | 32.0% | 34.0% | 48/70 | 72/72 |

## 2026-09-28: round 2 results on BID

Training took 1h41 on the M4 Pro with a 5.7 GB peak.

| BID | CNH label acc | Value recall | Real CNHs wrongly rejected | Non-CNH rejected | p50 s/img |
|---|---|---|---|---|---|
| LoRA v1 (one design) | 32.0% | 34.0% | 48/70 | 72/72 | 0.6 |
| **LoRA v2 (randomized)** | **52.3%** | 60.6% | **30/70** | 72/72 | 0.9 |
| Qwen3.5-9B zero-shot | 48.2% | 85.4% | 5/70 | 59/72 | 7.1 |

- **+20 points from variety alone** (same model, hyperparameters and image count). v2 edges past zero-shot Qwen at about 8× the speed.
- **Not solved:** 30/70 real CNHs are still rejected. The 40 accepted score 78.8% label acc and 91.8% recall (v1: 92.9% on 22; the newly accepted cards are harder). By class: CNH_Frente 43.7%, CNH_Aberta 61.4%.
- Weakest fields: DATA EMISSÃO 27%, CAT. HAB. 30%, LOCAL 35%.
- Hypothesis for round 3 (untested): train the Reader to always transcribe, and move the "is this a CNH?" gate downstream (Extractor or a separate classifier). Zero-shot Qwen already rejects real RG/CPF well (59/72).

## Next entries

- [ ] `smithtune doctor` output and install time
- [ ] pull: how many Teacher runs matched the `exact == 1` filter
- [ ] triage sample: council agreement with ground truth (`cnh_ocr.evaluation.council_agreement`)
- [ ] `plan` estimate vs. actual train time and cost
- [ ] replay-eval numbers vs. our field-level numbers
- [ ] deploy / undeploy: time to ready, cost per hour
- [ ] bugs found → upstream issue links
