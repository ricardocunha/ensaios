"""Alert agent: the numbers stay in code, and the citation audit catches invented ones (offline models only)."""

from datetime import datetime, timezone

import pytest
from pydantic_ai.messages import ModelResponse, RetryPromptPart, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.models.test import TestModel

from disaster_risk.alerts import (
    AlertDraft,
    Driver,
    _grounded,
    build_agent,
    build_input,
    citation_audit,
    prompt,
    stated_levels,
    write_alert,
)
from disaster_risk.fusion import PLACES, fuse
from disaster_risk.signals import Signal

T = datetime(2024, 5, 1, 4, tzinfo=timezone.utc)  # 01:00 local


def _sig(source, station, place, value, unit, lr, rel, status="fresh", age=0.0):
    return Signal(source, station, place, T, T, value, unit, lr, age, rel, status)


@pytest.fixture
def state():
    sigs = [
        _sig("ana_level", "86720000", "Encantado", 1355.0, "cm", 10.0, 0.67, "stale", 3.5),
        _sig("ana_level", "86510000", "Muçum", 1459.0, "cm", 4.0, 0.9),
        _sig("inmet_rain", "A840", "Bento Gonçalves", 151.0, "mm/24h", 10.0, 0.8),
    ]
    return fuse(PLACES["Encantado"], T, sigs, 0.5)  # prior 0.5 so the level is "emergency"


GOOD = AlertDraft(
    headline="Encantado flood risk",
    explanation="The Encantado gauge 86720000 is silent: its last reading, 1355 cm, is 3.5 h old and is trusted less.",
    drivers=[Driver(station="86720000", effect="raises"), Driver(station="86510000", effect="raises")],
    silent_gauges=["86720000"],
)


def test_fixture_level(state):
    assert state.level == "emergency"


def test_input_block_has_numbers_and_silent_gauges(state):
    inp = build_input(state, "en")
    assert "86720000 at Encantado: last reading 1355 cm, 3.5 h ago" in inp.text
    assert inp.silent == {"86720000": "Encantado"}
    assert f"{100 * state.probability:.1f}%" in inp.text
    assert inp.stations == {"86720000", "86510000", "A840"}


def test_audit_passes_a_grounded_draft(state):
    inp = build_input(state, "en")
    draft = GOOD.model_copy(update={"headline": f"Encantado: {state.level.upper()} flood risk, {100 * state.probability:.1f}%"})
    contribs = {c.station: c.log_odds for c in state.contributions}
    draft = draft.model_copy(update={"explanation": (
        f"The Encantado gauge 86720000 is silent: its last reading, 1355 cm, is 3.5 h old and is trusted less. "
        f"It still adds the most ({contribs['86720000']:+.2f}); upstream, Muçum 86510000 at 1459 cm adds "
        f"{contribs['86510000']:+.2f}. Rain at Bento Gonçalves (A840), 151 mm in 24 h, adds {contribs['A840']:+.2f} "
        f"in the Taquari valley.")})
    a = citation_audit(inp, draft)
    assert a.ok, a
    assert a.numbers_checked > 5


def test_audit_flags_invented_numbers_stations_places_and_levels(state):
    inp = build_input(state, "en")
    bad = AlertDraft(
        headline="Encantado: alert level, river will reach 25 m",
        explanation="Station 86879300 in Estrela shows a rise of 3.2 m. Level: alert.",
        drivers=[Driver(station="A999", effect="raises")],
        silent_gauges=[],
    )
    a = citation_audit(inp, bad)
    assert not a.ok
    assert "25" in a.ungrounded_numbers and "3.2" in a.ungrounded_numbers
    assert set(a.unknown_stations) == {"86879300", "A999"}
    assert a.unknown_places == ["Estrela"]
    assert a.silent_not_mentioned == ["86720000"]
    assert a.silent_field_mismatch == ["86720000"]
    assert a.wrong_level == ["alert"]


def test_silent_gauge_needs_code_or_place_with_a_silence_word(state):
    inp = build_input(state, "en")
    vague = GOOD.model_copy(update={"explanation": "Encantado is at risk. Levels are high."})
    assert citation_audit(inp, vague).silent_not_mentioned == ["86720000"]
    named = GOOD.model_copy(update={"explanation": "The Encantado gauge has stopped reporting."})
    assert citation_audit(inp, named).silent_not_mentioned == []


