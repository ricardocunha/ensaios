"""Is this Transcription a CNH? A text-side gate (ADR-0003).

Round 1 and 2 put this decision in the vision model, which learned "CNH = my
renderer's look" and rejected real CNHs. Here the Reader always transcribes,
and the decision is made from the text. In the full pipeline the Extractor
decides (`reject_document`); this deterministic rule is the Stage 1 stand-in
and a cheap pre-filter.

A CNH prints labels no RG, CPF card or invoice has. Generic labels (NOME,
FILIAÇÃO, DATA NASCIMENTO) are shared with other IDs and don't count.
"""

from __future__ import annotations

from .transcription import NOT_A_CNH, parse

CNH_ONLY_LABELS = frozenset({"CAT. HAB.", "Nº REGISTRO", "1ª HABILITAÇÃO", "VALIDADE", "PERMISSÃO", "ACC"})
MIN_CNH_ONLY_LABELS = 2


def is_cnh(transcription: str) -> bool:
    if NOT_A_CNH in transcription.upper():
        return False
    return len(CNH_ONLY_LABELS & parse(transcription).keys()) >= MIN_CNH_ONLY_LABELS
