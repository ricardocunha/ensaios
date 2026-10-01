"""LLM-only fusion harness: the model sees only what fusion saw at t, the prompt is fixed, scoring is plain (offline models only)."""

import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest
from helpers import T0, TH, ana_rows, inmet_rows
from pydantic_ai.messages import ModelResponse, ToolCallPart, UserPromptPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from disaster_risk import llm_fusion
from disaster_risk.backtest import replay
from disaster_risk.fusion import PLACES, FusionConfig, band_key, fuse
from disaster_risk.observations import Store
from disaster_risk.signals.ana import AnaAdapter
from disaster_risk.signals.inmet import InmetAdapter

H = timedelta(hours=1)
MUCUM = PLACES["Muçum"]
LEVELS = [300, 350, None, 500, 900, 1300, None, None, 1900, 2400, 2500, 2000, 1500, None, 800, 600]
RAINS = [0, 5, 20, None, 40, 60, 10, 0, 0, None, 0, 0, 0, 0, 0, 0]
CFG = FusionConfig("full", lr_table={band_key("gauge", "ana_level", 20.0): 300.0, band_key("rain", "inmet_rain", 2.0): 20.0})
THS = {"86510000": TH}


def _adapters():
    return [AnaAdapter(THS, {"86510000": 1800}), InmetAdapter()]


def _snapshots(rows, t_end):
    """Snapshot text per replay hour, built exactly as prepare() does (replay -> fuse -> render)."""
    return [llm_fusion.render_snapshot(fuse(MUCUM, st.t, st.signals, 0.01, CFG), THS, {"86510000": 1800})
            for st in replay(Store(rows), _adapters(), T0, t_end)]


def _capturing_model(p=0.42, level="attention"):
    seen = []

    def fn(messages, info: AgentInfo) -> ModelResponse:
        user = [part.content for m in messages for part in getattr(m, "parts", []) if isinstance(part, UserPromptPart)]
        seen.append({"user": user, "instructions": getattr(messages[0], "instructions", None)})
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {"probability": p, "level": level, "reason": "r"})])

    return FunctionModel(fn), seen


def _rows():
    return ana_rows(LEVELS, RAINS) + inmet_rows(RAINS)


def test_model_prompt_equals_prompt_from_data_truncated_at_t():
    rows = _rows()
    end = T0 + len(LEVELS) * H
    model, seen = _capturing_model()
    agent = llm_fusion.build_agent(model)
    for k, snap in enumerate(_snapshots(rows, end)):
        t = T0 + (k + 1) * H
        cut = [r for r in rows if r.available_at <= t]
        st = next(s for s in replay(Store(cut), _adapters(), t - H, t))
        expected = llm_fusion.render_snapshot(fuse(MUCUM, t, st.signals, 0.01, CFG), THS, {"86510000": 1800})
        llm_fusion.estimate(snap, agent)
        assert seen[-1]["user"] == [llm_fusion.prompt(expected)]


def test_future_spike_never_reaches_earlier_prompts():
    rows = _rows()
    end = T0 + len(LEVELS) * H
    k = 4
    spiked = [replace(r, level_cm=77777.0) if r.hour_end > T0 + (k + 1) * H and r.level_cm is not None else r for r in rows]
    model, seen = _capturing_model()
    agent = llm_fusion.build_agent(model)
    for snap in _snapshots(spiked, end):
        llm_fusion.estimate(snap, agent)
    prompts = [s["user"][0] for s in seen]
    assert prompts[: k + 1] == [llm_fusion.prompt(s) for s in _snapshots(rows, end)][: k + 1]
    assert all("77777" not in p for p in prompts[: k + 1])
    assert "77777" in prompts[k + 1]


def test_snapshot_hides_what_fusion_computed():
    rows = _rows()
    st = list(replay(Store(rows), _adapters(), T0, T0 + 11 * H))[-1]
    f = fuse(MUCUM, st.t, st.signals, 0.01, CFG)
    text = llm_fusion.render_snapshot(f, THS, {"86510000": 1800})
    assert f.level == "alert"
    for leak in (f"{100 * f.probability:.1f}%", f"{f.probability:.3f}", "log-odds", "effect", "without it", "alert",
                 "weight"):
        assert leak not in text
    assert "LR 300" in text and "official flood level 1800 cm" in text and "p99 1000 cm" in text
    assert "Prior (share of 2019-2022 hours with the hypothesis true): 1.00%" in text


