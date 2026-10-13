"""Collect the replay run files into one JSON for the React viewer in `viewer/` (no model, nothing re-run).

    make viewer                                  # this, then the page at http://localhost:5179
    uv run python -m maintenance_agents.viewer   # only viewer/public/data.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
RUNS = ROOT / "runs"
OUT = ROOT / "viewer" / "public"
TAGS = {"v1": "m3", "v2": "m3v2"}  # prompt version -> run tag
TARGETS = {"v1": "replay", "v2": "replay-v2"}
ARMS = ("none", "ungated", "gated")
CLASSES = ("pre_incident", "false_alarm", "near_incident")
DETECTOR = "iforest_resid"  # the detector the replayed episodes come from
CHART_DAYS = 14

_SCORE = re.compile(r"^Detector score that day: (-?[\d.]+)", re.MULTILINE)
_SIGNALS = re.compile(r"^Top residual signals that day \(z\): (.*)\.$", re.MULTILINE)
_CONTEXT = re.compile(r"^Top context signal: (.*)\.$", re.MULTILINE)
_TRACK = re.compile(r"^Track record of .*$", re.MULTILINE)
_SIGNAL = re.compile(r"^(\S+)(?: \((.*)\))? ([+-]?[\d.]+)$")
_MEMORY = re.compile(r"^\d+\. Episode #(\d+), (.*?)\. Similarity [\d.]+, \d+ days ago\.\n   Diagnosis then: (.*?)\n   Outcome: (.*?)$", re.MULTILINE | re.DOTALL)


def _rows(path: Path) -> dict[int, dict]:
    if not path.exists():
        return {}
    return {r["episode_id"]: r for r in map(json.loads, filter(str.strip, path.read_text().splitlines()))}


def _signals(text: str) -> list[dict]:
    """ "sensor_x (label) +1.2; ..." as the prompt printed it -> [{signal, label, z}]."""
    out = []
    for part in text.split("; "):
        m = _SIGNAL.match(part.strip())
        if m:
            out.append({"signal": m[1], "label": m[2] or m[1], "z": float(m[3])})
    return out


def _alarm(row: dict) -> dict:
    """The episode as the prompt stated it at decision time."""
    prompt = row["prompt"]
    score, signals, context = _SCORE.search(prompt), _SIGNALS.search(prompt), _CONTEXT.search(prompt)
    return {
        "id": row["episode_id"],
        "turbine": row["turbine_id"],
        "start": row["start"],
        "decision_time": row["decision_time"][:16],
        "score": float(score[1].rstrip(".")) if score else None,
        "top_group": row["top_group"],
        "detector_component": row["detector_component"],
        "signals": _signals(signals[1]) if signals else [],
        "context_signal": context[1] if context else None,
    }


def _arm(row: dict) -> dict:
    """One arm's recorded run of one episode: tools, memory as shown in the prompt, diagnosis."""
    shown = {}
    for m in _MEMORY.finditer(row["prompt"]):
        outcome, _, lesson = m[4].partition(" Lesson: ")
        shown[int(m[1])] = {"summary": m[2], "diagnosis_then": m[3].rstrip("."), "outcome": outcome.rstrip("."), "lesson": lesson or None}
    track = _TRACK.search(row["prompt"])
    usage = row["usage"]
    return {
        "diagnosis": row["diagnosis"],
        "error": row["error"],
        "tools": usage["tools_called"],
        "requests": usage["requests"],
        "input_tokens": usage["input_tokens"],
        "output_tokens": usage["output_tokens"],
        "seconds": row["seconds"],
        "memories": [m | shown.get(m["episode_id"], {}) for m in row["memories"]],
        "memories_visible": row["memories_visible"],
        "gate_rejections": row["gate_rejections"],
        "track_record": track[0] if track else None,
    }


def _summary(runs: Path, tag: str) -> tuple[dict, dict]:
    """The numbers `replay` already wrote for one run tag, and its per-episode scoring rows by arm."""
    path = runs / f"{tag}_summary.json"
    if not path.exists():
        return {}, {}
    s = json.loads(path.read_text())
    arms, scored = {}, {}
    for arm, a in s["arms"].items():
        arms[arm] = {
            "episodes": a["episodes"],
            "inspect": sum(a.get(f"actions_{k}", {}).get("inspect", 0) for k in CLASSES),
            "component_ok": a["component_accuracy_pre_incident"],
            "ignore_on_false_alarm": a["ignore_on_false_alarm"],
            "mean_memories": a.get("mean_memories_in_prompt"),
        }
        scored[arm] = {p["episode_id"]: p for p in a.get("per_episode", [])}
    classes = {}
    for p in next(iter(scored.values()), {}).values():
        classes[p["klass"]] = classes.get(p["klass"], 0) + 1
    out = {"model": s.get("model"), "horizon_days": s.get("horizon_days"), "policies": s.get("policies", {}), "classes": classes, "arms": arms}
    return out, scored


