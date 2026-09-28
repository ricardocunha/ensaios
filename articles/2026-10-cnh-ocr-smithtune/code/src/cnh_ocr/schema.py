"""The CNH Record: the Extractor's final, validated output (see CONTEXT.md)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

UFS = (
    "AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO"
).split()

CATEGORIAS = ("A", "B", "C", "D", "E", "AB", "AC", "AD", "AE")

DATE_PATTERN = r"^\d{2}/\d{2}/\d{4}$"


class CnhRecord(BaseModel):
    """Field names follow the labels printed on the CNH.

    A field is null when its line is absent or illegible in the Transcription;
    an incomplete CNH is still a CNH (Rejection is only for Non-CNH documents).
    """

    nome: str | None = None
    doc_identidade: str | None = Field(None, description="Número do RG, sem órgão emissor")
    orgao_emissor: str | None = None
    uf_emissor: str | None = None
    cpf: str | None = Field(None, pattern=r"^\d{3}\.\d{3}\.\d{3}-\d{2}$")
    data_nascimento: str | None = Field(None, pattern=DATE_PATTERN)
    filiacao: list[str] | None = Field(None, description="Nomes dos pais, na ordem impressa")
    permissao: str | None = None
    acc: str | None = None
    categoria: str | None = None
    numero_registro: str | None = Field(None, pattern=r"^\d{11}$")
    validade: str | None = Field(None, pattern=DATE_PATTERN)
    primeira_habilitacao: str | None = Field(None, pattern=DATE_PATTERN)
    observacoes: str | None = None
    local: str | None = Field(None, description="Cidade, UF de emissão")
    data_emissao: str | None = Field(None, pattern=DATE_PATTERN)
    # Physical card vs CNH Digital is known from how the image was captured, not from the
    # text, so the Extractor doesn't fill it and it isn't scored.
    formato: Literal["fisica", "digital"] | None = Field(None, exclude=True)


class Rejection(BaseModel):
    """The Extractor's outcome for a Non-CNH."""

    motivo: str


FIELD_NAMES: tuple[str, ...] = tuple(f for f in CnhRecord.model_fields if f != "formato")  # what the Extractor is scored on
