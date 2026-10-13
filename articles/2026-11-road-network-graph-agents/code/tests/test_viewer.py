import json

import pytest

from road_agents.viewer import build, write

FACTS = """SOLVER PLAN
Plan at 5% of the total repair cost.
Length by class: primary 2.0 km.
Top roads by value in the plan: Avenida A (value 0.5).

FINAL PLAN (after deviations)
Length by class: primary 1.0 km, residential 1.0 km.

DEVIATIONS
- add S00002 Rua B (residential): requests 50, condition 1.000, criticality 0.0010, value 0.00100, cost 10.0. Agent's reason: many requests.
"""


def _agent(ok=True, output=None, error=None, transcript=()):
    return {"ok": ok, "seconds": 1.0, "requests": 2, "error": error, "output": output, "transcript": list(transcript)}


def _plan(n, value, vs=None):
    return {"budget_share_pct": 5.0, "budget": 100.0, "n_sections": n, "km": 2.0, "cost": 99.0, "budget_used_pct": 99.0, "value_share_pct": value, "requests_covered": 7, "requests_covered_pct": 1.5, "value_vs_solver_pct": vs}


def _row(run, closure):
    schedule = {"violations": 0, "interaction_nodes": 0, "peak_total_delay_s": 5.0, "sum_total_delay_s": 9.0, "months": {"1": ["S00001"]}, "conflicting_pairs": {}, "hospital_nodes_lost": {"1": 0}}
    maintenance = _agent(output={"deviations": [{"section_id": "S00002", "action": "add", "reason": "many requests"}], "rationale": "r"})
    coordinator = _agent(output={"summary": "s", "trade_offs": [], "risks": []})
    raw = {"solver": _plan(2, 60.0), "final": _plan(2, 57.0, 95.0), "works": ["S00001"], "maintenance": maintenance, "closure": closure, "coordinator": coordinator, "ledger_size": 12}
    audit = {"checked": 4, "grounded": 3, "trivial_skipped": 0, "not_found": [{"where": "coordinator.summary", "number": "9.9", "context": "c"}]}
    ev = {"plan": {"adds": ["S00002"], "removes": [], "jaccard_vs_solver": 0.5}, "naive": schedule, "heuristic": schedule, "text_audit": audit}
    return {"type": "run", "budget_share": 0.05, "run": run, "model": "local", "limits": {"maintenance": 1, "closure": 1, "coordinator": 1}, "seconds_agents": 3.0, "raw": raw, "facts": FACTS, "eval": ev}


def _fixture(tmp_path):
    runs, figures = tmp_path / "runs", tmp_path / "figures"
    runs.mkdir()
    figures.mkdir()
    (figures / "map.png").write_bytes(b"png")
    retry = {"kind": "retry", "tool": "check_schedule", "content": "\"unknown section ids: ['S010128']\""}
    call = {"kind": "call", "tool": "check_schedule", "args": "{}"}
    failed = _agent(False, error="UnexpectedModelBehavior: Tool 'check_schedule' exceeded max retries count of 3. Consider raising it", transcript=[call, retry, call, retry])
    rows = [{"type": "reference", "budget_share": 0.05, "run": None}, _row(0, failed), _row(1, _agent(output={"phases": [], "flags": [], "rationale": "ok"}))]
    (runs / "m3-eval-local.jsonl").write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    (tmp_path / "sections.csv").write_text("section_id,name,highway\nS00001,Avenida A,primary\nS00009,Rua Z,residential\n", encoding="utf-8")
    return runs, figures


def test_build_follows_each_run_and_omits_missing_summaries(tmp_path):
    runs, figures = _fixture(tmp_path)
    data = build(runs, sections=tmp_path / "sections.csv", figures=figures)
    first, second = data["runs"]
    assert [r["id"] for r in data["runs"]] == ["5-0", "5-1"]
    assert first["solver"]["top_roads"] == "Avenida A (value 0.5)" and first["final"]["length_by_class"] == "primary 1.0 km, residential 1.0 km"
    assert first["maintenance"]["output"]["deviations"][0] == {"section_id": "S00002", "action": "add", "reason": "many requests", "name": "Rua B", "highway": "residential", "requests": 50, "condition": 1.0, "criticality": 0.001, "value": 0.001, "cost": 10.0}
    assert first["closure"]["error"] == "UnexpectedModelBehavior: Tool 'check_schedule' exceeded max retries count of 3"
    assert first["closure"]["rejected"] == [{"tool": "check_schedule", "message": "unknown section ids: ['S010128']", "times": 2}]
    assert first["closure"]["calls"] == {"check_schedule": 2} and first["closure"]["distinct_calls"] == 1
    assert second["closure"]["ok"] and "agent_schedule" not in second["schedules"] and "regrade" not in second
    assert data["sections"] == {"S00001": {"name": "Avenida A", "highway": "primary"}}
    assert data["figures"][0]["src"] == "figures/map.png" and "OpenStreetMap contributors" in data["figures"][0]["attribution"]
    assert data["tiles"] == [] and data["budgets"] == {}


def test_tiles_and_regrade_come_from_the_summary_files(tmp_path):
    runs, figures = _fixture(tmp_path)
    run = {"agents_ok": {"maintenance": True, "closure": False, "coordinator": True}, "value_vs_solver_pct": 95.0, "requests_covered_pct": 1.5, "text_numbers_grounded": "3/4"}
    summary = {"0.05": {"reference": {"solver_requests_covered_pct": 1.0}, "runs": [run, {**run, "value_vs_solver_pct": 100.0, "agents_ok": {"maintenance": True, "closure": True}}], "consistency": {"runs": 2}}}
    (runs / "m3-eval-local.summary.json").write_text(json.dumps(summary), encoding="utf-8")
    regrade = [{"budget_share": 0.05, "run": 0, "strict": "3/4", "with_derived": "4/4", "counts": {"strict": 3, "notation": 1}, "not_strict": [], "ledger": [1.0]}]
    (runs / "m3-eval-local.regrade.json").write_text(json.dumps(regrade), encoding="utf-8")
    data = build(runs, sections=tmp_path / "none.csv", figures=figures)
    tiles = {t["label"]: t["value"] for t in data["tiles"]}
    assert tiles == {"Agent plan value": "95.0–100.0%", "Request coverage change": "+0.50 to +0.50", "Maintenance proposals returned": "2 of 2", "Closure schedules completed": "1 of 2", "Prose numbers traced, strict": "75.0%", "Prose numbers traced, lenient": "100.0%"}
    assert data["runs"][0]["regrade"] == {"strict": "3/4", "with_derived": "4/4", "counts": {"strict": 3, "notation": 1}, "not_strict": []}
    assert "regrade" not in data["runs"][1] and data["budgets"]["5"]["consistency"] == {"runs": 2} and data["sections"] == {}


def test_missing_run_file_names_the_make_target_and_write_links_the_figures(tmp_path):
    with pytest.raises(FileNotFoundError, match="make agents-eval"):
        build(tmp_path / "nowhere")
    runs, figures = _fixture(tmp_path)
    out = tmp_path / "public"
    for _ in range(2):  # a second run replaces the link
        path = write(build(runs, sections=tmp_path / "sections.csv", figures=figures), out, figures)
    assert len(json.loads(path.read_text(encoding="utf-8"))["runs"]) == 2
    assert (out / "figures").is_symlink() and (out / "figures" / "map.png").read_bytes() == b"png"
