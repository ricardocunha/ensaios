from datetime import timedelta

import pytest
from helpers import T0, TH, ana_rows, inmet_rows

from disaster_risk.observations import Store
from disaster_risk.signals import _rain, staleness
from disaster_risk.signals.ana import AnaAdapter, level_bands, level_lr, level_signal
from disaster_risk.signals.copernicus_ems import CopernicusEmsAdapter
from disaster_risk.signals.inmet import InmetAdapter
from disaster_risk.sources.copernicus_ems import Product


@pytest.mark.parametrize(
    "acc24,acc72,lr",
    [(0, 5, 0.5), (10, 40, 1.0), (50, 60, 2.0), (20, 100, 2.0), (100, 150, 5.0), (60, 200, 5.0),
     (150, 150, 10.0), (0, 300, 10.0)],
)
def test_rain_bands(acc24, acc72, lr):
    assert _rain.rain_lr(acc24, acc72)[0] == lr


def test_level_bands_prefer_official_flood_level():
    bands = level_bands(TH, 1800)
    assert [(lo, lr) for lo, lr, _ in bands] == [(1800, 10.0), (1000, 4.0), (400, 1.5)]
    assert level_lr(1799, bands)[0] == 4.0 and level_lr(1800, bands)[0] == 10.0
    assert level_lr(399, bands)[0] == 0.5
    # without an official level, p99.9 is the top band
    assert level_lr(2000, level_bands(TH, None))[0] == 10.0


def test_gauge_without_record_is_uninformative():
    assert level_lr(417, level_bands(None, None))[0] == 1.0


def test_rise_doubles_the_lr():
    rows = ana_rows([500, 520, 540, 560, 580, 600, 620, 700])  # +200 cm over 6 h
    s = level_signal("86510000", rows[-1].hour_end, rows, TH, 1800)
    assert s.details["rise_6h_cm"] == 180 and s.likelihood_ratio == 3.0  # 1.5 x 2


def test_silent_gauge_keeps_last_real_value_and_loses_reliability():
    rows = ana_rows([900, 1200, None, None, None, None, None, None])
    sigs = [level_signal("86510000", r.hour_end, rows[: i + 1], TH, 1800) for i, r in enumerate(rows)]
    assert [s.value for s in sigs] == [900, 1200, 1200, 1200, 1200, 1200, 1200, 1200]  # no interpolation
    assert [s.freshness_h for s in sigs] == [0, 0, 1, 2, 3, 4, 5, 6]
    assert sigs[1].status == "fresh" and sigs[3].status == "stale"
    rel = [s.reliability for s in sigs[1:]]
    assert rel == sorted(rel, reverse=True) and rel[-1] < rel[0]


def test_reading_older_than_max_age_is_missing():
    rows = ana_rows([1200] + [None] * 80)
    s = level_signal("86510000", rows[-1].hour_end, rows, TH, 1800)
    assert s.status == "missing" and s.likelihood_ratio == 1.0 and s.reliability == 0.0


def test_staleness_curve():
    assert staleness(0.5) == ("fresh", 1.0)
    assert staleness(7.0) == ("stale", 0.5)
    assert staleness(None)[0] == "missing" and staleness(100)[0] == "missing"


def test_rain_signal_accumulates_and_scales_by_coverage():
    rows = inmet_rows([10.0] * 12 + [None] * 12)  # 120 mm in 12 of 24 hours
    s = _rain.rain_signal("inmet_rain", "A840", "x", rows[-1].hour_end, rows, 0.8)
    assert s.details["acc24_mm"] == 120.0 and s.likelihood_ratio == 5.0
    assert s.details["coverage72"] == round(12 / 72, 3)
    assert s.freshness_h == 12.0 and s.status == "stale"


def test_adapters_emit_explicit_missing_signals():
    store = Store(ana_rows([None, None], [None, None]) + inmet_rows([None, None]))
    snap = store.as_of(T0 + timedelta(hours=2))
    sigs = AnaAdapter({"86510000": TH}).emit(snap) + InmetAdapter().emit(snap)
    assert {s.source for s in sigs} == {"ana_level", "ana_rain", "inmet_rain"}
    assert all(s.status == "missing" and s.likelihood_ratio == 1.0 and s.reliability == 0 for s in sigs)


def test_ems_is_a_label_not_evidence():
    p = Product("EMSR720", 2, "Encantado", "DEL", 0, "RADARSAT-2", "2024-05-04T22:10:00", "u",
                delivered="2024-05-05T09:28:48", flooded_ha=163.5)
    store = Store([], [p])
    (s,) = CopernicusEmsAdapter().emit(store.as_of(T0 + timedelta(days=5)))
    assert s.kind == "label" and s.likelihood_ratio is None and s.value == 163.5