def test_rounding_is_allowed_but_not_new_digits(state):
    inp = build_input(state, "en")
    p = 100 * state.probability
    ok = GOOD.model_copy(update={"headline": f"Encantado {p:.0f}%", "explanation": "Gauge 86720000 (Encantado) is silent."})
    assert citation_audit(inp, ok).ungrounded_numbers == []
    off = ok.model_copy(update={"headline": f"Encantado {p + 3:.0f}%"})
    assert citation_audit(inp, off).ungrounded_numbers == [f"{p + 3:.0f}"]


def _tool_model(drafts):
    calls = []

    def fn(messages, info: AgentInfo) -> ModelResponse:
        calls.append(messages)
        d = drafts[min(len(calls) - 1, len(drafts) - 1)]
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, d.model_dump())])

    return FunctionModel(fn), calls


def test_alert_numbers_come_from_fusion_not_the_model(state):
    lying = GOOD.model_copy(update={"headline": "Encantado: normal, 37%"})
    model, _ = _tool_model([lying])
    alert, meta = write_alert(state, build_agent(model), "en")
    assert alert.probability == state.probability and alert.level == state.level
    assert not alert.audit.ok and "37" in alert.audit.ungrounded_numbers and "normal" in alert.audit.wrong_level
    assert meta["requests"] == 1


def test_audit_retry_feeds_the_complaints_back(state):
    bad = GOOD.model_copy(update={"headline": "Encantado: 42 cm above flood level"})
    good = GOOD.model_copy(update={"headline": "Encantado flood risk", "explanation": "Gauge 86720000 at Encantado is silent (3.5 h)."})
    model, calls = _tool_model([bad, good])
    alert, meta = write_alert(state, build_agent(model, audit_retry=True), "en")
    assert alert.audit.ok and meta["requests"] == 2
    retry = [p for m in calls[1] for p in getattr(m, "parts", []) if isinstance(p, RetryPromptPart)]
    assert retry and "42" in str(retry[0].content)


def test_prompt_and_wiring_with_test_model(state):
    alert, _ = write_alert(state, build_agent(TestModel()), "en")
    assert alert.place == "Encantado" and alert.level == state.level


def test_river_names_are_not_place_citations(state):
    inp = build_input(state, "en")
    d = GOOD.model_copy(update={"headline": "Encantado", "explanation": "Gauge 86720000 is silent. The Taquari River and Lake Guaíba are not places here."})
    assert citation_audit(inp, d).unknown_places == []


def test_silent_gauge_line_uses_the_level_signal_not_the_rain_of_the_same_station():
    # ANA rain and level share the station code; here the rain signal has the larger effect, so it sorts first.
    sigs = [
        _sig("ana_rain", "86720000", "Encantado", 146.0, "mm/24h", 10.0, 0.8),
        _sig("ana_level", "86720000", "Encantado", 1355.0, "cm", 4.0, 0.08, "stale", 22.5),
        _sig("ana_level", "86879300", "Estrela", 2756.0, "cm", 10.0, 0.9),
    ]
    inp = build_input(fuse(PLACES["Estrela"], T, sigs, 0.01), "en")
    assert "86720000 at Encantado: last reading 1355 cm, 22.5 h ago" in inp.text
    assert "last reading 146 cm" not in inp.text


# --- pt-BR (the default language) ---------------------------------------------------------------


def _pt(x: float, nd: int = 1) -> str:
    return f"{x:.{nd}f}".replace(".", ",")


def test_default_input_is_portuguese_with_decimal_commas(state):
    inp = build_input(state)
    assert inp.lang == "pt"
    assert "86720000 em Encantado: última leitura 1355 cm, há 3,5 h" in inp.text
    assert "1355 cm (13,55 m)" in inp.text
    assert f"Probabilidade combinada: {_pt(100 * state.probability)}% -> nível de risco: EMERGÊNCIA" in inp.text
    assert inp.silent == {"86720000": "Encantado"}
    assert "Escreva o alerta" in prompt(inp)


