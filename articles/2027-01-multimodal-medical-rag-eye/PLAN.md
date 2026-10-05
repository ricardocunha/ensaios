# Plan: Multimodal RAG for eye scans, and why "explainable" needs evaluation

**Branch:** `article/2027-01-multimodal-medical-rag-eye` · **Target date:** 2027-01-08 · **Video project:** #2 (multimodal medical RAG for eye disease)

## Question

Does retrieving similar labeled eye images (with their reports) help a vision model classify retinal disease, compared with the model alone, and are its explanations faithful to what it retrieved?

## Dataset decision (2026-10-01)

**Public fallback first, BRSET later if access is granted.** The pipeline runs on **RFMiD 1.0** (3,200 fundus photos, 45 conditions, multi-label, official 1,920 / 640 / 640 split, CC BY 4.0), downloaded from a CC BY mirror on Hugging Face with no account. RFMiD 2.0 (860 images, Zenodo, CC BY 4.0) is kept for an out-of-distribution check. The audit of 12 candidates and the reasons are in [code/docs/DATA.md](code/docs/DATA.md).

**BRSET: optional, "replicate later if access is granted".** No application is being made now (no sign-ups in this project). If credentialed access is ever granted, Milestone 3 swaps the index to BRSET and reruns the same evaluation.

## Brazilian angle (short framing section)

Brazil has a well-documented ophthalmology dataset, **BRSET** (Brazilian Multilabel Ophthalmological Dataset; Nakayama et al., *PLOS Digital Health*, 2024): 16,266 fundus photos of 8,524 patients from three ophthalmology centres in São Paulo, 2010–2020, with multi-label disease, image-quality and demographic labels (PhysioNet, v1.0.2). But "open" means **credentialed** access on PhysioNet: an account, CITI "Data or Specimens Only Research" training, and a signed data use agreement (PhysioNet Credentialed Health Data License 1.5.0). That's a reasonable protection for patient data, and it's also a real barrier for a reader who wants to rerun an article in an afternoon. The point for the article: a Brazilian dataset exists and is well documented, and the access model decides who can actually use it. Its DUA also asks anyone who publishes results to publish their code, which this repo does anyway. Decided 2026-10-05: the drafts do not mention mBRSET (smartphone fundus photos, also on PhysioNet); BRSET alone makes the point.

## Architecture

1. **Embeddings:** BiomedCLIP image embeddings + text embeddings of labels/reports. RFMiD has labels but no free-text reports, so a retrieved case's "report" will be text generated from its labels and the label descriptions in `eye_rag.labels`.
2. **Index:** Qdrant with hybrid search (dense image vectors + sparse text).
3. **Diagnosis:** a vision-language model gets the query image + top-k retrieved cases → labels.
4. **Explanation agent:** must cite the retrieved cases it relied on; a check verifies the citations.

## Evaluation

- Against dataset labels: macro-F1 per condition, for: zero-shot VLM · kNN on embeddings only · VLM + retrieval.
- Retrieval quality (label precision@k).
- Faithfulness: shuffle the retrieved cases' labels and see whether the diagnosis follows them.

## Guardrails

- **Not a medical device; a research demo only. No clinical claims.** The article and the code README say so up front.
- Numbers are about agreement with dataset labels on one public dataset (RFMiD, three cameras, India), not about diagnostic accuracy on patients.
- BiomedCLIP's own model card rules out "any deployed use case"; we use it for research only.
- No retinal images in git; at most a few attributed thumbnails in the article.

## Milestones

1. **Done (2026-10-01):** dataset choice (RFMiD) + BiomedCLIP embedding index (Qdrant, local) + kNN and zero-shot baselines.
2. **Done (2026-10-05):** VLM + retrieval (top-k cases in the prompt), explanation agent with citation check, faithfulness test (shuffled labels).
3. Optional: rerun on BRSET if credentialed access is ever granted; RFMiD 2.0 as an out-of-distribution check.
4. **Done (2026-10-05):** evaluation (paired bootstrap, RESULTS §3) + drafts (EN, EN Medium, PT-BR, LinkedIn EN/PT-BR), glossary (`code/CONTEXT.md`), ADRs 0001–0002. Left: proofread, launch-day links.

