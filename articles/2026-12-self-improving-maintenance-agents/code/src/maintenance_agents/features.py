"""Weather- and load-normalised features for Farm A: normal-behaviour residuals.

Milestone 1 showed that an Isolation Forest on raw 10-minute averages learns the
season: component temperatures follow ambient temperature and load. This module
removes both effects before any detector sees the data.

1. **Hourly aggregation.** 10-minute averages are averaged per clock hour
   (an hour needs at least ``MIN_ROWS_PER_HOUR`` rows). This cuts noise and
   compute six-fold; the detectors work on days anyway.
2. **Operating state (regressors).** Ambient temperature, wind speed, grid
   power, rotor speed, plus the mean power over the past 6 h and 24 h. The
   rolling means give the model the thermal inertia of oil and windings. They
   look backwards only (the current hour and earlier), so no future data enters.
3. **Targets.** Each monitored temperature *minus ambient temperature*. Taking
   the difference makes most of the seasonal shift cancel before the model is
   fitted; a tree model cannot extrapolate to a hotter summer than it has seen,
   but the temperature rise over ambient at a given load moves much less.
4. **Normal-behaviour model (NBM).** One gradient-boosted regressor per target,
   fitted on healthy history only (see ``detect.py`` for which rows count as
   healthy at each point in time). The residual ``observed - expected`` is the
   feature the detectors use.

Signals are grouped by component so an alarm can be attributed to one. The
logbook components map onto the groups in ``LOGBOOK_GROUP``. There are no
pressure signals in Farm A; the hydraulic group has a single oil temperature.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

MIN_ROWS_PER_HOUR = 3  # of 6 ten-minute rows

AMBIENT = "sensor_0_avg"
REGRESSORS_RAW = {
    "ambient": AMBIENT,
    "wind": "wind_speed_3_avg",
    "power": "power_30_avg",
    "rotor_rpm": "sensor_52_avg",
}

# component group -> monitored temperature signals (10-minute averages)
SIGNAL_GROUPS: dict[str, list[str]] = {
    "generator": ["sensor_15_avg", "sensor_16_avg", "sensor_17_avg", "sensor_19_avg"],
    "generator_bearing": ["sensor_13_avg", "sensor_14_avg"],
    "gearbox": ["sensor_11_avg", "sensor_12_avg"],
    "hydraulic": ["sensor_41_avg"],
    "hub": ["sensor_6_avg", "sensor_53_avg"],
    "transformer": ["sensor_38_avg", "sensor_39_avg", "sensor_40_avg"],
    "converter": ["sensor_8_avg", "sensor_9_avg", "sensor_10_avg", "sensor_21_avg", "sensor_35_avg", "sensor_36_avg", "sensor_37_avg"],
    "nacelle": ["sensor_7_avg", "sensor_20_avg", "sensor_43_avg"],
}
# Groups the detectors score. converter and nacelle residuals are computed and
# shown as context in the episode table, but no logbook component maps to them,
# so they do not raise alarms.
DETECTOR_GROUPS = ("generator", "generator_bearing", "gearbox", "hydraulic", "hub", "transformer")
DETECTOR_SIGNALS = [s for g in DETECTOR_GROUPS for s in SIGNAL_GROUPS[g]]
SIGNAL_GROUP = {s: g for g, sigs in SIGNAL_GROUPS.items() for s in sigs}
TARGETS = [s for sigs in SIGNAL_GROUPS.values() for s in sigs]

# EDP logbook component -> groups whose alarm counts as "pointing at it".
# The hydraulic group sits in the hub (remarks: "Oil leakage in Hub", pitch errors).
LOGBOOK_GROUP = {
    "generator": ("generator",),
    "generator_bearing": ("generator_bearing",),
    "gearbox": ("gearbox",),
    "hydraulic_group": ("hydraulic", "hub"),
    "transformer": ("transformer",),
}

SIGNAL_LABEL = {
    "sensor_6_avg": "hub controller temp",
    "sensor_7_avg": "top nacelle controller temp",
    "sensor_8_avg": "choke coils (VCS) temp",
    "sensor_9_avg": "VCP-board temp",
    "sensor_10_avg": "VCS cooling water temp",
    "sensor_11_avg": "gearbox HSS bearing temp",
    "sensor_12_avg": "gearbox oil temp",
    "sensor_13_avg": "generator bearing DE temp",
    "sensor_14_avg": "generator bearing NDE temp",
    "sensor_15_avg": "stator winding L1 temp",
    "sensor_16_avg": "stator winding L2 temp",
    "sensor_17_avg": "stator winding L3 temp",
    "sensor_19_avg": "split ring chamber temp",
    "sensor_20_avg": "busbar section temp",
    "sensor_21_avg": "grid-side IGBT temp",
    "sensor_35_avg": "rotor-side IGBT L1 temp",
    "sensor_36_avg": "rotor-side IGBT L2 temp",
    "sensor_37_avg": "rotor-side IGBT L3 temp",
    "sensor_38_avg": "HV transformer L1 temp",
    "sensor_39_avg": "HV transformer L2 temp",
    "sensor_40_avg": "HV transformer L3 temp",
    "sensor_41_avg": "hydraulic group oil temp",
    "sensor_43_avg": "nacelle temp",
    "sensor_53_avg": "nose cone temp",
}


def hourly(series: pd.DataFrame, columns: list[str] | None = None) -> pd.DataFrame:
    """Mean per clock hour of numeric 10-minute columns; hours with too few rows are NaN.

    ``status_type_id`` is dropped here on purpose: it is derived from the fault
    logbook and must never reach a feature.
    """
    num = series.drop(columns=["status_type_id", "asset_id", "source_event_id", "turbine_id"], errors="ignore")
    num = num.select_dtypes("number")
    if columns is not None:
        num = num[[c for c in columns if c in num.columns]]
    grouped = num.resample("1h")
    out = grouped.mean()
    counts = grouped.size()
    out.loc[counts < MIN_ROWS_PER_HOUR] = np.nan
    return out


def regressors(h: pd.DataFrame) -> pd.DataFrame:
    """Operating-state inputs of the normal-behaviour model (backward-looking only)."""
    x = pd.DataFrame({k: h[c] for k, c in REGRESSORS_RAW.items()}, index=h.index)
    x["power_6h"] = h[REGRESSORS_RAW["power"]].rolling(6, min_periods=1).mean()
    x["power_24h"] = h[REGRESSORS_RAW["power"]].rolling(24, min_periods=1).mean()
    return x


def targets(h: pd.DataFrame) -> pd.DataFrame:
    """Temperature rise over ambient for every monitored signal present."""
    present = [t for t in TARGETS if t in h.columns]
    return h[present].sub(h[AMBIENT], axis=0)


def raw_feature_columns(h: pd.DataFrame, angles: set[str] | None = None) -> list[str]:
    """Milestone-1 raw features: all 10-minute averages except angle sensors."""
    angles = angles or {"sensor_1", "sensor_2", "sensor_5", "sensor_42"}
    return [c for c in h.columns if c.endswith("_avg") and c.removesuffix("_avg") not in angles]
