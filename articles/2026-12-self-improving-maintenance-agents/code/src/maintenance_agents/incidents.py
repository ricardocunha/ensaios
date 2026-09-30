"""Clean the EDP failure logbook into incidents, and check what its timestamps mark.

**Incident rule.** Logbook rows on one turbine are chained into one incident when

* (a) the row has the same EDP component as the incident's previous row and
  comes at most ``same_component_gap_days`` (default 45) after it, or
* (b) the row comes at most ``any_component_gap_days`` (default 7) after the
  incident's previous row, whatever the component (one stop, several parts).

Rows are processed in time order and the rule chains (gaps are measured from
the previous row of the incident, not from its first row). The incident starts
at its first row; that is the time the detectors are scored against.

The 45-day value was set after reading the gaps, so treat it as a documented
choice, not a discovery: every same-component gap on a turbine is either
<= 43.9 days (T06 generator x5, T07 transformer x2, with repeated remarks such
as "Generator replaced" twice) or >= 76.1 days. ``incident_count_sensitivity``
reports the counts for other values.

**Timestamp check.** ``timestamp_context`` looks at the SCADA around each
logbook timestamp: did the generator stop within the 10-minute row that
contains it, was the turbine already stopped, or did it keep running?
"""

from __future__ import annotations

import pandas as pd

from .data import turbine_series


def merge_incidents(
    faults: pd.DataFrame, same_component_gap_days: float = 45.0, any_component_gap_days: float = 7.0
) -> pd.DataFrame:
    """One row per incident.

    Input: ``fault_events()`` (needs fault_id, turbine_id, asset_id, fault_time,
    component, remarks). Output columns: incident_id, turbine_id, asset_id,
    start (first row's time), end (last row's time), component (first row's),
    components (all, in order), n_rows, fault_ids, remarks.
    """
    same = pd.Timedelta(days=same_component_gap_days)
    anyc = pd.Timedelta(days=any_component_gap_days)
    rows = faults.sort_values(["turbine_id", "fault_time", "fault_id"])
    incidents: list[dict] = []
    for turbine, grp in rows.groupby("turbine_id", sort=True):
        current: dict | None = None
        for f in grp.itertuples():
            if current is not None:
                gap = f.fault_time - current["_last_time"]
                if (f.component == current["_last_component"] and gap <= same) or gap <= anyc:
                    current["fault_ids"].append(int(f.fault_id))
                    current["components"].append(f.component)
                    current["remarks"].append(str(f.remarks))
                    current["end"] = f.fault_time
                    current["_last_time"], current["_last_component"] = f.fault_time, f.component
                    continue
                incidents.append(current)
            current = {
                "turbine_id": turbine,
                "asset_id": int(f.asset_id),
                "start": f.fault_time,
                "end": f.fault_time,
                "component": f.component,
                "components": [f.component],
                "fault_ids": [int(f.fault_id)],
                "remarks": [str(f.remarks)],
                "_last_time": f.fault_time,
                "_last_component": f.component,
            }
        if current is not None:
            incidents.append(current)
    out = pd.DataFrame(incidents).drop(columns=["_last_time", "_last_component"])
    out["n_rows"] = out["fault_ids"].map(len)
    out = out.sort_values(["start", "turbine_id"]).reset_index(drop=True)
    out.insert(0, "incident_id", range(len(out)))
    return out[["incident_id", "turbine_id", "asset_id", "start", "end", "component", "components", "n_rows", "fault_ids", "remarks"]]


def incident_count_sensitivity(faults: pd.DataFrame, same_gaps=(0, 15, 30, 45, 60, 90), any_gaps=(0, 7)) -> list[dict]:
    return [
        {"same_component_gap_days": s, "any_component_gap_days": a, "incidents": len(merge_incidents(faults, s, a))}
        for s in same_gaps
        for a in any_gaps
    ]


def classify_stop(frame: pd.DataFrame, t: pd.Timestamp, running_rpm: float = 500.0, stopped_rpm: float = 100.0) -> str:
    """What the generator did around logbook time ``t`` (10-minute rows, end-labelled).

    * ``trip``: running in the last row before ``t`` and stopped in the row after
      the one that contains ``t`` (the stop happened within ~10 min of ``t``).
    * ``already_stopped``: stopped in both rows around ``t``.
    * ``kept_running``: running in the row after the one containing ``t``.
    * ``no_data`` / ``other``.
    """
    rpm = frame["sensor_18_avg"]
    before = rpm.loc[t - pd.Timedelta(minutes=10) : t - pd.Timedelta(microseconds=1)]
    after = rpm.loc[t.ceil("10min") + pd.Timedelta(minutes=10) : t.ceil("10min") + pd.Timedelta(minutes=10)]
    if before.empty or after.empty:
        return "no_data"
    b, a = float(before.iloc[-1]), float(after.iloc[0])
    if b >= running_rpm and a < stopped_rpm:
        return "trip"
    if b < stopped_rpm and a < stopped_rpm:
        return "already_stopped"
    if a >= running_rpm:
        return "kept_running"
    return "other"


def timestamp_context(faults: pd.DataFrame, series_by_asset: dict | None = None) -> pd.DataFrame:
    """Per logbook row: stop classification, wind speed at the time, hours stopped after."""
    series_by_asset = {} if series_by_asset is None else series_by_asset
    out = []
    for f in faults.itertuples():
        s = series_by_asset.get(f.asset_id)
        if s is None:
            s = series_by_asset.setdefault(f.asset_id, turbine_series(int(f.asset_id)))
        t = f.fault_time
        kind = classify_stop(s, t)
        after = s.loc[t.ceil("10min") + pd.Timedelta(minutes=10) : t + pd.Timedelta(days=7), "sensor_18_avg"]
        restart = after.index[after >= 500.0]
        wind = s.loc[t - pd.Timedelta(minutes=30) : t + pd.Timedelta(minutes=30), "wind_speed_3_avg"]
        out.append(
            {
                "fault_id": int(f.fault_id),
                "turbine_id": f.turbine_id,
                "fault_time": t,
                "component": f.component,
                "stop": kind,
                "wind_ms": round(float(wind.mean()), 1) if len(wind) else None,
                "hours_to_restart": round((restart[0] - t).total_seconds() / 3600, 1) if len(restart) and kind != "kept_running" else None,
            }
        )
    return pd.DataFrame(out)
