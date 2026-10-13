"""Deterministic, typed planning tools over road *sections* (milestone 3): the
agents call these and never do graph math themselves.
Access loss = nodes within ``hospital_s`` / ``school_s`` of a facility before a
closure but not after. Interaction loss = lost under a set of simultaneous
closures but under none of its sections alone (sequencing can avoid only this).
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import networkx as nx
import numpy as np
import pandas as pd
from pydantic import BaseModel, Field

from road_agents import baseline as knapsack
from road_agents.tools import (
    Baseline,
    Edge,
    closure_impact,
    compute_baseline,
    sample_od_pairs,
    snap_points,
    time_to_nearest,
    without_edges,
)

RankBy = Literal["value", "value_per_cost", "condition", "criticality", "requests"]
PlanFilter = Literal["any", "in_plan", "not_in_plan"]
Facility = Literal["hospital", "school"]


# --- data ------------------------------------------------------------------


@dataclass
class PlanningData:
    """Everything the tools need, loaded once per process."""

    D: nx.DiGraph
    sections: pd.DataFrame  # indexed by section_id (columns as in DATA.md)
    edges: dict[str, list[Edge]]  # section_id -> directed edges
    hospitals: list[int]  # snapped graph nodes
    schools: list[int]
    od: Baseline
    hospital_s: float = 600.0
    school_s: float = 300.0
    _closure_cache: dict = field(default_factory=dict, repr=False)
    _before_cache: dict = field(default_factory=dict, repr=False)

    @property
    def candidates(self) -> pd.DataFrame:
        return self.sections[self.sections["value"] > 0]

    @property
    def total_cost(self) -> float:
        return float(self.candidates["repair_cost"].sum())

    @property
    def total_value(self) -> float:
        return float(self.candidates["value"].sum())

    def budget(self, share: float) -> float:
        return share * self.total_cost

    def facilities(self, kind: Facility) -> tuple[list[int], float]:
        return (self.hospitals, self.hospital_s) if kind == "hospital" else (self.schools, self.school_s)

    def check_ids(self, ids: Iterable[str]) -> list[str]:
        ids = list(dict.fromkeys(ids))
        unknown = [s for s in ids if s not in self.sections.index]
        if unknown:
            raise KeyError(f"unknown section ids: {unknown}")
        return ids


def load_planning_data(city: str = "belo-horizonte", pairs: int = 1000, data_dir: Path | None = None) -> PlanningData:
    """Real data from milestone 2's tables (``scripts/section_pipeline.py``)."""
    from road_agents.graph import DATA_DIR, load_graph, slugify, to_simple_digraph
    from road_agents.pois import load_pois

    data_dir = data_dir or DATA_DIR
    slug = slugify(city)
    D = to_simple_digraph(load_graph(city, data_dir=data_dir))
    sections = pd.read_csv(data_dir / f"{slug}-sections.csv", keep_default_na=False, na_values=[""])
    sections["name"] = sections["name"].fillna("")
    se = pd.read_csv(data_dir / f"{slug}-section-edges.csv")
    edges = {sid: list(zip(g["u"].astype(int), g["v"].astype(int))) for sid, g in se.groupby("section_id")}
    hospitals = snap_points(D, [(p["lon"], p["lat"]) for p in load_pois(city, "hospital", data_dir=data_dir)])
    schools = snap_points(D, [(p["lon"], p["lat"]) for p in load_pois(city, "school", data_dir=data_dir)])
    od = compute_baseline(D, sample_od_pairs(D, pairs))
    return PlanningData(D, sections.set_index("section_id"), edges, hospitals, schools, od)


# --- typed outputs -----------------------------------------------------------


class SectionRow(BaseModel):
    section_id: str
    name: str
    highway: str
    length_m: float
    condition: float = Field(description="0-1 percentile of pothole-request density; 0 = no requests")
    criticality: float = Field(description="0-1, section betweenness / network max")
    requests: int = Field(description="Tapa-Buraco requests Aug 2022 - Jul 2023")
    repair_cost: float = Field(description="synthetic cost units (m2 of full resurfacing)")
    value: float = Field(description="condition x criticality x km")
    value_per_cost: float
    in_solver_plan: bool | None = None


