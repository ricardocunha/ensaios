"""MCP server that exposes parsed contracts to any agent.

Run: `uv run compliance-mcp` (stdio). Documents are read from $COMPLIANCE_DATA_DIR
(default data/pncp); parsing results are cached next to each PDF.
"""

from __future__ import annotations

import os
import unicodedata
from pathlib import Path

from mcp.server.mcpserver import MCPServer

from compliance_agents.parse import CLAUSE_RE, ParsedDocument, load_or_parse

PREAMBLE_CHARS = 1500  # the parties, their seats and the legal basis are usually here

server = MCPServer(
    "contract-parser",
    instructions=(
        "Parsed public-procurement contracts (Portuguese). Use parse_document for the outline, "
        "get_section for a clause's text, search_document to find clauses by keyword, and "
        "verify_quote to check that a quote appears verbatim in the document."
    ),
)


def data_dir() -> Path:
    return Path(os.environ.get("COMPLIANCE_DATA_DIR", "data/pncp"))


def _doc(doc_id: str) -> ParsedDocument:
    pdf = data_dir() / f"{Path(doc_id).name}.pdf"  # name only: no path traversal
    if not pdf.exists():
        raise ValueError(f"unknown document {doc_id!r}")
    return load_or_parse(pdf)


def normalize(text: str) -> str:
    """Case-, accent- and whitespace-insensitive form, for matching OCR text."""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return " ".join(text.lower().split())


def _page_quality(doc: ParsedDocument, pages: list[int]) -> float | None:
    """Lowest OCR score on these pages; None when they weren't OCR'd (a text layer needs no OCR).
    (Docling's mean_score mixes in layout confidence, which is low on perfectly readable pages.)"""
    scores = [doc.page_scores[p].get("ocr_score") for p in pages if p in doc.page_scores]
    scores = [s for s in scores if s is not None and s == s and s > 0]
    return round(min(scores), 3) if scores else None


def preamble_text(doc: ParsedDocument) -> str:
    """Everything before the first clause: letterhead, title and the parties' qualification.
    (Docling often labels the title as a heading, so the preamble can span several sections.)"""
    parts = []
    for s in doc.sections:
        if CLAUSE_RE.search(s.heading):
            break
        parts.append(f"{s.heading}\n{s.text}".strip())
    return "\n".join(parts)


@server.tool()
def list_documents() -> list[str]:
    """IDs of the available contracts."""
    return sorted(p.stem for p in data_dir().glob("*.pdf"))


@server.tool()
def parse_document(doc_id: str) -> dict:
    """Outline of a contract: page count, quality grades, the preamble (who the parties are) and section headings."""
    doc = _doc(doc_id)
    preamble = preamble_text(doc)
    return {
        "doc_id": doc.doc_id,
        "pages": doc.pages,
        "ocr_used": doc.ocr_used,
        "quality": {"mean_grade": doc.mean_grade, "low_grade": doc.low_grade},
        "preamble": preamble[:PREAMBLE_CHARS],
        "sections": [{"id": s.id, "heading": s.heading, "pages": s.pages, "chars": len(s.text)} for s in doc.sections],
    }


@server.tool()
def get_section(doc_id: str, section_id: int) -> dict:
    """Full text of one section, with the lowest quality score of the pages it spans."""
    doc = _doc(doc_id)
    if not 0 <= section_id < len(doc.sections):
        raise ValueError(f"section_id must be 0..{len(doc.sections) - 1}")
    s = doc.sections[section_id]
    return {"id": s.id, "heading": s.heading, "pages": s.pages, "page_quality": _page_quality(doc, s.pages), "text": s.text}


STEM = 6  # "vinculação" and "vincula-se" both start with "vincul"
STOPWORDS = {"a", "o", "as", "os", "de", "da", "do", "das", "dos", "e", "em", "no", "na", "ao", "à", "que", "com", "por", "para", "um", "uma"}


def _stems(text: str) -> list[str]:
    words = [w.strip(".,;:()[]\"'-/") for w in normalize(text).split()]
    return [w[:STEM] for w in words if w and w not in STOPWORDS]


@server.tool()
def search_document(doc_id: str, query: str, limit: int = 5) -> list[dict]:
    """Sections ranked by how many query words they contain (accent-insensitive, matching word stems,
    so "vinculação" finds "vincula-se"). Returns a snippet around the first match."""
    doc = _doc(doc_id)
    q = list(dict.fromkeys(_stems(query)))
    if not q:
        return []
    hits = []
    for s in doc.sections:
        body = normalize(s.heading + " " + s.text)
        words = set(_stems(body))
        matched = [w for w in q if w in words]
        if not matched:
            continue
        pos = min(body.find(w) for w in matched)
        hits.append({"id": s.id, "heading": s.heading, "pages": s.pages, "matched": f"{len(matched)}/{len(q)}",
                     "snippet": body[max(0, pos - 80) : pos + 220], "_score": len(matched) / len(q)})
    hits.sort(key=lambda h: -h["_score"])
    return [{k: v for k, v in h.items() if k != "_score"} for h in hits[:limit]]


@server.tool()
def verify_quote(doc_id: str, quote: str) -> dict:
    """Whether a quote appears verbatim in the document (ignoring case, accents and whitespace)."""
    doc = _doc(doc_id)
    q = normalize(quote)
    for s in doc.sections:
        if q and q in normalize(s.heading + " " + s.text):
            return {"found": True, "section_id": s.id, "heading": s.heading}
    return {"found": False}


def main() -> None:
    server.run("stdio")


if __name__ == "__main__":
    main()
