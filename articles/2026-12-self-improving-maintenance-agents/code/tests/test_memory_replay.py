"""Milestone 3: agent, memory, gating and replay. Offline: TestModel / FunctionModel only.

The core proof is ``test_replay_before_a_date_does_not_depend_on_anything_after_it``:
change the future, and every prompt, tool result and diagnosis before the split must stay identical.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re

import numpy as np
import pandas as pd
import pytest
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.models.test import TestModel

from maintenance_agents.agent import (
    INSTRUCTIONS,
    INSTRUCTIONS_V2,
    DiagnosisV2,
    Deps,
    build_agent,
    memory_block,
    needs_justification,
    render_prompt,
)
from maintenance_agents.episodes import DAY, SCORE_COL, VECTOR_SIGNALS, ReplayData, cosine, signal_vector
from maintenance_agents.memory import (
    GATED,
    UNGATED,
    Candidate,
    MemoryRecord,
    MemoryStore,
    MemoryView,
    Outcome,
    gate,
    TrackRecord,
    lesson,
    resolve_outcome,
    track_record,
)
from maintenance_agents.replay import ARMS, labels_from_eval, replay, score

T0 = pd.Timestamp("2016-01-01")
SPLIT = pd.Timestamp("2016-04-10 12:00")


# ------------------------------------------------------------------ fixtures


def make_daily(days=200, seed=0, turbines=("TA", "TB")) -> pd.DataFrame:
    """Daily scores for two turbines; z depends on (turbine, day) only."""
    frames = []
    for i, t in enumerate(turbines):
        rng = np.random.default_rng(seed * 10 + i)
        idx = pd.date_range(T0, periods=days, freq="D", name="day")
        df = pd.DataFrame({f"z_{s}": rng.normal(0, 0.3, days) for s in VECTOR_SIGNALS}, index=idx)
        df[SCORE_COL] = rng.normal(0, 1, days)
        df.insert(0, "turbine_id", t)
        df["n_hours"] = 24
        frames.append(df)
    return pd.concat(frames)


def alarm(daily: pd.DataFrame, turbine: str, day: str, signal: str, z: float) -> None:
    m = (daily["turbine_id"] == turbine) & (daily.index == pd.Timestamp(day))
    daily.loc[m, SCORE_COL] = 5.0
    daily.loc[m, f"z_{signal}"] = z


# (episode id, turbine, first alarm day, driving signal, z): generator-bearing and hydraulic patterns repeat
EPISODES = [
    (0, "TA", "2016-02-01", "sensor_13_avg", 9.0),
    (1, "TB", "2016-02-03", "sensor_41_avg", -8.0),
    (2, "TA", "2016-02-20", "sensor_13_avg", 7.0),
    (3, "TB", "2016-03-01", "sensor_41_avg", -9.0),
    (4, "TA", "2016-03-20", "sensor_13_avg", 8.0),
    (5, "TB", "2016-04-02", "sensor_41_avg", -7.0),
    (6, "TA", "2016-04-09", "sensor_13_avg", 9.5),  # decided 04-10 00:00, before the split
    (7, "TB", "2016-04-12", "sensor_41_avg", -8.5),  # after the split
    (8, "TA", "2016-04-25", "sensor_13_avg", 8.0),
    (9, "TB", "2016-05-10", "sensor_41_avg", -9.0),
]

FAULTS = [
    ("TA", "2016-02-10 10:00", "generator_bearing", "High temperature generator bearing"),  # 9 d after ep 0
    ("TB", "2016-03-05 08:00", "hydraulic_group", "Oil leakage in Hub"),  # 4 d after ep 3
    ("TA", "2016-04-11 09:00", "generator_bearing", "Generator bearings replaced"),  # after the split, 2 d after ep 6
    ("TB", "2016-05-20 12:00", "hydraulic_group", "Hydraulic group error"),
]


def make_data(daily=None, episodes=EPISODES, faults=FAULTS) -> ReplayData:
    daily = make_daily() if daily is None else daily
    for _, t, d, s, z in episodes:
        alarm(daily, t, d, s, z)
    ep = pd.DataFrame([(i, t, d) for i, t, d, *_ in episodes], columns=["episode_id", "turbine_id", "start"])
    f = pd.DataFrame(faults, columns=["turbine_id", "fault_time", "component", "remarks"])
    f["fault_time"] = pd.to_datetime(f["fault_time"])
    f.insert(0, "fault_id", range(len(f)))
    return ReplayData(daily=daily, faults=f, episodes=ep)


def diag(component="generator", action="inspect", urgency="medium", confidence=0.5) -> dict:
    return {"component": component, "action": action, "urgency": urgency, "evidence": "x", "confidence": confidence}


# ------------------------------------------------------------------ situations and tools


def test_replay_data_refuses_labels():
    d = make_data()
    ep = d.episodes.assign(healthy_start=True)
    with pytest.raises(ValueError):
        ReplayData(daily=d.daily, faults=d.faults, episodes=ep)


def test_situation_and_tools_see_only_up_to_the_first_alarm_day():
    base = make_data()
    changed_daily = make_daily()
    later = changed_daily.index > pd.Timestamp("2016-02-20")
    changed_daily.loc[later, [c for c in changed_daily.columns if c.startswith("z_")]] = 99.0
    changed = make_data(daily=changed_daily)
    a, b = base.situation(2), changed.situation(2)
    assert a.decision_time == pd.Timestamp("2016-02-21")
    assert a.summary() == b.summary() and np.array_equal(a.vector, b.vector)
    for grp in ("generator_bearing", "hydraulic", "converter"):
        sa = base.residual_series(a, grp, 60)
        assert sa == changed.residual_series(b, grp, 60)
        assert "2016-02-20" in sa and "2016-02-21" not in sa
    assert base.context(a) == changed.context(b)
    assert a.top_group == "generator_bearing" and a.top_component == "generator_bearing"


def test_maintenance_log_shows_only_rows_before_the_decision():
    d = make_data()
    s = d.situation(6)  # first alarm 2016-04-09, decided 04-10 00:00
    log = d.maintenance_log(s)
    assert "2016-02-10" in log and "2016-04-11" not in log
    s0 = d.situation(0)
    assert "No logbook entries" in d.maintenance_log(s0)


def test_signal_vector_keeps_sign_and_compresses_tails():
    z = pd.Series({"z_sensor_41_avg": -80.0, "z_sensor_13_avg": 1.0})
    v = signal_vector(z)
    i41, i13 = VECTOR_SIGNALS.index("sensor_41_avg"), VECTOR_SIGNALS.index("sensor_13_avg")
    assert v[i41] == pytest.approx(-np.log1p(80)) and v[i13] == pytest.approx(np.log1p(1))
    assert cosine(v, -v) == pytest.approx(-1.0) and cosine(v, np.zeros_like(v)) == 0.0


# ------------------------------------------------------------------ outcomes


def test_outcome_is_the_first_logbook_row_within_the_horizon_known_at_its_time():
    d = make_data()
    o = resolve_outcome(d.situation(0), d.faults)
    assert o.kind == "failure" and o.component == "generator_bearing"
    assert o.known_at == pd.Timestamp("2016-02-10 10:00") and o.days_after_start == 9


def test_no_failure_outcome_is_known_only_after_the_whole_horizon():
    d = make_data()
    s = d.situation(1)  # TB 02-03; next TB row is 03-05 = 31 days later
    o = resolve_outcome(s, d.faults, horizon_days=30)
    assert o.kind == "no_failure" and o.known_at == s.start + 31 * DAY
    o31 = resolve_outcome(s, d.faults, horizon_days=31)  # boundary day is inside the window
    assert o31.kind == "failure" and o31.known_at == pd.Timestamp("2016-03-05 08:00")


def test_outcome_ignores_other_turbines():
    d = make_data(faults=[("TB", "2016-02-05 10:00", "gearbox", "x")])
    assert resolve_outcome(d.situation(0), d.faults).kind == "no_failure"


def test_lessons():
    fail = Outcome("failure", pd.Timestamp("2016-01-10"), "gearbox", "noise", pd.Timestamp("2016-01-10"), 5)
    none = Outcome("no_failure", pd.Timestamp("2016-02-10"))
    assert lesson(diag("gearbox", "inspect"), fail) == "inspecting was right and the component was right."
    assert "the failed component was gearbox, not generator" in lesson(diag("generator", "monitor"), fail)
    assert "'monitor' missed it" in lesson(diag("generator", "monitor"), fail)
    assert "would have found nothing" in lesson(diag("generator", "inspect"), none)
    assert "'ignore' was fine" in lesson(diag("none", "ignore"), none)


# ------------------------------------------------------------------ store


def test_store_hides_outcomes_until_they_are_known():
    d = make_data()
    s = d.situation(0)
    o = resolve_outcome(s, d.faults)
    store = MemoryStore()
    store.add(MemoryRecord(s, diag(), s.decision_time, o))
    assert store.visible(s.decision_time - pd.Timedelta(seconds=1)) == []  # not diagnosed yet
    (v,) = store.visible(o.known_at - pd.Timedelta(seconds=1))
    assert v.outcome is None and v.lesson is None
    (v,) = store.visible(o.known_at)
    assert v.outcome == o and "inspecting was right" in v.lesson


def test_store_is_append_only_in_time_order():
    d = make_data()
    s0, s2 = d.situation(0), d.situation(2)
    store = MemoryStore()
    store.add(MemoryRecord(s2, diag(), s2.decision_time, resolve_outcome(s2, d.faults)))
    with pytest.raises(ValueError):
        store.add(MemoryRecord(s0, diag(), s0.decision_time, resolve_outcome(s0, d.faults)))


def test_candidates_exclude_the_query_and_rank_by_similarity():
    d = make_data()
    store = MemoryStore()
    for i in (0, 1, 2, 3):
        s = d.situation(i)
        store.add(MemoryRecord(s, diag(), s.decision_time, resolve_outcome(s, d.faults)))
    q = d.situation(4)
    c = store.candidates(q, q.decision_time)
    assert {x.view.situation.episode_id for x in c[:2]} == {0, 2}  # the same bearing pattern on the same turbine
    assert min(x.similarity for x in c[:2]) > 0.5 > max(x.similarity for x in c[2:])
    assert all(a.similarity >= b.similarity for a, b in zip(c, c[1:]))


# ------------------------------------------------------------------ gating


def _cand(d: ReplayData, eid: int, now: pd.Timestamp, sim: float, known: bool = True) -> Candidate:
    s = d.situation(eid)
    rec = MemoryRecord(s, diag(), s.decision_time, resolve_outcome(s, d.faults))
    view = MemoryView(rec, now, rec.outcome if known else None, "l" if known else None)
    return Candidate(view, sim, (now - s.decision_time) / DAY)


def test_gate_rules_one_by_one():
    d = make_data()
    q = d.situation(6)  # TA, generator_bearing pattern
    now = q.decision_time
    assert gate([_cand(d, 0, now, 0.9, known=False)], q, GATED).reasons() == {"outcome_pending": 1}
    assert gate([_cand(d, 0, now, 0.49)], q, GATED).reasons() == {"low_similarity": 1}
    assert gate([_cand(d, 0, now, 0.9)], q, GATED.with_(max_age_days=30)).reasons() == {"too_old": 1}
    # TB hydraulic memory: other turbine and other group
    assert gate([_cand(d, 1, now, 0.9)], q, GATED).reasons() == {"other_turbine_and_group": 1}
    assert gate([_cand(d, 1, now, 0.9)], q, GATED.with_(scope="same_turbine")).reasons() == {"other_turbine": 1}
    assert len(gate([_cand(d, 1, now, 0.9)], q, GATED.with_(scope="any")).selected) == 1
    ok = gate([_cand(d, 0, now, 0.9)], q, GATED)
    assert len(ok.selected) == 1 and ok.rejected == []


def test_gate_keeps_order_and_caps_at_k():
    d = make_data()
    q = d.situation(6)
    now = q.decision_time
    cands = [_cand(d, i, now, sim) for i, sim in ((0, 0.95), (2, 0.9), (4, 0.8), (3, 0.7))]
    g = gate(cands, q, GATED.with_(max_k=2, scope="any"))
    assert [c.view.situation.episode_id for c in g.selected] == [0, 2]
    assert g.reasons() == {"over_k": 2}


def test_ungated_lets_everything_through_up_to_k():
    d = make_data()
    q = d.situation(6)
    now = q.decision_time
    cands = [_cand(d, 1, now, -0.5, known=False), _cand(d, 3, now, 0.1)]
    assert len(gate(cands, q, UNGATED).selected) == 2


# ------------------------------------------------------------------ prompt and agent


def test_prompt_shows_memory_only_in_memory_arms_and_pending_outcomes_as_unknown():
    d = make_data()
    q = d.situation(6)
    assert "Past episodes" not in render_prompt(q, None)
    now = q.decision_time
    block = memory_block([_cand(d, 0, now, 0.9, known=False)], gated=False)
    assert "Outcome: not known yet." in block and "Episode #0" in block
    assert "none passed the memory filter" in memory_block([], gated=True)


def test_agent_runs_every_tool_with_test_model():
    d = make_data()
    agent = build_agent(TestModel(call_tools="all"))
    s = d.situation(6)
    r = agent.run_sync(render_prompt(s, None), deps=Deps(d, s))
    assert r.output.action in ("inspect", "monitor", "ignore")
    called = {p.tool_name for m in r.all_messages() for p in getattr(m, "parts", []) if getattr(p, "part_kind", "") == "tool-call"}
    assert {"residual_series", "context_signals", "maintenance_log"} <= called


# ------------------------------------------------------------------ the replay: no look-ahead


def recording_model(transcripts: dict[int, str]) -> FunctionModel:
    """Calls every tool once, then answers with a diagnosis derived from everything it saw.

    ``transcripts[episode_id]`` gets the prompt plus every tool result.
    """

    def fn(messages, info: AgentInfo) -> ModelResponse:
        parts = [p for m in messages for p in getattr(m, "parts", [])]
        prompt = next(p.content for p in parts if getattr(p, "part_kind", "") == "user-prompt")
        eid = int(re.search(r"Anomaly episode #(\d+)", prompt).group(1))
        returns = [p for p in parts if getattr(p, "part_kind", "") == "tool-return"]
        if not returns:
            return ModelResponse(
                parts=[
                    ToolCallPart("residual_series", {"group": "hydraulic", "days": 60}),
                    ToolCallPart("residual_series", {"group": "generator_bearing", "days": 60}),
                    ToolCallPart("context_signals", {}),
                    ToolCallPart("maintenance_log", {}),
                ]
            )
        seen = prompt + "\n" + "\n".join(f"{p.tool_name}: {p.content}" for p in returns)
        transcripts[eid] = seen
        h = int(hashlib.sha256(seen.encode()).hexdigest(), 16)
        out = {
            "component": ("generator_bearing", "hydraulic_group", "gearbox")[h % 3],
            "action": ("inspect", "monitor", "ignore")[(h // 3) % 3],
            "urgency": "low",
            "evidence": f"h{h % 1000}",
            "confidence": (h % 100) / 100,
        }
        if "differs_from_record" in str(info.output_tools[0].parameters_json_schema):
            out["differs_from_record"] = f"pattern h{h % 997}"
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, out)])

    return FunctionModel(fn)


def run_arm(data: ReplayData, arm: str, prompt: str = "v1") -> tuple[list[dict], dict[int, str]]:
    transcripts: dict[int, str] = {}
    rows = asyncio.run(replay(data, build_agent(recording_model(transcripts), prompt=prompt), ARMS[arm], arm=arm, prompt_version=prompt))
    return rows, transcripts


@pytest.mark.parametrize("prompt", ["v1", "v2"])
@pytest.mark.parametrize("arm", ["none", "ungated", "gated"])
def test_replay_before_a_date_does_not_depend_on_anything_after_it(arm, prompt):
    """Change the future, the past must not move.

    Three worlds: the base data, the future changed after SPLIT, and everything after SPLIT cut.
    Prompts, tool results and diagnoses decided before SPLIT must be identical in all three.
    """
    base = make_data()

    daily_b = make_daily()
    fut = daily_b.index >= SPLIT.normalize()
    daily_b.loc[fut, [c for c in daily_b.columns if c.startswith("z_")]] *= -3.0
    faults_b = [f if pd.Timestamp(f[1]) < SPLIT else (f[0], f[1], "gearbox", "Gearbox noise") for f in FAULTS]
    faults_b += [("TA", "2016-04-12 06:00", "transformer", "Transformer fan damaged")]
    eps_b = EPISODES + [(10, "TA", "2016-04-15", "sensor_38_avg", 12.0)]
    changed = make_data(daily=daily_b, episodes=eps_b, faults=faults_b)

    daily_c = make_daily()
    daily_c = daily_c[daily_c.index < SPLIT.normalize()]
    eps_c = [e for e in EPISODES if pd.Timestamp(e[2]) + DAY <= SPLIT]
    faults_c = [f for f in FAULTS if pd.Timestamp(f[1]) < SPLIT]
    truncated = make_data(daily=daily_c, episodes=eps_c, faults=faults_c)

    ra, ta = run_arm(base, arm, prompt)
    rb, tb = run_arm(changed, arm, prompt)
    rc, tc = run_arm(truncated, arm, prompt)

    past = [r["episode_id"] for r in ra if pd.Timestamp(r["decision_time"]) < SPLIT]
    assert past == [0, 1, 2, 3, 4, 5, 6] and [r["episode_id"] for r in rc] == past
    by = lambda rows: {r["episode_id"]: r for r in rows}  # noqa: E731
    a, b, c = by(ra), by(rb), by(rc)
    for eid in past:
        assert ta[eid] == tb[eid] == tc[eid], f"episode {eid} saw something different"
        for key in ("prompt", "diagnosis", "memories", "gate_rejections", "track_record"):
            assert a[eid][key] == b[eid][key] == c[eid][key], (eid, key)

    # teeth: the future change is visible after the split
    assert ta[7] != tb[7]
    if arm != "none":
        # memory is exercised: pre-split prompts hold outcomes that were known by then,
        # and the post-split fault (known 04-11 09:00) reaches episode 7's memory only in (a)
        assert any("Outcome: logbook failure" in a[e]["prompt"] for e in past)
        assert "Generator bearings replaced" not in "".join(a[e]["prompt"] for e in past)
        assert "Generator bearings replaced" in a[7]["prompt"] or "Generator bearings replaced" in a[8]["prompt"]
    if arm == "ungated":
        assert any("Outcome: not known yet." in a[e]["prompt"] for e in past)
    if arm == "gated":
        assert "Outcome: not known yet." not in "".join(r["prompt"] for r in ra)
    if prompt == "v2" and arm != "none":
        assert all("Track record of" in a[e]["prompt"] for e in past)
        assert any(a[e]["track_record"]["known"] > 0 for e in past)
    else:
        assert all("Track record of" not in a[e]["prompt"] for e in past)


def test_memory_arms_differ_only_in_what_enters_the_prompt():
    d = make_data()
    none, _ = run_arm(d, "none")
    ung, _ = run_arm(d, "ungated")
    gat, _ = run_arm(d, "gated")
    assert all(r["memories"] == [] for r in none)
    assert sum(len(r["memories"]) for r in ung) >= sum(len(r["memories"]) for r in gat) > 0
    assert all(m["outcome_known"] for r in gat for m in r["memories"])
    assert all(len(r["memories"]) <= 3 for r in ung + gat)
    json.dumps(gat, default=str)  # rows are serialisable


# ------------------------------------------------------------------ scoring


def test_labels_and_score():
    ev = pd.DataFrame(
        {
            "episode_id": [0, 1, 2, 3],
            "next_incident_id": [5, None, None, 6],
            "healthy_start": [False, True, False, False],
        }
    )
    labels = labels_from_eval(ev, {5: ["gearbox", "generator_bearing"], 6: ["transformer"]})
    assert labels["klass"].tolist() == ["pre_incident", "false_alarm", "near_incident", "pre_incident"]
    u = {"input_tokens": 100, "output_tokens": 10, "requests": 2, "tool_calls": 1}
    rows = [
        {"episode_id": 0, "decision_time": "2016-02-01 00:00:00", "diagnosis": diag("generator_bearing", "inspect"), "detector_component": "gearbox", "error": None, "memories": [], "usage": u, "seconds": 1.0},
        {"episode_id": 1, "decision_time": "2016-02-02 00:00:00", "diagnosis": diag("none", "ignore"), "detector_component": "generator", "error": None, "memories": [], "usage": u, "seconds": 2.0},
        {"episode_id": 2, "decision_time": "2016-03-01 00:00:00", "diagnosis": diag("gearbox", "inspect"), "detector_component": "gearbox", "error": None, "memories": [], "usage": u, "seconds": 3.0},
        {"episode_id": 3, "decision_time": "2016-03-02 00:00:00", "diagnosis": None, "detector_component": "generator", "error": "boom", "memories": [], "usage": u, "seconds": 4.0},
    ]
    s = score(rows, labels)
    assert s["component_accuracy_pre_incident"] == "1/2"
    assert s["detector_only_component_first_day"] == "1/2"
    assert s["inspect_on_pre_incident"] == "1/2" and s["ignore_on_false_alarm"] == "1/1"
    assert s["appropriate_total"] == "2/3" and s["errors"] == 1
    assert s["cost"]["input_tokens"] == 400 and s["cost"]["seconds"] == 10.0
    m = {r["month"]: r for r in s["monthly"]}
    assert m["2016-02"]["appropriate"] == 2 and m["2016-03"]["cum_appropriate"] == 2


def test_resume_reuses_only_the_unbroken_prefix():
    d = make_data()
    first, _ = run_arm(d, "gated")
    done = {r["episode_id"]: r for r in first if r["episode_id"] != 3}  # episode 3 failed / missing
    transcripts: dict[int, str] = {}
    rows = asyncio.run(replay(d, build_agent(recording_model(transcripts)), ARMS["gated"], arm="gated", done=done))
    assert sorted(transcripts) == [3, 4, 5, 6, 7, 8, 9]  # recomputed from the gap on
    assert [r["prompt"] for r in rows] == [r["prompt"] for r in first]


# ------------------------------------------------------------------ track record (v2)


def _store(d: ReplayData, ids) -> MemoryStore:
    store = MemoryStore()
    for i in ids:
        s = d.situation(i)
        store.add(MemoryRecord(s, diag(), s.decision_time, resolve_outcome(s, d.faults)))
    return store


def test_track_record_counts_only_outcomes_known_at_decision_time():
    d = make_data()
    store = _store(d, (0, 2, 4))  # TA bearing pattern; ep 0 -> failure known 02-10 10:00, ep 2 and 4 -> nothing
    q = d.situation(6)
    pol = GATED.with_(max_age_days=None)
    # ep 0 decided 02-02, its failure is logged 02-10 10:00: pending just before, a failure from then on
    before, at = pd.Timestamp("2016-02-10 09:59"), pd.Timestamp("2016-02-10 10:00")
    tb = track_record(store.candidates(q, before), q, pol)
    assert (tb.known, tb.failures, tb.pending) == (0, 0, 1)
    ta = track_record(store.candidates(q, at), q, pol)
    assert (ta.known, ta.failures, ta.pending, ta.failure_components) == (1, 1, 0, {"generator_bearing": 1})
    # at the query's decision time: ep 2 (no failure, known 03-22) counts, ep 4 (known 04-20) is still pending
    tq = track_record(store.candidates(q, q.decision_time), q, pol)
    assert (tq.known, tq.failures, tq.nothing, tq.pending) == (2, 1, 1, 1)
    assert not tq.mostly_nothing  # 1 of 2 is not more than half


def test_track_record_uses_the_gate_rules_without_the_k_cap():
    d = make_data()
    store = _store(d, (0, 1, 2, 3, 4, 5))
    q = d.situation(8)  # TA bearing, decided 04-26
    cands = store.candidates(q, q.decision_time)
    g = track_record(cands, q, GATED.with_(max_k=1))
    # TB hydraulic episodes 1, 3, 5 fail the similarity / scope rules; TA episodes 0, 2, 4 all count despite k=1
    assert g.known + g.pending == 3 and g.scope.startswith("similar past alarms")
    u = track_record(cands, q, UNGATED)
    assert u.known + u.pending == 6 and u.scope == "all past alarms on this farm"


def test_track_record_text_and_majority_rule():
    t = TrackRecord("x", known=5, failures=1, failure_components={"gearbox": 1}, pending=2)
    assert t.nothing == 4 and t.mostly_nothing
    txt = t.text()
    assert "5 with a known outcome" in txt and "1 of them" in txt and "(gearbox 1)" in txt and "4 were followed by nothing" in txt
    assert "2 more are still pending" in txt
    assert not TrackRecord("x", 1, 0, {}, 0).mostly_nothing  # one alarm is not a record
    assert not TrackRecord("x", 4, 2, {"gearbox": 2}, 0).mostly_nothing  # half is not most
    assert "no past alarm with a known outcome yet" in TrackRecord("x", 0, 0, {}, 0).text()


def test_inspect_against_a_mostly_nothing_record_must_say_why():
    d = make_data()
    s = d.situation(6)
    record = TrackRecord("x", known=4, failures=1, failure_components={"gearbox": 1}, pending=0)
    calls = []

    def fn(messages, info: AgentInfo) -> ModelResponse:
        calls.append(len(messages))
        why = "n/a" if len(calls) == 1 else "bearing NDE trend rising for 5 days, unlike the past alarms"
        args = diag("generator_bearing", "inspect") | {"differs_from_record": why}
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, args)])

    agent = build_agent(FunctionModel(fn), prompt="v2", tools=False)
    r = agent.run_sync(render_prompt(s, [], gated=True, track=record), deps=Deps(d, s, record))
    assert len(calls) == 2 and "unlike the past alarms" in r.output.differs_from_record
    # no retry when the record is not "mostly nothing", or the action is not inspect, or there is no record
    calls.clear()
    agent.run_sync("x", deps=Deps(d, s, TrackRecord("x", 2, 2, {"gearbox": 2}, 0)))
    assert len(calls) == 1
    assert not needs_justification(DiagnosisV2(**diag(action="monitor"), differs_from_record="n/a"), record)
    assert not needs_justification(DiagnosisV2(**diag(action="inspect"), differs_from_record="n/a"), None)
    assert needs_justification(DiagnosisV2(**diag(action="inspect"), differs_from_record=" N/A. "), record)


def test_v2_prompt_has_costs_and_the_none_arm_gets_no_record():
    d = make_data()
    rows, _ = run_arm(d, "none", "v2")
    assert all(r["track_record"] is None and "Track record" not in r["prompt"] for r in rows)
    assert "Cost 1" in INSTRUCTIONS_V2 and "costs about 10" in INSTRUCTIONS_V2 and "Cost 1" not in INSTRUCTIONS
