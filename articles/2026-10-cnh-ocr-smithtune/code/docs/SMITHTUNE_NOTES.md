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
- **No regression at home:** on the v1 synthetic test, 99.8% (same as v1). On the v1 hard set, 99.7% (v1: 99.8%). On the v2 test (86 CNH / 14 decoys), 99.4% label acc, 0/86 wrongly rejected, 14/14 decoys rejected. So the synthetic sets can't tell v1 and v2 apart; only BID can.
- Hypothesis for round 3 (untested): train the Reader to always transcribe, and move the "is this a CNH?" gate downstream (Extractor or a separate classifier). Zero-shot Qwen already rejects real RG/CPF well (59/72).

## 2026-09-28: round 3 (the Reader always transcribes; the text decides, ADR-0003)

Same images, model, hyperparameters and 2,293 images as round 2. Training took 1h43, peak 6.2 GB.

| BID | CNH label acc | Value recall | Gate: real CNHs rejected | Gate: RG/CPF rejected | p50 s/img |
|---|---|---|---|---|---|
| LoRA v1 | 32.0% | 34.0% | 48/70 | 72/72 | 0.6 |
| LoRA v2 | 52.3% | 60.6% | 31/70 | 72/72 | 0.9 |
| **LoRA v3** | **81.0%** | **94.4%** | **0/70** | 64/72 | 2.3 |
| Qwen3.5-9B zero-shot | 48.2% | 85.4% | 31/70 | 72/72 | 7.1 |

- Synthetic: 100% on the test set, 99.6% on the hard set, all decoys gated correctly. There's no regression.
- Per field on BID: CPF 97%, DATA NASCIMENTO 91%, VALIDADE 87%, NOME 84%, CAT. HAB. 83%, 1ª HAB 81%, Nº REGISTRO 69%, DATA EMISSÃO 52%, LOCAL 50%.
- **8/72 RG leak through the gate**, all the same (Minas Gerais) RG design. The Reader repeats CNH labels with *empty* values (`Nº REGISTRO:`, `PERMISSÃO:`), and the rule only checks that labels exist. Candidate fix: count only CNH labels with a plausible value. **Not applied**, because it was designed after seeing BID failures, so its BID score wouldn't be independent. It needs a fresh real set (e.g. the full BID beyond the sample).
- Slower (2.3 s vs 0.9 s): decoys are now transcribed in full instead of a one-line refusal.

## 2026-09-28: Teacher trajectories (Claude Sonnet 5)

Three 20-run checks before the real run. Each one found a bug in *my* setup, not in the model:

| Check | Exact | Real CNHs rejected | RG accepted as CNH | Cost | Fix |
|---|---|---|---|---|---|
| 1 | 8/20 (13 re-scored) | 5 | 0 | $0.75 | Noise dropped required lines; "reject" was the only way out → CNH Record fields nullable, Rejection = Non-CNH only. `formato` isn't in the text → not scored |
| 2 | 16/20 | 0 | 2 | $0.80 | Overcorrected → prompt states what makes a CNH; the submit tool refuses records with < 2 CNH-only fields |
| 3 (+ prompt caching) | 19/20 re-scored | 0 | 0 | $0.36 | Names compared accent-insensitively (the agent is told not to guess accents) |

**Prompt caching** (AnthropicPromptCachingMiddleware: system prompt, tools, conversation tail) served 80% of input tokens from cache: -55% cost.

**Main run** (`make teacher MAX_COST=5`, final prompt, window start 2026-09-28T18:44:39Z for the golden pull):
- 300 runs (budget cap reached at $5.14; in-flight runs finish), 0 failed.
- **261 exact (87%)**: noise inputs 217/256, decoys 44/44 rejected, 0 real CNHs rejected.
- Most-missed field: `doc_identidade` (22). The RG number has no checksum, so an O↔0 / S↔5 swap there can't be verified the way a CPF can.
- About $0.017 per run with caching.

## 2026-09-28: switching to an open-weight Teacher, and why the feedback filter found nothing

**Why switch.** smithtune's data-rights terms forbid circumventing model-license limits on distillation, and Anthropic's terms restrict training models on Claude outputs. The Teacher became **DeepSeek-V4-Pro-0813 (MIT)** on Baseten Model APIs, traced into a separate LangSmith project (`cnh-teacher-deepseek`), so the Claude runs can never reach a smithtune dataset.

**Baseten tool-calling quirk.** DeepSeek's list argument (`filiacao: ["A", "B"]`) arrived concatenated (`"AB"`). The failing tool call then looped until LangGraph's step cap (10,000), about 5 minutes for one run. Fixes: the tool takes `"PAI / MÃE"` as a string, and each run has `recursion_limit=40`.

**Main run:** 300 runs, $4.84, 0 failed, **266 exact (89%)**: 222/256 CNH, 44/44 decoys rejected, 0 real CNHs rejected. About the same quality and cost as Claude Sonnet 5 with caching.

