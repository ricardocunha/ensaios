.PHONY: test download scans ocr-eval mcp synth serve review propose-real score-real

test:
	uv run pytest -q

# Contract PDFs from PNCP into data/pncp (git-ignored)
download:
	uv run python -m compliance_agents.pncp --scanned 10 --digital 40 --days 120 --start 2026-05-01

# Degraded scans of 20 text-layer contracts, 4 levels, first 6 pages
scans:
	uv run python -m compliance_agents.scans --docs 20

# Docling OCR on the degraded scans vs. the text layer (runs/ocr_eval.jsonl)
ocr-eval:
	uv run python -m compliance_agents.ocr_eval

# The MCP server (stdio)
mcp:
	uv run compliance-mcp

DOCS := $(shell seq -f "synth-%03g" 0 19)

synth:
	uv run python -m compliance_agents.synth --n 60

# needs a local model server: make serve (other terminal)
serve:
	uv run --group local mlx_lm.server --model mlx-community/Qwen3-8B-4bit --port 8088

review:
	uv run python -m compliance_agents.reviewer $(DOCS) --decide code --data data/synth/text --out runs/review_text_v2.jsonl
	uv run python -m compliance_agents.evaluate runs/review_text_v2.jsonl --data data/synth/text

# Reviewer proposals for the real-contract sheet (labels/real_contracts_proposed.csv)
propose-real:
	uv run python -m compliance_agents.reviewer $$(uv run python -m compliance_agents.real_labels docs) --decide code --data data/pncp --out runs/review_real.jsonl
	uv run python -m compliance_agents.real_labels propose

score-real:
	uv run python -m compliance_agents.real_labels score
