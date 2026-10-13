"""Walk-forward detectors: no look-ahead, no label leakage, weather cancels."""

import numpy as np
import pandas as pd
import pytest

from maintenance_agents.detect import (
    TurbineData,
    WalkForwardConfig,
    cutoffs,
    healthy_mask,
    split_fit_calib,
    walk_forward,
)
from maintenance_agents.features import hourly, regressors, targets

CFG = WalkForwardConfig(
    first_train_days=40, retrain_every_days=20, calib_min_days=10, seeds=(0,), if_estimators=50, nbm_max_iter=30, min_fit_hours=100
)


def synthetic_scada(days=160, start="2016-01-01", seed=0, drift_day=None, drift=0.0):
    """10-minute SCADA: component temps = ambient + load heating + noise; ambient has a season."""
    rng = np.random.default_rng(seed)
    ts = pd.date_range(start, periods=days * 144, freq="10min")
    t = np.arange(len(ts)) / 144.0  # days
    ambient = 12 + 10 * np.sin(2 * np.pi * (t - 100) / 365) + 3 * np.sin(2 * np.pi * t) + rng.normal(0, 0.5, len(t))
    wind = np.clip(7 + 3 * np.sin(2 * np.pi * t / 3.7) + rng.normal(0, 1, len(t)), 0, None)
    power = np.clip((wind - 3) / 9, 0, 1) ** 1.5
    rotor = 5 + 12 * power
    heat = pd.Series(power).ewm(halflife=6).mean().to_numpy()  # thermal lag of ~1 h
    df = pd.DataFrame(
        {
            "sensor_0_avg": ambient,
            "wind_speed_3_avg": wind,
            "power_30_avg": power,
            "sensor_52_avg": rotor,
            "sensor_18_avg": rotor * 100,
            "sensor_13_avg": ambient + 25 * heat + rng.normal(0, 0.7, len(t)),
            "sensor_12_avg": ambient + 30 * heat + rng.normal(0, 0.7, len(t)),
            "sensor_38_avg": ambient + 40 * heat + rng.normal(0, 1.0, len(t)),
            "status_type_id": 0,
        },
        index=pd.DatetimeIndex(ts, name="time_stamp"),
    )
    if drift_day is not None:
        m = t >= drift_day
        df.loc[m, "sensor_13_avg"] += drift
    return df


def run(series, faults=(), cfg=CFG):
    return walk_forward(TurbineData.from_series(series), pd.Series(pd.to_datetime(list(faults)), dtype="datetime64[ns]"), cfg, "TX")


# ------------------------------------------------------------------ causality


def test_cutoffs_depend_only_on_series_start():
    a = cutoffs(pd.Timestamp("2016-01-01 00:10"), pd.Timestamp("2016-06-01"), CFG)
    b = cutoffs(pd.Timestamp("2016-01-01 00:10"), pd.Timestamp("2017-06-01"), CFG)
    assert a[0] == pd.Timestamp("2016-02-10")
    assert b[: len(a)] == a
    assert all(y - x == pd.Timedelta(days=20) for x, y in zip(a, a[1:]))


def test_calibration_block_is_the_end_of_the_training_window():
    first = pd.Timestamp("2016-01-01")
    assert split_fit_calib(pd.Timestamp("2016-02-10"), first, CFG) == pd.Timestamp("2016-01-31")  # min 10 days
    assert split_fit_calib(pd.Timestamp("2016-05-10"), first, CFG) == pd.Timestamp("2016-05-10") - pd.Timedelta(days=32)  # 25 % of 130


def test_healthy_mask_uses_only_faults_known_at_cutoff():
    idx = pd.date_range("2016-01-01", "2016-04-30", freq="1h")
    cut = pd.Timestamp("2016-03-01")
    past, future = pd.Timestamp("2016-02-01"), pd.Timestamp("2016-03-05")
    m = healthy_mask(idx, pd.Series([past, future]), cut, CFG)
    assert not m[idx >= cut].any()  # nothing at or after the cutoff
    assert not m[(idx >= past - pd.Timedelta(days=14)) & (idx < past + pd.Timedelta(days=3))].any()
    # the 14 days before the *future* fault are still training data: nobody knows yet
    assert m[(idx >= future - pd.Timedelta(days=14)) & (idx < cut)].all()


