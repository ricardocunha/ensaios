# I tested LangSmith's brand-new smithtune on Brazilian driver's licenses

**Status:** draft; Stage 1 done, Stage 2 (smithtune) pending · **Branch:** `article/2026-10-cnh-ocr-smithtune` · **Target date:** 2026-10-16

A field report on **smithtune** (LangSmith Fine-Tuning, v0.1.0, released 2026-09-24), applied to reading Brazilian CNHs with open models:

- **Stage 1 (Reader):** open OCR models (Chandra 2, PaddleOCR-VL-1.6, Qwen3.5-9B) on synthetic and real CNH templates. PaddleOCR-VL is fine-tuned with LoRA on an M4 Pro, across three rounds that close the synthetic-to-real gap.
- **Stage 2 (Extractor):** a Claude Sonnet 5 tool-using agent distilled into Qwen3.5-9B with smithtune. smithtune v0.1 can't train on images, which is why the pipeline has two stages.

| | |
|---|---|
| Article (EN) | [article-en.md](article-en.md) |
| Article (PT-BR) | [article-pt-br.md](article-pt-br.md) |
| LinkedIn | [EN](linkedin-en.md) · [PT-BR](linkedin-pt-br.md) |
| Code, results, ADRs, field notes | [code/](code/) · [results](code/docs/RESULTS.md) · [notes](code/docs/SMITHTUNE_NOTES.md) |

## Published

- Medium: [[LINK]]
- LinkedIn: [[LINK]]
