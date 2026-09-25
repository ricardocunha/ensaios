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
    """Field names follow the labels printed on the CNH."""

    nome: str
    doc_identidade: str = Field(description="Número do RG, sem órgão emissor")
    orgao_emissor: str
    uf_emissor: str
    cpf: str = Field(pattern=r"^\d{3}\.\d{3}\.\d{3}-\d{2}$")
    data_nascimento: str = Field(pattern=DATE_PATTERN)
    filiacao: list[str] = Field(description="Nomes dos pais, na ordem impressa")
    permissao: str | None = None
    acc: str | None = None
    categoria: str
    numero_registro: str = Field(pattern=r"^\d{11}$")
    validade: str = Field(pattern=DATE_PATTERN)
    primeira_habilitacao: str = Field(pattern=DATE_PATTERN)
    observacoes: str | None = None
    local: str = Field(description="Cidade, UF de emissão")
    data_emissao: str = Field(pattern=DATE_PATTERN)
    formato: Literal["fisica", "digital"]


class Rejection(BaseModel):
    """The Extractor's outcome for a Non-CNH."""

    motivo: str


FIELD_NAMES: tuple[str, ...] = tuple(CnhRecord.model_fields)
