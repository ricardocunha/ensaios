"""Random but internally consistent CNH Records (fake people, valid checksums)."""

from __future__ import annotations

import random
from datetime import date, timedelta

from faker import Faker

from ..schema import CATEGORIAS, UFS, CnhRecord
from ..validators import random_cnh_registro, random_cpf

_CATEGORIA_WEIGHTS = (6, 30, 3, 3, 3, 45, 3, 4, 3)
_ORGAOS = ("SSP", "SSP", "SSP", "DETRAN", "PC", "SESP", "SDS", "IFP")
_OBSERVACOES = ("", "", "", "", "A", "EAR", "A EAR", "D", "EXERCE ATIVIDADE REMUNERADA")


def _fmt(d: date) -> str:
    return d.strftime("%d/%m/%Y")


def _validity_years(age: int) -> int:
    # Lei 14.071/2020: 10 years under 50, 5 years 50-69, 3 years 70+.
    return 10 if age < 50 else 5 if age < 70 else 3


def random_record(rng: random.Random, fake: Faker, today: date) -> CnhRecord:
    birth = today - timedelta(days=rng.randint(18 * 365 + 60, 80 * 365))
    first_license = birth + timedelta(days=rng.randint(18 * 365 + 5, 18 * 365 + 12 * 365))
    first_license = min(first_license, today - timedelta(days=30))
    issued = today - timedelta(days=rng.randint(0, 9 * 365))
    issued = max(issued, first_license)
    age_at_issue = (issued - birth).days // 365
    if (issued.month, issued.day) == (2, 29):
        issued += timedelta(days=1)  # keep 'same day N years later' well-defined
    expires = issued.replace(year=issued.year + _validity_years(age_at_issue))

    uf = rng.choice(UFS)
    city = fake.city()
    upper = str.upper
    return CnhRecord(
        nome=upper(f"{fake.first_name()} {fake.last_name()} {fake.last_name()}"),
        doc_identidade=str(rng.randint(1_000_000, 99_999_999)),
        orgao_emissor=rng.choice(_ORGAOS),
        uf_emissor=uf,
        cpf=random_cpf(rng),
        data_nascimento=_fmt(birth),
        filiacao=[
            upper(f"{fake.first_name_male()} {fake.last_name()} {fake.last_name()}"),
            upper(f"{fake.first_name_female()} {fake.last_name()} {fake.last_name()}"),
        ],
        permissao=None,
        acc=None,
        categoria=rng.choices(CATEGORIAS, weights=_CATEGORIA_WEIGHTS)[0],
        numero_registro=random_cnh_registro(rng),
        validade=_fmt(expires),
        primeira_habilitacao=_fmt(first_license),
        observacoes=rng.choice(_OBSERVACOES) or None,
        local=upper(f"{city}, {uf}"),
        data_emissao=_fmt(issued),
        formato=rng.choice(("fisica", "fisica", "digital")),
    )
