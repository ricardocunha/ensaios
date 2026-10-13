"""Inject realistic OCR errors into a ground-truth Transcription.

A well-tuned Reader makes few mistakes; noise guarantees the Extractor sees
(and learns to fix) the error types that matter.
"""

from __future__ import annotations

import random

from .. import transcription as tx

_TO_LETTER = {"0": "O", "1": "I", "5": "S", "8": "B", "2": "Z", "6": "G"}
_ACCENTS = str.maketrans("ÁÀÂÃÉÊÍÓÔÕÚÇ", "AAAAEEIOOOUC")
_LABEL_TYPOS = {"Nº REGISTRO": "N° REGISTRO", "CAT. HAB.": "CAT HAB", "1ª HABILITAÇÃO": "1a HABILITACAO",
                "DATA NASCIMENTO": "DATA NASC1MENTO", "FILIAÇÃO": "FILIACAO"}


def _swap_digit(value: str, rng: random.Random) -> str:
    idx = [i for i, c in enumerate(value) if c in _TO_LETTER]
    if not idx:
        return value
    i = rng.choice(idx)
    return value[:i] + _TO_LETTER[value[i]] + value[i + 1:]


def _mangle(label: str, value: str, rng: random.Random) -> str:
    if not value:
        return value
    if label in ("CPF", "Nº REGISTRO"):
        op = rng.choice(("letter", "letter", "digit", "format"))
        if op == "letter":
            return _swap_digit(value, rng)
        if op == "digit":
            i = rng.choice([i for i, c in enumerate(value) if c.isdigit()])
            return value[:i] + rng.choice("0123456789") + value[i + 1:]
        return value.replace(".", rng.choice(("", " ", ","))).replace("-", rng.choice(("", " ", ".")))
    if label in ("DATA NASCIMENTO", "VALIDADE", "1ª HABILITAÇÃO", "DATA EMISSÃO"):
        return rng.choice((value.replace("/", rng.choice((".", "-", " ", "/ "))), _swap_digit(value, rng)))
    if label == "CAT. HAB.":
        return {"AB": "A8", "B": "8", "D": "0"}.get(value, value.lower())
    return rng.choice((value.translate(_ACCENTS), _swap_digit(value.replace("O", "0", 1), rng)))


def add_noise(clean: str, rng: random.Random, rate: float = 0.25, dropped: list[str] | None = None) -> str:
    """`dropped`, if given, receives the labels whose line was removed entirely."""
    values = tx.parse(clean)
    lines = []
    for label in tx.LABELS:
        value = values.get(label, "")
        if rng.random() < 0.03 and label not in ("CPF", "NOME"):
            if dropped is not None:
                dropped.append(label)
            continue  # Reader skipped the line
        shown = _LABEL_TYPOS.get(label, label) if rng.random() < 0.1 else label
        if rng.random() < rate:
            value = _mangle(label, value, rng)
        lines.append(f"{shown}: {value}".rstrip())
    if rng.random() < 0.15:
        lines.insert(0, rng.choice(("CARTEIRA NACIONAL DE HABILITAÇÃO", "AMOSTRA SINTETICA", "ASSINATURA DO PORTADOR")))
    return "\n".join(lines)