## Milestone 1 result (2026-10-01)

- **Dataset:** RFMiD 1.0 (CC BY 4.0, no account, via a pinned HF mirror with SHA-256 checks). 7.99 GB downloaded, 228 MB kept (1,024 px JPEGs). Twelve candidates audited in `code/docs/DATA.md`; BRSET deferred (credentialed access).
- **Index:** BiomedCLIP image embeddings of all 3,200 images in 34.9 s on MPS; Qdrant local mode, payload = labels; a second collection holds label-text embeddings for hybrid search later.
- **Baselines (test split, macro-F1 over the 16 conditions with ≥ 20 training images):** kNN weighted (k = 20, chosen on val) **0.339**; kNN majority (k = 5) 0.264; BiomedCLIP zero-shot 0.141 (0.183 with val-tuned thresholds); all-positive floor 0.108. Normal-vs-abnormal F1: kNN 0.931, zero-shot 0.793 (floor 0.883).
- **Retrieval:** 49.6% of top-10 neighbours share a label with the query (15.0% at random).
- **Surprises:** zero-shot is barely above the floor and badly calibrated (val-tuned thresholds 0.03–0.999); small findings (drusen, laser scars, disc pallor) are invisible to a global 224-px embedding; at least two test images have a near-identical training photo of the same eye with a different label.
- Details: `code/docs/RESULTS.md`. 19 offline tests.

## Milestone 2 result (2026-10-05)

- **Same-eye audit:** 154 same-eye pairs among 263 images (SIFT + RANSAC on the vessel pattern), 54 % with different labels; 31 test images excluded → 609 deduplicated. Duplicates did not inflate kNN (0.339 → 0.341); their real cost is label noise.
- **Hybrid retrieval** (Qdrant dense image + sparse label-report text, RRF) with kNN-derived query text: frequent-label P@3 0.329 vs 0.277 dense. With the VLM's own labels as query text it gets worse than dense.
- **VLM (Qwen3-VL-8B 4-bit, local):** zero-shot 0.058 macro-F1 (below the 0.107 floor); + 3 retrieved cases 0.298; kNN 0.341. Retrieval helps the VLM but it does not beat the kNN it is built on.
- **Shuffled labels:** same case photos, wrong labels → 0.056, back to zero-shot; 58 % of answers change; 29 % of images get a wrong label only the shown text explains.
- **Citation check:** passes 90.0 % (true labels) vs 89.3 % (shuffled) after retries; verified case citations name a true label 48.8 % vs 12.2 % of the time. The check measures consistency with the retrieved text, not correctness.
- Details: `code/docs/RESULTS.md` §2. 47 offline tests.

## Common rules (all five articles)

- **Source:** the idea comes from the video *"5 AI Agents Projects to Build in 2026: Full AI Architecture + 10X System"* (YouTube, 2026-09-28). Credit it in the article. The architecture here is ours; don't copy the video's code or diagrams.
- **Angle:** each article is a field report with runnable code, in the style of `2026-10-cnh-ocr-smithtune`: build it, measure it, show what broke.
- **Budget:** local first (M4 Pro 48 GB, mlx / Ollama). The cap for paid APIs is **US$10 per article**, set with `--max-cost` in the code; ask before any paid run.
- **Data:** public or synthetic only. No personal data. Record every dataset's license in `code/docs/DATA.md` before using it.
- **Numbers:** every number in the drafts comes from `code/docs/RESULTS.md`. Mark gaps with the RESULT / VERIFY placeholders described in CONTRIBUTING.md.
- **Deliverables:** EN long version + Medium short version, PT-BR, LinkedIn EN / PT-BR, code with tests + Makefile, `CONTEXT.md` glossary, ADRs for the hard decisions.
