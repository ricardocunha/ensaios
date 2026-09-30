"""Synthetic contracts with planted violations: ground truth for every (contract, rule).

Parties are fictitious (Faker pt_BR) and every page is marked DOCUMENTO SINTÉTICO. The
clauses follow the usual structure of Brazilian administrative contracts. Each contract gets
0-2 planted violations, plus "hard compliant" variants that look suspicious but are legal
(8% guarantee with the justification art. 98 requires, a 60-month term, "Comarca de <seat>").
"""

from __future__ import annotations

import argparse
import json
import random
from dataclasses import dataclass, field
from pathlib import Path

from faker import Faker
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

from compliance_agents.rules import RULES

ORDINALS = [
    "PRIMEIRA", "SEGUNDA", "TERCEIRA", "QUARTA", "QUINTA", "SEXTA", "SÉTIMA", "OITAVA", "NONA", "DÉCIMA",
    "DÉCIMA PRIMEIRA", "DÉCIMA SEGUNDA", "DÉCIMA TERCEIRA", "DÉCIMA QUARTA", "DÉCIMA QUINTA", "DÉCIMA SEXTA",
]
SEATS = [
    ("Chapecó", "SC"), ("Itajaí", "SC"), ("Londrina", "PR"), ("Caxias do Sul", "RS"), ("Juiz de Fora", "MG"),
    ("Campina Grande", "PB"), ("Feira de Santana", "BA"), ("Ribeirão Preto", "SP"), ("Anápolis", "GO"), ("Santarém", "PA"),
]
SERVICES = [
    ("prestação de serviços contínuos de limpeza e conservação predial", True),
    ("prestação de serviços contínuos de manutenção preventiva e corretiva de veículos da frota municipal", True),
    ("prestação de serviços contínuos de vigilância patrimonial desarmada", True),
    ("fornecimento contínuo de gêneros alimentícios para a merenda escolar", True),
    ("aquisição de equipamentos de informática, em entrega única", False),
    ("execução de obra de reforma da unidade básica de saúde", False),
]
INDICES = ["IPCA/IBGE", "INPC/IBGE", "IGP-M/FGV"]

# planted violation -> (rule it breaks, verdict)
VIOLATIONS = {
    "missing_vinculacao": ("vinculacao", "violation"),
    "missing_pagamento": ("preco_pagamento", "violation"),
    "missing_reajuste": ("reajuste", "violation"),
    "reajuste_sem_indice": ("reajuste", "violation"),
    "missing_dotacao": ("dotacao", "violation"),
    "missing_foro": ("foro", "violation"),
    "foro_outra_cidade": ("foro", "violation"),
    "garantia_8_sem_justificativa": ("garantia_limite", "violation"),
    "garantia_12": ("garantia_limite", "violation"),
    "vigencia_72_meses": ("vigencia_limite", "violation"),
    "prorrogacao_12_anos": ("vigencia_limite", "violation"),
}
# legal variants that look suspicious -> the rule they test
HARD_COMPLIANT = {"garantia_8_justificada": "garantia_limite", "vigencia_60_meses": "vigencia_limite", "foro_comarca": "foro"}


@dataclass
class Spec:
    doc_id: str
    seat: tuple[str, str]
    service: str
    continuous: bool
    value: float
    months: int
    guarantee: float | None  # percent; None = no guarantee required
    index: str
    planted: list[str] = field(default_factory=list)
    hard: list[str] = field(default_factory=list)

    def labels(self) -> dict[str, str]:
        labels = {r.id: "compliant" for r in RULES}
        if self.guarantee is None:
            labels["garantia_limite"] = "not_applicable"
        if not self.continuous:
            labels["vigencia_limite"] = "not_applicable"
        for v in self.planted:
            rule, verdict = VIOLATIONS[v]
            labels[rule] = verdict
        return labels


WORDS = {4: "quatro", 6: "seis", 8: "oito", 10: "dez", 12: "doze", 15: "quinze", 24: "vinte e quatro",
         30: "trinta", 60: "sessenta", 72: "setenta e dois"}


PERCENT = {2.0: "dois", 3.0: "três", 5.0: "cinco", 8.0: "oito", 12.0: "doze"}


