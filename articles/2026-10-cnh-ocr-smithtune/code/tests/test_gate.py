import random
from datetime import date

from faker import Faker

from cnh_ocr import transcription as tx
from cnh_ocr.gate import is_cnh
from cnh_ocr.synth.records import random_record
from cnh_ocr.synth.render import random_style, render_non_cnh


def test_every_synthetic_cnh_transcription_passes():
    fake = Faker("pt_BR")
    for seed in range(200):
        fake.seed_instance(seed)
        assert is_cnh(tx.from_record(random_record(random.Random(seed), fake, date(2026, 9, 25))))


def test_every_decoy_transcription_is_rejected():
    fake = Faker("pt_BR")
    for seed in range(200):
        rng = random.Random(seed)
        fake.seed_instance(seed)
        printed: list[str] = []
        render_non_cnh(rng, fake, random_style(rng), printed)
        assert printed and not is_cnh("\n".join(printed)), printed


def test_real_card_label_spellings_pass():
    assert is_cnh("NOME: X\nCAT.HAB.: B\nN° REGISTRO: 00095964237\nVALIDADE: 21/05/1954")


def test_refusal_and_generic_id_are_rejected():
    assert not is_cnh(tx.NOT_A_CNH)
    assert not is_cnh("NOME: FULANO\nFILIAÇÃO: A / B\nDATA DE NASCIMENTO: 01/01/1990")


def test_collecting_decoy_text_does_not_change_the_image():
    def render(collect):
        rng = random.Random(7)
        fake = Faker("pt_BR")
        fake.seed_instance(7)
        return render_non_cnh(rng, fake, random_style(rng), [] if collect else None).tobytes()

    assert render(True) == render(False)
