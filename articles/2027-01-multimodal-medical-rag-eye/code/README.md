# Multimodal RAG for eye scans: code

> **Research demo, not a medical device.** No clinical claims: the numbers measure agreement with one public dataset's labels.

Retinal fundus photos (RFMiD) embedded with BiomedCLIP into a local Qdrant index, plus two baselines: kNN over the index and BiomedCLIP zero-shot. See [../PLAN.md](../PLAN.md).

## Quickstart

```bash
uv sync
make test          # offline, synthetic fixtures
make download      # RFMiD 1.0 from a CC BY 4.0 mirror, no account (~8.2 GB transferred, ~1024 px JPEGs kept)
make stats         # label counts per official split
make baselines     # BiomedCLIP embeddings (cached) + Qdrant index + baselines -> runs/m1_baselines.{json,md}
```

Embeddings run on Apple Silicon (MPS) when available, else CUDA or CPU. The Qdrant index is a folder (`data/qdrant`), no server.

| Module | What |
|---|---|
| `eye_rag.rfmid` | download (pinned mirror revision, SHA-256 checked), loader with the official split |
| `eye_rag.labels` | the 45 RFMiD conditions with names and short visual descriptions |
| `eye_rag.embed` | BiomedCLIP image/text embeddings with an on-disk cache |
| `eye_rag.index` | Qdrant collections: `rfmid_images` (payload = labels) and `rfmid_labels` (label-text vectors, for hybrid search later) |
| `eye_rag.baselines`, `eye_rag.metrics`, `eye_rag.evaluate` | kNN and zero-shot baselines, macro-F1, label precision@k |

## Data and licences

RFMiD (Pachade et al., *Data* 2021, doi:10.3390/data6020014), CC BY 4.0. BiomedCLIP, MIT (research use per its model card). Nothing downloaded is committed. Details, alternatives and citations: [docs/DATA.md](docs/DATA.md). Results: [docs/RESULTS.md](docs/RESULTS.md).
