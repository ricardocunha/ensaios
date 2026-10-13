"""Collect the run files into one JSON for the React viewer in `viewer/` (no model, no network).

    make viewer                              # this, then the page at http://localhost:5177
    uv run python -m disaster_risk.viewer    # only viewer/public/data.json
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import basin, dataset, fusion
from .backtest import RUNS_DIR
from .signals import Signal
from .sources._http import DATA_DIR

OUT = Path("viewer/public")
HORIZON = timedelta(hours=24)
MIN_HOURS = 12  # fewer hours with a reading than this and "not reached" cannot be said
ALERT_FILES = {"pt": "alerts_pt", "en": "alerts_queued"}


def _utc(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(timezone.utc)


def _z(t: datetime | None) -> str | None:
    return None if t is None else f"{t:%Y-%m-%dT%H:%MZ}"


def _num(text: str) -> float | None:
    return float(text) if text else None


def _json(path: Path):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def _jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _signals(path: Path) -> dict[datetime, list[Signal]]:
    """The replay's signals by hour, as written by `make backtest`."""
    out: dict[datetime, list[Signal]] = {}
    if not path.exists():
        return out
    with open(path, newline="", encoding="utf-8") as fh:
        for d in csv.DictReader(fh):
            t = _utc(d["time"])
            out.setdefault(t, []).append(Signal(
                d["source"], d["station"], d["place"], t, _utc(d["observed_at"]) if d["observed_at"] else None,
                _num(d["value"]), d["unit"], _num(d["likelihood_ratio"]), _num(d["freshness_h"]),
                float(d["reliability"]), d["status"], d["kind"], d["reason"], json.loads(d["details"] or "{}"),
            ))
    return out


def _maps(signals: dict[datetime, list[Signal]]) -> list[dict]:
    """Each Copernicus EMS flood map with the first replay hour at which it was visible."""
    seen: dict[str, dict] = {}
    for t in sorted(signals):
        for s in signals[t]:
            if s.kind == "label" and s.station not in seen:
                seen[s.station] = {"id": s.station, "place": s.place, "ha": s.value, "visible_from": _z(t), "note": s.reason}
    return list(seen.values())


def _levels(path: Path) -> dict[str, list[tuple[datetime, datetime | None, float | None]]]:
    """Per ANA station: (hour end, reading time, level in cm) from the hourly dataset."""
    out: dict[str, list] = {}
    if path.exists():
        for r in dataset.read_csv(path):
            if r.source == "ana":
                out.setdefault(r.station, []).append((r.hour_end, r.level_time, r.level_cm))
    return {k: sorted(v, key=lambda x: x[0]) for k, v in out.items()}


def _next_24h(rows: list, t: datetime, flood_cm: float) -> dict:
    """Hindsight: the gauge's hourly readings in (t, t + 24 h]."""
    got = [(when, cm) for hour, when, cm in rows if t < hour <= t + HORIZON and cm is not None]
    out: dict = {"hours_with_reading": len(got)}
    if got:
        when, cm = max(got, key=lambda x: x[1])
        out |= {"max_cm": cm, "max_at": _z(when)}
    crossed = next((when for when, cm in got if cm >= flood_cm), None)
    out["reached_at"] = _z(crossed)
    out["verdict"] = "reached" if crossed else ("not_reached" if len(got) >= MIN_HOURS else "unknown")
    return out


def _alerts(runs: Path) -> dict[tuple[str, str], dict]:
    """Alert texts by (place, local time), then language, one entry per output mode."""
    out: dict[tuple[str, str], dict] = {}
    for lang, name in ALERT_FILES.items():
        for r in _jsonl(runs / "m3" / f"{name}.jsonl"):
            a = r.get("alert")
            if not a:
                continue
            audit = a["audit"]
            entry = out.setdefault((r["place"], r["time_local"]), {"kind": r["kind"], "texts": {}})
            entry["texts"].setdefault(lang, []).append({
                "mode": r["output_mode"] + ("+audit_retry" if r.get("audit_retry") else ""),
                "headline": a["headline"], "explanation": a["explanation"], "silent_gauges": a["silent_gauges"],
                "audit_ok": audit["ok"], "numbers_checked": audit["numbers_checked"],
                "problems": {k: v for k, v in audit.items() if isinstance(v, list) and v},
                "requests": r.get("requests"), "seconds": r.get("seconds"),
            })
    return out


def _llm(runs: Path) -> dict[tuple[str, datetime], list[dict]]:
    """LLM-only fusion answers by (place, hour), from the pre-registered hour set."""
    hours = _json(runs / "m4" / "llm_fusion_hours.json")
    if not hours:
        return {}
    by_id = {h["id"]: (h["place"], _utc(h["t"])) for h in hours["hours"]}
    out: dict[tuple[str, datetime], list[dict]] = {}
    for r in _jsonl(runs / "m4" / "llm_fusion_runs.jsonl"):
        if r["id"] in by_id and r.get("probability") is not None:
            out.setdefault(by_id[r["id"]], []).append({k: r[k] for k in ("sample", "probability", "level", "reason")})
    return out