def test_pt_audit_passes_a_grounded_portuguese_draft(state):
    inp = build_input(state)
    c = {x.station: x.log_odds for x in state.contributions}
    draft = AlertDraft(
        headline=f"Encantado: risco de EMERGÊNCIA, {_pt(100 * state.probability)}% de probabilidade",
        explanation=(
            f"A régua de Encantado (86720000) está silenciosa: a última leitura, 1.355 cm (13,55 m), é de 3,5 h atrás "
            f"e recebe menos peso. Ainda assim é o sinal de maior efeito ({_pt(c['86720000'], 2)}). A montante, Muçum "
            f"(86510000) marca 14,59 m e soma {_pt(c['86510000'], 2)}. A chuva em Bento Gonçalves (A840), 151 mm em "
            f"24 h, soma {_pt(c['A840'], 2)} no vale do Taquari."),
        drivers=[Driver(station="86720000", effect="raises")],
        silent_gauges=["86720000"],
    )
    a = citation_audit(inp, draft)
    assert a.ok, a
    assert a.numbers_checked > 6


@pytest.mark.parametrize("tok", ["3,66", "3.66", "13,55", "1.355", "1355", "1.355,0"])
def test_pt_and_en_number_formats_are_both_grounded(tok):
    inp = build_input(fuse(PLACES["Estrela"], T, [_sig("ana_level", "86879300", "Estrela", 366.0, "cm", 1.5, 0.9),
                                                   _sig("ana_level", "86720000", "Encantado", 1355.0, "cm", 4.0, 0.9)], 0.01))
    d = AlertDraft(headline="Estrela", explanation=f"A régua 86879300 marca {tok}.", drivers=[], silent_gauges=[])
    assert citation_audit(inp, d).ungrounded_numbers == []


def test_pt_audit_flags_invented_portuguese_numbers(state):
    inp = build_input(state)
    d = AlertDraft(headline="Encantado", explanation="A régua 86720000 está sem leitura; o rio vai a 3,2 m e 1.420 cm.",
                   drivers=[], silent_gauges=["86720000"])
    a = citation_audit(inp, d)
    assert a.ungrounded_numbers == ["3,2", "1.420"]
    # a decimal comma is a decimal, not a thousands group: 13,5 is not 135
    assert not _grounded("13,5", [135.0]) and _grounded("13,5", [13.55])


@pytest.mark.parametrize("text,level", [
    ("Encantado: risco de ALERTA, 98,8%", "alert"),
    ("Encantado: nível de risco: atenção", "attention"),
    ("Encantado em situação NORMAL", "normal"),
    ("Encantado: risco de emergência", "emergency"),
    ("Encantado: EMERGÊNCIA de cheia", "emergency"),
])
def test_pt_level_words_are_read(text, level):
    assert stated_levels(text, "") == {level}


def test_pt_generic_alerta_and_atencao_in_headline_are_not_levels():
    assert stated_levels("Alerta de cheia em Encantado", "") == set()
    assert stated_levels("Atenção: Encantado com risco de emergência", "") == {"emergency"}


def test_pt_wrong_level_is_flagged(state):
    inp = build_input(state)
    d = AlertDraft(headline="Encantado: risco de ALERTA", explanation="A régua 86720000 está silenciosa.",
                   drivers=[], silent_gauges=["86720000"])
    assert citation_audit(inp, d).wrong_level == ["alert"]


@pytest.mark.parametrize("sentence", [
    "A régua de Encantado está silenciosa.",
    "A régua de Encantado está sem leitura há 3,5 h.",
    "A régua de Encantado parou de transmitir.",
    "Encantado não está reportando, e a leitura está desatualizada.",
])
def test_pt_silence_by_place_name(state, sentence):
    inp = build_input(state)
    d = AlertDraft(headline="Encantado", explanation=sentence, drivers=[], silent_gauges=["86720000"])
    assert citation_audit(inp, d).silent_not_mentioned == []


def test_pt_place_without_silence_word_is_not_enough(state):
    inp = build_input(state)
    d = AlertDraft(headline="Encantado", explanation="Encantado está em risco. O rio Taquari subiu.",
                   drivers=[], silent_gauges=["86720000"])
    a = citation_audit(inp, d)
    assert a.silent_not_mentioned == ["86720000"] and a.unknown_places == []


def test_pt_agent_gets_portuguese_instructions(state):
    seen = []

    def fn(messages, info: AgentInfo) -> ModelResponse:
        seen.append(messages)
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, GOOD.model_dump())])

    write_alert(state, build_agent(FunctionModel(fn)))
    first = seen[0][0]
    assert "português do Brasil" in (first.instructions or "")
    assert "Escreva o alerta" in str(first.parts[0].content)
