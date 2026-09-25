# cnh-ocr-smithtune

Reading Brazilian driver's licenses (CNH) with open models. The project also serves as a hands-on test of **[smithtune](https://github.com/langchain-ai/smithtune)**, LangSmith's new fine-tuning CLI (v0.1.0, released 2026-09-24).

```
 CNH image ─► [ Reader ]  ─► Transcription ─► [ Extractor ] ─► CNH Record (validated JSON)
              vision OCR model                  text-only tool-calling agent
              LoRA via mlx-vlm / TRL            Teacher (Claude Sonnet 5) → Student (Qwen3.5-9B)
              Chandra 2 · PaddleOCR-VL-1.6      distilled with smithtune on Baseten
              · Qwen3.5-9B
```

**Why two stages?** smithtune v0.1 [filters out every trajectory containing images](docs/SMITHTUNE_NOTES.md), and it can only train a fixed list of text LLMs. So the vision part is fine-tuned with Hugging Face / MLX tooling, and smithtune does what it was built for: distilling an agent's behavior. See [ADR-0001](docs/adr/0001-two-stage-reader-extractor.md).

> ⚠️ **All training data is synthetic.** Every image says *AMOSTRA / SYNTHETIC*, the layout is deliberately not a replica, and the CPF and CNH numbers are random (with valid checksums). Never commit real documents ([ADR-0002](docs/adr/0002-synthetic-training-data-only.md), LGPD).

## Results

`[[RESULT: filled from docs/RESULTS.md after the runs]]`

## Quickstart

```bash
uv sync --all-extras
make test
make data                               # ~3.7k synthetic CNH images (free, local)
make zero-shot N=50                     # baseline for all three Readers on Apple Silicon
make train-reader MODEL=paddleocr_vl    # LoRA on the Mac; QLORA=--qlora for the 9B models
make eval-reader  MODEL=paddleocr_vl

cp .env.example .env                    # keys for the paid steps
make teacher                            # 1,500 Teacher runs → LangSmith, auto-graded
./smithtune/run.sh install && ./smithtune/run.sh doctor
./smithtune/run.sh pull-golden && ./smithtune/run.sh push-golden
./smithtune/run.sh prepare && ./smithtune/run.sh plan && ./smithtune/run.sh train
./smithtune/run.sh evaluate && ./smithtune/run.sh deploy && ./smithtune/run.sh student-eval
./smithtune/run.sh undeploy             # don't forget!
make report
```

## Layout

| Path | What |
|---|---|
| `CONTEXT.md` | Glossary: Reader, Transcription, Extractor, CNH Record, Teacher, Student, Golden Trajectory… |
| `src/cnh_ocr/synth/` | Synthetic CNH generator (records → render → phone-photo augmentation) |
| `src/cnh_ocr/reader/` | The three Base OCR Models, mlx-vlm inference + LoRA training |
| `src/cnh_ocr/extractor/` | Extractor agent (LangChain `create_agent`), tools, OCR-noise injector, traced runner |
| `src/cnh_ocr/evaluation/` | Metrics, report, smithtune council-vs-ground-truth agreement |
| `smithtune/` | `run.sh` (every smithtune step, paid steps gated) + triage `rubric.md` |
| `docs/` | ADRs, smithtune field notes, results |

## Models and licenses

| Model | License | Note |
|---|---|---|
| `datalab-to/chandra-ocr-2` | AI Pubs Open RAIL-M (modified) | Free for research and personal use. **Commercial use is prohibited above US$2M revenue or funding**, and a share-alike clause covers derivatives and outputs. Adapters are published under the same license. |
| `PaddlePaddle/PaddleOCR-VL-1.6` | Apache-2.0 | |
| `Qwen/Qwen3.5-9B` | Apache-2.0 | Used both as a Reader and as the smithtune Student |

Evaluation also uses the **BID Dataset** (Soares, Junior & Bezerra, SIBGRAPI 2020). It's cited only; it is not redistributed and not used for training (it has no license).

## License

Code: Apache-2.0. Synthetic dataset: CC-BY-4.0.
