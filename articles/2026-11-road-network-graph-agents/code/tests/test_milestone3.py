"""Milestone 3: planning tools, agents (TestModel / FunctionModel, no LLM),
number audit and evaluation. Synthetic graphs only; no network."""

from __future__ import annotations

import json
import random

import networkx as nx
import pytest
from pydantic_ai import models
from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.models.test import TestModel

from road_agents import audit, baseline
from road_agents.scripted import scripted_agent
from road_agents import planning as P
from road_agents.agents import (
    ClosureSchedule,
    Deps,
    Deviation,
    MaintenanceProposal,
    Phase,
    fact_sheet,
    closure_agent,
    maintenance_agent,
    result_json,
    run_pipeline,
    validate_proposal,
    validate_schedule,
)
from road_agents.condition import section_table
from road_agents.sections import build_sections, section_criticality
from road_agents.tools import accessibility_loss, closure_impact, compute_baseline, edge_criticality, sample_od_pairs

models.ALLOW_MODEL_REQUESTS = False  # any real LLM call in these tests is a bug


def road(D, u, v, name, hwy, length=100.0, speed=10.0):
    attrs = {"name": name, "highway": hwy, "length": length, "travel_time": length / speed}
    D.add_edge(u, v, **attrs)
    D.add_edge(v, u, **attrs)


def make_data(D: nx.DiGraph, hospitals, schools, pairs=80, seed=1, hospital_s=600.0, school_s=300.0) -> P.PlanningData:
    sections = build_sections(D)
    crit = section_criticality(D, sections, edge_criticality(D))
    rng = random.Random(seed)
    points = {s.section_id: rng.choice([0, 1, 2, 5, 9]) for s in sections}
    df = section_table(D, sections, crit, {k: 2 * v for k, v in points.items()}, points)
    od = compute_baseline(D, sample_od_pairs(D, pairs, seed=seed))
    return P.PlanningData(
        D, df.set_index("section_id"), {s.section_id: s.edges for s in sections}, list(hospitals), list(schools), od,
        hospital_s=hospital_s, school_s=school_s,
    )


@pytest.fixture
def grid() -> P.PlanningData:
    """6x6 grid: row 2 and column 3 are primary avenues, the rest residential
    streets named by row/column. Hospital and schools at a few nodes."""
    D = nx.DiGraph()
    n = 6
    for r in range(n):
        for c in range(n):
            node = r * n + c
            if c + 1 < n:
                road(D, node, node + 1, f"Avenida R{r}" if r == 2 else f"Rua R{r}", "primary" if r == 2 else "residential",
                     speed=15 if r == 2 else 8)
            if r + 1 < n:
                road(D, node, node + n, f"Avenida C{c}" if c == 3 else f"Rua C{c}", "primary" if c == 3 else "residential",
                     speed=15 if c == 3 else 8)
    return make_data(D, hospitals=[0, 35], schools=[7, 20, 28], hospital_s=60.0, school_s=40.0)


@pytest.fixture
def pinch() -> P.PlanningData:
    """Node 1 hangs between two differently named streets (A: 0-1, B: 1-2);
    a third street C (2-3-0) closes the loop. Hospital at 0. Closing A or B
    alone leaves node 1 a way out; closing both cuts it off: an interaction."""
    D = nx.DiGraph()
    road(D, 0, 1, "Rua A", "residential")
    road(D, 1, 2, "Rua B", "residential")
    road(D, 2, 3, "Rua C", "residential")
    road(D, 3, 0, "Rua C", "residential")
    road(D, 3, 4, "Rua D", "residential")
    road(D, 4, 5, "Rua E", "residential")
    road(D, 5, 3, "Rua F", "residential")
    return make_data(D, hospitals=[0], schools=[0], pairs=12)


def sid(data: P.PlanningData, name: str) -> str:
    return data.sections.index[data.sections["name"] == name][0]


# --- planning tools ---------------------------------------------------------------


def test_solve_budget_matches_greedy_and_honours_forced_sets(grid):
    cand = grid.candidates
    g = baseline.greedy(cand.index, cand["value"], cand["repair_cost"], grid.budget(0.3))
    p = P.solve_budget(grid, 0.3)
    assert p.chosen == g.chosen
    assert p.cost <= grid.budget(0.3) + 0.1
    left_out = next(s for s in cand.index if s not in p.chosen)
    dropped = p.chosen[0]
    q = P.solve_budget(grid, 0.3, must_include=[left_out], exclude=[dropped])
    assert left_out in q.chosen and dropped not in q.chosen
    assert q.value <= p.value + 1e-9  # greedy optimum here; forcing never helps much
    with pytest.raises(ValueError):
        P.solve_budget(grid, 0.001, must_include=list(cand.index))
    with pytest.raises(KeyError):
        P.solve_budget(grid, 0.3, must_include=["S99999"])


