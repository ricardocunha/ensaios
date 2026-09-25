"""The Transcription: the contract between the Reader and the Extractor (ADR-0001).

One `LABEL: value` line per printed field, exactly as it appears on the card.
The Reader never validates or normalizes, and OCR errors stay in.
"""

from __future__ import annotations

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


def parse(transcription: str) -> dict[str, str]:
    """Split a Transcription back into label -> raw value (no cleaning)."""
    values: dict[str, str] = {}
    for line in transcription.splitlines():
        label, sep, value = line.partition(":")
        if sep and label.strip() in LABELS:
            values[label.strip()] = value.strip()
    return values
