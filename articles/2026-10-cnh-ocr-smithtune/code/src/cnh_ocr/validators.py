"""Check-digit algorithms for Brazilian identifiers printed on a CNH.

Used in two places: the synthetic generator (to *make* valid-looking numbers)
and the Extractor's tools (to *verify* what the Reader transcribed).
"""

from __future__ import annotations

import random
import re

_NON_DIGITS = re.compile(r"\D")


def only_digits(value: str) -> str:
    return _NON_DIGITS.sub("", value)


# --- CPF ---------------------------------------------------------------------

def _cpf_digit(digits: str) -> str:
    weight = len(digits) + 1
    total = sum(int(d) * (weight - i) for i, d in enumerate(digits))
    rest = total % 11
    return "0" if rest < 2 else str(11 - rest)


def cpf_check_digits(base9: str) -> str:
    first = _cpf_digit(base9)
    return first + _cpf_digit(base9 + first)


def is_valid_cpf(value: str) -> bool:
    digits = only_digits(value)
    if len(digits) != 11 or digits == digits[0] * 11:
        return False
    return digits[9:] == cpf_check_digits(digits[:9])


def format_cpf(value: str) -> str:
    d = only_digits(value)
    return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}"


def random_cpf(rng: random.Random) -> str:
    while True:
        base = "".join(str(rng.randint(0, 9)) for _ in range(9))
        if base != base[0] * 9:
            return format_cpf(base + cpf_check_digits(base))


# --- CNH número de registro (11 digits) --------------------------------------

def cnh_registro_check_digits(base9: str) -> str:
    total = sum(int(d) * w for d, w in zip(base9, range(9, 0, -1)))
    first = total % 11
    discount = 0
    if first >= 10:
        first, discount = 0, 2
    total = sum(int(d) * w for d, w in zip(base9, range(1, 10)))
    second = total % 11 - discount
    if second < 0:
        second += 11
    if second >= 10:
        second = 0
    return f"{first}{second}"


def is_valid_cnh_registro(value: str) -> bool:
    digits = only_digits(value)
    if len(digits) != 11 or digits == digits[0] * 11:
        return False
    return digits[9:] == cnh_registro_check_digits(digits[:9])


def random_cnh_registro(rng: random.Random) -> str:
    while True:
        base = "".join(str(rng.randint(0, 9)) for _ in range(9))
        if base != base[0] * 9:
            return base + cnh_registro_check_digits(base)