def test_rank_sections_filters_and_orders(grid):
    plan = set(P.solve_budget(grid, 0.2).chosen)
    top = P.rank_sections(grid, by="requests", limit=5, plan=plan, plan_filter="not_in_plan")
    assert all(not r.in_solver_plan for r in top)
    assert [r.requests for r in top] == sorted((r.requests for r in top), reverse=True)
    prim = P.rank_sections(grid, by="criticality", highway="primary", limit=50)
    assert prim and all(r.highway == "primary" for r in prim)
    assert len(P.rank_sections(grid, limit=500)) <= 50


def test_section_details_rank_and_shares(grid):
    best = P.rank_sections(grid, by="value_per_cost", limit=1)[0]
    d = P.section_details(grid, best.section_id, budget=grid.budget(0.1))
    assert d.rank_value_per_cost == 1
    assert d.cost_share_of_budget_pct == pytest.approx(100 * d.repair_cost / grid.budget(0.1), abs=0.01)


def test_closure_report_equals_raw_tools(grid):
    ids = list(grid.sections.sort_values("criticality").index[-2:])
    rep = P.closure_report(grid, ids)
    edges = P._edges_of(grid, ids)
    raw = closure_impact(grid.D, edges, grid.od)
    assert rep.trips_affected == raw.n_affected
    assert rep.total_delay_s == pytest.approx(raw.total_delay_s, abs=0.05)
    assert rep.hospital_nodes_lost == len(accessibility_loss(grid.D, grid.hospitals, edges, 60.0)["lost_nodes"])
    assert rep.school_nodes_lost == len(accessibility_loss(grid.D, grid.schools, edges, 40.0)["lost_nodes"])
    assert P.closure_report(grid, ids, use_cache=False) == rep
    # a full recomputation without the cached OD baseline agrees
    full = closure_impact(grid.D, edges, grid.od.od_pairs)
    assert full.n_affected == rep.trips_affected


def test_interaction_loss_and_schedules(pinch):
    a, b = sid(pinch, "Rua A"), sid(pinch, "Rua B")
    e = sid(pinch, "Rua E")
    assert P.closure_report(pinch, [a]).hospital_nodes_lost == 0
    assert P.closure_report(pinch, [b]).hospital_nodes_lost == 0
    both = P.closure_report(pinch, [a, b])
    assert both.hospital_nodes_lost == 1 and both.hospital_nodes_cut_off == 1
    ph = P.phase_impact(pinch, 1, [a, b])
    assert ph.hospital_interaction_nodes == 1 and ph.violation
    works = [a, b, e]
    naive = P.naive_schedule(works, n_phases=2)  # cap 2: A and B land together
    assert P.schedule_report(pinch, naive).violations == 1
    smart = P.heuristic_schedule(pinch, works, n_phases=2)
    assert P.schedule_report(pinch, smart).violations == 0
    assert sorted(s for v in smart.values() for s in v) == sorted(works)


def test_access_loss_tool(pinch):
    a, b = sid(pinch, "Rua A"), sid(pinch, "Rua B")
    loss = P.accessibility_loss_sections(pinch, [a, b], "hospital")
    assert loss.nodes_lost == 1 and loss.nodes_cut_off == 1
    assert loss.nodes_within_before - loss.nodes_within_after == 1


def test_major_works_and_capacity(grid):
    plan = P.solve_budget(grid, 0.5)
    works = P.major_works(grid, plan.chosen, 5)
    crit = grid.sections.loc[works, "criticality"].tolist()
    assert crit == sorted(crit, reverse=True) and len(works) == min(5, len(plan.chosen))
    assert P.phase_capacity(15) == 5 and P.phase_capacity(16) == 6
    assert P.naive_schedule(list("abcdefg")) == {1: list("abc"), 2: list("def"), 3: ["g"]}


def test_text_summaries_are_map_free_and_numeric(grid):
    p = P.solve_budget(grid, 0.2)
    txt = P.plan_summary_text(grid, p)
    assert f"{p.n_sections} sections" in txt and f"{p.value_share_pct}%" in txt
    rep = P.closure_report(grid, [p.chosen[0]])
    assert str(rep.trips_affected) in P.closure_summary_text(rep)