class SectionDetail(SectionRow):
    oneway: bool
    lanes: float
    n_edges: int
    request_points: int
    value_share_pct: float = Field(description="share of the total value of all candidates, %")
    cost_share_of_budget_pct: float | None = Field(None, description="share of the current budget, %")
    rank_value_per_cost: int | None = Field(None, description="1 = best value/cost among candidates")


class ClosureReport(BaseModel):
    section_ids: list[str]
    n_edges_closed: int
    n_trips_sampled: int
    trips_affected: int
    trips_disconnected: int
    total_delay_s: float
    mean_delay_s: float
    max_delay_s: float
    hospital_nodes_lost: int = Field(description="nodes losing 10-min hospital access")
    hospital_nodes_cut_off: int = Field(description="of those, nodes that reach no hospital at all")
    school_nodes_lost: int = Field(description="nodes losing 5-min school access")
    school_nodes_cut_off: int


class AccessLoss(BaseModel):
    facility: Facility
    threshold_s: float
    section_ids: list[str]
    nodes_within_before: int
    nodes_within_after: int
    nodes_lost: int
    nodes_cut_off: int


class PlanResult(BaseModel):
    budget_share_pct: float
    budget: float
    n_sections: int
    km: float
    cost: float
    budget_used_pct: float
    value: float
    value_share_pct: float = Field(description="share of the total value of all candidates, %")
    requests_covered: int
    requests_covered_pct: float = Field(description="share of all snapped requests, %")
    must_include: list[str] = []
    exclude: list[str] = []
    value_vs_solver_pct: float | None = Field(None, description="value relative to the unconstrained solver plan, %")
    chosen: list[str] = Field(default=[], exclude=True)  # full list kept out of LLM-facing JSON


class PhaseImpact(BaseModel):
    month: int
    section_ids: list[str]
    impact: ClosureReport
    hospital_interaction_nodes: int = Field(description="nodes losing hospital access only because works overlap")
    school_interaction_nodes: int
    hospital_unavoidable_nodes: int = Field(description="nodes some single work in the phase already cuts")
    school_unavoidable_nodes: int
    conflicting_pairs: list[list[str]] = Field(default_factory=list, description="pairs of works in this month that cut access together but not alone")

    @property
    def violation(self) -> bool:
        return self.hospital_interaction_nodes > 0 or self.school_interaction_nodes > 0


class ScheduleReport(BaseModel):
    phases: list[PhaseImpact]
    violations: int = Field(description="phases whose overlapping works cut access that no single work cuts")
    interaction_nodes: int = Field(description="hospital + school interaction nodes, summed over phases")
    peak_total_delay_s: float
    sum_total_delay_s: float


# --- section tools -----------------------------------------------------------


def _row(data: PlanningData, sid: str, plan: set[str] | None = None) -> SectionRow:
    r = data.sections.loc[sid]
    cost = float(r["repair_cost"])
    return SectionRow(
        section_id=sid,
        name=str(r["name"]) or "(unnamed)",
        highway=str(r["highway"]),
        length_m=round(float(r["length_m"]), 1),
        condition=round(float(r["condition"]), 3),
        criticality=round(float(r["criticality"]), 4),
        requests=int(r["requests"]),
        repair_cost=round(cost, 1),
        value=round(float(r["value"]), 5),
        value_per_cost=round(float(r["value"]) / cost, 9) if cost > 0 else 0.0,
        in_solver_plan=(sid in plan) if plan is not None else None,
    )


