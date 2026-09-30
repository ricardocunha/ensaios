"""Parse contract PDFs with Docling into sections, keeping Docling's quality signals.

Scanned pages go through OCR (Apple Vision via ocrmac, pt-BR). Each parsed document is
cached as JSON next to the PDF, so the MCP server and the agents never re-run OCR.
"""

from __future__ import annotations

import argparse
import json
import re
import time
from dataclasses import asdict, dataclass, field
from functools import lru_cache
from pathlib import Path

from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import OcrMacOptions, PdfPipelineOptions
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling_core.types.doc import DocItemLabel

# Contract clauses: "CLÁUSULA PRIMEIRA – DO OBJETO", "CLÁUSULA 5ª", "CLÁUSULA DÉCIMA SEGUNDA"...
CLAUSE_RE = re.compile(r"^\s*(?:\d+[.)]?\s*)?CL[ÁA]USULA\b", re.IGNORECASE)  # "1. CLÁUSULA PRIMEIRA" too


@dataclass
class Section:
    id: int
    heading: str
    text: str
    pages: list[int]


@dataclass
class ParsedDocument:
    doc_id: str
    source: str
    pages: int
    seconds: float
    ocr_used: bool
    mean_grade: str  # Docling's confidence grade: poor / fair / good / excellent
    low_grade: str
    page_scores: dict[int, dict[str, float]] = field(default_factory=dict)
    sections: list[Section] = field(default_factory=list)
    markdown: str = ""


@lru_cache(maxsize=1)
def converter() -> DocumentConverter:
    opts = PdfPipelineOptions(do_ocr=True, ocr_options=OcrMacOptions(lang=["pt-BR"]))
    return DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=opts)})


def _is_heading(label: DocItemLabel, text: str) -> bool:
    return label in (DocItemLabel.SECTION_HEADER, DocItemLabel.TITLE) or bool(CLAUSE_RE.match(text))


def split_sections(items: list[tuple[DocItemLabel, str, int]]) -> list[Section]:
    """Group (label, text, page) items into sections, starting a new one at each heading."""
    preamble = "(preâmbulo)"
    sections: list[Section] = []
    current = Section(id=0, heading=preamble, text="", pages=[])

    def close() -> None:
        if current.text or current.heading != preamble:  # drop an empty preamble only
            current.id = len(sections)
            sections.append(current)

    for label, text, page in items:
        text = text.strip()
        if not text:
            continue
        if _is_heading(label, text):
            close()
            current = Section(id=0, heading=text, text="", pages=[page])
            continue
        current.text += text + "\n"
        if page not in current.pages:
            current.pages.append(page)
    close()
    return sections


def item_text(item, doc) -> str | None:
    """An item's text, with its list marker put back ("5.3 O prazo..."): Docling moves
    paragraph numbers into `marker`, and those numbers are what a finding cites."""
    if item.label == DocItemLabel.TABLE:
        return item.export_to_markdown(doc=doc)
    text = getattr(item, "text", None)
    marker = (getattr(item, "marker", "") or "").strip()
    if text is not None and marker and marker not in "-•*·":
        text = f"{marker} {text}"
    return text


def parse_pdf(pdf: Path) -> ParsedDocument:
    t0 = time.perf_counter()
    res = converter().convert(pdf)
    seconds = time.perf_counter() - t0
    doc = res.document

    items = []
    for item, _level in doc.iterate_items():
        text = item_text(item, doc)
        if text is None:
            continue
        page = item.prov[0].page_no if item.prov else 0
        items.append((item.label, text, page))

    conf = res.confidence
    page_scores = {
        int(p): {k: round(float(v), 3) for k, v in s.model_dump().items() if isinstance(v, (int, float)) and v == v}
        for p, s in conf.pages.items()
    }
    ocr_used = any(s.get("ocr_score", 0) > 0 for s in page_scores.values())
    return ParsedDocument(
        doc_id=pdf.stem,
        source=str(pdf),
        pages=len(res.pages),
        seconds=round(seconds, 1),
        ocr_used=ocr_used,
        mean_grade=str(conf.mean_grade.value),
        low_grade=str(conf.low_grade.value),
        page_scores=page_scores,
        sections=split_sections(items),
        markdown=doc.export_to_markdown(),
    )


def cache_path(pdf: Path) -> Path:
    return pdf.with_suffix(".parsed.json")


def load_or_parse(pdf: Path) -> ParsedDocument:
    cp = cache_path(pdf)
    if cp.exists():
        raw = json.loads(cp.read_text())
        raw["sections"] = [Section(**s) for s in raw["sections"]]
        raw["page_scores"] = {int(k): v for k, v in raw["page_scores"].items()}
        return ParsedDocument(**raw)
    parsed = parse_pdf(pdf)
    cp.write_text(json.dumps(asdict(parsed), ensure_ascii=False, indent=1))
    return parsed


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("pdfs", nargs="+", type=Path)
    args = ap.parse_args()
    for pdf in args.pdfs:
        p = load_or_parse(pdf)
        print(f"{p.doc_id}: {p.pages}p {p.seconds}s ocr={p.ocr_used} grade={p.mean_grade}/{p.low_grade} sections={len(p.sections)}")


if __name__ == "__main__":
    main()
