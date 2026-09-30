"""The rules the reviewer checks: a small subset of Lei 14.133/2021 (the Brazilian procurement law).

Each rule quotes the article it comes from (text checked against planalto.gov.br, l14133.htm).
"Presence" rules ask whether the contract has a clause; "limit" rules ask whether a value
stated in the contract is within what the law allows. Not legal advice: a test bench.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class Rule:
    id: str
    article: str
    kind: Literal["presence", "limit"]
    check: str  # what the reviewer must decide, in Portuguese like the contracts
    law: str  # the article's text, abridged


RULES: tuple[Rule, ...] = (
    Rule(
        "objeto",
        "Art. 92, I",
        "presence",
        "O contrato tem cláusula que define o objeto e seus elementos característicos?",
        "São necessárias em todo contrato cláusulas que estabeleçam: I - o objeto e seus elementos característicos",
    ),
    Rule(
        "vinculacao",
        "Art. 92, II",
        "presence",
        "O contrato declara vinculação ao edital e à proposta vencedora (ou ao ato de contratação direta)?",
        "II - a vinculação ao edital de licitação e à proposta do licitante vencedor ou ao ato que tiver autorizado a contratação direta e à respectiva proposta",
    ),
    Rule(
        "preco_pagamento",
        "Art. 92, V",
        "presence",
        "O contrato estabelece o preço e as condições de pagamento?",
        "V - o preço e as condições de pagamento, os critérios, a data-base e a periodicidade do reajustamento de preços",
    ),
    Rule(
        "reajuste",
        "Art. 92, § 3º",
        "presence",
        "O contrato define o índice de reajustamento de preço, com data-base vinculada à data do orçamento estimado?",
        "§ 3º Independentemente do prazo de duração, o contrato deverá conter cláusula que estabeleça o índice de reajustamento de preço, com data-base vinculada à data do orçamento estimado",
    ),
    Rule(
        "dotacao",
        "Art. 92, VIII",
        "presence",
        "O contrato indica o crédito (dotação orçamentária) pelo qual correrá a despesa?",
        "VIII - o crédito pelo qual correrá a despesa, com a indicação da classificação funcional programática e da categoria econômica",
    ),
    Rule(
        "foro",
        "Art. 92, § 1º",
        "presence",
        "O contrato tem cláusula que declara competente o foro da sede da Administração contratante?",
        "§ 1º Os contratos [...] deverão conter cláusula que declare competente o foro da sede da Administração para dirimir qualquer questão contratual",
    ),
    Rule(
        "garantia_limite",
        "Art. 98",
        "limit",
        "Se o contrato exige garantia, o percentual está dentro de 5% do valor inicial (ou até 10% com justificativa de complexidade técnica e riscos)?",
        "a garantia poderá ser de até 5% (cinco por cento) do valor inicial do contrato, autorizada a majoração desse percentual para até 10% (dez por cento), desde que justificada",
    ),
    Rule(
        "vigencia_limite",
        "Arts. 106 e 107",
        "limit",
        "Para serviços e fornecimentos contínuos, a vigência inicial é de até 5 anos e a vigência máxima com prorrogações é de até 10 anos?",
        "Art. 106. A Administração poderá celebrar contratos com prazo de até 5 (cinco) anos nas hipóteses de serviços e fornecimentos contínuos [...] Art. 107. [...] poderão ser prorrogados sucessivamente, respeitada a vigência máxima decenal",
    ),
)

RULES_BY_ID = {r.id: r for r in RULES}
