"""Milestone 2: walk-forward detectors scored against logbook incidents.

    uv run python -m maintenance_agents.evaluate            # ~5 min on 5 turbines

Writes (all under the git-ignored ``runs/``):

* ``m2_daily_scores.parquet``: one row per turbine-day, every detector's score.
* ``m2_eval.json``: event-level results, false-alarm rates, per-component hits.
* ``m2_episodes.csv``: anomaly episodes for the diagnosis agent (no labels).
* ``m2_episodes_eval.csv``: the same episodes joined to incidents (for scoring only).

Scoring rules (see docs/RESULTS.md):

* **Alarm day**: a day whose score is above ``k``.
* **Hit at horizon H**: an incident (or logbook row) whose date is D has at
  least one alarm day in ``[D - H, D)``. The fault day itself does not count.
  An event is *evaluable at H* when ``D - H`` is on or after the turbine's first
  scored day.
* **Healthy day**: no incident within 30 days before or after (from 30 days
  before an incident's first row to 30 days after its last row).
* **Episode**: consecutive alarm days, bridging gaps of one day.
* **False alarm**: an episode that starts on a healthy day. Rate = false alarms
  per healthy turbine-month (30.44 healthy scored days).
* **Quiet-window base rate** (the null, as in milestone 1): the share of H-day
  windows made only of healthy days that contain an alarm day.
"""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict

import numpy as np
import pandas as pd
from scipy.stats import binomtest

from .audit import RUNS_DIR
from .data import FARM_A_TURBINES, fault_events, turbine_series
from .detect import TurbineData, WalkForwardConfig, walk_forward
from .features import DETECTOR_SIGNALS, LOGBOOK_GROUP, SIGNAL_GROUP, SIGNAL_LABEL
from .incidents import incident_count_sensitivity, merge_incidents, timestamp_context

HORIZONS = (7, 14, 30)
HEALTHY_MARGIN_DAYS = 30
DAYS_PER_MONTH = 30.44
K_GRID = (1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 5.0, 6.0, 7.0, 8.0, 10.0, 12.0, 15.0, 20.0, 30.0)
DEFAULT_K = 5.0
# operating points: healthy alarm days per turbine-month (monotone in k, unlike the
# episode count, which falls again when alarms merge into a few long episodes)
FA_BUDGETS = (0.5, 1.0, 2.0)
EPISODE_BUDGET = 1.0  # episode table: each residual detector at this operating point


# ---------------------------------------------------------------- scoring


def score_columns(daily: pd.DataFrame) -> dict[str, list[str]]:
    """detector name -> its score columns (one per seed)."""
    out: dict[str, list[str]] = {}
    for c in daily.columns:
        if not c.startswith("score_"):
            continue
        name = c.removeprefix("score_")
        base = name.rsplit("_s", 1)[0] if name.rsplit("_s", 1)[-1].isdigit() else name
        out.setdefault(base, []).append(c)
    return out


def healthy_days(days: pd.DatetimeIndex, incidents_t: pd.DataFrame, margin: int = HEALTHY_MARGIN_DAYS) -> np.ndarray:
    ok = np.ones(len(days), dtype=bool)
    m = pd.Timedelta(days=margin)
    for inc in incidents_t.itertuples():
        ok &= ~np.asarray((days >= inc.start.normalize() - m) & (days <= inc.end.normalize() + m))
    return ok


def episodes_from_alarms(alarm: pd.Series, bridge_days: int = 1) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    """(start, end) of runs of alarm days; gaps of up to ``bridge_days`` days are bridged."""
    days = alarm.index[alarm.fillna(False).astype(bool)]
    out: list[list[pd.Timestamp]] = []
    for d in days:
        if out and (d - out[-1][1]).days <= bridge_days + 1:
            out[-1][1] = d
        else:
            out.append([d, d])
    return [(a, b) for a, b in out]


