"""Deterministic tools the Extractor calls. They also shape the Trajectories smithtune trains on."""

from __future__ import annotations

import itertools
import re
from datetime import date, datetime
from typing import Literal

from langchain.tools import tool

from ..schema import CATEGORIAS, CnhRecord
from ..validators import format_cpf, is_valid_cnh_registro, is_valid_cpf, only_digits

# Characters an OCR model commonly reads in place of a digit.
DIGIT_LOOKALIKES = {"O": "0", "Q": "0", "D": "0", "I": "1", "L": "1", "|": "1", "Z": "2", "S": "5",
                    "G": "6", "T": "7", "B": "8", "g": "9"}
DIGIT_SWAPS = {"0": "8", "8": "0", "1": "7", "7": "1", "5": "6", "6": "5", "3": "8", "9": "8"}


@tool
def validate_cpf(cpf: str) -> dict:
    """Check a CPF's two check digits. Accepts any formatting."""
    digits = only_digits(cpf)
    return {"valid": is_valid_cpf(digits), "digits_found": len(digits),
            "formatted": format_cpf(digits) if len(digits) == 11 else None}


@tool
def validate_cnh_number(numero_registro: str) -> dict:
    """Check the 11-digit CNH número de registro check digits."""
    digits = only_digits(numero_registro)
    return {"valid": is_valid_cnh_registro(digits), "digits_found": len(digits), "digits": digits}


def _candidates(raw: str) -> list[str]:
    mapped = "".join(DIGIT_LOOKALIKES.get(c, DIGIT_LOOKALIKES.get(c.upper(), c)) for c in raw)
    digits = only_digits(mapped)
    yield digits
    for i in range(len(digits)):  # single-digit misreads
        if digits[i] in DIGIT_SWAPS:
            yield digits[:i] + DIGIT_SWAPS[digits[i]] + digits[i + 1:]
        for d in "0123456789":
            yield digits[:i] + d + digits[i + 1:]


@tool
def suggest_ocr_fixes(value: str, kind: Literal["cpf", "numero_registro"]) -> dict:
    """Propose corrections for a CPF or CNH number whose checksum fails.

    Maps letter/digit look-alikes (O->0, S->5, B->8...) and tries single-digit
    misreads. Returns only candidates whose check digits are valid, most likely first.
    """
    check = is_valid_cpf if kind == "cpf" else is_valid_cnh_registro
    seen: dict[str, None] = {}
    for cand in itertools.islice(_candidates(value), 500):
        if len(cand) == 11 and check(cand):
            seen.setdefault(format_cpf(cand) if kind == "cpf" else cand)
    found = list(seen)[:5]
    return {"candidates": found, "ambiguous": len(found) > 1}


_DATE = re.compile(r"(\d{1,2})\D{1,2}(\d{1,2})\D{1,2}(\d{2,4})")


@tool
def normalize_date(text: str) -> dict:
    """Turn a transcribed date (any separators, look-alike letters) into DD/MM/AAAA."""
    cleaned = "".join(DIGIT_LOOKALIKES.get(c, c) for c in text)
    m = _DATE.search(cleaned)
    if not m:
        return {"ok": False, "reason": "no date pattern found"}
    d, mth, y = m.groups()
    if len(y) == 2:
        y = ("20" if int(y) <= 30 else "19") + y
    try:
        parsed = date(int(y), int(mth), int(d))
    except ValueError as e:
        return {"ok": False, "reason": str(e)}
    return {"ok": True, "date": parsed.strftime("%d/%m/%Y")}


def _d(s: str) -> date:
    return datetime.strptime(s, "%d/%m/%Y").date()


@tool
def check_dates(data_nascimento: str, primeira_habilitacao: str, data_emissao: str, validade: str) -> dict:
    """Sanity-check CNH dates (all DD/MM/AAAA): order, minimum age and validity period (Lei 14.071/2020)."""
    try:
        born, first, issued, expires = map(_d, (data_nascimento, primeira_habilitacao, data_emissao, validade))
    except ValueError as e:
        return {"ok": False, "problems": [f"unparseable date: {e}"]}
    problems = []
    if (first - born).days < 18 * 365:
        problems.append("primeira_habilitacao is before the holder turned 18")
    if issued < first:
        problems.append("data_emissao is before primeira_habilitacao")
    age = (issued - born).days // 365
    expected = 10 if age < 50 else 5 if age < 70 else 3
    years = expires.year - issued.year
    if years not in (expected, expected - 1, expected + 1):  # tolerate older rules / renewal quirks
        problems.append(f"validade is {years}y after emissão; expected ~{expected}y for age {age}")
    return {"ok": not problems, "problems": problems}


@tool
def normalize_categoria(text: str) -> dict:
    """Map a transcribed CAT. HAB. (e.g. 'A8', 'A B', 'ab') to a valid category."""
    cleaned = text.upper().replace(" ", "").replace("8", "B").replace("0", "D").replace("3", "B")
    return {"ok": cleaned in CATEGORIAS, "categoria": cleaned if cleaned in CATEGORIAS else None,
            "allowed": list(CATEGORIAS)}


@tool(args_schema=CnhRecord)
def submit_cnh_record(**record) -> str:
    """Submit the final CNH Record. Call exactly once, after validating CPF, CNH number and dates."""
    rec = CnhRecord(**record)
    warnings = []
    if not is_valid_cpf(rec.cpf):
        warnings.append("cpf check digits invalid")
    if not is_valid_cnh_registro(rec.numero_registro):
        warnings.append("numero_registro check digits invalid")
    return "ACCEPTED" + (f" with warnings: {'; '.join(warnings)}" if warnings else "")


@tool
def reject_document(motivo: str) -> str:
    """Reject the input because it is not a CNH (e.g. RG, invoice, unrelated text)."""
    return "REJECTED"


TOOLS = [validate_cpf, validate_cnh_number, suggest_ocr_fixes, normalize_date, check_dates,
         normalize_categoria, submit_cnh_record, reject_document]
