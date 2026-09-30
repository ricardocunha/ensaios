"""Labels (future-looking, scoring only), priors, calibrated LRs and episode scoring."""

from datetime import datetime, timedelta, timezone

import pytest
from helpers import T0

from disaster_risk import calibration, evaluate, labels
from disaster_risk.fusion import PLACES, band_key
from disaster_risk.signals import Signal
from disaster_risk.sources.ana import Reading

H = timedelta(hours=1)
Q = timedelta(minutes=15)


def series(levels, flood=1000.0, start=datetime(2024, 5, 1)):
    """15-min readings in local time; None = no reading."""
    rs = [Reading("x", start + i * Q, lv, None, None) for i, lv in enumerate(levels)]
    return labels.LevelSeries.from_readings(rs, flood)


def test_series_is_in_utc():
    s = series([500])
    assert s.times[0] == datetime(2024, 5, 1, 3, tzinfo=timezone.utc)


def test_label_positive_negative_unknown():
    lv = [500] * 4 * 30 + [1200] + [500] * 4 * 30
    s = series(lv)
    t_cross = s.times[4 * 30]
    assert s.label(t_cross - 23 * H) == 1  # within the 24 h horizon
    assert s.label(t_cross - 25 * H) == 0  # the crossing is beyond the horizon; enough readings
    assert s.label(t_cross + 2 * Q) == 1  # 1 h look-back
    assert s.label(t_cross + 2 * H) == 0
    silent = series([500] * 8 + [None] * 200)
    assert silent.label(silent.times[0] + 2 * H) is None


def test_flood_onsets_need_a_gap():
    day = 4 * 24
    lv = [1200] + [500] * day + [1200] + [500] * 8 * day + [1200]
    s = series(lv)
    onsets = s.flood_onsets(s.times[0] - H, s.times[-1])
    assert onsets == [s.times[0], s.times[-1]]  # the second reading is within 7 days of the first


def test_prior_is_smoothed_share_of_positive_hours():
    lv = [500] * 4 * 100
    s = series(lv)
    p, pos, n = labels.historical_prior(s, s.times[0], s.times[0] + 50 * H)
    assert pos == 0 and n == 50 and p == pytest.approx(1 / 52)


def _sig(source, station, lr, status="fresh"):
    return Signal(source, station, "x", T0, T0, 1.0, "cm", lr, 0.0, 0.9, status)


def test_band_counts_and_fitted_lr():
    rec = []
    for _ in range(90):
        rec.append(("Muçum", 0, [_sig("ana_level", "86510000", 0.5)]))
    for _ in range(10):
        rec.append(("Muçum", 0, [_sig("ana_level", "86510000", 4.0)]))
    for _ in range(30):
        rec.append(("Muçum", 1, [_sig("ana_level", "86510000", 4.0)]))
    rec.append(("Muçum", None, [_sig("ana_level", "86510000", 4.0)]))  # unlabelled: skipped
    rec.append(("Muçum", 1, [_sig("ana_level", "86510000", 1.0, "missing")]))  # missing: skipped
    counts = calibration.count_bands(rec)
    k4, k05 = band_key("gauge", "ana_level", 4.0), band_key("gauge", "ana_level", 0.5)
    assert counts == {k05: [90, 0], k4: [10, 30]}
    stats = calibration.fit_lr_table(counts)
    # P(band4|H) = 30.5/31, P(band4|~H) = 10.5/101
    assert stats[k4].lr == pytest.approx((30.5 / 31) / (10.5 / 101))
    assert stats[k05].lr == pytest.approx((0.5 / 31) / (90.5 / 101))


def test_rare_band_keeps_lr_one_and_lrs_are_clipped():
    k = band_key("gauge", "ana_level", 10.0)
    counts = {k: [0, 5], band_key("gauge", "ana_level", 0.5): [100000, 1]}
    stats = calibration.fit_lr_table(counts)
    assert stats[k].lr == 1.0  # fewer than MIN_RECORDS
    counts[k] = [0, 500]
    assert calibration.fit_lr_table(counts)[k].lr == calibration.LR_MAX


def test_places_cover_the_gauges_with_flood_levels():
    from disaster_risk import basin

    assert {p.gauge for p in PLACES.values()} == set(basin.FLOOD_LEVEL_CM)


# --- episodes and lead time ----------------------------------------------------------------


def track(ranks, start=datetime(2024, 5, 1, tzinfo=timezone.utc)):
    return evaluate.Track([start + i * H for i in range(len(ranks))], [0.0] * len(ranks), ranks)


def test_episodes_merge_short_gaps():
    tr = track([0, 2, 2, 0, 0, 2, 0] + [0] * 30 + [3])
    eps = evaluate.episodes(tr, merge_h=24)
    assert eps == [(tr.times[1], tr.times[5]), (tr.times[-1], tr.times[-1])]


def test_lead_time_uses_episode_onset():
    tr = track([0] * 5 + [2] * 20)
    eps = evaluate.episodes(tr)
    lead, onset = evaluate.lead_time_h(tr, eps, tr.times[15])
    assert onset == tr.times[5] and lead == 10
    assert evaluate.lead_time_h(track([0] * 25), [], tr.times[15]) == (None, None)


def test_false_alarm_classification():
    s = series([500] * 4 * 72 + [1200] + [500] * 4 * 72)
    t0 = s.times[0]
    cross = s.times[4 * 72]
    eps = [(t0 + 2 * H, t0 + 3 * H), (cross - 5 * H, cross - 4 * H), (s.times[-1] + 100 * H, s.times[-1] + 101 * H)]
    k = evaluate.classify_episodes(eps, s)
    assert (k["hits"], k["false"], k["unverifiable"]) == (1, 1, 1)
    assert k["false_peak_share"] == [0.5]