def evaluate_events(daily_t: pd.DataFrame, alarm: pd.Series, events_t: pd.DataFrame, time_col: str) -> list[dict]:
    """Hit / lead time per event on one turbine."""
    first_day = daily_t.index.min()
    rows = []
    for ev in events_t.itertuples():
        d = getattr(ev, time_col).normalize()
        row = {"event_time": str(getattr(ev, time_col))}
        for h in HORIZONS:
            start = d - pd.Timedelta(days=h)
            if pd.isna(first_day) or start < first_day:
                row[f"hit_{h}d"] = None
                continue
            w = alarm.loc[(alarm.index >= start) & (alarm.index < d)]
            row[f"hit_{h}d"] = bool(w.any())
        w = alarm.loc[(alarm.index >= d - pd.Timedelta(days=max(HORIZONS))) & (alarm.index < d)]
        row["lead_days"] = int((d - w.index[w][0]).days) if w.any() else None
        rows.append(row)
    return rows


def quiet_windows(alarm: pd.Series, healthy: pd.Series, h: int) -> list[bool]:
    """For every H-day window [end - H, end) made only of healthy scored days: does it contain an alarm?"""
    if alarm.empty:
        return []
    full = pd.date_range(alarm.index.min(), alarm.index.max(), freq="D")
    ok = healthy.reindex(full, fill_value=False).astype(float)
    al = alarm.reindex(full, fill_value=False).astype(float)
    all_ok = ok.rolling(h).sum().shift(1) == h
    any_alarm = al.rolling(h).max().shift(1) > 0
    ends = alarm.index
    return any_alarm.reindex(ends)[all_ok.reindex(ends)].astype(bool).tolist()


def top_signals(z_row: pd.Series, n: int = 3, only: list[str] | None = None) -> list[tuple[str, float]]:
    z = z_row.dropna()
    if only is not None:
        z = z[[c for c in z.index if c.removeprefix("z_") in only]]
    z = z.reindex(z.abs().sort_values(ascending=False).index)
    return [(c.removeprefix("z_"), float(v)) for c, v in z.head(n).items()]


def episode_attribution(daily_t: pd.DataFrame, start, end) -> dict:
    """Component group and top signals of an episode, from per-signal daily residual z."""
    zc = [c for c in daily_t.columns if c.startswith("z_")]
    if not zc:
        return {"component_group": None, "top_signals": ""}
    w = daily_t.loc[start:end, zc]
    peak = w.abs().max()  # per-signal peak |z| over the episode
    signed = pd.Series({c: w[c].loc[w[c].abs().idxmax()] if w[c].notna().any() else np.nan for c in zc})
    scored = [c for c in zc if c.removeprefix("z_") in DETECTOR_SIGNALS]
    if peak[scored].dropna().empty:
        return {"component_group": None, "top_signals": ""}
    best = peak[scored].idxmax()
    top = top_signals(signed, 3, only=DETECTOR_SIGNALS)
    ctx = top_signals(signed, 1, only=[c.removeprefix("z_") for c in zc if c.removeprefix("z_") not in DETECTOR_SIGNALS])
    fmt = lambda s, v: f"{s} ({SIGNAL_LABEL.get(s, s)}) {v:+.1f}"  # noqa: E731
    return {
        "component_group": SIGNAL_GROUP[best.removeprefix("z_")],
        "top_signals": "; ".join(fmt(s, v) for s, v in top),
        "context_signal": fmt(*ctx[0]) if ctx else "",
    }


