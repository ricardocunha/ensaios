"""Is this Transcription a CNH? A text-side gate (ADR-0003).

A deterministic Stage 1 stand-in for the Extractor's `reject_document`: a CNH prints
labels no RG, CPF card or invoice has. Labels shared with other IDs don't count.
"""

from __future__ import annotations

from .transcription import NOT_A_CNH, parse

CNH_ONLY_LABELS = frozenset({"CAT. HAB.", "Nº REGISTRO", "1ª HABILITAÇÃO", "VALIDADE", "PERMISSÃO", "ACC"})
MIN_CNH_ONLY_LABELS = 2


def is_cnh(transcription: str) -> bool:
    if NOT_A_CNH in transcription.upper():
        return False
    return len(CNH_ONLY_LABELS & parse(transcription).keys()) >= MIN_CNH_ONLY_LABELS
