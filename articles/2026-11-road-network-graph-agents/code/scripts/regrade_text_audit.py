"""Re-score the prose-number audit of a finished evaluation, without an LLM:
rebuilds the ledger by replaying the logged tool calls, checks it against the
logged size and strict counts, then runs ``audit.audit_text_lenient``.

Usage:
    nice uv run python scripts/regrade_text_audit.py runs/m3-eval-local.jsonl
Writes ``<input>.regrade.json`` next to the input.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from road_agents import audit
from road_agents import planning as P
from road_agents.agents import (
    CLOSURE_INSTRUCTIONS,
    COORDINATOR_INSTRUCTIONS,
    MAINTENANCE_INSTRUCTIONS,
    ClosureSchedule,
    Deps,
    MaintenanceProposal,
    QuarterlyPlan,
    closure_prompt,
    fact_sheet,
    maintenance_prompt,
    numbers_in,
    schedule_dict,
    split_deviations,
)


def replay_call(data: P.PlanningData, deps: Deps, c: dict):
    tool, a = c["tool"], c["args"]
    if tool == "rank_sections":
        return P.rank_sections(data, plan=deps.solver_set, **a)
    if tool == "get_section":
        if c["agent"] == "closure":
            return P.section_details(data, a["section_id"])
        return P.section_details(data, a["section_id"], deps.solver_set, deps.solver.budget)
    if tool == "try_plan":
        p = P.with_solver_comparison(P.solve_budget(data, deps.budget_share, a["add"], a["remove"]), deps.solver)
        return P.plan_summary_text(data, p)
    if tool == "closure_impact":
        return P.closure_report(data, a["section_ids"])
    if tool == "check_schedule":
        return P.schedule_summary_text(P.schedule_report(data, {int(k): v for k, v in a["months"].items()}))
    if tool == "accessibility_loss":
        return P.accessibility_loss_sections(data, a["section_ids"], a["facility"])
    raise ValueError(f"unknown tool {tool}")


def rebuild(data: P.PlanningData, raw: dict) -> tuple[list[float], dict[str, list[float]], dict[str, str]]:
    """Ledger, upstream numbers per agent, and the agents' texts, as in ``run_pipeline``."""
    share = raw["budget_share"]
    solver = P.solve_budget(data, share)
    deps = Deps(data, share, solver)
    led: list[float] = []
    led += numbers_in(MAINTENANCE_INSTRUCTIONS + CLOSURE_INSTRUCTIONS + COORDINATOR_INSTRUCTIONS)
    led += [2022.0, 2023.0, data.hospital_s, data.school_s, data.hospital_s / 60, data.school_s / 60]
    led += numbers_in(maintenance_prompt(deps))
    m_out = raw["maintenance"]["output"]
    proposal = MaintenanceProposal(**m_out) if raw["maintenance"]["ok"] else MaintenanceProposal(deviations=[], rationale="(maintenance agent failed)")
    adds, removes = split_deviations(proposal)
    final = P.with_solver_comparison(P.solve_budget(data, share, adds, removes), solver)
    deps.final_plan = final
    deps.works = P.major_works(data, final.chosen, len(raw["works"]))
    assert deps.works == raw["works"], "works differ from the log"
    prompt, _ = closure_prompt(deps)
    led += numbers_in(prompt)
    schedule = ClosureSchedule(**raw["closure"]["output"]) if raw["closure"]["ok"] else None
    sched_report = P.schedule_report(data, schedule_dict(schedule)) if schedule else None
    led += numbers_in(fact_sheet(deps, proposal, final, schedule, sched_report, agent_text=False))
    for c in raw["calls"]:
        led += numbers_in(replay_call(data, deps, c))
    # numbers the coordinator saw only through earlier agents' own words
    with_text = audit.extract_numbers(fact_sheet(deps, proposal, final, schedule, sched_report, agent_text=True))
    upstream = {"coordinator.": [n.value for n in with_text]}
    plan = QuarterlyPlan(**raw["coordinator"]["output"]) if raw["coordinator"]["ok"] else None
    texts = audit.agent_texts(proposal if raw["maintenance"]["ok"] else None, schedule, plan)
    return led, upstream, texts


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("log", type=Path)
    ap.add_argument("--city", default="belo-horizonte")
    a = ap.parse_args()
    rows = [json.loads(x) for x in a.log.read_text().splitlines() if x.strip()]
    data = P.load_planning_data(a.city)
    out = []
    for r in rows:
        if r["type"] != "run":
            continue
        raw = r["raw"]
        ledger, upstream, texts = rebuild(data, raw)
        strict = audit.audit_text(texts, ledger)
        logged = r["eval"]["text_audit"]
        lenient = audit.audit_text_lenient(texts, ledger, upstream)
        row = {
            "budget_share": r["budget_share"], "run": r["run"],
            "ledger_size": len(ledger), "ledger_size_logged": raw["ledger_size"],
            "strict": f"{strict['grounded']}/{strict['checked']}",
            "strict_logged": f"{logged['grounded']}/{logged['checked']}",
            "with_derived": f"{lenient['grounded_with_derived']}/{lenient['checked']}",
            "counts": lenient["counts"],
            "not_strict": lenient["not_strict"],
            "texts": texts,
            "ledger": sorted(set(ledger)),
        }
        out.append(row)
        print(f"[{r['budget_share']:.0%} run {r['run']}] ledger {len(ledger)} (logged {raw['ledger_size']}); "
              f"strict {row['strict']} (logged {row['strict_logged']}); with derived {row['with_derived']}; {lenient['counts']}",
              flush=True)
    path = a.log.with_suffix(".regrade.json")
    path.write_text(json.dumps(out, indent=2, ensure_ascii=False))
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
