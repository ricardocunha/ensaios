"""Deterministic evaluation of an agent pipeline run.

Three checks, none of them uses an LLM:

1. **Plan vs. solver**: value captured, budget use, requests covered.
2. **Schedule**: access-loss violations (a month whose overlapping works cut
   hospital/school access that no single work cuts alone), peak delay; the
   agent's schedule vs. a naive priority-order schedule and a deterministic
   heuristic on the same works.
3. **Number audit**:
   - *structured*: every number in a ``Phase`` (trips, delay, access nodes)
     and every ``AccessFlag`` is recomputed from scratch (no cache) and must
     match (integers exactly; seconds within 0.05 s, i.e. the tools'
     rounding to 0.1 s);
   - *free text*: every number in the agents' prose is looked up in the
     run's ledger (all numbers the tools returned and the prompts showed).
     Match = equal after rounding to the digits the agent printed, allowing
     x100 (shares as %), /60 (s -> min) or /1000 (m -> km). No other
     tolerance: with thousands of ledger numbers a relative tolerance would
     match almost anything. Integers from 0 to 12 without decimals are skipped as trivial
     (months, list numbers, small counts, which the structured audit covers).
     A ledger match only shows the number came from *some* tool output, not
     that it is used in the right place; the structured audit is the strict one.
"""

from __future__ import annotations

import itertools
import re
from dataclasses import dataclass
from statistics import mean, pstdev

from road_agents import planning as P
from road_agents.agents import ClosureSchedule, MaintenanceProposal, PipelineResult, QuarterlyPlan, schedule_dict

NUM_RE = re.compile(r"(?<![\w.])[-+]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?:[eE][-+]?\d+)?")
TRIVIAL_MAX_INT = 12
CONVERSIONS = (1.0, 100.0, 1 / 60, 1 / 1000)
SECONDS_TOL = 0.051


@dataclass
class Num:
    raw: str
    value: float
    decimals: int
    start: int

    @property
    def trivial(self) -> bool:
        return self.decimals == 0 and "e" not in self.raw.lower() and abs(self.value) <= TRIVIAL_MAX_INT


def extract_numbers(text: str) -> list[Num]:
    out = []
    for m in NUM_RE.finditer(text or ""):
        raw = m.group(0)
        clean = raw.replace(",", "")
        try:
            value = float(clean)
        except ValueError:
            continue
        mant = clean.lower().split("e")[0]
        decimals = len(mant.split(".")[1]) if "." in mant else 0
        out.append(Num(raw, value, decimals, m.start()))
    return out


def grounded(n: Num, ledger: list[float]) -> bool:
    x = abs(n.value)
    for y in ledger:
        y = abs(y)
        for f in CONVERSIONS:
            z = y * f
            if abs(round(z, n.decimals) - x) < 1e-9:
                return True
    return False


def audit_text(texts: dict[str, str], ledger: list[float]) -> dict:
    """``texts``: label -> prose. Returns counts and the unmatched numbers with context."""
    uniq = sorted(set(ledger))
    n_total = n_trivial = n_ok = 0
    missing = []
    for label, text in texts.items():
        for n in extract_numbers(text):
            n_total += 1
            if n.trivial:
                n_trivial += 1
            elif grounded(n, uniq):
                n_ok += 1
            else:
                ctx = text[max(0, n.start - 60): n.start + len(n.raw) + 30].replace("\n", " ")
                missing.append({"where": label, "number": n.raw, "context": ctx})
    checked = n_total - n_trivial
    return {"numbers": n_total, "trivial_skipped": n_trivial, "checked": checked, "grounded": n_ok,
            "grounded_share": (n_ok / checked) if checked else None, "not_found": missing}


