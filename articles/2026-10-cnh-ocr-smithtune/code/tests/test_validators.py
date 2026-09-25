import random

import pytest
from validate_docbr import CNH, CPF

from cnh_ocr.validators import (
    format_cpf,
    is_valid_cnh_registro,
    is_valid_cpf,
    random_cnh_registro,
    random_cpf,
)


def test_generated_cpfs_agree_with_reference_implementation():
    rng = random.Random(0)
    reference = CPF()
    for _ in range(2000):
        cpf = random_cpf(rng)
        assert is_valid_cpf(cpf)
        assert reference.validate(cpf)


def test_generated_cnh_numbers_agree_with_reference_implementation():
    rng = random.Random(0)
    reference = CNH()
    for _ in range(2000):
        num = random_cnh_registro(rng)
        assert is_valid_cnh_registro(num)
        assert reference.validate(num)


def test_reference_generated_numbers_pass_our_validators():
    for _ in range(500):
        assert is_valid_cpf(CPF().generate())
        assert is_valid_cnh_registro(CNH().generate())


@pytest.mark.parametrize("bad", ["111.111.111-11", "123.456.789-00", "12345", ""])
def test_rejects_invalid_cpf(bad):
    assert not is_valid_cpf(bad)


def test_single_ocr_slip_breaks_cpf_checksum():
    cpf = random_cpf(random.Random(1))
    digits = cpf.replace(".", "").replace("-", "")
    slipped = digits[:4] + str((int(digits[4]) + 1) % 10) + digits[5:]
    assert not is_valid_cpf(format_cpf(slipped))


@pytest.mark.parametrize("bad", ["00000000000", "12345678901", "1234"])
def test_rejects_invalid_cnh_registro(bad):
    assert not is_valid_cnh_registro(bad)