**The pull found 0 traces.** Two bugs in how *we* wrote feedback, both silent:
1. `create_feedback` without `session_id` (the project UUID). It's deprecated, and such feedback isn't indexed for trace filters.
2. The feedback went on `collect_runs().traced_runs[0]`, which is the **first model call (a child run)**, not the agent's root. Trace filters, and so smithtune's `--filter`, only look at roots.

Fix: feedback on `trace_id` with `session_id`. The 300 runs' scores were re-attached (no re-run needed), but the backfill hit LangSmith's rate limit (429) at 8 parallel requests; batched lookups plus serial writes worked. Tip: **test the filter with `langsmith trace list --filter` before `smithtune dataset pull`**, as smithtune's skill says.

## 2026-09-29: dataset pushed; training provider

- `dataset pull`: 266/266 golden trajectories passed structural checks. `dataset push --confirm` created LangSmith dataset `cnh-extractor-golden` (266 examples).
- **Baseten:** `prepare` fails with `Loops training is not enabled for your workspace. Contact Baseten`. Loops is gated per workspace. Request sent / pending.
- **Fireworks:** also needs `BASETEN_API_KEY` for nothing, *but* my `run.sh` sourced `.env` after reading the environment, so `SMITHTUNE_PROVIDER=fireworks` was overridden and smithtune ran the Baseten preflight. Fixed: `.env` no longer overrides variables that are already set.
- `prepare --provider fireworks --model qwen3p8-27b`: 266 accepted, split 214 / 23 / 29, rendered with the pinned Qwen3.8-27B tokenizer.
- `plan`: LoRA rank 8, lr 1e-4, batch 32, max 5 epochs with early stopping (patience 1). Replay eval: 58 cases (29 text + 29 tool call), judge `deepseek-v4p1-flash`. **No dollar estimate:** "serverless token charges at the current account rate; resolve in the Fireworks console before confirmation".
- My estimate: about 1.76M training tokens per epoch (upper bound). Fireworks SFT is $3.00/M tokens for 16–80B models, so about $5 per epoch, up to about $26 at 5 epochs.
- smithtune's default replay judge is a Baseten model; on Fireworks pass `--judge-model accounts/fireworks/models/deepseek-v4p1-flash`. `--max-spend-usd` is Baseten-only; on Fireworks cap `--max-epochs`.

## 2026-09-29: first smithtune training (Fireworks, qwen3p8-27b, 1 epoch)

**Training worked.** Serverless LoRA SFT: rank 8, lr 1e-4, batch 32, 1 epoch = 7 steps on 214 trajectories. Validation loss **0.0133** (ppl 1.013). There's a promotable checkpoint on Fireworks. Run `sft-20260929-201651-9879a3d797fe`. (Epochs capped at 1 because of about $11 of Fireworks credit; about 1.76M tokens/epoch at $3/M ≈ $5 upper bound. Actual charge: check the Fireworks console.)

**Replay evaluation: interrupted and unreliable.**
- `evaluation interrupted: 63 cases failed; 45/108 saved; rerun to resume`. smithtune keeps only the count; the first exception is chained internally but the CLI doesn't print it. The cause is unknown (possibly credit).
- On the 45 saved cases, **both base and tuned** are judged "Candidate tool calls violate the tools available at this assistant turn" in 32/35 tool-call cases. The deterministic metrics show `tool_name_match: true` but `arguments_json_valid: false`. The Fireworks sampler returns tool-call `arguments` as a **parsed object**, and the check expects a JSON **string** (OpenAI wire format). That looks like a sampler/parser mismatch in v0.1, not a model failure. It's worth an upstream issue.
- A genuine model error in both: `numero_registro` sent as an integer (24885519110), not a string.
- **Base vs tuned: identical output in 26/45 cases** (they are served from different routes: base model vs the epoch-1 checkpoint). The rest differ in details (`null` vs `""`). One epoch of rank-8 LoRA on 214 examples barely moved a 27B model that is already competent at the task, or the eval can't see the difference.

**Takeaways for the article.** (1) smithtune's Fireworks path trains fine, but its replay eval needs work for tool-heavy agents. (2) Always inspect the deterministic metrics before trusting the judge's verdict. (3) Our own field-level eval on held-out transcriptions is the metric that matters, but it needs a deployment (US$8/h on Fireworks).

## Next entries

- [ ] `smithtune doctor` output and install time
- [ ] pull: how many Teacher runs matched the `exact == 1` filter
- [ ] triage sample: council agreement with ground truth (`cnh_ocr.evaluation.council_agreement`)
- [ ] `plan` estimate vs. actual train time and cost
- [ ] replay-eval numbers vs. our field-level numbers
- [ ] deploy / undeploy: time to ready, cost per hour
- [ ] bugs found → upstream issue links