def evaluate_detector(daily: pd.DataFrame, col: str, k: float, incidents: pd.DataFrame, faults: pd.DataFrame) -> dict:
    per_inc, per_row, base = [], [], {h: [] for h in HORIZONS}
    fa_episodes, healthy_n, alarm_healthy, episodes = 0, 0, 0, []
    for turbine, d_t in daily.groupby("turbine_id"):
        d_t = d_t.sort_index()
        score = d_t[col]
        alarm = (score > k) & score.notna()
        alarm = alarm[score.notna()]
        inc_t = incidents[incidents["turbine_id"] == turbine]
        healthy = pd.Series(healthy_days(alarm.index, inc_t), index=alarm.index)
        for r, inc in zip(evaluate_events(d_t, alarm, inc_t, "start"), inc_t.itertuples()):
            per_inc.append(r | {"incident_id": inc.incident_id, "turbine_id": turbine, "component": inc.component, "components": list(inc.components)})
        f_t = faults[faults["turbine_id"] == turbine]
        for r, f in zip(evaluate_events(d_t, alarm, f_t, "fault_time"), f_t.itertuples()):
            per_row.append(r | {"fault_id": f.fault_id, "turbine_id": turbine})
        for h in HORIZONS:
            base[h] += quiet_windows(alarm, healthy, h)
        healthy_n += int(healthy.sum())
        alarm_healthy += int((alarm & healthy).sum())
        for a, b in episodes_from_alarms(alarm):
            is_fa = bool(healthy.get(a, False))
            fa_episodes += is_fa
            episodes.append((turbine, a, b, is_fa))
    inc_df, row_df = pd.DataFrame(per_inc), pd.DataFrame(per_row)
    per_date = ((daily[col] > k) & daily[col].notna()).groupby(daily.index).sum()
    months = healthy_n / DAYS_PER_MONTH
    res = {
        "k": k,
        "healthy_turbine_months": round(months, 2),
        "false_alarms": fa_episodes,
        "false_alarms_per_turbine_month": round(fa_episodes / months, 3) if months else None,
        "healthy_alarm_day_share": round(alarm_healthy / healthy_n, 4) if healthy_n else None,
        "healthy_alarm_days_per_turbine_month": round(alarm_healthy / months, 3) if months else None,
        "episodes": len(episodes),
        # weather/grid events hit every turbine at once; a component fault does not
        "farm_wide_alarm_dates": int((per_date >= 3).sum()),
        "horizons": {},
    }
    for h in HORIZONS:
        hits = inc_df[f"hit_{h}d"].dropna().astype(bool)
        rhits = row_df[f"hit_{h}d"].dropna().astype(bool)
        b = np.array(base[h], dtype=bool)
        p0 = float(b.mean()) if len(b) else float("nan")
        res["horizons"][f"{h}d"] = {
            "incidents_evaluable": int(len(hits)),
            "incidents_hit": int(hits.sum()),
            "logbook_rows_evaluable": int(len(rhits)),
            "logbook_rows_hit": int(rhits.sum()),
            "quiet_windows": int(len(b)),
            "quiet_window_alarm_rate": round(p0, 3),
            "binomial_p": round(binomtest(int(hits.sum()), int(len(hits)), p0, alternative="greater").pvalue, 4) if len(hits) and 0 < p0 < 1 else None,
        }
    res["per_incident"] = per_inc
    return res


def per_component(result: dict, daily: pd.DataFrame, col: str, k: float, h: int = 30) -> dict:
    """Hits by incident component and whether the alarm points at the right component group."""
    out: dict[str, dict] = {}
    for r in result["per_incident"]:
        c = out.setdefault(r["component"], {"incidents": 0, "evaluable": 0, "hit": 0, "attributed_to_logbook_component": 0})
        c["incidents"] += 1
        if r[f"hit_{h}d"] is None:
            continue
        c["evaluable"] += 1
        if not r[f"hit_{h}d"]:
            continue
        c["hit"] += 1
        d_t = daily[daily["turbine_id"] == r["turbine_id"]].sort_index()
        d = pd.Timestamp(r["event_time"]).normalize()
        w = d_t.loc[(d_t.index >= d - pd.Timedelta(days=h)) & (d_t.index < d)]
        w = w[w[col] > k]
        if w.empty or not any(x.startswith("z_") for x in w.columns):
            continue
        groups = {g for comp in r["components"] for g in LOGBOOK_GROUP.get(comp, ())}
        attr = [episode_attribution(d_t, day, day)["component_group"] for day in w.index]
        if any(a in groups for a in attr):
            c["attributed_to_logbook_component"] += 1
    return out


# ---------------------------------------------------------------- episodes


