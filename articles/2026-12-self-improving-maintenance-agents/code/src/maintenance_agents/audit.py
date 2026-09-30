"""Audit CARE Wind Farm A + EDP logbooks: alignment, coverage, labels.

    uv run python -m maintenance_agents.audit            # prints, writes runs/audit.json
"""

from __future__ import annotations

import itertools
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .data import FARM_A_TURBINES, META_COLUMNS, fault_events, read_dataset, read_edp_logbook, read_event_info, turbine_series
from .download import DATA_ROOT

RUNS_DIR = DATA_ROOT.parent / "runs"


def overlap_agreement(a: pd.DataFrame, b: pd.DataFrame) -> tuple[int, float]:
    """Rows shared by two files of one turbine, and the share of equal sensor values."""
    a, b = a.set_index("time_stamp"), b.set_index("time_stamp")
    idx = a.index.intersection(b.index)
    cols = [c for c in a.columns if c not in META_COLUMNS and c != "source_event_id"]
    if len(idx) == 0:
        return 0, float("nan")
    x = a.loc[idx, cols].to_numpy(float)
    y = b.loc[idx, cols].to_numpy(float)
    return len(idx), float(np.isclose(x, y, equal_nan=True).mean())


def alignment_report(edp_calendar: bool = True) -> list[dict]:
    events = read_event_info("A", edp_calendar=edp_calendar)
    out = []
    for asset_id, grp in events.groupby("asset_id"):
        frames = {e: read_dataset("A", e, edp_calendar=edp_calendar) for e in grp["event_id"]}
        for e1, e2 in itertools.combinations(sorted(frames), 2):
            n, agree = overlap_agreement(frames[e1], frames[e2])
            if n:
                out.append({"asset_id": int(asset_id), "a": e1, "b": e2, "overlap_rows": n, "agreement": round(agree, 4)})
    return out


def coverage_report() -> list[dict]:
    rows = []
    for asset_id, turbine in FARM_A_TURBINES.items():
        s = turbine_series(asset_id)
        idx = s.index
        expected = int((idx.max() - idx.min()) / pd.Timedelta(minutes=10)) + 1
        gaps = idx.to_series().diff()
        big = gaps[gaps > pd.Timedelta(days=1)]
        status = s["status_type_id"].value_counts(normalize=True).round(4)
        rows.append(
            {
                "asset_id": asset_id,
                "turbine_id": turbine,
                "start": str(idx.min()),
                "end": str(idx.max()),
                "rows": len(s),
                "expected_rows": expected,
                "missing_share": round(1 - len(s) / expected, 4),
                "gaps_over_1_day": [(str(t - g), str(t), str(g)) for t, g in big.items()],
                "status_share": {int(k): float(v) for k, v in status.items()},
            }
        )
    return rows


def status_near_faults(faults: pd.DataFrame, before=pd.Timedelta(days=7), after=pd.Timedelta(days=7)) -> list[dict]:
    """Share of 'service'/'downtime' status around each fault: is status leaking the label?"""
    out = []
    cache = {}
    for _, f in faults.iterrows():
        s = cache.setdefault(f.asset_id, turbine_series(int(f.asset_id)))
        pre = s.loc[f.fault_time - before : f.fault_time, "status_type_id"]
        post = s.loc[f.fault_time : f.fault_time + after, "status_type_id"]
        out.append(
            {
                "fault_id": int(f.fault_id),
                "turbine_id": f.turbine_id,
                "fault_time": str(f.fault_time),
                "pre_rows": len(pre),
                "pre_non_normal_share": round(float(pre.isin([3, 4]).mean()), 3) if len(pre) else None,
                "post_non_normal_share": round(float(post.isin([3, 4]).mean()), 3) if len(post) else None,
            }
        )
    return out


def label_summary(faults: pd.DataFrame) -> dict:
    care = read_event_info("A")
    gaps = (
        faults.sort_values("fault_time")
        .groupby("turbine_id")["fault_time"]
        .apply(lambda t: t.diff().dt.total_seconds().div(86400).dropna().round(1).tolist())
        .to_dict()
    )
    return {
        "edp_faults_total": len(faults),
        "edp_faults_by_year": faults["fault_time"].dt.year.value_counts().sort_index().to_dict(),
        "edp_faults_by_component": faults["component"].value_counts().to_dict(),
        "edp_faults_by_turbine": faults["turbine_id"].value_counts().sort_index().to_dict(),
        "edp_faults_with_care_event": int(faults["care_event_id"].notna().sum()),
        "days_between_faults_same_turbine": gaps,
        "care_events_by_label": care["event_label"].value_counts().to_dict(),
        "care_anomaly_components": care.loc[care.event_label == "anomaly", "component"].value_counts().to_dict(),
        "care_anomaly_window_days": care.loc[care.event_label == "anomaly"]
        .assign(d=lambda d: ((d.event_end - d.event_start).dt.total_seconds() / 86400).round(2))
        .set_index("event_id")["d"]
        .to_dict(),
    }


def other_farms_summary() -> dict:
    out = {}
    for farm in ("B", "C"):
        try:
            ev = read_event_info(farm, edp_calendar=False)
        except FileNotFoundError:
            continue
        out[farm] = {
            "events": ev["event_label"].value_counts().to_dict(),
            "assets": int(ev["asset_id"].nunique()),
            "anomaly_components": ev.loc[ev.event_label == "anomaly", "component"].value_counts().to_dict(),
        }
    return out


def main() -> None:
    faults = fault_events()
    logbook_rows = len(read_edp_logbook())
    report = {
        "alignment_raw_calendar": [r for r in alignment_report(edp_calendar=False) if r["agreement"] < 0.999],
        "alignment_edp_calendar": alignment_report(edp_calendar=True),
        "coverage": coverage_report(),
        "labels": label_summary(faults) | {"edp_logbook_rows": logbook_rows},
        "status_near_faults": status_near_faults(faults),
        "other_farms": other_farms_summary(),
    }
    RUNS_DIR.mkdir(exist_ok=True)
    path = RUNS_DIR / "audit.json"
    path.write_text(json.dumps(report, indent=2, default=str))
    worst = min(r["agreement"] for r in report["alignment_edp_calendar"])
    print(f"alignment on EDP calendar: {len(report['alignment_edp_calendar'])} overlapping pairs, min agreement {worst}")
    print(f"pairs disagreeing on raw CARE calendar: {[(r['a'], r['b']) for r in report['alignment_raw_calendar']]}")
    for c in report["coverage"]:
        print(f"{c['turbine_id']} (asset {c['asset_id']}): {c['start']} .. {c['end']}, {c['rows']} rows, missing {c['missing_share']:.2%}, gaps>1d {len(c['gaps_over_1_day'])}")
    print(json.dumps(report["labels"], indent=1, default=str))
    print(pd.DataFrame(report["status_near_faults"]).to_string())
    print(json.dumps(report["other_farms"], indent=1))
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