def test_regressors_look_backwards_only():
    s = synthetic_scada(days=5)
    h = hourly(s)
    x = regressors(h)
    s2 = s.copy()
    s2.loc["2016-01-04":, "power_30_avg"] = 99.0
    x2 = regressors(hourly(s2))
    before = x.index < pd.Timestamp("2016-01-04")
    pd.testing.assert_frame_equal(x[before], x2[before])


def test_scores_before_a_date_do_not_depend_on_anything_after_it():
    """The core no-look-ahead proof: change the future, the past must not move.

    Scores before the split date must be identical with the future changed and with it cut off.
    """
    split = pd.Timestamp("2016-04-15")  # not on a cutoff boundary
    base = synthetic_scada(days=160, seed=1)
    fault_past = pd.Timestamp("2016-02-20 10:00")

    changed = base.copy()
    fut = changed.index >= split
    changed.loc[fut, "sensor_13_avg"] += 40.0
    changed.loc[fut, "sensor_38_avg"] = synthetic_scada(days=160, seed=99).loc[fut, "sensor_38_avg"]
    truncated = base[base.index < split]

    a = run(base, [fault_past])
    b = run(changed, [fault_past, pd.Timestamp("2016-04-20 08:00")])
    c = run(truncated, [fault_past])

    past = a.index < split
    assert past.sum() > 30
    cols = [col for col in a.columns if col.startswith(("score_", "z_"))] + ["cutoff"]
    pd.testing.assert_frame_equal(a.loc[past, cols], b.loc[b.index < split, cols])
    pd.testing.assert_frame_equal(a.loc[past, cols], c[cols])
    # and the future change is visible after the split (until the next retrain
    # starts absorbing it), so the test has teeth
    nxt = b.loc[b.index >= split, "cutoff"].iloc[0] + pd.Timedelta(days=CFG.retrain_every_days)
    window = (b.index >= split) & (b.index < nxt)
    assert (b.loc[window, "score_threshold_resid"] > 20).all()
    assert (a.loc[window, "score_threshold_resid"] < 5).all()


def test_status_type_id_is_never_used():
    s = synthetic_scada(days=120, seed=2)
    leaky = s.copy()
    leaky.loc["2016-03-10":"2016-03-24", "status_type_id"] = 4  # what Farm A does before a fault
    assert "status_type_id" not in hourly(s).columns
    pd.testing.assert_frame_equal(run(s), run(leaky))


# ------------------------------------------------------------------ behaviour


def test_residuals_cancel_season_and_catch_drift():
    """Trained in winter, scored into spring/summer: residual detector stays quiet
    until a real +6 degC bearing drift starts; the drifting signal is the top one."""
    s = synthetic_scada(days=200, seed=3, drift_day=170, drift=6.0)
    out = run(s)
    pre = out[(out.index >= "2016-03-01") & (out.index < "2016-06-15")]
    post = out[out.index >= "2016-06-20"]
    assert (pre["score_threshold_resid"] > 5).mean() < 0.1
    assert (post["score_threshold_resid"] > 5).mean() > 0.9
    assert (post["z_sensor_13_avg"].abs() > post["z_sensor_12_avg"].abs()).all()
    # the ambient rise between March and June is ~9 degC: bigger than the drift
    assert s.loc["2016-06-01":"2016-06-15", "sensor_0_avg"].mean() - s.loc["2016-03-01":"2016-03-15", "sensor_0_avg"].mean() > 6


def test_output_has_one_row_per_scored_day_and_all_detectors():
    out = run(synthetic_scada(days=90, seed=4))
    assert out.index.is_unique and out.index.is_monotonic_increasing
    assert out.index.min() == pd.Timestamp("2016-02-10")
    assert {"score_threshold_resid", "score_iforest_resid_s0", "score_iforest_raw_s0", "z_sensor_13_avg"} <= set(out.columns)
    assert (out["turbine_id"] == "TX").all()


@pytest.mark.parametrize("col", ["sensor_13_avg", "sensor_38_avg"])
def test_targets_are_rise_over_ambient(col):
    h = hourly(synthetic_scada(days=3))
    y = targets(h)
    np.testing.assert_allclose(y[col], h[col] - h["sensor_0_avg"])