def rank_sections(
    data: PlanningData,
    by: RankBy = "value",
    limit: int = 10,
    highway: str | None = None,
    plan: set[str] | None = None,
    plan_filter: PlanFilter = "any",
    name_contains: str | None = None,
) -> list[SectionRow]:
    """Top ``limit`` sections by ``by`` (descending; ties by id), optionally
    filtered by highway class, name substring and membership in ``plan``."""
    df = data.sections
    if highway:
        df = df[df["highway"] == highway]
    if name_contains:
        df = df[df["name"].str.contains(name_contains, case=False, regex=False)]
    if plan is not None and plan_filter != "any":
        mask = df.index.isin(list(plan))
        df = df[mask] if plan_filter == "in_plan" else df[~mask]
    key = df["value"] / df["repair_cost"].where(df["repair_cost"] > 0, np.inf) if by == "value_per_cost" else df[by]
    order = sorted(df.index, key=lambda s: (-float(key[s]), s))[: max(0, min(limit, 50))]
    return [_row(data, s, plan) for s in order]


def section_details(data: PlanningData, sid: str, plan: set[str] | None = None, budget: float | None = None) -> SectionDetail:
    data.check_ids([sid])
    r = data.sections.loc[sid]
    cand = data.candidates
    rank = None
    if sid in cand.index:
        ratio = cand["value"] / cand["repair_cost"]
        rank = int((ratio > ratio[sid]).sum()) + 1
    return SectionDetail(
        **_row(data, sid, plan).model_dump(),
        oneway=bool(r["oneway"]),
        lanes=float(r["lanes"]),
        n_edges=int(r["n_edges"]),
        request_points=int(r["request_points"]),
        value_share_pct=round(100 * float(r["value"]) / data.total_value, 4) if data.total_value else 0.0,
        cost_share_of_budget_pct=round(100 * float(r["repair_cost"]) / budget, 3) if budget else None,
        rank_value_per_cost=rank,
    )


# --- budget solver -------------------------------------------------------------


def solve_budget(
    data: PlanningData,
    budget_share: float,
    must_include: Sequence[str] = (),
    exclude: Sequence[str] = (),
) -> PlanResult:
    """Greedy knapsack at ``budget_share`` of the candidates' total cost, with
    forced inclusions (taken first) and exclusions. Raises ``ValueError`` if
    the forced sections alone exceed the budget."""
    must = data.check_ids(must_include)
    excl = set(data.check_ids(exclude))
    if set(must) & excl:
        raise ValueError(f"sections both included and excluded: {sorted(set(must) & excl)}")
    budget = data.budget(budget_share)
    forced_cost = float(data.sections.loc[must, "repair_cost"].sum()) if must else 0.0
    if forced_cost > budget + 1e-9:
        raise ValueError(f"forced sections cost {forced_cost:.1f}, more than the budget {budget:.1f}")
    cand = data.candidates
    rest = cand[~cand.index.isin(list(excl) + must)]
    plan = knapsack.greedy(rest.index, rest["value"], rest["repair_cost"], budget - forced_cost)
    chosen = must + plan.chosen
    return plan_result(data, budget_share, chosen, must, sorted(excl))


def plan_result(
    data: PlanningData, budget_share: float, chosen: Sequence[str], must: Sequence[str] = (), exclude: Sequence[str] = ()
) -> PlanResult:
    sel = data.sections.loc[list(chosen)]
    budget = data.budget(budget_share)
    total_req = float(data.sections["requests"].sum())
    return PlanResult(
        budget_share_pct=round(100 * budget_share, 2),
        budget=round(budget, 1),
        n_sections=len(sel),
        km=round(float(sel["length_m"].sum()) / 1000, 1),
        cost=round(float(sel["repair_cost"].sum()), 1),
        budget_used_pct=round(100 * float(sel["repair_cost"].sum()) / budget, 2) if budget else 0.0,
        value=round(float(sel["value"].sum()), 4),
        value_share_pct=round(100 * float(sel["value"].sum()) / data.total_value, 2) if data.total_value else 0.0,
        requests_covered=int(sel["requests"].sum()),
        requests_covered_pct=round(100 * float(sel["requests"].sum()) / total_req, 2) if total_req else 0.0,
        must_include=list(must),
        exclude=list(exclude),
        chosen=list(chosen),
    )


