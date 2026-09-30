import pandas as pd
import pytest

from maintenance_agents.data import (
    fault_events,
    merge_datasets,
    normalise_component,
    read_dataset,
    read_edp_logbook,
    read_event_info,
    turbine_series,
)


def test_event_info_is_moved_to_edp_calendar(care_dir):
    ev = read_event_info("A", care_dir).set_index("event_id")
    assert ev.loc[73, "event_end"] == pd.Timestamp("2017-06-17 11:40")
    assert ev.loc[40, "event_start"] == pd.Timestamp("2017-06-20")  # 2192-day file
    assert ev.loc[73, "turbine_id"] == "T07"
    assert ev.loc[73, "component"] == "hydraulic"
    assert pd.isna(ev.loc[26, "component"])


def test_raw_calendar_is_kept_on_request(care_dir):
    ev = read_event_info("A", care_dir, edp_calendar=False).set_index("event_id")
    assert ev.loc[73, "event_end"] == pd.Timestamp("2023-06-17 11:40")


def test_extra_shift_realigns_file_40(care_dir):
    a = read_dataset("A", 73, care_dir).set_index("time_stamp")
    b = read_dataset("A", 40, care_dir).set_index("time_stamp")
    idx = a.index.intersection(b.index)
    assert len(idx) > 1000
    pd.testing.assert_series_equal(a.loc[idx, "sensor_12_avg"], b.loc[idx, "sensor_12_avg"])


def test_turbine_series_is_deduplicated_union(care_dir):
    s = turbine_series(0, "A", care_dir, cache=False)
    assert s.index.is_unique and s.index.is_monotonic_increasing
    assert s.index.min() == pd.Timestamp("2017-06-01")
    assert len(s) == 6 * 24 * 30  # three overlapping files cover the 30 days exactly once
    assert (s["turbine_id"] == "T07").all()
    assert {"train_test", "id"}.isdisjoint(s.columns)


def test_merge_prefers_one_copy_per_timestamp():
    t = pd.to_datetime(["2017-01-01 00:00", "2017-01-01 00:10"])
    a = pd.DataFrame({"time_stamp": t, "x": [1.0, 2.0], "source_event_id": 1, "train_test": "train", "id": [0, 1]})
    b = pd.DataFrame({"time_stamp": t[1:], "x": [2.0], "source_event_id": 2, "train_test": "prediction", "id": [9]})
    m = merge_datasets([b, a])
    assert list(m["x"]) == [1.0, 2.0]
    assert list(m["source_event_id"]) == [1, 1]


def test_turbine_series_unknown_asset(care_dir):
    with pytest.raises(KeyError):
        turbine_series(99, "A", care_dir, cache=False)


def test_fault_events_join_logbook_and_care(care_dir, edp_dir):
    f = fault_events(care_dir, edp_dir)
    assert list(f["fault_id"]) == [0, 1]
    assert f.loc[0, "care_event_id"] == "73"  # CARE end 11:40 is 5 min after the 11:35 entry
    assert pd.isna(f.loc[1, "care_event_id"])
    assert list(f["component"]) == ["hydraulic_group", "generator"]
    assert (f["asset_id"] == 0).all()


def test_logbook_timestamps_are_naive_utc(edp_dir):
    log = read_edp_logbook(edp_dir)
    assert log["fault_time"].dt.tz is None
    assert log.loc[0, "fault_time"] == pd.Timestamp("2017-06-17 11:35")


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Generator bearing failure", "generator_bearing"),
        ("Gearbox bearings damaged", "gearbox"),
        ("Transformer failure", "transformer"),
        ("Hydraulic group", "hydraulic"),
        ("23020 : Axis 3 not ready-to-operate", "pitch"),
        ("Turbine is stopped due to a main bearing damage", "rotor_bearing"),
        ("Communication fault BK1120 in NC300", "other"),
        (None, "unknown"),
    ],
)
def test_normalise_component(text, expected):
    assert normalise_component(text) == expected
