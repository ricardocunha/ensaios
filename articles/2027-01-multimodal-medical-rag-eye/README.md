# My eye-scan RAG cited its sources. It was reading the labels.

**Status:** drafts complete (EN, EN Medium, LinkedIn); numbers final; proofread; links pending · **Branch:** `article/2027-01-multimodal-medical-rag-eye` · **Target date:** 2027-01-08

> **Research demo, not a medical device.** Nothing here diagnoses anyone or supports a clinical decision. The numbers measure agreement with the labels of one public dataset, not diagnostic accuracy.

A field report on multimodal medical RAG, run entirely locally: BiomedCLIP embeddings in a Qdrant hybrid index, a local Qwen3-VL-8B that diagnoses a retinal photo next to the 3 most similar labelled cases, and an explanation agent whose citations are checked in code. On RFMiD (public, CC BY 4.0; 609 deduplicated test images), retrieval lifts the VLM from 0.058 to 0.298 macro-F1 (16 frequent conditions) but stays below the plain kNN vote (0.341). Showing the same case photos with shuffled labels erases the whole gain (0.056), and the citation check verifies 90.0 % vs 89.3 % of explanations either way: it proves consistency with the text shown, not correctness. The Brazil angle: BRSET (16,266 photos, São Paulo) exists but needs credentialed access; the harness is built to be rerun on it. See [PLAN.md](PLAN.md), [code/docs/DATA.md](code/docs/DATA.md) and [code/docs/RESULTS.md](code/docs/RESULTS.md).

| | |
|---|---|
| Article (EN) | [article-en.md](article-en.md) · Medium version: [article-en-medium.md](article-en-medium.md) |
| LinkedIn | [linkedin-en.md](linkedin-en.md) |
| Code | [code/](code/) |
| Plan | [PLAN.md](PLAN.md) |

## Published

- Medium: [[LINK]]
- LinkedIn: [[LINK]]
