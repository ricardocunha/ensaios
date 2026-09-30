"""Alert agent: the numbers stay in code, and the citation audit catches invented ones (offline models only)."""

from datetime import datetime, timezone

import pytest
from pydantic_ai.messages import ModelResponse, RetryPromptPart, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.models.test import TestModel

from disaster_risk.alerts import AlertDraft, Driver, build_agent, build_input, citation_audit, write_alert
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
    inp = build_input(state)
    assert "86720000 at Encantado: last reading 1355 cm, 3.5 h ago" in inp.text
    assert inp.silent == {"86720000": "Encantado"}
    assert f"{100 * state.probability:.1f}%" in inp.text
    assert inp.stations == {"86720000", "86510000", "A840"}


def test_audit_passes_a_grounded_draft(state):
    inp = build_input(state)
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
    inp = build_input(state)
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
    inp = build_input(state)
    vague = GOOD.model_copy(update={"explanation": "Encantado is at risk. Levels are high."})
    assert citation_audit(inp, vague).silent_not_mentioned == ["86720000"]
    named = GOOD.model_copy(update={"explanation": "The Encantado gauge has stopped reporting."})
    assert citation_audit(inp, named).silent_not_mentioned == []


def test_rounding_is_allowed_but_not_new_digits(state):
    inp = build_input(state)
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
    alert, meta = write_alert(state, build_agent(model))
    assert alert.probability == state.probability and alert.level == state.level
    assert not alert.audit.ok and "37" in alert.audit.ungrounded_numbers and "normal" in alert.audit.wrong_level
    assert meta["requests"] == 1


def test_audit_retry_feeds_the_complaints_back(state):
    bad = GOOD.model_copy(update={"headline": "Encantado: 42 cm above flood level"})
    good = GOOD.model_copy(update={"headline": "Encantado flood risk", "explanation": "Gauge 86720000 at Encantado is silent (3.5 h)."})
    model, calls = _tool_model([bad, good])
    alert, meta = write_alert(state, build_agent(model, audit_retry=True))
    assert alert.audit.ok and meta["requests"] == 2
    retry = [p for m in calls[1] for p in getattr(m, "parts", []) if isinstance(p, RetryPromptPart)]
    assert retry and "42" in str(retry[0].content)


def test_prompt_and_wiring_with_test_model(state):
    alert, _ = write_alert(state, build_agent(TestModel()))
    assert alert.place == "Encantado" and alert.level == state.level


def test_river_names_are_not_place_citations(state):
    inp = build_input(state)
    d = GOOD.model_copy(update={"headline": "Encantado", "explanation": "Gauge 86720000 is silent. The Taquari River and Lake Guaíba are not places here."})
    assert citation_audit(inp, d).unknown_places == []