def episode_table(daily: pd.DataFrame, col: str, k: float, detector: str) -> pd.DataFrame:
    rows = []
    for turbine, d_t in daily.groupby("turbine_id"):
        d_t = d_t.sort_index()
        score = d_t[col]
        alarm = ((score > k) & score.notna())[score.notna()]
        for a, b in episodes_from_alarms(alarm):
            att = episode_attribution(d_t, a, b)
            rows.append(
                {
                    "turbine_id": turbine,
                    "start": a.date(),
                    "end": b.date(),
                    "n_days": int((b - a).days) + 1,
                    "alarm_days": int(alarm.loc[a:b].sum()),
                    "peak_score": round(float(score.loc[a:b].max()), 2),
                    "component_group": att["component_group"],
                    "top_signals": att["top_signals"],
                    "context_signal": att.get("context_signal", ""),
                    "model_cutoff": d_t.loc[a, "cutoff"].date(),
                    "detector": detector,
                    "k": k,
                }
            )
    out = pd.DataFrame(rows)
    if not out.empty:
        out = out.sort_values(["start", "turbine_id"]).reset_index(drop=True)
        out.insert(0, "episode_id", range(len(out)))
    return out


def label_episodes(ep: pd.DataFrame, incidents: pd.DataFrame, h: int = 30) -> pd.DataFrame:
    """For scoring only: the incident each episode precedes (within ``h`` days), if any."""
    ep = ep.copy()
    ep["next_incident_id"], ep["days_before_incident"], ep["incident_component"], ep["healthy_start"] = None, None, None, None
    for i, e in ep.iterrows():
        inc = incidents[incidents["turbine_id"] == e.turbine_id]
        start = pd.Timestamp(e.start)
        healthy = healthy_days(pd.DatetimeIndex([start]), inc)[0]
        ep.at[i, "healthy_start"] = bool(healthy)
        nxt = inc[(inc["start"].dt.normalize() > start) & (inc["start"].dt.normalize() - start <= pd.Timedelta(days=h))]
        if len(nxt):
            n = nxt.iloc[0]
            ep.at[i, "next_incident_id"] = int(n.incident_id)
            ep.at[i, "days_before_incident"] = int((n.start.normalize() - start).days)
            ep.at[i, "incident_component"] = n.component
    return ep


# ---------------------------------------------------------------- driver


def run_walk_forward(cfg: WalkForwardConfig, faults: pd.DataFrame, jobs: int = 1) -> pd.DataFrame:
    from joblib import Parallel, delayed
    from threadpoolctl import threadpool_limits

    def one(asset_id: int, turbine: str) -> pd.DataFrame:
        with threadpool_limits(1):
            data = TurbineData.from_series(turbine_series(asset_id))
            return walk_forward(data, faults.loc[faults["asset_id"] == asset_id, "fault_time"], cfg, turbine)

    frames = Parallel(n_jobs=jobs)(delayed(one)(a, t) for a, t in FARM_A_TURBINES.items())
    return pd.concat(frames)


