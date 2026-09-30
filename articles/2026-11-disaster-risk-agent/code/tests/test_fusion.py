"""Fusion: the formula, the weights, the ablations, and no look-ahead."""

import math
from dataclasses import replace
from datetime import timedelta

import pytest
from helpers import T0, TH, ana_rows, inmet_rows

from disaster_risk import fusion
from disaster_risk.backtest import replay
from disaster_risk.fusion import PLACES, FusionConfig, band_key, fuse, fuse_all, logit, risk_level
from disaster_risk.history import chunked_replay
from disaster_risk.observations import Store
from disaster_risk.signals import Signal
from disaster_risk.signals.ana import AnaAdapter
from disaster_risk.signals.inmet import InmetAdapter

H = timedelta(hours=1)
MUCUM = PLACES["Muçum"]
PRIORS = {name: 0.01 for name in PLACES}


def sig(source, station, lr, rel=0.9, status="fresh", age=0.0, value=1000.0):
    return Signal(source, station, "x", T0, T0, value, "cm", lr, age, rel, status)


def test_log_odds_is_prior_plus_weighted_log_lrs():
    sigs = [sig("ana_level", "86510000", 10.0, 0.9), sig("ana_rain", "86510000", 5.0, 0.8),
            sig("inmet_rain", "A840", 2.0, 0.4)]
    f = fuse(MUCUM, T0, sigs, 0.01)
    n = len(MUCUM.rain)
    expected = logit(0.01) + 1.0 * 0.9 * math.log(10) + (1 / n) * 0.8 * math.log(5) + (1 / n) * 0.4 * math.log(2)
    assert f.log_odds == pytest.approx(expected)
    assert f.probability == pytest.approx(1 / (1 + math.exp(-expected)))


def test_signals_of_other_places_and_labels_are_ignored():
    sigs = [sig("ana_level", "87450004", 20.0), replace(sig("ana_level", "86510000", None), kind="label")]
    f = fuse(MUCUM, T0, sigs, 0.01)
    assert f.contributions == () and f.probability == pytest.approx(0.01)


def test_missing_signal_adds_nothing_and_is_flagged_silent():
    f = fuse(MUCUM, T0, [sig("ana_level", "86510000", 1.0, 0.0, "missing", None, None)], 0.01)
    assert f.log_odds == pytest.approx(logit(0.01))
    assert f.silent_gauges == ("86510000",)


def test_stale_gauge_is_silent_after_threshold():
    fresh = fuse(MUCUM, T0, [sig("ana_level", "86510000", 10.0, age=2.0)], 0.01)
    stale = fuse(MUCUM, T0, [sig("ana_level", "86510000", 10.0, age=fusion.SILENT_AFTER_H + 0.5, status="stale")], 0.01)
    assert fresh.silent_gauges == () and stale.silent_gauges == ("86510000",)


def test_upstream_gauge_has_half_weight():
    enc = PLACES["Encantado"]
    f = fuse(enc, T0, [sig("ana_level", "86510000", 10.0, 1.0)], 0.01)
    assert f.contributions[0].role == "upstream"
    assert f.contributions[0].log_odds == pytest.approx(0.5 * math.log(10))


@pytest.mark.parametrize("p,level", [(0.0999, "normal"), (0.10, "attention"), (0.4999, "attention"),
                                     (0.5, "alert"), (0.8999, "alert"), (0.9, "emergency")])
def test_risk_levels(p, level):
    assert risk_level(p) == level


def test_ablations_drop_sources_and_roles():
    sigs = [sig("ana_level", "86720000", 10.0), sig("ana_level", "86510000", 10.0), sig("ana_rain", "86720000", 5.0)]
    enc = PLACES["Encantado"]
    assert {c.source for c in fuse(enc, T0, sigs, 0.01, FusionConfig(drop_sources=frozenset({"ana_level"}))).contributions} == {"ana_rain"}
    roles = {c.role for c in fuse(enc, T0, sigs, 0.01, FusionConfig(drop_roles=frozenset({"upstream"}))).contributions}
    assert roles == {"gauge", "rain"}
    eq = fuse(enc, T0, sigs, 0.01, FusionConfig(equal_weights=True))
    assert all(c.weight == 1.0 for c in eq.contributions)


