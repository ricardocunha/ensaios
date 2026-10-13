.PHONY: test download stats embed baselines dedup m2-baselines retrieval vlm-zero-shot vlm-retrieval m2-score retrieval-vlm vlm-shuffled explain explain-shuffled explain-score evaluate viewer

N ?=            # VLM subset size (empty = the whole deduplicated test split)
RETRIEVAL ?= dense

test:
	uv run pytest -q

# RFMiD 1.0 from the pinned CC BY 4.0 mirror into data/rfmid (git-ignored).
# Downloads ~8.2 GB of PNGs, keeps ~1024 px JPEG copies.
download:
	nice -n 10 uv run python -m eye_rag.rfmid download

# Label counts per official split (markdown)
stats:
	uv run python -m eye_rag.rfmid stats

# BiomedCLIP image embeddings (cached in data/embeddings)
embed:
	nice -n 10 uv run python -m eye_rag.embed

# Qdrant index + kNN and zero-shot baselines -> runs/m1_baselines.{json,md}
baselines:
	nice -n 10 uv run python -m eye_rag.evaluate

# --- Milestone 2
# Same-eye audit over all image pairs -> docs/exclusions.json (committed) + runs/dedup_pairs.json
dedup:
	nice -n 10 uv run python -m eye_rag.dedup

# M1 baselines re-scored on all vs deduplicated test -> runs/m2_baselines_dedup.json
m2-baselines:
	nice -n 10 uv run python -m eye_rag.m2 baselines

# Label precision@k, dense vs hybrid (dense + sparse label-report text, RRF) -> runs/m2_retrieval.json
retrieval:
	nice -n 10 uv run python -m eye_rag.m2 retrieval

# VLM arms (local, mlx-vlm, Qwen3-VL-8B 4-bit) -> runs/m2_vlm_test_*.jsonl (resumable)
vlm-zero-shot:
	nice -n 10 uv run --group vlm python -m eye_rag.diagnose --arm zero_shot --split test $(if $(N),--n $(N))

vlm-retrieval:
	nice -n 10 uv run --group vlm python -m eye_rag.diagnose --arm retrieval --split test --retrieval $(RETRIEVAL) $(if $(N),--n $(N))

# Three-arm table (VLM zero-shot, VLM + retrieved cases, kNN) -> runs/m2_three_arms_test.json
m2-score:
	nice -n 10 uv run python -m eye_rag.m2 score

# Retrieval again, adding the hybrid query built from the VLM zero-shot labels (needs vlm-zero-shot)
retrieval-vlm:
	nice -n 10 uv run python -m eye_rag.m2 retrieval --with-vlm

# Faithfulness test: the retrieval arm's case images with wrong (random other training) labels
vlm-shuffled:
	nice -n 10 uv run --group vlm python -m eye_rag.diagnose --arm shuffled --split test --retrieval hybrid_knn $(if $(N),--n $(N))

# Explanation agent + citation check on each arm's diagnoses -> runs/m2_explain_test_*.jsonl (resumable)
explain:
	nice -n 10 uv run --group vlm python -m eye_rag.explain run --arm retrieval --split test $(if $(N),--n $(N))

explain-shuffled:
	nice -n 10 uv run --group vlm python -m eye_rag.explain run --arm shuffled --split test $(if $(N),--n $(N))

# Citation, explanation and faithfulness scores -> runs/m2_explain_test.json
explain-score:
	nice -n 10 uv run python -m eye_rag.explain score

# --- Milestone 4
# Paired bootstrap 95 % intervals for the Milestone 2 numbers (reads run files only) -> runs/m4_eval.json
evaluate:
	nice -n 10 uv run python -m eye_rag.m4

# --- Viewer
# React page that walks one test image through the pipeline, from the run files (needs Node) -> http://localhost:5174
viewer:
	uv run python -m eye_rag.viewer
	npm --prefix viewer install --no-audit --no-fund
	npm --prefix viewer run dev