def brl(v: float) -> str:
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def make_spec(i: int, rng: random.Random) -> Spec:
    service, continuous = rng.choice(SERVICES)
    spec = Spec(
        doc_id=f"synth-{i:03d}",
        seat=rng.choice(SEATS),
        service=service,
        continuous=continuous,
        value=round(rng.uniform(30_000, 2_500_000), 2),
        months=rng.choice([12, 12, 24, 30]) if continuous else rng.choice([4, 6, 8]),
        guarantee=rng.choice([None, 2.0, 3.0, 5.0]),
        index=rng.choice(INDICES),
    )
    n = rng.choices([0, 1, 2], weights=[4, 4, 2])[0]
    options = [v for v in VIOLATIONS if continuous or not v.startswith(("vigencia", "prorrogacao"))]
    while len(spec.planted) < n:
        v = rng.choice(options)
        if VIOLATIONS[v][0] not in {VIOLATIONS[p][0] for p in spec.planted}:
            spec.planted.append(v)
    broken = {VIOLATIONS[p][0] for p in spec.planted}
    for h, rule in HARD_COMPLIANT.items():
        if rule in broken or (h == "vigencia_60_meses" and not continuous) or rng.random() > 0.2:
            continue
        spec.hard.append(h)
    if "garantia_8_justificada" in spec.hard or "garantia_8_sem_justificativa" in spec.planted:
        spec.guarantee = 8.0
    if "garantia_12" in spec.planted:
        spec.guarantee = 12.0
    if "vigencia_60_meses" in spec.hard:
        spec.months = 60
    if "vigencia_72_meses" in spec.planted:
        spec.months = 72
    return spec


def clauses(spec: Spec, fake: Faker, rng: random.Random) -> list[tuple[str, list[str]]]:
    city, uf = spec.seat
    p = set(spec.planted) | set(spec.hard)
    out: list[tuple[str, list[str]]] = []

    objeto = [f"O objeto do presente contrato é a {spec.service}, conforme especificações do Termo de Referência."]
    if "missing_vinculacao" not in p:
        objeto.append("Este contrato vincula-se ao Edital do Pregão Eletrônico nº "
                      f"{rng.randint(10, 199)}/2026 e à proposta vencedora, independentemente de transcrição.")
    out.append(("DO OBJETO", objeto))

    vig = [f"O prazo de vigência deste contrato é de {spec.months} ({WORDS[spec.months]}) meses, contados da data de sua assinatura."]
    if spec.continuous:
        max_years = 12 if "prorrogacao_12_anos" in p else 10
        vig.append(f"O prazo poderá ser prorrogado sucessivamente, respeitada a vigência máxima de {max_years} ({WORDS[max_years]}) anos, "
                   "desde que a autoridade competente ateste que as condições e os preços permanecem vantajosos.")
    out.append(("DA VIGÊNCIA", vig))

    preco = [f"O valor global deste contrato é de {brl(spec.value)}."]
    if "missing_pagamento" not in p:
        days = rng.choice([10, 15, 30])
        preco.append(f"O pagamento será efetuado em até {days} ({WORDS[days]}) dias após o atesto da nota fiscal pelo fiscal do contrato, "
                     "mediante crédito em conta corrente da CONTRATADA.")
    out.append(("DO PREÇO E DO PAGAMENTO", preco))

    if "missing_reajuste" not in p:
        if "reajuste_sem_indice" in p:
            out.append(("DO REAJUSTE", ["Os preços poderão ser reajustados na forma da legislação vigente, a critério da Administração."]))
        else:
            out.append(("DO REAJUSTE", [f"Os preços serão reajustados após o interregno mínimo de 1 (um) ano, pelo índice {spec.index}, "
                                        "tendo como data-base a data do orçamento estimado da licitação."]))

    if "missing_dotacao" not in p:
        out.append(("DA DOTAÇÃO ORÇAMENTÁRIA", [f"As despesas correrão à conta da dotação orçamentária {rng.randint(10, 99)}.{rng.randint(100, 999)}."
                                                f"{rng.randint(1000, 9999)}.3.3.90.39, Fonte de Recursos {rng.randint(1000, 1999)}."]))

    if spec.guarantee is not None:
        g = [f"A CONTRATADA prestará garantia de {spec.guarantee:g}% ({PERCENT[spec.guarantee]} por cento) do valor inicial do contrato, "
             "em uma das modalidades do art. 96 da Lei nº 14.133/2021."]
        if "garantia_8_justificada" in p:
            g.append("A majoração do percentual acima de 5% foi justificada no processo, mediante análise da complexidade técnica e dos riscos envolvidos, "
                     "nos termos do art. 98 da Lei nº 14.133/2021.")
        out.append(("DA GARANTIA", g))

    out.append(("DAS OBRIGAÇÕES DA CONTRATADA", [
        "Executar o objeto com zelo e eficiência, observadas as especificações do Termo de Referência.",
        "Manter, durante toda a execução do contrato, todas as condições de habilitação exigidas na licitação.",
    ]))
    out.append(("DAS SANÇÕES", [f"O atraso injustificado sujeitará a CONTRATADA a multa de mora de {rng.choice(['0,3', '0,5'])}% por dia sobre o valor da parcela em atraso, "
                                "sem prejuízo das demais sanções do art. 156 da Lei nº 14.133/2021."]))
    out.append(("DA EXTINÇÃO", ["O contrato poderá ser extinto nas hipóteses do art. 137 da Lei nº 14.133/2021."]))

    if "missing_foro" not in p:
        if "foro_outra_cidade" in p:
            other = rng.choice([s for s in SEATS if s != spec.seat])
            forum = f"Fica eleito o foro da cidade de {other[0]}/{other[1]} para dirimir as questões oriundas deste contrato."
        elif "foro_comarca" in p:
            forum = f"As partes elegem a Comarca de {city} para dirimir quaisquer questões decorrentes deste contrato."
        else:
            forum = f"Fica eleito o foro da cidade de {city}/{uf}, sede da CONTRATANTE, para dirimir as questões oriundas deste contrato."
        out.append(("DO FORO", [forum]))
    return out


