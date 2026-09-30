import numpy as np
import pandas as pd

from maintenance_agents.baseline import Config, daily_scores, feature_columns, window_has_alarm
from maintenance_agents.data import turbine_series


def test_feature_columns_drop_angles_and_meta(care_dir):
    s = turbine_series(0, "A", care_dir, cache=False)
    assert feature_columns(s, "A", care_dir) == ["sensor_0_avg", "sensor_12_avg", "power_30_avg"]


def synthetic_turbine(days=90, fault_day=80, seed=0):
    rng = np.random.default_rng(seed)
    ts = pd.date_range("2016-01-01", periods=days * 144, freq="10min")
    x = rng.normal(size=(len(ts), 3))
    df = pd.DataFrame(x, index=ts, columns=["a_avg", "b_avg", "c_avg"])
    df["status_type_id"] = 0
    # a drifting sensor over the 5 days before the fault
    drift = (ts >= ts[0] + pd.Timedelta(days=fault_day - 5)) & (ts < ts[0] + pd.Timedelta(days=fault_day))
    df.loc[drift, "a_avg"] += 6
    # logbook-derived status marks the pre-fault window; training must drop it
    df.loc[drift, "status_type_id"] = 4
    return df


def test_daily_scores_flag_the_drift_and_not_the_rest():
    df = synthetic_turbine()
    cfg = Config(train_days=30)
    day, train_end, feats = daily_scores(df, cfg, feats=["a_avg", "b_avg", "c_avg"])
    assert train_end == pd.Timestamp("2016-01-31")
    test = day[~day["train"]]
    drift_days = test.loc["2016-03-16":"2016-03-20"]
    assert drift_days["alarm"].all()
    other = test.drop(drift_days.index)
    assert other["alarm"].mean() < 0.1


def test_training_ignores_non_normal_status():
    df = synthetic_turbine(fault_day=20)  # drift falls inside the training period
    cfg = Config(train_days=30)
    day, *_ = daily_scores(df, cfg, feats=["a_avg", "b_avg", "c_avg"])
    # had the drift been trained on, its days would score like normal ones
    drift = day.loc["2016-01-16":"2016-01-20", "mean"]
    normal = day.loc["2016-02-01":, "mean"]
    assert drift.min() > normal.quantile(0.99)


def test_window_has_alarm():
    idx = pd.date_range("2017-01-01", periods=10, freq="D")
    day = pd.DataFrame({"alarm": [False] * 10}, index=idx)
    day.loc["2017-01-05", "alarm"] = True
    fault = pd.Timestamp("2017-01-08")
    assert window_has_alarm(day, fault, 3) is True  # window is [Jan 5, Jan 8)
    assert window_has_alarm(day, fault, 2) is False  # [Jan 6, Jan 8)
    assert window_has_alarm(day, pd.Timestamp("2017-01-06"), 1) is True
    assert window_has_alarm(day, pd.Timestamp("2016-12-01"), 7) is None
