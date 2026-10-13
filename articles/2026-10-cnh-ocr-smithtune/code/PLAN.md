# Plan: CNH OCR + smithtune field test

> **Historical document.** This is the plan as agreed on 2026-09-25, kept for the record. Several decisions changed once real results came in:
> - **Teacher:** Claude Sonnet 5 → DeepSeek-V4-Pro (MIT), for license reasons ([ADR-0004](docs/adr/0004-open-weight-teacher.md)).
> - **Student:** Qwen3.5-9B → Qwen3-8B, trained locally on smithtune's prepared splits. Baseten Loops wasn't enabled, Fireworks credit ran out, and Qwen3.5-9B needs >48 GB to train locally.
> - **Reader:** three rounds instead of one; the Reader always transcribes ([ADR-0003](docs/adr/0003-reader-always-transcribes.md)). Only PaddleOCR-VL was fine-tuned.
> - **Council triage experiment:** not run (budget).
>
> What actually happened, with numbers: [README](README.md) · [docs/SMITHTUNE_NOTES.md](docs/SMITHTUNE_NOTES.md) · [docs/RESULTS.md](docs/RESULTS.md).


Terms follow `CONTEXT.md`. Architecture: `docs/adr/0001`. Data policy: `docs/adr/0002`.
Target publish date: **2026-10-16** (about 3 weeks after smithtune's 2026-09-24 launch).

## Decisions (grilling rounds, 2026-09-25)

| # | Decision |
|---|---|
| Q1 | Two stages: vision **Reader** (HF/MLX LoRA) → text **Extractor** (distilled with smithtune) |
| Q2 | The job is **Extraction**, CNH only. Non-CNH inputs are Rejected. No document classification |
| Q3 | Formats: physical 2022+ and CNH Digital |
| Q4 | Train on synthetic data only. Evaluate on BID (cited) and a few Private Real Samples (local, never committed) |
| Q5 | Stage 1 compute: local M4 Pro 48 GB with mlx-vlm (supports all 3 models). HF Jobs only as fallback |
| Q6 | Budget cap about US$150–300 |
| Q7 | smithtune on **Baseten** with Student **Qwen3.5-9B** |
| Q8 | Teacher: **Claude Sonnet 5** (`claude-sonnet-5`, adaptive thinking, effort=medium, no temperature) |
| Q9 | EN article (Medium/dev.to/Hashnode), LinkedIn post |
| Q10 | `ricardocunha/cnh-ocr-smithtune`, private until launch day |
| Q11 | **Chandra 2** (`datalab-to/chandra-ocr-2`); license caveat goes in the article |
| Q12 | **PaddleOCR-VL-1.6**. Fallback: Qwen3.5-0.8B/2B |
| Q13 | **Qwen3.5-9B** as the generalist Reader (same base as the Student) |
| Q14 | Fireworks one-stage Qwen3-VL-8B experiment: only if budget remains after Phase 5 |
| Q15 | Transcription = `LABEL: value` lines as printed, OCR errors kept |
| Q16 | CNH Record fields named in Portuguese, matching the printed labels |
| Q17 | Extractor = LangChain `create_agent` |
| Q18 | 1,500 Teacher runs → about 1,000 Golden Trajectories, about 10% Non-CNH |
| Q19 | Headline metric: field-level exact match. Cost/1k CNHs is the business angle. Replay eval reported as-is |
| Q20 | Article voice: first-person field report with the commands built in |
| Q21 | Free/local work done by Claude; paid steps run from scripts, gated by y/N |
| Q22 | Article drafted now with `[[RESULT]]` / `[[VERIFY]]` placeholders |

Also decided while building: select Golden Trajectories with a **feedback filter** (`exact == 1`, from our own ground-truth grading). Run council triage only as an **agreement experiment** on about 200 trajectories.

## Status

### Done (2026-09-25)
- [x] Domain: schema, CPF/CNH checksum validators (cross-checked against `validate-docbr` on 4,000 numbers), Transcription contract
- [x] Synthetic CNH generator (physical + digital + Non-CNH decoys, phone-photo augmentation, watermark)
- [x] Reader: model registry, mlx/OpenAI-compatible inference, mlx-vlm LoRA/QLoRA training wrapper
- [x] **Spike:** zero-shot PaddleOCR-VL-1.6 runs locally at 4–8 s/img. Value recall 91.8%, label accuracy 17.9% (n=4)
- [x] Extractor: 8 tools, agent, OCR-noise injector, traced runner with LangSmith feedback
- [x] Evaluation: metrics (label accuracy, value recall, CER, field accuracy), report, council-agreement script
- [x] smithtune: `run.sh` (all steps, paid steps gated) + `rubric.md`
- [x] Repo: README, LICENSE, Makefile, `.env.example`, `.gitignore`, 21 passing tests
- [x] Article drafts: EN long-form, LinkedIn EN (+ carousel outline)

### Next: free / local
- [ ] Full dataset built (`make data`), then spot-check 30 images by eye
- [ ] `make zero-shot N=50` for all 3 Readers (downloads about 30 GB of weights)
- [ ] LoRA: `make train-reader MODEL=paddleocr_vl`, then chandra2 and qwen35_9b with `QLORA=--qlora`
- [ ] `make eval-reader` for each + hard set
- [ ] BID loader (`evaluation/bid.py`): download the sample, inspect the annotation format, map to Transcription labels
- [ ] Private Real Samples check (local only)

### Next: paid (needs `.env`)
- [ ] `make teacher` (1,500 runs; estimate the cost on 20 runs first)
- [ ] `./smithtune/run.sh install doctor pull-golden push-golden`
- [ ] `triage-sample` → `cnh_ocr.evaluation.council_agreement`
- [ ] `prepare plan train evaluate deploy student-eval undeploy`
- [ ] `make report` → `docs/RESULTS.md` → fill in the article placeholders

### Launch
- [ ] Publish the synthetic dataset to the HF Hub (dataset card: synthetic, watermark, not a template)
- [ ] Push adapters (Chandra 2 adapter under Chandra's license terms)
- [ ] Repo public → Medium EN → LinkedIn EN → dev.to/Hashnode → HF community post