def agent_texts(proposal: MaintenanceProposal | None, schedule: ClosureSchedule | None, plan: QuarterlyPlan | None) -> dict[str, str]:
    t: dict[str, str] = {}
    if proposal:
        t["maintenance.rationale"] = proposal.rationale
        for i, d in enumerate(proposal.deviations):
            t[f"maintenance.deviation[{i}].reason"] = d.reason
    if schedule:
        t["closure.rationale"] = schedule.rationale
        for i, f in enumerate(schedule.flags):
            t[f"closure.flag[{i}].note"] = f.note
    if plan:
        t["coordinator.summary"] = plan.summary
        for i, x in enumerate(plan.trade_offs):
            t[f"coordinator.trade_off[{i}]"] = f"{x.topic}. {x.decision}. {x.cost}"
        for i, r in enumerate(plan.risks):
            t[f"coordinator.risk[{i}]"] = r
    return t


def audit_phases(data: P.PlanningData, schedule: ClosureSchedule) -> dict:
    """Stated per-month numbers vs. a fresh recomputation (cache bypassed)."""
    rows, fields_total, fields_ok = [], 0, 0
    for ph in schedule.phases:
        truth = P.closure_report(data, ph.section_ids, use_cache=False)
        checks = {
            "trips_affected": (ph.trips_affected, truth.trips_affected, ph.trips_affected == truth.trips_affected),
            "total_delay_s": (ph.total_delay_s, truth.total_delay_s, abs(ph.total_delay_s - truth.total_delay_s) <= SECONDS_TOL),
            "hospital_nodes_lost": (ph.hospital_nodes_lost, truth.hospital_nodes_lost, ph.hospital_nodes_lost == truth.hospital_nodes_lost),
            "school_nodes_lost": (ph.school_nodes_lost, truth.school_nodes_lost, ph.school_nodes_lost == truth.school_nodes_lost),
        }
        fields_total += len(checks)
        fields_ok += sum(ok for *_, ok in checks.values())
        rows.append({"month": ph.month, **{k: {"stated": s, "true": t, "ok": ok} for k, (s, t, ok) in checks.items()}})
    # flags: stated nodes vs. recomputation on the flagged sections; months needing a flag
    flag_rows = []
    for f in schedule.flags:
        try:
            truth = P.closure_report(data, f.section_ids, use_cache=False) if f.section_ids else None
        except KeyError:
            truth = None
        true_n = None if truth is None else (truth.hospital_nodes_lost if f.facility == "hospital" else truth.school_nodes_lost)
        flag_rows.append({"month": f.month, "facility": f.facility, "stated": f.nodes_lost, "true": true_n, "ok": true_n == f.nodes_lost})
    flagged = {(f.month, f.facility) for f in schedule.flags}
    need = []
    for ph in schedule.phases:
        truth = P.closure_report(data, ph.section_ids)
        for fac, n in (("hospital", truth.hospital_nodes_lost), ("school", truth.school_nodes_lost)):
            if n > 0:
                need.append((ph.month, fac))
    return {
        "phase_fields": fields_total,
        "phase_fields_ok": fields_ok,
        "phases": rows,
        "flags": flag_rows,
        "flags_ok": sum(r["ok"] for r in flag_rows),
        "flags_needed": len(need),
        "flags_missed": sorted(set(need) - flagged),
    }


def schedule_metrics(rep: P.ScheduleReport) -> dict:
    return {
        "violations": rep.violations,
        "interaction_nodes": rep.interaction_nodes,
        "peak_total_delay_s": rep.peak_total_delay_s,
        "sum_total_delay_s": rep.sum_total_delay_s,
        "months": {p.month: p.section_ids for p in rep.phases},
        "conflicting_pairs": {p.month: p.conflicting_pairs for p in rep.phases if p.conflicting_pairs},
        "hospital_nodes_lost": {p.month: p.impact.hospital_nodes_lost for p in rep.phases},
    }