def with_solver_comparison(p: PlanResult, solver: PlanResult) -> PlanResult:
    return p.model_copy(update={"value_vs_solver_pct": round(100 * p.value / solver.value, 2) if solver.value else None})


# --- closure and access --------------------------------------------------------


def _edges_of(data: PlanningData, sids: Iterable[str]) -> list[Edge]:
    return sorted({e for s in sids for e in data.edges.get(s, [])})


def _before(data: PlanningData, kind: Facility) -> dict[int, float]:
    fac, th = data.facilities(kind)
    if kind not in data._before_cache:
        data._before_cache[kind] = time_to_nearest(data.D, fac, cutoff=th)
    return data._before_cache[kind]


def _access_sets(data: PlanningData, kind: Facility, closed: list[Edge]) -> tuple[set[int], set[int], int]:
    """(lost nodes, cut-off nodes among them, nodes within after)."""
    fac, th = data.facilities(kind)
    before = _before(data, kind)
    view = without_edges(data.D, closed)
    after = time_to_nearest(view, fac, cutoff=th)
    lost = set(before) - set(after)
    if not lost:
        return set(), set(), len(after)
    reach_any = time_to_nearest(view, fac)  # no cutoff: can the node reach a facility at all?
    return lost, {n for n in lost if n not in reach_any}, len(after)


def _closure(data: PlanningData, sids: Sequence[str], use_cache: bool = True) -> tuple[ClosureReport, set[int], set[int]]:
    ids = sorted(data.check_ids(sids))
    key = frozenset(ids)
    if use_cache and key in data._closure_cache:
        return data._closure_cache[key]
    closed = _edges_of(data, ids)
    imp = closure_impact(data.D, closed, data.od)
    h_lost, h_cut, _ = _access_sets(data, "hospital", closed)
    s_lost, s_cut, _ = _access_sets(data, "school", closed)
    rep = ClosureReport(
        section_ids=ids,
        n_edges_closed=len(closed),
        n_trips_sampled=imp.n_pairs,
        trips_affected=imp.n_affected,
        trips_disconnected=imp.n_disconnected,
        total_delay_s=round(imp.total_delay_s, 1),
        mean_delay_s=round(imp.mean_delay_s, 1),
        max_delay_s=round(imp.max_delay_s, 1),
        hospital_nodes_lost=len(h_lost),
        hospital_nodes_cut_off=len(h_cut),
        school_nodes_lost=len(s_lost),
        school_nodes_cut_off=len(s_cut),
    )
    out = (rep, h_lost, s_lost)
    if use_cache:
        data._closure_cache[key] = out
    return out


def closure_report(data: PlanningData, sids: Sequence[str], use_cache: bool = True) -> ClosureReport:
    """Trips and access lost when all ``sids`` are closed at the same time."""
    if not sids:
        raise ValueError("no sections given")
    return _closure(data, sids, use_cache)[0]


def accessibility_loss_sections(data: PlanningData, sids: Sequence[str], facility: Facility = "hospital") -> AccessLoss:
    ids = sorted(data.check_ids(sids))
    _, th = data.facilities(facility)
    lost, cut, after = _access_sets(data, facility, _edges_of(data, ids))
    return AccessLoss(
        facility=facility,
        threshold_s=th,
        section_ids=ids,
        nodes_within_before=len(_before(data, facility)),
        nodes_within_after=after,
        nodes_lost=len(lost),
        nodes_cut_off=len(cut),
    )


# --- sequencing --------------------------------------------------------------------


def major_works(data: PlanningData, chosen: Iterable[str], n: int = 15) -> list[str]:
    """The ``n`` plan sections with the highest criticality (ties by id): the
    works whose closure matters for traffic. The rest of the plan is assumed
    to run under partial closure / off-peak and is not sequenced."""
    chosen = list(chosen)
    crit = data.sections.loc[chosen, "criticality"]
    return sorted(chosen, key=lambda s: (-float(crit[s]), s))[:n]


