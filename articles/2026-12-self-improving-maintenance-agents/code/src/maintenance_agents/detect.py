"""Walk-forward (expanding-window) anomaly detectors for one turbine.

Protocol, per turbine, with no future data anywhere:

* **Cutoffs.** ``T_0 = first day + first_train_days``, then every
  ``retrain_every_days``. The model built at ``T_k`` scores the days in
  ``[T_k, T_{k+1})``. Cutoffs depend only on the series start, never on its end.
* **Training window** ``W = [series start, T_k)``, split in time into a *fit*
  part ``F`` and a *calibration* part ``C`` (the last ``max(calib_min_days,
  calib_share * |W|)`` days). Models are fitted on ``F``; score scales and
  thresholds come from ``C``, which the models have not seen.
* **Healthy rows.** Training and calibration drop the hours from 14 days before
  to 3 days after every logbook fault *already recorded before* ``T_k``. Faults
  after ``T_k`` are unknown at ``T_k`` and are not used. (Farm A's
  ``status_type_id`` encodes the same windows for *all* faults, including future
  ones, so it is not used at all here.)
* **Daily score.** Each detector turns a day into a robust z-score against the
  calibration days: ``(x - median_C) / (1.4826 * MAD_C)``. A day is an alarm
  when that score exceeds ``k`` (applied in ``evaluate.py``, so ``k`` can be
  swept without refitting).

Detectors:

* ``iforest_raw``: milestone-1 Isolation Forest on hourly raw averages (42
  signals, angles excluded), fitted on ``F``; day score = mean anomaly score.
* ``iforest_resid``: Isolation Forest on hourly normal-behaviour residuals,
  each scaled by its hourly median/MAD on ``C``.
* ``threshold_resid``: no learning beyond the NBM. For every signal, the daily
  mean residual is z-scored against ``C``; the day score is the largest
  ``|z|`` over signals. The per-signal z-scores are kept for attribution.

Both residual detectors score only the signals of the component groups the
logbook covers (``features.DETECTOR_GROUPS``); converter and nacelle residuals
are kept as ``z_`` context columns.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor, IsolationForest

from .features import DETECTOR_SIGNALS, hourly, raw_feature_columns, regressors, targets

MAD_TO_SD = 1.4826


@dataclass
class WalkForwardConfig:
    first_train_days: int = 60
    retrain_every_days: int = 30
    calib_min_days: int = 21
    calib_share: float = 0.25
    exclude_before_fault_days: int = 14
    exclude_after_fault_days: int = 3
    min_hours_per_day: int = 12
    min_fit_hours: int = 240
    nbm_max_iter: int = 100
    if_estimators: int = 200
    seeds: tuple[int, ...] = (0, 1, 2)
    resid_scale_floor: float = 0.25  # degC, daily-mean residual scale floor
    operating_power_min: float | None = None  # if set, residual detectors use only hours with mean power above it
    detectors: tuple[str, ...] = field(default=("threshold_resid", "iforest_resid", "iforest_raw"))


def cutoffs(first_time: pd.Timestamp, last_time: pd.Timestamp, cfg: WalkForwardConfig) -> list[pd.Timestamp]:
    start = first_time.normalize() + pd.Timedelta(days=cfg.first_train_days)
    out = []
    t = start
    while t <= last_time:
        out.append(t)
        t += pd.Timedelta(days=cfg.retrain_every_days)
    return out


def healthy_mask(index: pd.DatetimeIndex, fault_times: pd.Series, cutoff: pd.Timestamp, cfg: WalkForwardConfig) -> np.ndarray:
    """True for rows usable for training at ``cutoff``: before it, and not near a fault known by then."""
    ok = np.asarray(index < cutoff)
    for ft in pd.to_datetime(pd.Series(fault_times)):
        if ft >= cutoff:
            continue  # not yet in the logbook at training time
        lo = ft - pd.Timedelta(days=cfg.exclude_before_fault_days)
        hi = ft + pd.Timedelta(days=cfg.exclude_after_fault_days)
        ok &= ~np.asarray((index >= lo) & (index < hi))
    return ok


def split_fit_calib(cutoff: pd.Timestamp, first_time: pd.Timestamp, cfg: WalkForwardConfig) -> pd.Timestamp:
    """Start of the calibration part C = [calib_start, cutoff)."""
    w_days = (cutoff - first_time.normalize()).days
    c_days = max(cfg.calib_min_days, int(round(cfg.calib_share * w_days)))
    return cutoff - pd.Timedelta(days=c_days)


def robust_center_scale(x: pd.DataFrame | pd.Series, floor: float) -> tuple:
    med = x.median()
    mad = (x - med).abs().median() * MAD_TO_SD
    return med, np.maximum(mad, floor) if isinstance(mad, float) else mad.clip(lower=floor).fillna(floor)


def daily_mean(frame: pd.DataFrame | pd.Series, min_hours: int):
    """Mean per calendar day; days with fewer than ``min_hours`` non-NaN hours become NaN."""
    g = frame.groupby(frame.index.normalize())
    mean, count = g.mean(), g.count()
    return mean.where(count >= min_hours)


class NormalBehaviourModel:
    """One gradient-boosted regressor per target (temperature rise over ambient)."""

    def __init__(self, max_iter: int = 100, min_fit_hours: int = 240):
        self.max_iter = max_iter
        self.min_fit_hours = min_fit_hours
        self.models: dict[str, HistGradientBoostingRegressor] = {}

    def fit(self, x: pd.DataFrame, y: pd.DataFrame) -> NormalBehaviourModel:
        for col in y.columns:
            m = y[col].notna() & x["power"].notna()
            if m.sum() < self.min_fit_hours:
                continue
            reg = HistGradientBoostingRegressor(
                max_iter=self.max_iter, learning_rate=0.1, max_leaf_nodes=15, min_samples_leaf=40, early_stopping=False
            )
            self.models[col] = reg.fit(x[m], y.loc[m, col])
        return self

    def residuals(self, x: pd.DataFrame, y: pd.DataFrame) -> pd.DataFrame:
        out = pd.DataFrame(index=y.index, columns=list(self.models), dtype=float)
        ok = x["power"].notna()
        for col, reg in self.models.items():
            if ok.any():
                out.loc[ok, col] = y.loc[ok, col].to_numpy() - reg.predict(x[ok])
        return out


@dataclass
class TurbineData:
    """Everything the walk-forward needs, precomputed once (all transforms are causal)."""

    h: pd.DataFrame  # hourly means
    x: pd.DataFrame  # NBM regressors
    y: pd.DataFrame  # NBM targets
    raw: pd.DataFrame  # raw hourly features for iforest_raw

    @classmethod
    def from_series(cls, series: pd.DataFrame) -> TurbineData:
        h = hourly(series)
        return cls(h=h, x=regressors(h), y=targets(h), raw=h[raw_feature_columns(h)])


def _mostly_present(z: pd.DataFrame) -> pd.DataFrame:
    """Hours with at least half of the residuals present; missing ones set to 0 (= as expected)."""
    return z[z.notna().mean(axis=1) >= 0.5].fillna(0.0)


def _iforest_daily(model: IsolationForest, frame: pd.DataFrame, min_hours: int) -> pd.Series:
    rows = frame.dropna()
    if rows.empty:
        return pd.Series(dtype=float)
    score = pd.Series(-model.score_samples(rows), index=rows.index)
    return daily_mean(score, min_hours)


def walk_forward(
    data: TurbineData, fault_times: pd.Series, cfg: WalkForwardConfig, turbine_id: str = ""
) -> pd.DataFrame:
    """Daily scores for every day after the first cutoff.

    Columns: turbine_id, cutoff, n_hours, one ``score_<detector>[_s<seed>]`` per
    detector (and seed), and ``z_<signal>`` (per-signal daily residual z, the
    threshold detector's attribution).
    """
    idx = data.h.index
    first, last = idx.min(), idx.max()
    cuts = cutoffs(first, last, cfg)
    blocks = []
    for k, cut in enumerate(cuts):
        nxt = cuts[k + 1] if k + 1 < len(cuts) else last + pd.Timedelta(days=1)
        test = np.asarray((idx >= cut) & (idx < nxt))
        if not test.any():
            continue
        healthy = healthy_mask(idx, fault_times, cut, cfg)
        c_start = split_fit_calib(cut, first, cfg)
        fit = healthy & np.asarray(idx < c_start)
        cal = healthy & np.asarray(idx >= c_start)
        if cfg.operating_power_min is not None:
            operating = np.asarray(data.h["power_30_avg"] > cfg.operating_power_min)
        else:
            operating = np.ones(len(idx), dtype=bool)
        out = pd.DataFrame(index=pd.DatetimeIndex(sorted(set(idx[test].normalize())), name="day"))
        out["cutoff"] = cut
        out["n_hours"] = data.h.loc[test, "power_30_avg"].notna().groupby(idx[test].normalize()).sum()

        resid_needed = {"threshold_resid", "iforest_resid"} & set(cfg.detectors)
        if resid_needed:
            fit_r, cal_r, test_r = fit & operating, cal & operating, test & operating
            nbm = NormalBehaviourModel(cfg.nbm_max_iter, cfg.min_fit_hours).fit(data.x[fit_r], data.y[fit_r])
            r_cal = nbm.residuals(data.x[cal_r], data.y[cal_r])
            r_test = nbm.residuals(data.x[test_r], data.y[test_r])
            # threshold detector: per-signal daily mean residual, z against C's days
            d_cal = daily_mean(r_cal, cfg.min_hours_per_day)
            d_test = daily_mean(r_test, cfg.min_hours_per_day)
            med, scale = robust_center_scale(d_cal, cfg.resid_scale_floor)
            z = (d_test - med) / scale
            z = z.dropna(axis=1, how="all")
            for col in z.columns:
                out[f"z_{col}"] = z[col]
            if "threshold_resid" in cfg.detectors:
                scored = [c for c in z.columns if c in DETECTOR_SIGNALS]
                out["score_threshold_resid"] = z[scored].abs().max(axis=1)
            if "iforest_resid" in cfg.detectors:
                sig = [c for c in r_cal.columns if c in DETECTOR_SIGNALS]
                hmed, hscale = robust_center_scale(r_cal[sig], 1e-3)
                r_fit = nbm.residuals(data.x[fit_r], data.y[fit_r])[sig]
                r_cal, r_test = r_cal[sig], r_test[sig]
                zf, zc, zt = ((r - hmed) / hscale for r in (r_fit, r_cal, r_test))
                zf, zc, zt = (_mostly_present(z_) for z_ in (zf, zc, zt))
                for seed in cfg.seeds:
                    model = IsolationForest(n_estimators=cfg.if_estimators, random_state=seed).fit(zf)
                    s_cal = _iforest_daily(model, zc, cfg.min_hours_per_day)
                    s_test = _iforest_daily(model, zt, cfg.min_hours_per_day)
                    m, sc = robust_center_scale(s_cal, 1e-4)
                    out[f"score_iforest_resid_s{seed}"] = (s_test - m) / sc
        if "iforest_raw" in cfg.detectors:
            train = data.raw[fit].dropna()
            for seed in cfg.seeds:
                model = IsolationForest(n_estimators=cfg.if_estimators, random_state=seed).fit(train)
                s_cal = _iforest_daily(model, data.raw[cal], cfg.min_hours_per_day)
                s_test = _iforest_daily(model, data.raw[test], cfg.min_hours_per_day)
                m, sc = robust_center_scale(s_cal, 1e-4)
                out[f"score_iforest_raw_s{seed}"] = (s_test - m) / sc
        blocks.append(out)
    res = pd.concat(blocks) if blocks else pd.DataFrame()
    res.insert(0, "turbine_id", turbine_id)
    return res
