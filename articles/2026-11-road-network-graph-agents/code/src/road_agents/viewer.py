"""Collect the milestone-3 run files into one JSON for the React viewer in `viewer/` (no model, no graph, no re-scoring).

    make viewer                             # this, then the page at http://localhost:5178
    uv run python -m road_agents.viewer     # only viewer/public/data.json and the figures link
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path

CODE = Path(__file__).resolve().parents[2]
RUNS = CODE / "runs"
SECTIONS = CODE / "data" / "belo-horizonte-sections.csv"
FIGURES = CODE.parent / "figures"
OUT = CODE / "viewer" / "public"

ATTRIBUTION = "Road data © OpenStreetMap contributors (ODbL), openstreetmap.org/copyright."
CAPTIONS = {
    "bh-critical-sections.png": "Most critical road sections: top 100 of 19,842 by sampled travel-time betweenness.",
    "bh-pothole-density.png": "Tapa-Buraco pothole requests, Aug 2022 – Jul 2023: distinct locations per km per section, smoothed. "
    "Where repairs are requested, not measured pavement condition. Requests: Prefeitura de Belo Horizonte, BH Digital, CC-BY.",
}
PLAN_KEYS = ("budget", "n_sections", "km", "cost", "budget_used_pct", "value_share_pct", "requests_covered", "requests_covered_pct", "value_vs_solver_pct")
SCHEDULE_KEYS = ("violations", "interaction_nodes", "peak_total_delay_s", "sum_total_delay_s", "months", "conflicting_pairs", "hospital_nodes_lost")
DEVIATION = re.compile(
    r"^- (add|remove) (S\d+) (.*?) \(([\w-]+)\): requests (\d+), condition ([\d.]+), criticality ([\d.]+), value ([\d.]+), cost ([\d.]+)\.", re.M
)


def _rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _json(path: Path):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def _names(path: Path, ids: set[str]) -> dict[str, dict]:
    """Name and road class of the given sections from the cached section table, if it is on disk."""
    if not path.exists():
        return {}
    with path.open(encoding="utf-8", newline="") as f:
        return {r["section_id"]: {"name": r["name"], "highway": r["highway"]} for r in csv.DictReader(f) if r["section_id"] in ids}


def _plan(plan: dict, facts: str, block: str) -> dict:
    """The plan's numbers plus the two descriptive lines of its block in the facts text."""
    out = {k: plan.get(k) for k in PLAN_KEYS}
    text = facts.partition(block)[2].partition("\n\n")[0]
    for key, start in (("length_by_class", "Length by class: "), ("top_roads", "Top roads by value in the plan: ")):
        line = next((x for x in text.splitlines() if x.startswith(start)), None)
        if line:
            out[key] = line[len(start) :].rstrip(".")
    return out


def _message(content: str) -> str:
    """The readable part of a logged validation error."""
    found = re.search(r"'msg': '([^']+)'", content)
    return found.group(1) if found else content.strip('"')[:300]


def _agent(a: dict) -> dict:
    """Status of one agent and what its transcript shows: tool calls made and answers that were rejected."""
    calls = [t for t in a["transcript"] if t["kind"] == "call"]
    rejected = Counter((t["tool"], _message(t["content"])) for t in a["transcript"] if t["kind"] == "retry")
    returns = [t["content"] for t in a["transcript"] if t["kind"] == "return" and t["tool"] != "final_result"]
    return {
        "ok": a["ok"],
        "error": (a["error"] or "").split(". Consider")[0] or None,
        "seconds": a["seconds"],
        "requests": a["requests"],
        "calls": dict(Counter(t["tool"] for t in calls)),
        "distinct_calls": len({(t["tool"], t["args"]) for t in calls}),
        "rejected": [{"tool": tool, "message": message, "times": n} for (tool, message), n in rejected.items()],
        "last_tool_answer": returns[-1] if returns and not a["ok"] else None,
        "output": a["output"],
    }


def _run(row: dict, run_id: str, regrade: dict | None) -> dict:
    raw, ev, facts = row["raw"], row["eval"], row.get("facts", "")
    maintenance = _agent(raw["maintenance"])
    table = {m[1]: m for m in DEVIATION.findall(facts)}
    for d in (maintenance["output"] or {}).get("deviations", []):
        if d["section_id"] in table:
            _, _, name, highway, requests, condition, criticality, value, cost = table[d["section_id"]]
            d.update(name=name, highway=highway, requests=int(requests), condition=float(condition), criticality=float(criticality), value=float(value), cost=float(cost))
    schedules = {k: {f: ev[k].get(f) for f in SCHEDULE_KEYS} for k in ("naive", "heuristic", "agent_schedule") if ev.get(k)}
    out = {
        "id": run_id,
        "model": row["model"],
        "budget_pct": raw["solver"]["budget_share_pct"],
        "run": row["run"],
        "limits": row.get("limits"),
        "seconds_agents": row.get("seconds_agents"),
        "solver": _plan(raw["solver"], facts, "SOLVER PLAN"),
        "final": _plan(raw["final"], facts, "FINAL PLAN"),
        "plan_audit": {k: ev["plan"].get(k) for k in ("adds", "removes", "jaccard_vs_solver")},
        "works": raw["works"],
        "maintenance": maintenance,
        "closure": _agent(raw["closure"]),
        "coordinator": _agent(raw["coordinator"]),
        "schedules": schedules,
        "phase_audit": ev.get("phase_audit"),
        "text_audit": {k: ev["text_audit"].get(k) for k in ("checked", "grounded", "trivial_skipped", "not_found")},
        "ledger_size": raw.get("ledger_size"),
    }
    if regrade:
        out["regrade"] = {k: regrade[k] for k in ("strict", "with_derived", "counts", "not_strict")}
    return out