def summarise(daily: pd.DataFrame, incidents: pd.DataFrame, faults: pd.DataFrame) -> dict:
    out: dict = {"detectors": {}}
    for det, cols in score_columns(daily).items():
        det_out = {"seeds": {}}
        for col in cols:
            sweep = []
            for k in K_GRID:
                r = evaluate_detector(daily, col, k, incidents, faults)
                sweep.append(r)
            per_seed = {"sweep": [{kk: v for kk, v in r.items() if kk != "per_incident"} for r in sweep]}
            default = next(r for r in sweep if r["k"] == DEFAULT_K)
            per_seed["default_k"] = {kk: v for kk, v in default.items()} | {
                "per_component_30d": per_component(default, daily, col, DEFAULT_K, 30),
                "per_component_14d": per_component(default, daily, col, DEFAULT_K, 14),
            }
            for budget in FA_BUDGETS:
                key = "healthy_alarm_days_per_turbine_month"
                ok = [r for r in sweep if r[key] is not None and r[key] <= budget]
                if ok:
                    best = min(ok, key=lambda r: r["k"])
                    per_seed[f"fa_budget_{budget}"] = {kk: v for kk, v in best.items()} | {
                        "per_component_30d": per_component(best, daily, col, best["k"], 30)
                    }
            det_out["seeds"][col] = per_seed
        out["detectors"][det] = det_out
    return out


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--jobs", type=int, default=1)
    parser.add_argument("--reuse", action="store_true", help="reuse runs/<tag>_daily_scores.parquet")
    parser.add_argument("--operating-power-min", type=float, default=None, help="residual detectors: only hours with power above this")
    parser.add_argument("--calib-share", type=float, default=WalkForwardConfig.calib_share)
    parser.add_argument("--tag", default="m2")
    args = parser.parse_args(argv)
    cfg = WalkForwardConfig(operating_power_min=args.operating_power_min, calib_share=args.calib_share)
    tag = args.tag
    faults = fault_events()
    incidents = merge_incidents(faults)
    RUNS_DIR.mkdir(exist_ok=True)
    scores_path = RUNS_DIR / f"{tag}_daily_scores.parquet"
    t0 = time.time()
    if args.reuse and scores_path.exists():
        daily = pd.read_parquet(scores_path)
    else:
        daily = run_walk_forward(cfg, faults, args.jobs)
        daily.to_parquet(scores_path)
    t_wf = time.time() - t0
    ts = timestamp_context(faults)
    result = {
        "config": asdict(cfg) | {"horizons": HORIZONS, "healthy_margin_days": HEALTHY_MARGIN_DAYS, "k_grid": K_GRID, "default_k": DEFAULT_K},
        "walk_forward_seconds": round(t_wf, 1),
        "scored_days_per_turbine": {t: {"first": str(g.index.min().date()), "last": str(g.index.max().date()), "days": int(len(g)), "retrains": int(g["cutoff"].nunique())} for t, g in daily.groupby("turbine_id")},
        "incidents": {
            "logbook_rows": len(faults),
            "incidents": len(incidents),
            "rule": {"same_component_gap_days": 45, "any_component_gap_days": 7},
            "sensitivity": incident_count_sensitivity(faults),
            "by_component": incidents["component"].value_counts().to_dict(),
            "merged": incidents[incidents["n_rows"] > 1][["incident_id", "turbine_id", "start", "end", "components", "fault_ids"]].astype(str).to_dict("records"),
        },
        "logbook_timestamp_check": {"counts": ts["stop"].value_counts().to_dict(), "rows": ts.astype(str).to_dict("records")},
    } | summarise(daily, incidents, faults)
    (RUNS_DIR / f"{tag}_eval.json").write_text(json.dumps(result, indent=2, default=str))

    eps = []
    for det, col in (("iforest_resid", "score_iforest_resid_s0"), ("threshold_resid", "score_threshold_resid")):
        point = result["detectors"].get(det, {}).get("seeds", {}).get(col, {}).get(f"fa_budget_{EPISODE_BUDGET}")
        if point is not None:
            eps.append(episode_table(daily, col, point["k"], det))
    ep = pd.concat(eps, ignore_index=True)
    ep["episode_id"] = range(len(ep))
    ep.to_csv(RUNS_DIR / f"{tag}_episodes.csv", index=False)
    label_episodes(ep, incidents).to_csv(RUNS_DIR / f"{tag}_episodes_eval.csv", index=False)
    print_summary(result)
    print(f"walk-forward {t_wf:.0f}s; wrote runs/{tag}_eval.json, runs/{tag}_episodes.csv, runs/{tag}_episodes_eval.csv")


def print_summary(result: dict) -> None:
    for det, d in result["detectors"].items():
        for col, s in d["seeds"].items():
            for key in ["default_k"] + [f"fa_budget_{b}" for b in FA_BUDGETS]:
                r = s.get(key)
                if r is None:
                    print(f"{col:28s} {key:15s} (no k meets the budget)")
                    continue
                hz = " ".join(
                    f"{h}:{v['incidents_hit']}/{v['incidents_evaluable']} vs {v['quiet_window_alarm_rate']:.3f} (p={v['binomial_p']})"
                    for h, v in r["horizons"].items()
                )
                print(f"{col:28s} {key:15s} k={r['k']:<5} FA/tm={r['false_alarms_per_turbine_month']} AD/tm={r['healthy_alarm_days_per_turbine_month']} {hz}")


if __name__ == "__main__":
    main()
