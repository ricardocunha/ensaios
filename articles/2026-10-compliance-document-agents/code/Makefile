.PHONY: test download scans ocr-eval mcp

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
