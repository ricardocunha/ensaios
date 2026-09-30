"""Synthetic, network-free fixtures shaped like CARE Wind Farm A + EDP logbooks."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

SHIFT = pd.Timedelta(days=2191)


def _series(start: str, periods: int, seed: int) -> pd.DataFrame:
    """A deterministic fake turbine: sensor values depend only on the timestamp."""
    ts = pd.date_range(start, periods=periods, freq="10min")
    minutes = (ts - pd.Timestamp("2016-01-01")).total_seconds().to_numpy() / 600
    return pd.DataFrame(
        {
            "time_stamp": ts,
            "sensor_0_avg": 10 + np.sin(minutes / 144),
            "sensor_1_avg": (minutes * 7) % 360,  # an angle: must be excluded from features
            "sensor_12_avg": 40 + np.cos(minutes / 50) + seed,
            "power_30_avg": (np.sin(minutes / 30) + 1) / 2,
        }
    )


def _care_file(real: pd.DataFrame, asset_id: int, shift: pd.Timedelta, pred_start: str) -> pd.DataFrame:
    df = real.copy()
    df["time_stamp"] = df["time_stamp"] + shift
    df.insert(1, "asset_id", asset_id)
    df.insert(2, "id", range(len(df)))
    df.insert(3, "train_test", np.where(real["time_stamp"] >= pd.Timestamp(pred_start), "prediction", "train"))
    df.insert(4, "status_type_id", 0)
    df["time_stamp"] = df["time_stamp"].dt.strftime("%Y-%m-%d %H:%M:%S")
    return df


@pytest.fixture
def care_dir(tmp_path):
    """data/care with Farm A: asset 0 (= T07) has three overlapping files.

    File 40 uses the extra one-day shift that real files 40 and 71 have.
    """
    root = tmp_path / "care"
    farm = root / "Wind Farm A"
    (farm / "datasets").mkdir(parents=True)
    real = _series("2017-06-01", 6 * 24 * 30, seed=0)  # 30 days on the real (EDP) calendar
    files = {
        73: (real.iloc[: 6 * 24 * 20], SHIFT, "2017-06-10"),
        26: (real.iloc[6 * 24 * 10 :], SHIFT, "2017-06-25"),
        40: (real.iloc[6 * 24 * 5 : 6 * 24 * 25], SHIFT + pd.Timedelta(days=1), "2017-06-20"),
    }
    for eid, (part, shift, pred) in files.items():
        _care_file(part, 0, shift, pred).to_csv(farm / "datasets" / f"{eid}.csv", sep=";", index=False)
    events = pd.DataFrame(
        [
            # anomaly ending at the next 10-min stamp after the logbook entry 2017-06-17 11:35
            (0, 73, "anomaly", "2023-06-10 11:40:00", 1, "2023-06-17 11:40:00", 2, "Hydraulic group"),
            (0, 26, "normal", "2023-06-25 00:00:00", 1, "2023-06-28 00:00:00", 2, None),
            (0, 40, "normal", "2023-06-21 00:00:00", 1, "2023-06-23 00:00:00", 2, None),
        ],
        columns=["asset", "event_id", "event_label", "event_start", "event_start_id", "event_end", "event_end_id", "event_description"],
    )
    events.to_csv(farm / "event_info.csv", sep=";", index=False)
    desc = pd.DataFrame(
        {
            "sensor_name": ["sensor_0", "sensor_1", "sensor_12", "power_30"],
            "statistics_type": ["average"] * 4,
            "description": ["Ambient temperature", "Wind absolute direction", "Temperature oil in gearbox", "Grid power"],
            "unit": ["C", "deg", "C", "kW"],
            "is_angle": [False, True, False, False],
            "is_counter": [False] * 4,
        }
    )
    desc.to_csv(farm / "feature_description.csv", sep=";", index=False)
    return root


@pytest.fixture
def edp_dir(tmp_path):
    d = tmp_path / "edp"
    d.mkdir()
    rows = [
        ("T07", "HYDRAULIC_GROUP", "2017-06-17T11:35:00+00:00", "Oil leakage in Hub"),
        ("T07", "GENERATOR", "2017-06-28T09:00:00+00:00", "Generator damaged"),
    ]
    pd.DataFrame(rows, columns=["Turbine_ID", "Component", "Timestamp", "Remarks"]).to_excel(d / "failures-2017.xlsx", index=False)
    return d
