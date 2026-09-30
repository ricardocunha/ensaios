"""The replay must never use a reading before it exists."""

from dataclasses import replace
from datetime import datetime, timedelta, timezone

from helpers import T0, TH, ana_rows, inmet_rows

from disaster_risk.backtest import first_crossings, replay
from disaster_risk.observations import Store
from disaster_risk.signals.ana import AnaAdapter
from disaster_risk.signals.copernicus_ems import CopernicusEmsAdapter
from disaster_risk.signals.inmet import InmetAdapter
from disaster_risk.sources.copernicus_ems import Product

H = timedelta(hours=1)
LEVELS = [300, 350, None, 500, 900, 1300, None, None, 1900, 2400, 2500, 2000, 1500, None, 800, 600]
RAINS = [0, 5, 20, None, 40, 60, 10, 0, 0, None, 0, 0, 0, 0, 0, 0]
PRODUCT = Product("EMSR720", 2, "Encantado", "DEL", 0, "RADARSAT-2", "2024-05-01T03:00:00", "u",
                  delivered="2024-05-01T09:30:00", flooded_ha=163.5)


def _rows():
    return ana_rows(LEVELS, RAINS) + inmet_rows(RAINS)


def _adapters():
    return [AnaAdapter({"86510000": TH}, {"86510000": 1800}), InmetAdapter(), CopernicusEmsAdapter()]


def _run(rows, products=(), **kw):
    return list(replay(Store(rows, products, **kw), _adapters(), T0, T0 + len(LEVELS) * H))


def test_signals_equal_those_computed_from_data_truncated_at_t():
    """For every t, the full dataset and a dataset cut at t give identical signals."""
    rows = _rows()
    full = _run(rows, [PRODUCT])
    for step in full:
        cut_rows = [r for r in rows if r.available_at <= step.t]
        cut_products = [PRODUCT] if datetime(2024, 5, 1, 9, 30, tzinfo=timezone.utc) <= step.t else []
        snap = Store(cut_rows, cut_products).as_of(step.t)
        expected = [s for a in _adapters() for s in a.emit(snap)]
        assert expected and step.signals == expected


def test_future_spike_does_not_change_past_signals():
    rows = _rows()
    base = _run(rows)
    k = 5  # corrupt everything after step k with absurd values
    spiked = [replace(r, level_cm=99999.0, rain_mm=999.0) if r.hour_end > base[k].t and r.level_cm is not None
              else replace(r, rain_mm=999.0) if r.hour_end > base[k].t and r.rain_mm is not None else r for r in rows]
    after = _run(spiked)
    assert [s.signals for s in base[: k + 1]] == [s.signals for s in after[: k + 1]]
    assert base[k + 1].signals != after[k + 1].signals  # sanity: the spike is visible once it happens


def test_row_is_invisible_until_its_hour_closes():
    rows = ana_rows([1200])  # hour ending T0+1h
    store = Store(rows)
    assert store.as_of(T0 + timedelta(minutes=59)).rows("ana", "86510000") == []
    assert len(store.as_of(T0 + H).rows("ana", "86510000")) == 1


def test_latency_delays_availability():
    store = Store(ana_rows([1200]), latency=timedelta(minutes=30))
    assert store.as_of(T0 + H).rows("ana", "86510000") == []
    assert len(store.as_of(T0 + H + timedelta(minutes=30)).rows("ana", "86510000")) == 1


def test_ems_product_visible_at_delivery_not_acquisition():
    steps = _run(_rows(), [PRODUCT])
    labels = [(s.t, [x for x in s.signals if x.kind == "label"]) for s in steps]
    first = next(t for t, ls in labels if ls)
    assert first == datetime(2024, 5, 1, 10, tzinfo=timezone.utc)  # delivered 09:30, acquired 03:00
    assert all(not ls for t, ls in labels if t < first)


def test_signal_observed_at_never_after_emission_time():
    for step in _run(_rows(), [PRODUCT]):
        for s in step.signals:
            assert s.observed_at is None or s.observed_at <= step.t
            assert s.freshness_h is None or s.freshness_h >= 0


def test_first_crossings():
    steps = _run(_rows())
    fc = first_crossings(steps)
    assert fc[("ana_level", "86510000")][10.0] == T0 + 9 * H  # 1900 >= flood level 1800 at hour 9


class _LeakyAdapter:
    """Cheats: reads the whole series behind the snapshot's back."""

    name = "leaky"

    def emit(self, snap):
        rows = snap.store._series[("ana", "86510000")]
        return [max(r.level_cm or 0 for r in rows)]


def test_truncation_check_catches_a_leaky_adapter():
    """Sanity check on the test above: the same comparison exposes an adapter that looks ahead."""
    rows = _rows()
    t = T0 + 3 * H
    full = _LeakyAdapter().emit(Store(rows).as_of(t))
    cut = _LeakyAdapter().emit(Store([r for r in rows if r.available_at <= t]).as_of(t))
    assert full != cut