def test_no_decay_ablation_restores_base_reliability():
    s = sig("ana_level", "86510000", 10.0, rel=0.45, status="stale", age=7.0)  # 0.9 * 0.5 (one half-life)
    assert fuse(MUCUM, T0, [s], 0.01).contributions[0].reliability == pytest.approx(0.45)
    assert fuse(MUCUM, T0, [s], 0.01, FusionConfig(freshness_decay=False)).contributions[0].reliability == pytest.approx(0.9)


def test_calibrated_table_replaces_the_handset_lr_by_band():
    table = {band_key("gauge", "ana_level", 10.0): 500.0}
    f = fuse(MUCUM, T0, [sig("ana_level", "86510000", 10.0, 1.0), sig("ana_rain", "86510000", 5.0, 1.0)], 0.01,
             FusionConfig("full", lr_table=table))
    by = {c.source: c for c in f.contributions}
    assert by["ana_level"].likelihood_ratio == 500.0 and by["ana_level"].handset_lr == 10.0
    assert by["ana_rain"].likelihood_ratio == 1.0  # band not in the table: no evidence


def test_ablation_set_shares_one_table():
    table = {"x": 2.0}
    cfgs = fusion.ablations(table)
    assert [c.name for c in cfgs][0] == "full" and all(c.lr_table is table for c in cfgs)
    assert len({c.name for c in cfgs}) == len(cfgs)


# --- no look-ahead -------------------------------------------------------------------

LEVELS = [300, 350, None, 500, 900, 1300, None, None, 1900, 2400, 2500, 2000, 1500, None, 800, 600]
RAINS = [0, 5, 20, None, 40, 60, 10, 0, 0, None, 0, 0, 0, 0, 0, 0]
CFG = FusionConfig("full", lr_table={band_key("gauge", "ana_level", 10.0): 300.0, band_key("rain", "inmet_rain", 2.0): 20.0})


def _adapters():
    return [AnaAdapter({"86510000": TH}, {"86510000": 1800}), InmetAdapter()]


def _fused(rows, t_end):
    steps = replay(Store(rows), _adapters(), T0, t_end)
    return [fuse_all(st.t, st.signals, PRIORS, CFG) for st in steps]


def test_fused_state_equals_state_from_data_truncated_at_t():
    rows = ana_rows(LEVELS, RAINS) + inmet_rows(RAINS)
    full = _fused(rows, T0 + len(LEVELS) * H)
    for k, states in enumerate(full):
        t = T0 + (k + 1) * H
        cut = [r for r in rows if r.available_at <= t]
        snap = Store(cut).as_of(t)
        expected = fuse_all(t, [s for a in _adapters() for s in a.emit(snap)], PRIORS, CFG)
        assert states == expected


def test_future_spike_does_not_change_past_fused_states():
    rows = ana_rows(LEVELS, RAINS) + inmet_rows(RAINS)
    base = _fused(rows, T0 + len(LEVELS) * H)
    k = 4
    spiked = [replace(r, level_cm=99999.0) if r.hour_end > T0 + (k + 1) * H and r.level_cm is not None else r for r in rows]
    after = _fused(spiked, T0 + len(LEVELS) * H)
    assert base[: k + 1] == after[: k + 1]
    assert base[k + 1] != after[k + 1]


def test_chunked_history_replay_equals_one_pass():
    n = 200
    levels = [300 + (i % 37) * 50 if i % 11 else None for i in range(n)]
    rains = [float(i % 7) * 3 for i in range(n)]
    rows = ana_rows(levels, rains) + inmet_rows(rains)
    one = list(replay(Store(rows), _adapters(), T0, T0 + n * H))
    chunked = list(chunked_replay(rows, _adapters(), T0, T0 + n * H, chunk=timedelta(hours=50), warmup=timedelta(hours=90)))
    assert [s.t for s in one] == [s.t for s in chunked]
    assert [s.signals for s in one] == [s.signals for s in chunked]
