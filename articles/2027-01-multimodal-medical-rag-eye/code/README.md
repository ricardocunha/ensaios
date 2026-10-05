# Multimodal RAG for eye scans: code

> **Research demo, not a medical device.** No clinical claims: the numbers measure agreement with one public dataset's labels.

Retinal fundus photos (RFMiD) embedded with BiomedCLIP into a local Qdrant index (dense image vectors + sparse label-report text), a same-eye duplicate audit, kNN and BiomedCLIP zero-shot baselines, and a local vision-language model (Qwen3-VL-8B via mlx-vlm) with and without retrieved cases in the prompt. See [../PLAN.md](../PLAN.md).

## Quickstart

```bash
uv sync
make test          # offline, synthetic fixtures
make download      # RFMiD 1.0 from a CC BY 4.0 mirror, no account (~8.2 GB transferred, ~1024 px JPEGs kept)
make stats         # label counts per official split
make embed         # BiomedCLIP embeddings only (cached; `make baselines` also builds them)
make baselines     # BiomedCLIP embeddings (cached) + Qdrant index + baselines -> runs/m1_baselines.{json,md}

# Milestone 2
make dedup         # same-eye audit over all image pairs -> docs/exclusions.json (~11 min, CPU)
make m2-baselines  # M1 baselines on all vs deduplicated test
make retrieval     # label precision@k, dense vs hybrid (hybrid_knn and the oracle bound)
uv sync --group vlm                 # mlx-vlm (Apple Silicon only)
make vlm-zero-shot                  # Qwen3-VL-8B 4-bit, ~5 s per image on an M4 Pro
make vlm-retrieval RETRIEVAL=hybrid_knn   # + 3 retrieved cases per image, ~7.5 s per image
make m2-score      # three-arm table
make retrieval-vlm # retrieval again, plus the hybrid query built from the VLM zero-shot labels
make vlm-shuffled   # faithfulness test: same case images, wrong labels, ~7 s per image
make explain explain-shuffled   # explanation agent + citation check on both arms, ~12-13 s per image
make explain-score  # citation, explanation and faithfulness scores

# Milestone 4
make evaluate      # paired bootstrap 95 % intervals from the run files (no model) -> runs/m4_eval.json
```

`N=…` on the `vlm-*` targets runs a seeded subset of the deduplicated test split.

Embeddings run on Apple Silicon (MPS) when available, else CUDA or CPU. The Qdrant index is a folder (`data/qdrant`), no server.

| Module | What |
|---|---|
| `eye_rag.rfmid` | download (pinned mirror revision, SHA-256 checked), loader with the official split |
| `eye_rag.labels` | the 45 RFMiD conditions with names and short visual descriptions |
| `eye_rag.embed` | BiomedCLIP image/text embeddings with an on-disk cache |
| `eye_rag.index` | Qdrant collections: `rfmid_images` (payload = labels) and `rfmid_labels` (label-text vectors; not used by the reported results) |
| `eye_rag.baselines`, `eye_rag.metrics`, `eye_rag.evaluate` | kNN and zero-shot baselines, macro-F1, label precision@k |
| `eye_rag.dedup` | same-eye audit (cosine, pHash, SIFT + RANSAC on the retina) and the exclusion list |
| `eye_rag.hybrid` | hybrid Qdrant collection `rfmid_hybrid`: dense image vector + sparse "report" built from labels, RRF fusion |
| `eye_rag.vlm`, `eye_rag.diagnose` | typed VLM diagnosis (Pydantic, retries on invalid JSON), mlx-vlm backend, the run loop (incl. the shuffled-labels arm) |
| `eye_rag.m2` | Milestone 2 evaluation: dedup re-score, retrieval precision, three-arm table |
| `eye_rag.explain` | Explanation agent, deterministic citation check, faithfulness scores |
| `eye_rag.m4` | Milestone 4 evaluation: paired bootstrap intervals over the 609 deduplicated test images |

## Data and licences

RFMiD (Pachade et al., *Data* 2021, doi:10.3390/data6020014), CC BY 4.0. BiomedCLIP, MIT (research use per its model card). Qwen3-VL-8B-Instruct, Apache-2.0. Nothing downloaded is committed. Details, alternatives and citations: [docs/DATA.md](docs/DATA.md). Results: [docs/RESULTS.md](docs/RESULTS.md).
