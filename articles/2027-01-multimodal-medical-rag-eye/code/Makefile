.PHONY: test download stats embed baselines

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
