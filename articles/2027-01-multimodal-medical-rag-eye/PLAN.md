# Plan: Multimodal RAG for eye scans, and why "explainable" needs evaluation

**Branch:** `article/2027-01-multimodal-medical-rag-eye` · **Target date:** 2027-01-08 · **Video project:** #2 (multimodal medical RAG for eye disease)

## Question

Does retrieving similar labeled eye images (with their reports) help a vision model classify retinal disease, compared with the model alone, and are its explanations faithful to what it retrieved?

## Brazilian angle

**BRSET**, the Brazilian Multilabel Ophthalmological Dataset (retinal fundus photos with labels). [[VERIFY: BRSET access is via PhysioNet credentialed access (CITI training + data use agreement); timeline and whether publishing derived results/code is allowed]]. Fallback: public datasets such as APTOS / ODIR / IDRiD [[VERIFY: licenses]].

**This is last in the queue because of that access process. Start the application now.**

## Architecture

1. **Embeddings:** BiomedCLIP image embeddings + text embeddings of labels/reports.
2. **Index:** Qdrant with hybrid search (dense image vectors + sparse text).
3. **Diagnosis:** a vision-language model gets the query image + top-k retrieved cases → labels.
4. **Explanation agent:** must cite the retrieved cases it relied on; a check verifies the citations.

## Evaluation

- Against dataset labels: macro-F1 per condition, for: zero-shot VLM · kNN on embeddings only · VLM + retrieval.
- Retrieval quality (label precision@k).
- Faithfulness: shuffle the retrieved cases' labels and see whether the diagnosis follows them.

## Guardrails

Not a medical device; a research demo only. No clinical claims. The article says so up front.

## Milestones

1. **Now:** PhysioNet credentialing for BRSET.
2. Pipeline on a public fallback dataset.
3. Swap in BRSET when access is approved.
4. Evaluation + drafts.

## Common rules (all five articles)

- **Source:** the idea comes from the video *"5 AI Agents Projects to Build in 2026: Full AI Architecture + 10X System"* (YouTube, 2026-09-28). Credit it in the article. The architecture here is ours; don't copy the video's code or diagrams.
- **Angle:** each article is a field report with runnable code, in the style of `2026-10-cnh-ocr-smithtune`: build it, measure it, show what broke.
- **Budget:** local first (M4 Pro 48 GB, mlx / Ollama). The cap for paid APIs is **US$10 per article**, set with `--max-cost` in the code; ask before any paid run.
- **Data:** public or synthetic only. No personal data. Record every dataset's license in `code/docs/DATA.md` before using it.
- **Numbers:** every number in the drafts comes from `code/docs/RESULTS.md`. Mark gaps with the RESULT / VERIFY placeholders described in CONTRIBUTING.md.
- **Deliverables:** EN long version + Medium short version, PT-BR, LinkedIn EN / PT-BR, code with tests + Makefile, `CONTEXT.md` glossary, ADRs for the hard decisions.