def solver_reference(data: P.PlanningData, budget_share: float, n_works: int) -> dict:
    """The pure-solver arm: solver plan, its major works, naive and heuristic schedules."""
    solver = P.solve_budget(data, budget_share)
    works = P.major_works(data, solver.chosen, n_works)
    return {
        "plan": solver.model_dump(),
        "works": works,
        "naive": schedule_metrics(P.schedule_report(data, P.naive_schedule(works))),
        "heuristic": schedule_metrics(P.schedule_report(data, P.heuristic_schedule(data, works))),
    }


def evaluate_run(data: P.PlanningData, r: PipelineResult) -> dict:
    proposal = r.maintenance.output
    schedule = r.closure.output
    plan = r.coordinator.output
    out: dict = {
        "agents_ok": {"maintenance": r.maintenance.ok, "closure": r.closure.ok, "coordinator": r.coordinator.ok},
        "plan": {
            "value_share_pct": r.final.value_share_pct,
            "solver_value_share_pct": r.solver.value_share_pct,
            "value_vs_solver_pct": r.final.value_vs_solver_pct,
            "budget_used_pct": r.final.budget_used_pct,
            "solver_budget_used_pct": r.solver.budget_used_pct,
            "requests_covered_pct": r.final.requests_covered_pct,
            "solver_requests_covered_pct": r.solver.requests_covered_pct,
            "n_sections": r.final.n_sections,
            "adds": r.final.must_include,
            "removes": r.final.exclude,
            "jaccard_vs_solver": jaccard(r.final.chosen, r.solver.chosen),
        },
        "works": r.works,
        "naive": schedule_metrics(P.schedule_report(data, P.naive_schedule(r.works))),
        "heuristic": schedule_metrics(P.schedule_report(data, P.heuristic_schedule(data, r.works))),
    }
    if schedule is not None:
        out["agent_schedule"] = schedule_metrics(P.schedule_report(data, schedule_dict(schedule)))
        out["phase_audit"] = audit_phases(data, schedule)
    out["text_audit"] = audit_text(agent_texts(proposal, schedule, plan), r.ledger)
    return out


def jaccard(a, b) -> float:
    a, b = set(a), set(b)
    return len(a & b) / len(a | b) if a | b else 1.0


def co_assignment_agreement(s1: dict, s2: dict) -> float | None:
    """Rand index between two month assignments over their common works."""
    m1 = {w: m for m, ws in s1.items() for w in ws}
    m2 = {w: m for m, ws in s2.items() for w in ws}
    common = sorted(set(m1) & set(m2))
    pairs = list(itertools.combinations(common, 2))
    if not pairs:
        return None
    return sum((m1[a] == m1[b]) == (m2[a] == m2[b]) for a, b in pairs) / len(pairs)


def consistency(evals: list[dict], raws: list[dict]) -> dict:
    """Across repeated runs with the same inputs."""
    devs = [{(d["section_id"], d["action"]) for d in (r["maintenance"]["output"] or {}).get("deviations", [])} for r in raws]
    finals = [set(r["final"]["chosen"]) for r in raws]
    scheds = [e["agent_schedule"]["months"] for e in evals if "agent_schedule" in e]
    pairs = lambda xs: list(itertools.combinations(xs, 2))  # noqa: E731
    vals = [e["plan"]["value_share_pct"] for e in evals]
    agree = [a for s1, s2 in pairs(scheds) if (a := co_assignment_agreement(s1, s2)) is not None]
    return {
        "runs": len(evals),
        "n_deviations": [len(d) for d in devs],
        "deviation_jaccard_mean": mean(jaccard(a, b) for a, b in pairs(devs)) if len(devs) > 1 else None,
        "identical_deviation_sets": len({frozenset(d) for d in devs}) == 1,
        "final_plan_jaccard_mean": mean(jaccard(a, b) for a, b in pairs(finals)) if len(finals) > 1 else None,
        "value_share_pct": vals,
        "value_share_pct_std": pstdev(vals) if vals else None,
        "schedule_co_assignment_mean": mean(agree) if agree else None,
        "violations": [e.get("agent_schedule", {}).get("violations") for e in evals],
    }