def _table(path: Path) -> dict[int, dict]:
    """An episode CSV of `make detect`, the replayed detector's rows by episode id."""
    if not path.exists():
        return {}
    df = pd.read_csv(path)
    df = df[df["detector"] == DETECTOR].astype(object).where(lambda d: d.notna(), None)
    return {int(r["episode_id"]): r for r in df.to_dict("records")}


def _series(daily: pd.DataFrame | None, alarm: dict) -> dict | None:
    """Daily residual z of the top signal, the last days up to the first alarm day (nothing later)."""
    if daily is None or not alarm["signals"]:
        return None
    top, start = alarm["signals"][0], pd.Timestamp(alarm["start"])
    col = f"z_{top['signal']}"
    if col not in daily.columns:
        return None
    d = daily[(daily["turbine_id"] == alarm["turbine"]) & (daily.index <= start) & (daily.index > start - pd.Timedelta(days=CHART_DAYS))].sort_index()
    if len(d) < 2:
        return None
    return {"signal": top["signal"], "label": top["label"], "days": [f"{x:%Y-%m-%d}" for x in d.index], "z": [None if pd.isna(v) else round(float(v), 2) for v in d[col]]}


def _hindsight(episode_id: int, labels: dict, episodes: dict, scored: dict) -> dict:
    """What became known after the decision: scoring class, the incident that followed, how the alarm went on."""
    out: dict = {"scored": {v: {a: s[episode_id] for a, s in arms.items() if episode_id in s} for v, arms in scored.items()}}
    klass = next((p["klass"] for arms in out["scored"].values() for p in arms.values()), None)
    if klass:
        out["klass"] = klass
    if lab := labels.get(episode_id):
        days = lab["days_before_incident"]
        out |= {"days_before_incident": None if days is None else int(days), "incident_component": lab["incident_component"]}
    if ep := episodes.get(episode_id):
        out |= {"end": ep["end"], "n_days": ep["n_days"], "peak_score": ep["peak_score"]}
    return out


def build(runs: Path = RUNS) -> dict:
    """One entry per replayed episode, in decision-time order, with every recorded arm and prompt version."""
    rows = {v: {a: _rows(runs / f"{tag}_{a}.jsonl") for a in ARMS} for v, tag in TAGS.items()}
    rows = {v: {a: r for a, r in arms.items() if r} for v, arms in rows.items()}
    rows = {v: arms for v, arms in rows.items() if arms}
    if not rows:
        raise FileNotFoundError(f"no {runs}/m3_<arm>.jsonl: run `make replay` first (after `make data` and `make detect`)")
    summaries, scored = {}, {}
    for v in rows:
        summaries[v], scored[v] = _summary(runs, TAGS[v])
    labels, table = _table(runs / "m2_episodes_eval.csv"), _table(runs / "m2_episodes.csv")
    scores = runs / "m2_daily_scores.parquet"
    daily = pd.read_parquet(scores) if scores.exists() else None
    first = {i: r for arms in reversed(list(rows.values())) for a in reversed(list(arms)) for i, r in arms[a].items()}
    episodes = []
    for i, row in sorted(first.items(), key=lambda x: (x[1]["decision_time"], x[0])):
        alarm = _alarm(row)
        if series := _series(daily, alarm):
            alarm["series"] = series
        alarm["runs"] = {v: {a: _arm(r[i]) for a, r in arms.items() if i in r} for v, arms in rows.items()}
        alarm["hindsight"] = _hindsight(i, labels, table, scored)
        episodes.append(alarm)
    data = {"versions": list(rows), "targets": TARGETS, "summary": summaries, "episodes": episodes}
    m2 = runs / "m2_eval.json"
    if m2.exists():
        inc = json.loads(m2.read_text())["incidents"]
        data["logbook"] = {"rows": inc["logbook_rows"], "incidents": inc["incidents"]}
    return data


def write(data: dict, out: Path = OUT) -> Path:
    """Write data.json (git-ignored)."""
    out.mkdir(parents=True, exist_ok=True)
    path = out / "data.json"
    path.write_text(json.dumps(data, ensure_ascii=False))
    return path


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--runs", type=Path, default=RUNS)
    p.add_argument("--out", type=Path, default=OUT)
    a = p.parse_args(argv)
    try:
        data = build(a.runs)
    except FileNotFoundError as e:
        sys.exit(str(e))
    path = write(data, a.out)
    print(f"{len(data['episodes'])} episodes, prompts {', '.join(data['versions'])} -> {path}", file=sys.stderr)


if __name__ == "__main__":
    main()