def phase_impact(data: PlanningData, month: int, sids: Sequence[str]) -> PhaseImpact:
    rep, h_lost, s_lost = _closure(data, sids)
    h_single: set[int] = set()
    s_single: set[int] = set()
    for s in sids:
        _, h, sc = _closure(data, [s])
        h_single |= h
        s_single |= sc
    conflicts = []
    if h_lost - h_single or s_lost - s_single:
        conflicts = sorted(sorted(p) for p in pair_conflicts(data, sorted(sids)))
    return PhaseImpact(
        month=month,
        section_ids=sorted(sids),
        conflicting_pairs=conflicts,
        impact=rep,
        hospital_interaction_nodes=len(h_lost - h_single),
        school_interaction_nodes=len(s_lost - s_single),
        hospital_unavoidable_nodes=len(h_lost & h_single),
        school_unavoidable_nodes=len(s_lost & s_single),
    )


def schedule_report(data: PlanningData, phases: dict[int, Sequence[str]]) -> ScheduleReport:
    rows = [phase_impact(data, m, ids) for m, ids in sorted(phases.items()) if ids]
    delays = [p.impact.total_delay_s for p in rows] or [0.0]
    return ScheduleReport(
        phases=rows,
        violations=sum(p.violation for p in rows),
        interaction_nodes=sum(p.hospital_interaction_nodes + p.school_interaction_nodes for p in rows),
        peak_total_delay_s=round(max(delays), 1),
        sum_total_delay_s=round(sum(delays), 1),
    )


def phase_capacity(n_works: int, n_phases: int = 3) -> int:
    return max(1, math.ceil(n_works / n_phases))


def naive_schedule(works: Sequence[str], n_phases: int = 3) -> dict[int, list[str]]:
    """Priority order, chunked: the first ``cap`` works in month 1, etc. What
    a plan that ignores simultaneity would do."""
    cap = phase_capacity(len(works), n_phases)
    return {m + 1: list(works[m * cap : (m + 1) * cap]) for m in range(n_phases)}


def _access_only(data: PlanningData, sids: Sequence[str]) -> tuple[set[int], set[int]]:
    key = ("access", frozenset(sids))
    if key not in data._closure_cache:
        closed = _edges_of(data, sids)
        data._closure_cache[key] = (_access_sets(data, "hospital", closed)[0], _access_sets(data, "school", closed)[0])
    return data._closure_cache[key]


def pair_conflicts(data: PlanningData, works: Sequence[str]) -> set[frozenset[str]]:
    """Pairs of works that, closed together, cut hospital or school access
    that neither cuts alone."""
    single = {w: _closure(data, [w]) for w in works}
    out = set()
    for i, a in enumerate(works):
        for b in works[i + 1 :]:
            h, s = _access_only(data, [a, b])
            if (h - single[a][1] - single[b][1]) or (s - single[a][2] - single[b][2]):
                out.add(frozenset((a, b)))
    return out


def heuristic_schedule(data: PlanningData, works: Sequence[str], n_phases: int = 3) -> dict[int, list[str]]:
    """Deterministic non-LLM sequencer (the fair comparison for the closure agent):
    greedy by single-closure delay avoiding ``pair_conflicts``, then a swap search.
    Summed single delays are a proxy; conflicts of three or more works are not searched."""
    works = list(works)
    cap = phase_capacity(len(works), n_phases)
    delay = {w: _closure(data, [w])[0].total_delay_s for w in works}
    conf = pair_conflicts(data, works)
    phases: dict[int, list[str]] = {m + 1: [] for m in range(n_phases)}

    def n_conf(ids: Sequence[str]) -> int:
        return sum(frozenset((a, b)) in conf for i, a in enumerate(ids) for b in ids[i + 1 :])

    def score(ph: dict[int, list[str]]) -> tuple[int, float]:
        return (sum(n_conf(v) for v in ph.values()), max(sum(delay[w] for w in v) for v in ph.values()))

    for w in sorted(works, key=lambda s: (-delay[s], s)):
        room = [m for m, v in phases.items() if len(v) < cap]
        m = min(room, key=lambda m: (n_conf(phases[m] + [w]), sum(delay[x] for x in phases[m]) + delay[w], m))
        phases[m].append(w)

    improved = True
    while improved:
        improved = False
        best = score(phases)
        for m1 in phases:
            for m2 in phases:
                if m2 <= m1:
                    continue
                for a in list(phases[m1]):
                    for b in list(phases[m2]):
                        trial = {**phases, m1: [x if x != a else b for x in phases[m1]], m2: [x if x != b else a for x in phases[m2]]}
                        if score(trial) < best:
                            phases, best, improved = trial, score(trial), True
                            break
                    if improved:
                        break
                if improved:
                    break
            if improved:
                break
    return {m: sorted(v) for m, v in phases.items()}