def _summary(runs: Path, m3: dict) -> dict:
    """Headline numbers already written by `make evaluate`, `make alerts-*` and `make llm-fusion-score`."""
    out: dict = {"event": {}}
    for place, e in m3.get("event", {}).items():
        out["event"][place] = {
            k: _z(_utc(e[k])) if e.get(k) else None for k in ("crossing", "attention", "alert_onset", "handset_alert_onset")
        } | {k: e.get(k) for k in ("lead_h", "handset_lead_h")}
    full = m3.get("configs", {}).get("full", {})
    test = full.get("false_alarms", {}).get("TEST")
    if test:
        out["false_alarms_test"] = {k: test["total"][k] for k in ("episodes", "hits", "false", "unverifiable")} | {
            "per_place_year": test["false_per_place_year"], "place_years": test["place_years"]}
    cal = full.get("calibration", {}).get("TEST")
    if cal:
        out["calibration_test"] = {k: cal[k] for k in ("n", "positives", "brier", "brier_climatology", "bss")}
    for lang, name in ALERT_FILES.items():
        s = _json(runs / "m3" / f"{name}_summary.json")
        if s:
            out.setdefault("alert_audit", {})[lang] = {m: {"runs": v["runs"], "audit_ok": v["audit_ok"]} for m, v in s.items()}
    llm = _json(runs / "m4" / "llm_fusion_summary.json")
    if llm:
        out["llm_fusion"] = {"brier": llm["brier"], "leads": llm["leads"], "hours": llm["hours"]}
    return out


def build(runs: Path = RUNS_DIR, data: Path = DATA_DIR) -> dict:
    """One entry per place and replay hour from `runs/m3/fused_2024.csv`; other files are joined when present."""
    fused, m3 = runs / "m3" / "fused_2024.csv", _json(runs / "m3" / "summary.json")
    if not fused.exists() or m3 is None:
        raise FileNotFoundError(f"no {fused} or summary.json next to it: run `make evaluate` first")
    signals = _signals(runs / "signals.csv")
    levels = _levels(dataset.cache_path(data))
    thresholds = _json(data / "cache" / "level_thresholds.json") or {}
    alerts, llm = _alerts(runs), _llm(runs)
    # the per-signal breakdown is not stored for every hour: fusion.fuse reads it back from the signals
    cfg = fusion.FusionConfig("full", lr_table={k: v["lr"] for k, v in m3["lr_table"].items()})

    places: dict[str, dict] = {}
    with open(fused, newline="", encoding="utf-8") as fh:
        for d in csv.DictReader(fh):
            pl = fusion.PLACES[d["place"]]
            flood = basin.FLOOD_LEVEL_CM[pl.gauge]
            prior = m3["priors"][pl.name]["prior"]
            place = places.setdefault(pl.name, {
                "name": pl.name, "gauge": pl.gauge, "flood_cm": flood, "prior": prior, "signals": [], "hours": [],
            })
            t = _utc(d["time_utc"])
            now = {(s.source, s.station): s for s in signals.get(t, [])}
            rows = []
            for c in fusion.fuse(pl, t, now.values(), prior, cfg).contributions:
                head = {"source": c.source, "station": c.station, "place": c.station_place, "role": c.role, "weight": c.weight}
                if head not in place["signals"]:
                    place["signals"].append(head)
                details = now[c.source, c.station].details
                extra = details.get("rise_6h_cm") if c.source == "ana_level" else details.get("acc72_mm")
                rows.append([place["signals"].index(head), c.status, c.value, c.freshness_h, extra, c.handset_lr,
                             round(c.likelihood_ratio, 3), c.reliability, round(c.log_odds, 3), c.reason])
            own = levels.get(pl.gauge, [])
            hour = {
                "t": _z(t), "p": float(d["probability"]), "log_odds": float(d["log_odds"]), "level": d["level"],
                "silent": d["silent_gauges"].split() if d["silent_gauges"] else [],
                "cm": next((cm for h, _, cm in own if h == t), None), "signals": rows,
            }
            if own:
                hour["next_24h"] = _next_24h(own, t, flood)
            if (pl.name, d["time_local"]) in alerts:
                hour["alert"] = alerts[pl.name, d["time_local"]]
            if (pl.name, t) in llm:
                hour["llm"] = sorted(llm[pl.name, t], key=lambda r: r["sample"])
            place["hours"].append(hour)

    names = {k: v[0] for k, v in basin.ANA_STATIONS.items()} | basin.INMET_STATIONS
    stations = {
        code: {"name": name, "place": basin.STATION_PLACE.get(code, ""), "flood_cm": basin.FLOOD_LEVEL_CM.get(code)}
        | {q: thresholds[code][q] for q in ("p90", "p99") if code in thresholds}
        for code, name in names.items()
    }
    return {
        "levels": [list(x) for x in fusion.LEVELS], "silent_after_h": fusion.SILENT_AFTER_H, "utc_offset_h": -3,
        "summary": _summary(runs, m3), "stations": stations, "maps": _maps(signals), "places": list(places.values()),
    }


def write(data: dict, out: Path = OUT) -> Path:
    """Write data.json (git-ignored)."""
    out.mkdir(parents=True, exist_ok=True)
    path = out / "data.json"
    path.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--runs", type=Path, default=RUNS_DIR)
    p.add_argument("--data", type=Path, default=DATA_DIR)
    p.add_argument("--out", type=Path, default=OUT)
    a = p.parse_args(argv)
    try:
        data = build(a.runs, a.data)
    except FileNotFoundError as e:
        sys.exit(str(e))
    path = write(data, a.out)
    hours = sum(len(pl["hours"]) for pl in data["places"])
    print(f"{len(data['places'])} places, {hours} place-hours -> {path} ({path.stat().st_size / 1e6:.1f} MB)", file=sys.stderr)


if __name__ == "__main__":
    main()
