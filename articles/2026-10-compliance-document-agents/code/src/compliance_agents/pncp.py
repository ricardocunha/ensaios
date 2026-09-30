"""Download contract PDFs from PNCP (Portal Nacional de Contratações Públicas).

The PDFs are public, but they carry personal data (suppliers, signatories), so they
stay in data/ (git-ignored) and only a manifest of their identifiers is reported.
"""

from __future__ import annotations

import argparse
import json
import random
import time
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from pathlib import Path

import httpx
import numpy as np
import pypdfium2 as pdfium

CONSULTA = "https://pncp.gov.br/api/consulta/v1"
PNCP = "https://pncp.gov.br/api/pncp/v1"
MIN_CHARS_PER_PAGE = 200  # below this, a page has no usable text layer
MIN_INK = 0.005  # share of dark pixels; PNCP has many blank or broken uploads


@dataclass
class ContractPdf:
    control: str  # numeroControlePNCP
    cnpj: str
    year: int
    seq: int
    category: str
    title: str
    path: str
    pages: int
    text_pages: int  # pages with a usable text layer
    ink_pages: int = 0  # sampled pages (up to 3) that aren't blank

    @property
    def scanned(self) -> bool:
        return self.text_pages == 0

    @property
    def blank(self) -> bool:
        return self.text_pages == 0 and self.ink_pages == 0


def _get(client: httpx.Client, url: str, **params) -> httpx.Response:
    for attempt in range(4):
        resp = client.get(url, params=params or None)
        if resp.status_code in (429, 500, 502, 503, 504):
            time.sleep(2 * (attempt + 1))
            continue
        resp.raise_for_status()
        return resp
    resp.raise_for_status()
    return resp


def list_contracts(client: httpx.Client, day: date, page: int = 1, size: int = 50) -> list[dict]:
    d = day.strftime("%Y%m%d")
    resp = _get(client, f"{CONSULTA}/contratos", dataInicial=d, dataFinal=d, pagina=page, tamanhoPagina=size)
    if resp.status_code == 204 or not resp.content:
        return []
    return resp.json().get("data", [])


def text_layer_pages(pdf_path: Path) -> tuple[int, int]:
    doc = pdfium.PdfDocument(pdf_path)
    try:
        text = sum(
            len(doc[i].get_textpage().get_text_range().strip()) >= MIN_CHARS_PER_PAGE for i in range(len(doc))
        )
        return len(doc), text
    finally:
        doc.close()


def ink_pages(pdf_path: Path, sample: int = 3) -> int:
    """How many of the first pages have visible content (scans with no text layer look empty to pdfium)."""
    doc = pdfium.PdfDocument(pdf_path)
    try:
        n = 0
        for i in range(min(len(doc), sample)):
            gray = np.asarray(doc[i].render(scale=0.5).to_pil().convert("L"))
            n += float((gray < 128).mean()) >= MIN_INK
        return n
    finally:
        doc.close()


def download_contract(client: httpx.Client, c: dict, out: Path) -> ContractPdf | None:
    cnpj = c["orgaoEntidade"]["cnpj"]
    year, seq = c["anoContrato"], c["sequencialContrato"]
    resp = _get(client, f"{PNCP}/orgaos/{cnpj}/contratos/{year}/{seq}/arquivos")
    if not resp.content:  # some contracts have no files: empty 200/204 instead of []
        return None
    files = resp.json()
    doc = next((f for f in files if f.get("tipoDocumentoNome") == "Contrato"), None)
    if doc is None:
        return None
    resp = _get(client, doc["url"])
    if not resp.content.startswith(b"%PDF"):
        return None  # docx, zip, html error pages, ...
    path = out / f"{cnpj}-{year}-{seq}.pdf"
    path.write_bytes(resp.content)
    try:
        pages, text_pages = text_layer_pages(path)
        inked = ink_pages(path) if text_pages == 0 else 0
    except Exception:
        path.unlink(missing_ok=True)
        return None
    return ContractPdf(
        control=c["numeroControlePNCP"],
        cnpj=cnpj,
        year=year,
        seq=seq,
        category=(c.get("categoriaProcesso") or {}).get("nome", ""),
        title=doc.get("titulo", ""),
        path=str(path),
        pages=pages,
        text_pages=text_pages,
        ink_pages=inked,
    )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=Path("data/pncp"))
    ap.add_argument("--scanned", type=int, default=20, help="scanned PDFs to collect")
    ap.add_argument("--digital", type=int, default=10, help="PDFs with a text layer to collect")
    ap.add_argument("--max-pages", type=int, default=30)
    ap.add_argument("--start", type=date.fromisoformat, default=date(2026, 6, 1))
    ap.add_argument("--days", type=int, default=90)
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    manifest_path = args.out / "manifest.jsonl"
    have = [json.loads(line) for line in manifest_path.read_text().splitlines()] if manifest_path.exists() else []
    seen = {h["control"] for h in have}
    n_scanned = sum(h["text_pages"] == 0 for h in have)
    n_digital = len(have) - n_scanned

    rng = random.Random(args.seed)
    days = [args.start + timedelta(days=i) for i in range(args.days)]
    rng.shuffle(days)
    with httpx.Client(timeout=60, follow_redirects=True) as client, manifest_path.open("a") as manifest:
        for day in days:
            if n_scanned >= args.scanned and n_digital >= args.digital:
                break
            contracts = list_contracts(client, day)
            rng.shuffle(contracts)
            for c in contracts[:40]:
                if c["numeroControlePNCP"] in seen:
                    continue
                try:
                    pdf = download_contract(client, c, args.out)
                except (httpx.HTTPError, ValueError):  # network errors, malformed JSON
                    continue
                if pdf is None or pdf.blank:
                    if pdf is not None:
                        Path(pdf.path).unlink(missing_ok=True)
                    continue
                need = n_scanned < args.scanned if pdf.scanned else n_digital < args.digital
                if not need or pdf.pages > args.max_pages:
                    Path(pdf.path).unlink(missing_ok=True)
                    continue
                seen.add(pdf.control)
                manifest.write(json.dumps(asdict(pdf), ensure_ascii=False) + "\n")
                manifest.flush()
                n_scanned += pdf.scanned
                n_digital += not pdf.scanned
                print(f"{'scan' if pdf.scanned else 'text'} {pdf.pages:>3}p {pdf.control}  [{n_scanned}/{args.scanned} scanned, {n_digital}/{args.digital} text]")
                if n_scanned >= args.scanned and n_digital >= args.digital:
                    break


if __name__ == "__main__":
    main()
