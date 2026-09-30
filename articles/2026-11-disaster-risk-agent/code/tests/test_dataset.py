from datetime import datetime, timedelta, timezone

from disaster_risk import dataset
from disaster_risk.sources.ana import Reading
from disaster_risk.sources.inmet import HourlyRain

UTC = timezone.utc


def R(local: str, level=None, rain=None, flow=None, st="86510000"):
    return Reading(st, datetime.strptime(local, "%Y-%m-%d %H:%M"), level, flow, rain)


def test_ana_local_time_is_shifted_to_utc():
    assert dataset.ana_time_utc(datetime(2024, 5, 2, 7, 30)) == datetime(2024, 5, 2, 10, 30, tzinfo=UTC)


def test_hour_ending_convention():
    assert dataset.hour_end_of(datetime(2024, 5, 2, 0, 15, tzinfo=UTC)) == datetime(2024, 5, 2, 1, tzinfo=UTC)
    assert dataset.hour_end_of(datetime(2024, 5, 2, 1, 0, tzinfo=UTC)) == datetime(2024, 5, 2, 1, tzinfo=UTC)


def _hours(readings, start, n):
    s = datetime(*start, tzinfo=UTC)
    return dataset.ana_hourly("86510000", readings, s, s + timedelta(hours=n))


def test_ana_hourly_bins_last_level_and_sums_rain():
    # local 21:15..22:00 == UTC 00:15..01:00 -> hour ending 01:00Z
    rs = [R("2024-05-01 21:15", 100, 1.0), R("2024-05-01 21:30", 110, 2.0),
          R("2024-05-01 21:45", 120, 0.5), R("2024-05-01 22:00", 130, 0.0, flow=5.0)]
    (h,) = _hours(rs, (2024, 5, 2, 0), 1)
    assert h.hour_end == datetime(2024, 5, 2, 1, tzinfo=UTC)
    assert (h.level_cm, h.flow_m3s, h.rain_mm) == (130, 5.0, 3.5)
    assert h.level_time == datetime(2024, 5, 2, 1, tzinfo=UTC)
    assert (h.n_received, h.level_n, h.status, h.level_age_h) == (4, 4, "ok", 0.0)


def test_gap_is_never_interpolated_and_age_grows():
    rs = [R("2024-05-01 21:15", 100, 1.0), R("2024-05-02 00:00", 400, 1.0)]
    rows = _hours(rs, (2024, 5, 2, 0), 3)  # hours ending 01Z, 02Z, 03Z
    assert [r.level_cm for r in rows] == [100, None, 400]
    assert [r.status for r in rows] == ["partial", "missing", "partial"]
    assert rows[1].level_last_time == datetime(2024, 5, 2, 0, 15, tzinfo=UTC)
    assert rows[1].level_age_h == 1.75
    assert rows[2].level_age_h == 0.0


def test_empty_rows_count_as_received_but_not_as_data():
    rs = [R("2024-05-01 21:15"), R("2024-05-01 21:30")]  # the gauge sent rows with no values
    (h,) = _hours(rs, (2024, 5, 2, 0), 1)
    assert (h.n_received, h.level_n, h.rain_n, h.status) == (2, 0, 0, "missing")
    assert h.level_cm is None and h.rain_mm is None and h.level_age_h is None


def test_readings_before_the_window_seed_the_age():
    rs = [R("2024-05-01 18:00", 90)]  # 21:00Z, before the first hour
    (h,) = _hours(rs, (2024, 5, 2, 0), 1)
    assert h.level_cm is None and h.level_age_h == 4.0


def test_inmet_hourly_missing_and_age():
    s = datetime(2024, 5, 2, 0, tzinfo=UTC)
    rows = [HourlyRain("A840", s + timedelta(hours=1), 5.0), HourlyRain("A840", s + timedelta(hours=2), None)]
    out = dataset.inmet_hourly("A840", rows, s, s + timedelta(hours=3))
    assert [r.rain_mm for r in out] == [5.0, None, None]
    assert [r.status for r in out] == ["ok", "missing", "missing"]
    assert [r.rain_age_h for r in out] == [0.0, 1.0, 2.0]
    assert out[1].n_received == 1 and out[2].n_received == 0


def test_csv_round_trip(tmp_path):
    rs = [R("2024-05-01 21:15", 100, 1.0), R("2024-05-02 00:00", 400, 1.0)]
    rows = _hours(rs, (2024, 5, 2, 0), 3)
    path = dataset.write_csv(rows, tmp_path / "h.csv")
    assert dataset.read_csv(path) == rows


def test_coverage_longest_gap():
    rs = [R("2024-05-01 21:15", 100), R("2024-05-02 01:00", 100)]
    rows = _hours(rs, (2024, 5, 2, 0), 5)  # 01Z ok-ish, 02..03Z missing, 04Z reading, 05Z missing
    gap, start = dataset.longest_gap_h(rows)
    assert gap == 2 and start == datetime(2024, 5, 2, 1, tzinfo=UTC)
