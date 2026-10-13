from pathlib import Path

import pytest
from pydantic import ValidationError

from eye_rag.vlm import Case, Diagnosis, build_parts, case_report, diagnose, extract_json, parse_diagnosis


def test_diagnosis_accepts_codes_and_normalises_case():
    d = Diagnosis.model_validate({"labels": ["dr", "MH", "DR"]})
    assert d.labels == ["DR", "MH"]
    assert Diagnosis.model_validate({"labels": ["Normal"]}).labels == ["normal"]


@pytest.mark.parametrize("bad", [{"labels": ["GLAUCOMA"]}, {"labels": []}, {"labels": ["normal", "DR"]}, {"labels": ["DR"], "extra": 1}])
def test_diagnosis_rejects_bad_answers(bad):
    with pytest.raises(ValidationError):
        Diagnosis.model_validate(bad)


def test_extract_json_from_fences_and_prose():
    assert extract_json('Sure!\n```json\n{"labels": ["DR"]}\n```') == '{"labels": ["DR"]}'
    assert parse_diagnosis('answer: {"labels": ["normal"], "rationale": "ok"} thanks').labels == ["normal"]
    with pytest.raises(ValueError):
        extract_json("no json here")


def test_case_report_is_deterministic_text_from_labels():
    assert case_report(["NORMAL"]).startswith("normal fundus")
    r = case_report(["MH", "DR"])
    assert r.index("diabetic retinopathy (DR)") < r.index("media haze (MH)")


def test_build_parts_puts_cases_then_query_last():
    q, c1, c2 = Path("q.jpg"), Path("a.jpg"), Path("b.jpg")
    parts = build_parts(q, [Case(c1, ("DR",)), Case(c2, ("NORMAL",))])
    imgs = [p for p in parts if isinstance(p, Path)]
    assert imgs == [c1, c2, q]
    assert "2 reference cases" in parts[0] and "Recorded findings: diabetic retinopathy" in parts[1]
    assert not any(isinstance(p, Path) for p in build_parts(q)[:-2]) and build_parts(q)[-2] == q


class Stub:
    """Scripted VLM: returns the given answers in order and records prompts."""

    name = "stub"

    def __init__(self, answers):
        self.answers, self.prompts = list(answers), []

    def generate(self, parts, max_tokens):
        self.prompts.append(parts)
        return self.answers.pop(0)


def test_diagnose_retries_with_error_feedback():
    m = Stub(['{"labels": ["GLAUCOMA"]}', "```json\n{\"labels\": [\"ODC\"], \"cited_cases\": [1]}\n```"])
    o = diagnose(m, Path("q.jpg"), [Case(Path("a.jpg"), ("ODC",))])
    assert o.diagnosis.labels == ["ODC"] and o.diagnosis.cited_cases == [1]
    assert o.attempts == 2 and "labels" in o.errors[0]
    assert "previous answer was invalid" in m.prompts[1][-1]


def test_diagnose_gives_up_after_retries():
    o = diagnose(Stub(["nope"] * 3), Path("q.jpg"), retries=2)
    assert o.diagnosis is None and o.attempts == 3 and len(o.errors) == 3
