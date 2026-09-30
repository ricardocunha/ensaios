"""Isolation Forest sanity check on Farm A: do alarm days precede logbook faults?

Per turbine:
1. Train an Isolation Forest on the first ``train_days`` of the turbine's
   series, using only rows with status 0. (Farm A status 3/4 is derived from
   the fault logbook, so it is fine for cleaning training data and must never
   be used after that: no status feature, no status filter at test time.)
2. Score every 10-minute row after the training period; average per day.
3. A day is an *alarm day* when its mean score exceeds the 99th percentile of
   the turbine's own daily scores in the training period.

Event check: a logbook fault is *hit* at horizon H if at least one alarm day
falls in the H calendar days before the fault's date. The null is the share of
*quiet* H-day windows (all days >= 30 days from any fault on that turbine) that
contain at least one alarm day. Hit rate well above that base rate means the
alarms carry signal; near it means they don't.

    uv run python -m maintenance_agents.baseline
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import binomtest
from sklearn.ensemble import IsolationForest

from .audit import RUNS_DIR
from .data import FARM_A_TURBINES, farm_dir, fault_events, read_event_info, turbine_series
from .download import DEFAULT_DATA_DIR


@dataclass
class Config:
    train_days: int = 60
    n_estimators: int = 200
    daily_quantile: float = 0.99
    min_rows_per_day: int = 72  # half a day of 10-minute rows
    horizons: tuple[int, ...] = (7, 14, 30)
    quiet_margin_days: int = 30
    seed: int = 0


def feature_columns(frame: pd.DataFrame, farm: str = "A", data_dir: Path = DEFAULT_DATA_DIR) -> list[str]:
    """10-minute averages of non-angle sensors (Min/Max/Std have known data issues)."""
    desc = pd.read_csv(farm_dir(farm, data_dir) / "feature_description.csv", sep=";")
    angles = set(desc.loc[desc["is_angle"].astype(str) == "True", "sensor_name"])
    return [c for c in frame.columns if c.endswith("_avg") and c.removesuffix("_avg") not in angles]


def daily_scores(
    series: pd.DataFrame, cfg: Config, feats: list[str] | None = None
) -> tuple[pd.DataFrame, pd.Timestamp, list[str]]:
    feats = feats or feature_columns(series)
    train_end = series.index.min().normalize() + pd.Timedelta(days=cfg.train_days)
    train = series[(series.index < train_end) & (series["status_type_id"] == 0)][feats].dropna()
    model = IsolationForest(n_estimators=cfg.n_estimators, random_state=cfg.seed).fit(train)
    x = series[feats].dropna()
    score = pd.Series(-model.score_samples(x), index=x.index, name="score")
    day = score.groupby(score.index.normalize()).agg(["mean", "size"])
    day = day[day["size"] >= cfg.min_rows_per_day]
    threshold = day.loc[day.index < train_end, "mean"].quantile(cfg.daily_quantile)
    day["alarm"] = day["mean"] > threshold
    day["train"] = day.index < train_end
    day.attrs["threshold"] = float(threshold)
    return day, train_end, feats


def window_has_alarm(day: pd.DataFrame, end_date: pd.Timestamp, horizon: int) -> bool | None:
    """Any alarm in the `horizon` days before `end_date` (exclusive)? None if no scored day there."""
    w = day.loc[(day.index >= end_date - pd.Timedelta(days=horizon)) & (day.index < end_date)]
    return None if w.empty else bool(w["alarm"].any())


def evaluate(cfg: Config) -> dict:
    faults = fault_events()
    care = read_event_info("A")
    per_fault, base, care_rows, turbines, test_days = [], {h: [] for h in cfg.horizons}, [], [], []
    for asset_id, turbine in FARM_A_TURBINES.items():
        series = turbine_series(asset_id)
        day, train_end, feats = daily_scores(series, cfg)
        test = day[~day["train"]]
        test_days.append(test["alarm"])
        turbines.append(
            {
                "turbine_id": turbine,
                "train_end": str(train_end.date()),
                "threshold": round(day.attrs["threshold"], 4),
                "test_days": len(test),
                "alarm_days": int(test["alarm"].sum()),
                "alarm_day_share": round(float(test["alarm"].mean()), 4),
                "n_features": len(feats),
            }
        )
        f_t = faults[faults["asset_id"] == asset_id]
        fault_dates = f_t["fault_time"].dt.normalize()
        for f in f_t.itertuples():
            fdate = f.fault_time.normalize()
            row = {"fault_id": f.fault_id, "turbine_id": turbine, "fault_time": str(f.fault_time), "component": f.component}
            if fdate < series.index.min().normalize():
                row["status"] = "before_data_start"
            elif fdate - pd.Timedelta(days=max(cfg.horizons)) < train_end:
                row["status"] = "in_training_period"
            else:
                row["status"] = "evaluated"
                prior = fault_dates[(fault_dates < fdate) & (fault_dates >= fdate - pd.Timedelta(days=cfg.quiet_margin_days))]
                row["other_fault_in_prior_30d"] = bool(len(prior))
                for h in cfg.horizons:
                    row[f"hit_{h}d"] = window_has_alarm(test, fdate, h)
                w = test.loc[(test.index >= fdate - pd.Timedelta(days=max(cfg.horizons))) & (test.index < fdate)]
                first = w.index[w["alarm"]].min() if w["alarm"].any() else None
                row["first_alarm_days_before"] = None if first is None else int((fdate - first).days)
            per_fault.append(row)
        # quiet windows: every day of the window is >= margin days from any fault on this turbine
        for h in cfg.horizons:
            for end in test.index:
                start = end - pd.Timedelta(days=h)
                if start < train_end:
                    continue
                near = ((fault_dates >= start - pd.Timedelta(days=cfg.quiet_margin_days)) & (fault_dates < end + pd.Timedelta(days=cfg.quiet_margin_days))).any()
                if near:
                    continue
                v = window_has_alarm(test, end, h)
                if v is not None:
                    base[h].append(v)
        for e in care[care["asset_id"] == asset_id].itertuples():
            w = test.loc[(test.index >= e.event_start.normalize()) & (test.index < e.event_end.normalize())]
            care_rows.append({"event_id": e.event_id, "label": e.event_label, "turbine_id": turbine, "scored_days": len(w), "any_alarm": bool(w["alarm"].any()) if len(w) else None})

    pf = pd.DataFrame(per_fault)
    ev = pf[pf["status"] == "evaluated"]
    summary = {"faults_total": len(pf), "faults_by_status": pf["status"].value_counts().to_dict(), "horizons": {}}
    for h in cfg.horizons:
        hits = ev[f"hit_{h}d"].dropna().astype(bool)
        clean = ev[~ev["other_fault_in_prior_30d"].astype(bool)][f"hit_{h}d"].dropna().astype(bool)
        b = np.array(base[h], dtype=bool)
        p0 = float(b.mean()) if len(b) else float("nan")
        summary["horizons"][f"{h}d"] = {
            "faults_evaluated": int(len(hits)),
            "faults_hit": int(hits.sum()),
            "hit_rate": round(float(hits.mean()), 3),
            "clean_faults_evaluated": int(len(clean)),
            "clean_faults_hit": int(clean.sum()),
            "quiet_windows": int(len(b)),
            "quiet_window_alarm_rate": round(p0, 3),
            "binomial_p_hit_rate_gt_base": round(binomtest(int(hits.sum()), int(len(hits)), p0, alternative="greater").pvalue, 4),
        }
    care_df = pd.DataFrame(care_rows)
    care_eval = care_df.dropna(subset=["any_alarm"])
    summary["care_windows"] = {
        lab: {"windows": int(len(g)), "with_alarm": int(g["any_alarm"].astype(bool).sum())} for lab, g in care_eval.groupby("label")
    }
    alarms = pd.concat(test_days)
    summary["alarm_day_share_by_month"] = {
        str(k): round(float(v), 3) for k, v in alarms.groupby(alarms.index.to_period("M")).mean().items()
    }
    return {"config": asdict(cfg), "turbines": turbines, "summary": summary, "faults": per_fault, "care_windows": care_rows}


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--train-days", type=int, default=Config.train_days)
    parser.add_argument("--seed", type=int, default=Config.seed)
    args = parser.parse_args(argv)
    cfg = Config(train_days=args.train_days, seed=args.seed)
    result = evaluate(cfg)
    RUNS_DIR.mkdir(exist_ok=True)
    path = RUNS_DIR / f"baseline_iforest_train{cfg.train_days}_seed{cfg.seed}.json"
    path.write_text(json.dumps(result, indent=2, default=str))
    print(pd.DataFrame(result["turbines"]).to_string(index=False))
    print(pd.DataFrame(result["faults"]).to_string(index=False))
    print(json.dumps(result["summary"], indent=2))
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