def render(spec: Spec, out_dir: Path, seed: int) -> Path:
    rng = random.Random(f"{seed}-{spec.doc_id}")
    fake = Faker("pt_BR")
    fake.seed_instance(f"{seed}-{spec.doc_id}")
    city, uf = spec.seat
    company = fake.company()
    if not company.endswith(("Ltda.", "S.A.", "S/A", "EIRELI", "ME")):
        company += " Ltda."
    base = ParagraphStyle("b", fontName="Times-Roman", fontSize=11, leading=15, alignment=TA_JUSTIFY, spaceAfter=6)
    head = ParagraphStyle("h", parent=base, fontName="Times-Bold", spaceBefore=8)
    title = ParagraphStyle("t", parent=head, alignment=TA_CENTER, fontSize=12)

    story = [
        Paragraph(f"MUNICÍPIO DE {city.upper()} – {uf}", title),
        Paragraph(f"CONTRATO ADMINISTRATIVO Nº {rng.randint(1, 400)}/2026", title),
        Spacer(1, 6),
        Paragraph(
            f"O MUNICÍPIO DE {city.upper()}, pessoa jurídica de direito público, com sede na cidade de {city}/{uf}, "
            f"doravante denominado CONTRATANTE, e a empresa {company}, inscrita no CNPJ sob o nº {fake.cnpj()}, "
            "doravante denominada CONTRATADA, celebram o presente contrato, regido pela Lei nº 14.133/2021, "
            "mediante as cláusulas e condições seguintes.", base),
    ]
    for n, (name, items) in enumerate(clauses(spec, fake, rng), start=1):
        story.append(Paragraph(f"CLÁUSULA {ORDINALS[n - 1]} – {name}", head))
        for k, text in enumerate(items, start=1):
            story.append(Paragraph(f"{n}.{k} {text}", base))
    story += [
        Spacer(1, 12),
        Paragraph(f"{city}/{uf}, {rng.randint(1, 28)} de {rng.choice(['março', 'maio', 'julho', 'agosto'])} de 2026.", base),
        Paragraph(f"{fake.name()} – Prefeito(a) Municipal &nbsp;&nbsp;&nbsp; {fake.name()} – Representante da CONTRATADA", base),
    ]

    def page_marks(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica-Bold", 8)
        canvas.drawString(2 * cm, A4[1] - 1.2 * cm, "DOCUMENTO SINTÉTICO – SEM VALIDADE – ensaios")
        canvas.setFont("Helvetica", 8)
        canvas.drawRightString(A4[0] - 2 * cm, 1.2 * cm, str(doc.page))
        canvas.restoreState()

    path = out_dir / f"{spec.doc_id}.pdf"
    SimpleDocTemplate(str(path), pagesize=A4, leftMargin=2.5 * cm, rightMargin=2.5 * cm,
                      topMargin=2 * cm, bottomMargin=2 * cm).build(story, onFirstPage=page_marks, onLaterPages=page_marks)
    return path


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--n", type=int, default=60)
    ap.add_argument("--out", type=Path, default=Path("data/synth/text"))
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    rng = random.Random(args.seed)
    with (args.out / "labels.jsonl").open("w") as f:
        for i in range(args.n):
            spec = make_spec(i, rng)
            render(spec, args.out, args.seed)
            f.write(json.dumps({"doc": spec.doc_id, "planted": spec.planted, "hard": spec.hard, "labels": spec.labels()}, ensure_ascii=False) + "\n")
    print(f"{args.n} contracts in {args.out}")


if __name__ == "__main__":
    main()
