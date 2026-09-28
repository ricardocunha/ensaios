import random
from datetime import date

from faker import Faker

from cnh_ocr import transcription as tx
from cnh_ocr.extractor.noise import add_noise
from cnh_ocr.extractor.tools import (
    check_dates,
    normalize_categoria,
    normalize_date,
    submit_cnh_record,
    suggest_ocr_fixes,
    validate_cpf,
)
from cnh_ocr.synth.records import random_record


def _record(seed=0):
    fake = Faker("pt_BR")
    fake.seed_instance(seed)
    return random_record(random.Random(seed), fake, date(2026, 9, 25))


def test_letter_lookalike_in_cpf_is_recovered_uniquely():
    cpf = _record().cpf
    broken = cpf.replace("0", "O", 1) if "0" in cpf else cpf.replace("5", "S", 1)
    out = suggest_ocr_fixes.invoke({"value": broken, "kind": "cpf"})
    assert out["candidates"][0] == cpf


def test_validate_cpf_accepts_any_formatting():
    cpf = _record().cpf
    assert validate_cpf.invoke({"cpf": cpf.replace(".", " ").replace("-", "")})["valid"]


def test_normalize_date_handles_ocr_separators_and_letters():
    assert normalize_date.invoke({"text": "O7.O3-1990"}) == {"ok": True, "date": "07/03/1990"}


def test_categoria_ocr_slip():
    assert normalize_categoria.invoke({"text": "A8"})["categoria"] == "AB"


def test_generated_records_pass_date_checks():
    for seed in range(200):
        r = _record(seed)
        out = check_dates.invoke({"data_nascimento": r.data_nascimento,
                                  "primeira_habilitacao": r.primeira_habilitacao,
                                  "data_emissao": r.data_emissao, "validade": r.validade})
        assert out["ok"], (seed, out)


def test_submit_accepts_clean_record():
    assert submit_cnh_record.invoke(_record().model_dump()) == "ACCEPTED"


def test_noise_keeps_structure_and_changes_something():
    rng = random.Random(3)
    clean = tx.from_record(_record())
    noisy = [add_noise(clean, rng, rate=0.5) for _ in range(20)]
    assert any(n != clean for n in noisy)
    assert all("CPF:" in n for n in noisy)


def test_many_records_generate_without_date_errors():
    for seed in range(3000):
        _record(seed)


def test_incomplete_record_is_accepted_with_nulls():
    rec = _record().model_copy(update={"doc_identidade": None, "orgao_emissor": None, "uf_emissor": None,
                                       "cpf": None})
    assert submit_cnh_record.invoke(rec.model_dump()) == "ACCEPTED"


def test_formato_is_not_scored():
    from cnh_ocr.evaluation.metrics import score_record
    rec = _record()
    other = rec.model_copy(update={"formato": "digital" if rec.formato == "fisica" else "fisica"})
    assert score_record(other, rec).exact


def test_dropped_lines_become_expected_nulls():
    from pathlib import Path
    from cnh_ocr.extractor.run import load_inputs
    from cnh_ocr.transcription import LABEL_FIELDS, parse
    items = [i for i in load_inputs(Path("data/synth-v3/train"), None, 400, 0) if i["source"] == "noise"]
    checked = 0
    for item in items:
        present = set(parse(item["transcription"]))
        missing = [label for label in LABEL_FIELDS if label not in present]
        for label in missing:
            for field in LABEL_FIELDS[label]:
                assert getattr(item["truth"], field) in (None, [], ""), (label, field)
                checked += 1
    assert checked > 0


def test_submit_refuses_an_rg_shaped_record():
    out = submit_cnh_record.invoke({"nome": "NATHAN RAMOS", "filiacao": ["HELOÍSA DA PAZ"]})
    assert out.startswith("NOT ACCEPTED")


def test_names_compare_accent_insensitively_numbers_do_not():
    from cnh_ocr.evaluation.metrics import score_record
    rec = _record().model_copy(update={"nome": "ANA VITÓRIA DA LUZ"})
    assert score_record(rec.model_copy(update={"nome": "ANA VITORIA DA LUZ"}), rec).exact
    assert not score_record(rec.model_copy(update={"numero_registro": "00000000000"}), rec).exact


def test_filiacao_accepts_a_single_string():
    from cnh_ocr.schema import CnhRecord
    assert CnhRecord(filiacao="JOSÉ DA SILVA / MARIA DA SILVA").filiacao == ["JOSÉ DA SILVA", "MARIA DA SILVA"]
    assert CnhRecord(filiacao=["A", "B"]).filiacao == ["A", "B"]