def test_instructions_and_prompt_template_are_identical_across_hours():
    rows = _rows()
    model, seen = _capturing_model()
    agent = llm_fusion.build_agent(model)
    for snap in _snapshots(rows, T0 + 6 * H):
        llm_fusion.estimate(snap, agent)
    assert len({s["instructions"] for s in seen}) == 1
    assert seen[0]["instructions"] == llm_fusion.INSTRUCTIONS.strip()
    assert all(s["user"][0].startswith("Signals at this hour:\n\nPlace: Muçum\n") for s in seen)
    assert llm_fusion.model_settings()["temperature"] == 0.7
    assert llm_fusion.model_settings()["extra_body"] == {"chat_template_kwargs": {"enable_thinking": False}}


def test_event_grid_is_every_3h_from_minus_48_to_plus_12_around_the_crossing_hour():
    c = datetime(2024, 5, 1, 15, 45, tzinfo=timezone.utc)
    grid = llm_fusion.event_grid(c)
    assert len(grid) == 21
    assert grid[0] == (-48, datetime(2024, 4, 29, 15, tzinfo=timezone.utc))
    assert grid[-1] == (12, datetime(2024, 5, 2, 3, tzinfo=timezone.utc))
    assert all(t <= c + timedelta(hours=k) for k, t in grid)


def test_quiet_draw_is_fixed_by_the_seed():
    cands = {"A": [T0 + i * H for i in range(100)], "B": [T0 + i * H for i in range(50)]}
    a = llm_fusion.draw_quiet(cands, {"A": 3, "B": 2})
    assert a == llm_fusion.draw_quiet(cands, {"A": 3, "B": 2})
    assert [len(v) for v in a.values()] == [3, 2]


def test_first_alert_lead():
    c = datetime(2024, 5, 1, 12, tzinfo=timezone.utc)
    rows = [(k, c + timedelta(hours=k), c, lv) for k, lv in ((-6, "normal"), (-3, "alert"), (0, "emergency"))]
    assert llm_fusion.first_alert_lead(rows) == 3.0
    assert llm_fusion.first_alert_lead([(0, c, c, "attention")]) is None


@pytest.fixture
def hour_set(tmp_path):
    c = datetime(2024, 5, 1, 12, tzinfo=timezone.utc)
    hours = []
    for i, (s, k, y, fp, fl) in enumerate([("event", -3, 0, 0.6, "alert"), ("event", 0, 1, 0.95, "emergency"),
                                           ("quiet_fa", None, 0, 0.7, "alert"), ("quiet_random", None, 0, 0.01, "normal")]):
        t = c + timedelta(hours=k or -100 - i)
        h = {"id": i, "set": s, "place": "Muçum", "t": t.isoformat(), "t_local": "x", "label": y, "fusion_p": fp,
             "fusion_level": fl, "silent_gauges": [], "snapshot": f"snapshot {i}"}
        if s == "event":
            h |= {"offset_h": k, "crossing": c.isoformat()}
        hours.append(h)
    path = tmp_path / "hours.json"
    path.write_text(json.dumps({"prompt_sha": llm_fusion.prompt_sha(), "hours": hours}))
    return path


def test_run_is_resumable_and_score_counts(hour_set, tmp_path):
    out = tmp_path / "runs.jsonl"
    model, seen = _capturing_model(p=0.3, level="attention")
    llm_fusion.run(hour_set, out, limit=5, agent=llm_fusion.build_agent(model))
    assert len(seen) == 5
    llm_fusion.run(hour_set, out, agent=llm_fusion.build_agent(model))
    assert len(seen) == 4 * llm_fusion.SAMPLES
    s = llm_fusion.score(hour_set, out, tmp_path / "summary.json")
    assert s["complete_hours"] == 4 and s["errors"] == 0
    assert s["leads"]["Muçum"]["fusion"] == 3.0 and s["leads"]["Muçum"]["llm_samples"] == [None] * 3
    assert s["quiet"]["quiet_fa"]["fusion_alert"] == 1 and s["quiet"]["quiet_fa"]["llm_attention_per_sample"] == [1] * 3
    assert s["brier"]["all"]["llm_mean_p"] == pytest.approx((0.3 ** 2 * 3 + 0.7 ** 2) / 4)
    assert s["consistency"]["spread_max"] == 0


def test_run_refuses_a_changed_prompt(hour_set, tmp_path):
    spec = json.loads(hour_set.read_text())
    spec["prompt_sha"] = "different"
    hour_set.write_text(json.dumps(spec))
    with pytest.raises(SystemExit):
        llm_fusion.run(hour_set, tmp_path / "r.jsonl", agent=llm_fusion.build_agent(_capturing_model()[0]))