def _fraction(pairs: list[str]) -> tuple[int, int]:
    """Add up "found/checked" strings."""
    split = [p.split("/") for p in pairs]
    return sum(int(a) for a, _ in split), sum(int(b) for _, b in split)


def _tiles(summary: dict | None, regrade: list | None) -> list[dict]:
    """Headline tiles: counts and ranges over the per-run numbers the summary and regrade files hold."""
    if not summary:
        return []
    runs = [(b["reference"], r) for b in summary.values() for r in b["runs"]]
    n = len(runs)
    value = [r["value_vs_solver_pct"] for _, r in runs]
    cover = [round(r["requests_covered_pct"] - ref["solver_requests_covered_pct"], 2) for ref, r in runs]
    found, checked = _fraction([r["text_numbers_grounded"] for _, r in runs])
    tiles = [
        {"label": "Agent plan value", "value": f"{min(value):.1f}–{max(value):.1f}%", "unit": f"of the solver plan's value, range over {n} runs"},
        {"label": "Request coverage change", "value": f"{min(cover):+.2f} to {max(cover):+.2f}".replace("-", "−"), "unit": "percentage points vs the solver plan"},
        {"label": "Maintenance proposals returned", "value": f"{sum(r['agents_ok']['maintenance'] for _, r in runs)} of {n}", "unit": "pipeline runs"},
        {"label": "Closure schedules completed", "value": f"{sum(r['agents_ok']['closure'] for _, r in runs)} of {n}", "unit": "pipeline runs"},
    ]
    if checked:
        tiles.append({"label": "Prose numbers traced, strict", "value": f"{100 * found / checked:.1f}%", "unit": f"{found} of {checked} found verbatim in tool results"})
    if regrade:
        found, checked = _fraction([r["with_derived"] for r in regrade])
        tiles.append({"label": "Prose numbers traced, lenient", "value": f"{100 * found / checked:.1f}%", "unit": f"{found} of {checked} with notation variants and derived numbers"})
    return tiles


def build(runs: Path = RUNS, name: str = "m3-eval-local", sections: Path = SECTIONS, figures: Path = FIGURES) -> dict:
    """One entry per pipeline run of `<name>.jsonl`; the scripted dry run is added when present."""
    rows = [r for r in _rows(runs / f"{name}.jsonl") if r["type"] == "run"]
    if not rows:
        raise FileNotFoundError(f"no pipeline runs in {runs / name}.jsonl: run `make agents-eval` first (or `make agents-dry`, then `--name m3-eval-scripted`)")
    summary = _json(runs / f"{name}.summary.json")
    regrade = _json(runs / f"{name}.regrade.json")
    graded = {(r["budget_share"], r["run"]): r for r in regrade or []}
    out = [_run(r, f"{r['raw']['solver']['budget_share_pct']:g}-{r['run']}", graded.get((r["budget_share"], r["run"]))) for r in rows]
    if name != "m3-eval-scripted":
        dry = [r for r in _rows(runs / "m3-eval-scripted.jsonl") if r["type"] == "run"]
        out += [_run(r, f"dry-{r['raw']['solver']['budget_share_pct']:g}-{r['run']}", None) for r in dry]
    ids = {i for r in out for i in r["works"]} | {i for r in out for m in r["schedules"].values() for month in m["months"].values() for i in month}
    budgets = {f"{100 * float(share):g}": {k: b.get(k) for k in ("consistency", "mean_seconds_per_pipeline")} for share, b in (summary or {}).items()}
    pngs = sorted(figures.glob("*.png")) if figures.is_dir() else []
    return {
        "source": f"runs/{name}.jsonl",
        "tiles": _tiles(summary, regrade),
        "budgets": budgets,
        "sections": _names(sections, ids),
        "figures": [{"src": f"figures/{p.name}", "caption": CAPTIONS.get(p.name, p.stem), "attribution": ATTRIBUTION} for p in pngs],
        "runs": out,
    }


def write(data: dict, out: Path = OUT, figures: Path = FIGURES) -> Path:
    """Write data.json and link the committed maps next to it (both git-ignored; nothing is copied)."""
    out.mkdir(parents=True, exist_ok=True)
    (out / "data.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    link = out / "figures"
    if link.is_symlink():
        link.unlink()
    if figures.is_dir() and not link.exists():
        link.symlink_to(figures.resolve(), target_is_directory=True)
    return out / "data.json"


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--runs", type=Path, default=RUNS)
    p.add_argument("--name", default="m3-eval-local", help="run file stem in runs/")
    p.add_argument("--out", type=Path, default=OUT)
    a = p.parse_args(argv)
    try:
        data = build(a.runs, a.name)
    except FileNotFoundError as e:
        sys.exit(str(e))
    path = write(data, a.out)
    print(f"{len(data['runs'])} pipeline runs -> {path}", file=sys.stderr)


if __name__ == "__main__":
    main()
