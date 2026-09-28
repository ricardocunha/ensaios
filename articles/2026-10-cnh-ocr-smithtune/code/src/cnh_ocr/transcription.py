"""The Transcription: the contract between the Reader and the Extractor (ADR-0001).

One `LABEL: value` line per printed field, exactly as it appears on the card.
The Reader never validates or normalizes, and OCR errors stay in.
"""

from __future__ import annotations

import difflib
import re
import unicodedata

from .schema import CnhRecord

# Label printed on the card -> how the record's value is laid out on that line.
LABELS: tuple[str, ...] = (
    "NOME",
    "DOC. IDENTIDADE / ÓRG. EMISSOR / UF",
    "CPF",
    "DATA NASCIMENTO",
    "FILIAÇÃO",
    "PERMISSÃO",
    "ACC",
    "CAT. HAB.",
    "Nº REGISTRO",
    "VALIDADE",
    "1ª HABILITAÇÃO",
    "OBSERVAÇÕES",
    "LOCAL",
    "DATA EMISSÃO",
)

READER_PROMPT = (
    "Transcreva esta CNH. Para cada campo impresso, escreva uma linha no formato "
    "`RÓTULO: valor`, exatamente como aparece no documento, sem corrigir nada. "
    "Se a imagem não for uma CNH, responda apenas `NÃO É CNH`."
)

NOT_A_CNH = "NÃO É CNH"

# Round 3 (ADR-0003): the Reader always transcribes; deciding "is this a CNH?" is the
# Extractor's job (see CONTEXT.md: Rejection). No refusal instruction in the prompt.
READER_PROMPT_V3 = (
    "Transcreva este documento. Para cada campo impresso, escreva uma linha no formato "
    "`RÓTULO: valor`, exatamente como aparece, sem corrigir nada. Texto sem rótulo vai "
    "em linhas próprias, na ordem de leitura."
)
PROMPTS = {"v1": READER_PROMPT, "v3": READER_PROMPT_V3}


# Which CNH Record fields each printed line carries (a dropped line empties all of them).
LABEL_FIELDS: dict[str, tuple[str, ...]] = {
    "NOME": ("nome",),
    "DOC. IDENTIDADE / ÓRG. EMISSOR / UF": ("doc_identidade", "orgao_emissor", "uf_emissor"),
    "CPF": ("cpf",),
    "DATA NASCIMENTO": ("data_nascimento",),
    "FILIAÇÃO": ("filiacao",),
    "PERMISSÃO": ("permissao",),
    "ACC": ("acc",),
    "CAT. HAB.": ("categoria",),
    "Nº REGISTRO": ("numero_registro",),
    "VALIDADE": ("validade",),
    "1ª HABILITAÇÃO": ("primeira_habilitacao",),
    "OBSERVAÇÕES": ("observacoes",),
    "LOCAL": ("local",),
    "DATA EMISSÃO": ("data_emissao",),
}


def printed_values(record: CnhRecord) -> dict[str, str]:
    """What is physically printed next to each label for a given record."""
    return {
        "NOME": record.nome,
        "DOC. IDENTIDADE / ÓRG. EMISSOR / UF": (
            f"{record.doc_identidade} {record.orgao_emissor} {record.uf_emissor}"
        ),
        "CPF": record.cpf,
        "DATA NASCIMENTO": record.data_nascimento,
        "FILIAÇÃO": " / ".join(record.filiacao),
        "PERMISSÃO": record.permissao or "",
        "ACC": record.acc or "",
        "CAT. HAB.": record.categoria,
        "Nº REGISTRO": record.numero_registro,
        "VALIDADE": record.validade,
        "1ª HABILITAÇÃO": record.primeira_habilitacao,
        "OBSERVAÇÕES": record.observacoes or "",
        "LOCAL": record.local,
        "DATA EMISSÃO": record.data_emissao,
    }


def render(values: dict[str, str]) -> str:
    return "\n".join(f"{label}: {values.get(label, '')}".rstrip() for label in LABELS)


def from_record(record: CnhRecord) -> str:
    """The ground-truth Transcription for a Synthetic CNH."""
    return render(printed_values(record))


def label_key(text: str) -> str:
    """Accent-, case-, space- and punctuation-insensitive form of a printed label."""
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Z0-9]", "", text.upper())


# Printed variants seen on real cards / produced by Readers -> canonical label.
_ALIASES = {
    "NREGISTRO": "Nº REGISTRO", "NOREGISTRO": "Nº REGISTRO", "NDEREGISTRO": "Nº REGISTRO",
    "1OHABILITACAO": "1ª HABILITAÇÃO", "1AHAB": "1ª HABILITAÇÃO", "PRIMEIRAHABILITACAO": "1ª HABILITAÇÃO",
    "DATADENASCIMENTO": "DATA NASCIMENTO", "DATADEEMISSAO": "DATA EMISSÃO",
    "CATEGORIA": "CAT. HAB.", "CATHABILITACAO": "CAT. HAB.",
    "DOCIDENTIDADEORGEMISSORUF": "DOC. IDENTIDADE / ÓRG. EMISSOR / UF",
}
_KEYS = {label_key(label): label for label in LABELS} | _ALIASES


def canonical_label(text: str) -> str | None:
    """Map a printed/transcribed label to its canonical form, tolerating OCR slips ('CAT.HA8')."""
    key = label_key(text)
    if key in _KEYS:
        return _KEYS[key]
    if len(key) >= 5:
        close = difflib.get_close_matches(key, [k for k in _KEYS if len(k) >= 5], n=1, cutoff=0.8)
        if close:
            return _KEYS[close[0]]
    return None


def parse(transcription: str) -> dict[str, str]:
    """Split a Transcription back into canonical label -> raw value (values are not cleaned)."""
    values: dict[str, str] = {}
    for line in transcription.splitlines():
        label, sep, value = line.partition(":")
        canonical = canonical_label(label) if sep else None
        if canonical:
            values[canonical] = value.strip()
    return values