# --- number audit ----------------------------------------------------------------


def test_extract_numbers():
    nums = audit.extract_numbers("S01760 costs 1,234.5 units, 70.2% of value, delay -3.5 s, 1e-5 gap, 10-min")
    assert [n.raw for n in nums] == ["1,234.5", "70.2", "-3.5", "1e-5", "10"]
    assert nums[0].value == 1234.5 and nums[1].decimals == 1
    assert nums[4].trivial and not nums[0].trivial


def test_grounding_rules():
    ledger = [0.70236, 1234.56, 389.0, 1760.0]
    ok = lambda s: audit.grounded(audit.extract_numbers(s)[0], ledger)  # noqa: E731
    assert ok("70.2%")  # share as percent, rounded
    assert ok("1,234.6")  # rounded to printed digits
    assert ok("6.5 min")  # 389 s / 60 = 6.48
    assert ok("1.76 km")  # m -> km
    assert not ok("512.3")
    res = audit.audit_text({"t": "value 70.2%, 3 months, cost 999.9"}, ledger)
    assert res["checked"] == 2 and res["grounded"] == 1 and res["not_found"][0]["number"] == "999.9"


def test_phase_audit_catches_wrong_numbers(grid):
    ids = list(grid.sections.sort_values("criticality").index[-2:])
    truth = P.closure_report(grid, ids)
    good = Phase(month=1, section_ids=ids, trips_affected=truth.trips_affected, total_delay_s=truth.total_delay_s,
                 hospital_nodes_lost=truth.hospital_nodes_lost, school_nodes_lost=truth.school_nodes_lost)
    bad = good.model_copy(update={"month": 2, "trips_affected": truth.trips_affected + 7, "total_delay_s": truth.total_delay_s + 30})
    res = audit.audit_phases(grid, ClosureSchedule(phases=[good, bad], rationale=""))
    assert res["phase_fields"] == 8 and res["phase_fields_ok"] == 6


def test_consistency_metrics():
    raw = {"maintenance": {"output": {"deviations": [{"section_id": "S1", "action": "add"}]}}, "final": {"chosen": ["S1", "S2"]}}
    ev = {"plan": {"value_share_pct": 50.0}, "agent_schedule": {"months": {1: ["a", "b"], 2: ["c"]}, "violations": 0}}
    ev2 = {"plan": {"value_share_pct": 48.0}, "agent_schedule": {"months": {1: ["a"], 2: ["b", "c"]}, "violations": 1}}
    c = audit.consistency([ev, ev, ev2], [raw, raw, raw])
    assert c["identical_deviation_sets"] and c["deviation_jaccard_mean"] == 1.0
    assert c["schedule_co_assignment_mean"] == pytest.approx((1 + 1 / 3 + 1 / 3) / 3)
    assert c["violations"] == [0, 0, 1]


# --- agents without an LLM ---------------------------------------------------------------


def test_pipeline_end_to_end_with_scripted_model(grid):
    r = run_pipeline(grid, 0.3, model=FunctionModel(scripted_agent), settings={}, n_works=6)
    assert r.maintenance.ok and r.closure.ok and r.coordinator.ok, (r.maintenance.error, r.closure.error, r.coordinator.error)
    assert len(r.final.must_include) == 1 and r.final.must_include[0] in r.final.chosen
    assert r.final.cost <= grid.budget(0.3) + 0.1
    ev = audit.evaluate_run(grid, r)
    assert ev["phase_audit"]["phase_fields_ok"] == ev["phase_audit"]["phase_fields"] > 0
    assert ev["phase_audit"]["flags_missed"] == [] or all(f[1] == "school" for f in ev["phase_audit"]["flags_missed"])
    ta = ev["text_audit"]
    assert [m["number"] for m in ta["not_found"]] == ["123.45"]
    assert {c["tool"] for c in r.calls} >= {"rank_sections", "try_plan", "closure_impact"}
    json.dumps(result_json(r), default=str)  # serializable for the jsonl log


