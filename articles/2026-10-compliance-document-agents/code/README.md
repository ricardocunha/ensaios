# Compliance agents that know when they're unsure: code

Compliance review over Brazilian public-procurement contracts (PNCP): Docling parses scanned PDFs, an MCP server exposes them to agents, and a Pydantic AI reviewer checks rules and escalates what it isn't sure about. See [../PLAN.md](../PLAN.md).

## Quickstart

```bash
uv sync
make test
make download     # contract PDFs from the PNCP public API (no key needed)
make scans        # degraded "scans" with known ground truth
make ocr-eval     # how good is OCR, and does Docling's confidence predict its errors?
```

Use the parser from any MCP client (Claude Code, Claude Desktop, Pydantic AI…):

```json
{"mcpServers": {"contract-parser": {"command": "uv", "args": ["run", "--directory", "<this folder>", "compliance-mcp"]}}}
```

Tools: `list_documents`, `parse_document`, `get_section`, `search_document`, `verify_quote`.

OCR uses Apple Vision (`ocrmac`), so parsing scans needs macOS. On other systems, change `OcrMacOptions` in `parse.py` to `EasyOcrOptions` or `TesseractOcrOptions`.

## Data

Public contracts contain personal data, so nothing downloaded is committed. See [docs/DATA.md](docs/DATA.md).
