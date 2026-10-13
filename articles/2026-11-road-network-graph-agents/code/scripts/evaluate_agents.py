"""Milestone 3 evaluation: agent pipeline vs. pure solver, per budget share,
evaluated deterministically (``road_agents.audit``). Rows are appended to a
JSONL file; finished (budget, run) pairs are skipped on restart.

Usage:
    nice uv run python scripts/evaluate_agents.py --model scripted          # no LLM, dry run
    nice uv run python scripts/evaluate_agents.py --model local --runs 3    # Qwen3-8B via mlx-lm
    nice uv run python scripts/evaluate_agents.py --model local --runs 1 --budgets 0.10 \\
        --out runs/m3-smoke.jsonl --limits 6 6 2                            # smoke
"""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from statistics import mean

os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")
from pydantic_ai.models.function import FunctionModel  # noqa: E402

from road_agents import audit
from road_agents.agents import N_MAJOR_WORKS, local_model, model_settings, result_json, run_pipeline
from road_agents.planning import load_planning_data
from road_agents.scripted import scripted_agent

RUNS = Path(__file__).resolve().parents[1] / "runs"


def read_rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def append(path: Path, row: dict) -> None:
    with path.open("a") as f:
        f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")


def summarize(rows: list[dict]) -> dict:
    out: dict = {}
    refs = {r["budget_share"]: r for r in rows if r["type"] == "reference"}
    for share in sorted({r["budget_share"] for r in rows}):
        runs = sorted((r for r in rows if r["type"] == "run" and r["budget_share"] == share), key=lambda r: r["run"])
        evs = [r["eval"] for r in runs]
        ref = refs.get(share, {}).get("reference")
        b: dict = {"reference": None if ref is None else {
            "solver_value_share_pct": ref["plan"]["value_share_pct"],
            "solver_budget_used_pct": ref["plan"]["budget_used_pct"],
            "solver_requests_covered_pct": ref["plan"]["requests_covered_pct"],
            "naive": {k: ref["naive"][k] for k in ("violations", "interaction_nodes", "peak_total_delay_s")},
            "heuristic": {k: ref["heuristic"][k] for k in ("violations", "interaction_nodes", "peak_total_delay_s")},
        }}
        per_run = []
        for r, e in zip(runs, evs):
            raw = r["raw"]
            pa = e.get("phase_audit", {})
            ta = e["text_audit"]
            per_run.append({
                "run": r["run"],
                "agents_ok": e["agents_ok"],
                "value_share_pct": e["plan"]["value_share_pct"],
                "value_vs_solver_pct": e["plan"]["value_vs_solver_pct"],
                "budget_used_pct": e["plan"]["budget_used_pct"],
                "requests_covered_pct": e["plan"]["requests_covered_pct"],
                "adds": len(e["plan"]["adds"]),
                "removes": len(e["plan"]["removes"]),
                "agent_violations": e.get("agent_schedule", {}).get("violations"),
                "agent_peak_delay_s": e.get("agent_schedule", {}).get("peak_total_delay_s"),
                "naive_violations": e["naive"]["violations"],
                "heuristic_violations": e["heuristic"]["violations"],
                "heuristic_peak_delay_s": e["heuristic"]["peak_total_delay_s"],
                "phase_fields_ok": f"{pa.get('phase_fields_ok', 0)}/{pa.get('phase_fields', 0)}",
                "flags_ok": f"{pa.get('flags_ok', 0)}/{len(pa.get('flags', []))}",
                "flags_missed": len(pa.get("flags_missed", [])),
                "text_numbers_grounded": f"{ta['grounded']}/{ta['checked']}",
                "requests": {k: raw[k]["requests"] for k in ("maintenance", "closure", "coordinator")},
                "seconds": {k: raw[k]["seconds"] for k in ("maintenance", "closure", "coordinator")},
                "errors": {k: raw[k]["error"] for k in ("maintenance", "closure", "coordinator") if raw[k]["error"]},
            })
        b["runs"] = per_run
        if len(runs) > 1:
            b["consistency"] = audit.consistency(evs, [r["raw"] for r in runs])
        if per_run:
            b["mean_seconds_per_pipeline"] = mean(sum(p["seconds"].values()) for p in per_run)
        out[str(share)] = b
    return out


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--city", default="belo-horizonte")
    p.add_argument("--model", choices=["local", "scripted"], default="scripted")
    p.add_argument("--budgets", type=float, nargs="+", default=[0.05, 0.10, 0.20])
    p.add_argument("--runs", type=int, default=3)
    p.add_argument("--works", type=int, default=N_MAJOR_WORKS)
    p.add_argument("--limits", type=int, nargs=3, default=[12, 14, 4], metavar=("MAINT", "CLOSURE", "COORD"),
                   help="request limits per agent")
    p.add_argument("--temperature", type=float, default=0.7)
    p.add_argument("--out", type=Path, default=None)
    a = p.parse_args()
    RUNS.mkdir(exist_ok=True)
    out = a.out or RUNS / f"m3-eval-{a.model}.jsonl"
    summary_path = out.with_suffix(".summary.json")

    t = time.perf_counter()
    data = load_planning_data(a.city)
    print(f"data loaded in {time.perf_counter() - t:.1f} s", flush=True)
    if a.model == "local":
        model, settings = local_model(), model_settings(a.temperature)
    else:
        model, settings = FunctionModel(scripted_agent), {}
    limits = dict(zip(["maintenance", "closure", "coordinator"], a.limits))

    rows = read_rows(out)
    done = {(r["budget_share"], r.get("run")) for r in rows}
    for share in a.budgets:
        if (share, None) not in done:
            t = time.perf_counter()
            ref = audit.solver_reference(data, share, a.works)
            row = {"type": "reference", "budget_share": share, "run": None, "seconds": round(time.perf_counter() - t, 1), "reference": ref}
            append(out, row)
            rows.append(row)
            print(f"[{share:.0%}] reference in {row['seconds']} s: naive violations {ref['naive']['violations']}, "
                  f"heuristic {ref['heuristic']['violations']}", flush=True)
        for run in range(a.runs):
            if (share, run) in done:
                continue
            t = time.perf_counter()
            r = run_pipeline(data, share, model=model, settings=settings, limits=limits, n_works=a.works)
            t_agents = time.perf_counter() - t
            ev = audit.evaluate_run(data, r)
            row = {"type": "run", "budget_share": share, "run": run, "model": a.model, "temperature": a.temperature,
                   "limits": limits, "seconds_total": round(time.perf_counter() - t, 1), "seconds_agents": round(t_agents, 1),
                   "raw": result_json(r), "facts": r.facts, "eval": ev}
            append(out, row)
            rows.append(row)
            print(f"[{share:.0%} run {run}] {row['seconds_agents']} s agents; ok={ev['agents_ok']} "
                  f"value {ev['plan']['value_share_pct']}% (solver {ev['plan']['solver_value_share_pct']}%), "
                  f"violations agent {ev.get('agent_schedule', {}).get('violations')} / naive {ev['naive']['violations']} "
                  f"/ heuristic {ev['heuristic']['violations']}", flush=True)
            summary_path.write_text(json.dumps(summarize(rows), indent=2, ensure_ascii=False, default=str))
    s = summarize(rows)
    summary_path.write_text(json.dumps(s, indent=2, ensure_ascii=False, default=str))
    print(json.dumps(s, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