# --- map-free text summaries -----------------------------------------------------


def plan_summary_text(data: PlanningData, p: PlanResult, top: int = 5) -> str:
    sel = data.sections.loc[p.chosen]
    by_class = sel.groupby("highway")["length_m"].sum().sort_values(ascending=False) / 1000
    classes = ", ".join(f"{h} {km:.1f} km" for h, km in by_class.head(6).items())
    roads = (
        sel[sel["name"] != ""].groupby("name")["value"].sum().sort_values(ascending=False).head(top)
    )
    road_txt = "; ".join(f"{n} (value {v:.4f})" for n, v in roads.items())
    lines = [
        f"Plan at {p.budget_share_pct:g}% of the total repair cost (budget {p.budget:.1f} cost units): "
        f"{p.n_sections} sections, {p.km} km, cost {p.cost:.1f} ({p.budget_used_pct}% of budget used).",
        f"Value captured: {p.value_share_pct}% of the total value of all candidate sections.",
        f"Pothole requests on chosen sections: {p.requests_covered} ({p.requests_covered_pct}% of all snapped requests).",
        f"Length by class: {classes}.",
        f"Top roads by value in the plan: {road_txt}.",
    ]
    if p.must_include or p.exclude:
        lines.append(f"Forced in: {', '.join(p.must_include) or 'none'}; excluded: {', '.join(p.exclude) or 'none'}.")
    if p.value_vs_solver_pct is not None:
        lines.append(f"Value relative to the unconstrained solver plan: {p.value_vs_solver_pct}%.")
    return "\n".join(lines)


def closure_summary_text(rep: ClosureReport) -> str:
    return (
        f"Closing {', '.join(rep.section_ids)} ({rep.n_edges_closed} directed edges): "
        f"{rep.trips_affected} of {rep.n_trips_sampled} sampled trips affected, {rep.trips_disconnected} disconnected; "
        f"extra time total {rep.total_delay_s} s, mean {rep.mean_delay_s} s, max {rep.max_delay_s} s. "
        f"Hospital 10-min access lost at {rep.hospital_nodes_lost} nodes ({rep.hospital_nodes_cut_off} cut off); "
        f"school 5-min access lost at {rep.school_nodes_lost} nodes ({rep.school_nodes_cut_off} cut off)."
    )


def schedule_summary_text(rep: ScheduleReport) -> str:
    lines = []
    for p in rep.phases:
        i = p.impact
        lines.append(
            f"Month {p.month} ({', '.join(p.section_ids)}): trips_affected {i.trips_affected}, "
            f"total_delay_s {i.total_delay_s}, hospital_nodes_lost {i.hospital_nodes_lost}, "
            f"school_nodes_lost {i.school_nodes_lost}; lost only because works overlap: "
            f"hospital {p.hospital_interaction_nodes}, school {p.school_interaction_nodes}"
            + (" -> VIOLATION" if p.violation else "")
            + (f" (pairs that conflict: {'; '.join(' + '.join(c) for c in p.conflicting_pairs)})" if p.conflicting_pairs else "")
        )
    lines.append(f"Violations: {rep.violations}. Worst month total_delay_s {rep.peak_total_delay_s}.")
    return "\n".join(lines)