def test_maintenance_validator_rejects_then_accepts(grid):
    solver = P.solve_budget(grid, 0.3)
    deps = Deps(grid, 0.3, solver)
    inside = solver.chosen[0]
    outside = next(s for s in grid.candidates.index if s not in solver.chosen)
    bad = MaintenanceProposal(deviations=[Deviation(section_id=inside, action="add", reason="x")], rationale="")
    assert any("already in the solver plan" in e for e in validate_proposal(deps, bad))
    assert validate_proposal(deps, MaintenanceProposal(deviations=[Deviation(section_id="S00000", action="add", reason="x")], rationale=""))
    calls = {"n": 0}

    def fn(messages, info):
        calls["n"] += 1
        sid_ = inside if calls["n"] == 1 else outside
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {
            "deviations": [{"section_id": sid_, "action": "add", "reason": "many requests"}], "rationale": "r"})])

    res = maintenance_agent(FunctionModel(fn), settings={}).run_sync("go", deps=deps)
    assert calls["n"] == 2 and res.output.deviations[0].section_id == outside


def test_schedule_validator():
    works = ["S1", "S2", "S3", "S4"]
    ph = lambda m, ids: Phase(month=m, section_ids=ids, trips_affected=0, total_delay_s=0, hospital_nodes_lost=0, school_nodes_lost=0)  # noqa: E731
    ok = ClosureSchedule(phases=[ph(1, ["S1", "S2"]), ph(2, ["S3"]), ph(3, ["S4"])], rationale="")
    assert validate_schedule(works, ok) == []
    errs = validate_schedule(works, ClosureSchedule(phases=[ph(1, ["S1", "S2", "S3"]), ph(1, ["S1", "S9"])], rationale=""))
    text = " ".join(errs)
    assert "once" in text and "S4" in text and "S9" in text and "capacity" in text


def test_agents_run_under_test_model(grid):
    """TestModel fills every schema field; with no tool calls the agents
    still return typed outputs (checks the wiring, not the reasoning)."""
    solver = P.solve_budget(grid, 0.3)
    deps = Deps(grid, 0.3, solver)
    m = maintenance_agent(TestModel(call_tools=[], custom_output_args={"deviations": [], "rationale": "keep"}), settings={})
    assert m.run_sync("go", deps=deps).output.deviations == []
    deps.works = P.major_works(grid, solver.chosen, 3)
    phases = [{"month": i + 1, "section_ids": [w], "trips_affected": 0, "total_delay_s": 0.0,
               "hospital_nodes_lost": 0, "school_nodes_lost": 0} for i, w in enumerate(deps.works)]
    c = closure_agent(TestModel(call_tools=[], custom_output_args={"phases": phases, "flags": [], "rationale": "r"}), settings={})
    out = c.run_sync("go", deps=deps).output
    assert [p.section_ids for p in out.phases] == [[w] for w in deps.works]


def test_failed_agent_is_recorded_not_raised(grid):
    def broken(messages, info):
        return ModelResponse(parts=[TextPart("I refuse to use the output tool.")])

    r = run_pipeline(grid, 0.3, model=FunctionModel(broken), settings={}, n_works=3, limits={"maintenance": 3, "closure": 3, "coordinator": 3})
    assert not r.maintenance.ok and r.maintenance.error
    assert r.final.chosen == r.solver.chosen  # falls back to the solver plan
    ev = audit.evaluate_run(grid, r)
    assert "agent_schedule" not in ev and ev["heuristic"]["violations"] >= 0


def test_pair_conflicts_and_schedule_text(pinch):
    a, b, e = sid(pinch, "Rua A"), sid(pinch, "Rua B"), sid(pinch, "Rua E")
    assert P.pair_conflicts(pinch, [a, b, e]) == {frozenset((a, b))}
    rep = P.schedule_report(pinch, {1: [a, b], 2: [e], 3: []})
    txt = P.schedule_summary_text(rep)
    assert "Month 1" in txt and "VIOLATION" in txt and "Violations: 1." in txt
    assert rep.phases[0].conflicting_pairs == [sorted([a, b])] and " + ".join(sorted([a, b])) in txt
    assert "Month 3" not in txt  # empty months are skipped


def test_agent_text_never_grounds_itself(grid):
    solver = P.solve_budget(grid, 0.3)
    deps = Deps(grid, 0.3, solver)
    outside = next(s for s in grid.candidates.index if s not in solver.chosen)
    prop = MaintenanceProposal(deviations=[Deviation(section_id=outside, action="add", reason="saves 98765.4 units")], rationale="")
    final = P.solve_budget(grid, 0.3, [outside])
    assert "98765.4" in fact_sheet(deps, prop, final, None, None)
    assert "98765.4" not in fact_sheet(deps, prop, final, None, None, agent_text=False)
