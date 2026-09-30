"""Limit rules decided in code: the model extracts the values, these functions apply the law.

Same split as the CNH article's ADR 0003 ("the model reads, rules decide"): an 8B model
quotes "12 meses" correctly and then says it exceeds "5 anos".
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class GuaranteeFacts(BaseModel):
    guarantee_required: bool = Field(description="Does the contract require the contractor to provide a guarantee (garantia contratual)?")
    percent: float | None = Field(description="The guarantee as a percentage of the contract value, e.g. 5 for 5%; null if none")
    justification_quote: str = Field(
        description="Verbatim quote justifying a guarantee above 5% (technical complexity and risks); empty if there is none"
    )
    section_id: int | None
    evidence: str = Field(description="Verbatim quote of the guarantee clause; empty if there is none")
    confidence: float = Field(ge=0, le=1)


class TermFacts(BaseModel):
    continuous: bool = Field(description="Is the object a continuous service or continuous supply (serviço/fornecimento contínuo)?")
    initial_months: int | None = Field(description="Initial term (vigência) in months; convert years to months")
    max_total_months: int | None = Field(description="Maximum total term including extensions (prorrogações), in months; null if not stated")
    section_id: int | None
    evidence: str = Field(description="Verbatim quote of the term clause")
    confidence: float = Field(ge=0, le=1)


def decide_guarantee(f: GuaranteeFacts) -> tuple[str, str]:
    """Art. 98: up to 5% of the initial value; up to 10% if justified by technical complexity and risks."""
    if not f.guarantee_required or f.percent is None:
        return "not_applicable", "O contrato não exige garantia."
    if f.percent <= 5:
        return "compliant", f"Garantia de {f.percent:g}%, dentro do limite de 5%."
    if f.percent <= 10 and f.justification_quote.strip():
        return "compliant", f"Garantia de {f.percent:g}%, acima de 5% mas justificada (limite de 10%)."
    if f.percent <= 10:
        return "violation", f"Garantia de {f.percent:g}% acima de 5% sem justificativa de complexidade técnica e riscos."
    return "violation", f"Garantia de {f.percent:g}% acima do limite máximo de 10%."


def decide_term(f: TermFacts) -> tuple[str, str]:
    """Art. 106: continuous services/supplies up to 5 years; art. 107: up to 10 years with extensions."""
    if not f.continuous:
        return "not_applicable", "O objeto não é serviço ou fornecimento contínuo."
    if f.initial_months is None:
        return "unclear", "Vigência inicial não identificada."
    if f.initial_months > 60:
        return "violation", f"Vigência inicial de {f.initial_months} meses excede 5 anos (60 meses)."
    if f.max_total_months is not None and f.max_total_months > 120:
        return "violation", f"Vigência máxima com prorrogações de {f.max_total_months} meses excede 10 anos (120 meses)."
    return "compliant", f"Vigência inicial de {f.initial_months} meses dentro de 5 anos; máximo dentro de 10 anos."


EXTRACTORS = {
    "garantia_limite": (GuaranteeFacts, decide_guarantee),
    "vigencia_limite": (TermFacts, decide_term),
}
