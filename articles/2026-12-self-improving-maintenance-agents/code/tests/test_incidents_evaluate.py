import numpy as np
import pandas as pd

from maintenance_agents.evaluate import (
    episode_table,
    episodes_from_alarms,
    evaluate_detector,
    evaluate_events,
    healthy_days,
    label_episodes,
    quiet_windows,
    score_columns,
)
from maintenance_agents.incidents import classify_stop, incident_count_sensitivity, merge_incidents


def logbook(rows):
    df = pd.DataFrame(rows, columns=["turbine_id", "fault_time", "component", "remarks"])
    df["fault_time"] = pd.to_datetime(df["fault_time"])
    df["asset_id"] = df["turbine_id"].map({"T06": 21, "T07": 0, "T09": 10})
    df = df.sort_values("fault_time").reset_index(drop=True)
    df["fault_id"] = range(len(df))
    return df


REAL_LIKE = logbook(
    [
        # T06 generator: 5 rows, gaps 12.9 / 41.6 / 28.4 / 25.0 days -> one incident
        ("T06", "2016-07-11 19:48", "generator", "Generator replaced"),
        ("T06", "2016-07-24 17:01", "generator", "Generator temperature sensor failure"),
        ("T06", "2016-09-04 08:08", "generator", "High temperature generator error"),
        ("T06", "2016-10-02 17:08", "generator", "Refrigeration system ... replaced"),
        ("T06", "2016-10-27 16:26", "generator", "Generator replaced"),
        # T09: gearbox then generator bearing 6.1 days later -> one incident (rule b)
        ("T09", "2016-10-11 08:06", "gearbox", "Gearbox repaired"),
        ("T09", "2016-10-17 09:19", "generator_bearing", "Generator bearings replaced"),
        # T09 generator bearing 76 days before that: same component but too far -> separate
        ("T09", "2016-08-22 18:25", "generator_bearing", "High temperature generator bearing"),
        # T07: two hydraulic rows 124 days apart -> separate
        ("T07", "2017-06-17 11:35", "hydraulic_group", "Oil leakage in Hub"),
        ("T07", "2017-10-19 10:11", "hydraulic_group", "Oil leakage in Hub"),
    ]
)


def test_merge_incidents_rule():
    inc = merge_incidents(REAL_LIKE)
    assert len(inc) == 5
    t06 = inc[inc.turbine_id == "T06"].iloc[0]
    assert t06.n_rows == 5 and t06.start == pd.Timestamp("2016-07-11 19:48") and t06.end == pd.Timestamp("2016-10-27 16:26")
    t09 = inc[inc.turbine_id == "T09"].sort_values("start")
    assert list(t09.n_rows) == [1, 2]
    assert t09.iloc[1].components == ["gearbox", "generator_bearing"]
    assert t09.iloc[1].component == "gearbox"  # the first row names the incident
    assert list(inc[inc.turbine_id == "T07"].n_rows) == [1, 1]
    assert list(inc.incident_id) == list(range(5))


def test_merge_chains_from_the_previous_row_not_the_first():
    lb = logbook([("T06", "2016-01-01", "generator", ""), ("T06", "2016-02-10", "generator", ""), ("T06", "2016-03-20", "generator", "")])
    assert len(merge_incidents(lb)) == 1  # 40 + 39 days, each gap <= 45
    assert len(merge_incidents(lb, same_component_gap_days=30)) == 3


def test_incident_count_sensitivity_is_monotone():
    counts = [r["incidents"] for r in incident_count_sensitivity(REAL_LIKE, same_gaps=(0, 30, 45, 90), any_gaps=(7,))]
    assert counts == sorted(counts, reverse=True)


def test_classify_stop():
    idx = pd.date_range("2017-01-01 00:00", periods=12, freq="10min")
    rpm = pd.DataFrame({"sensor_18_avg": [1680.0] * 5 + [900.0] + [20.0] * 6}, index=idx)
    # trip at 00:46: row 00:50 (40-50) is partial, row 01:00 is stopped
    assert classify_stop(rpm, pd.Timestamp("2017-01-01 00:46")) == "trip"
    assert classify_stop(rpm, pd.Timestamp("2017-01-01 01:21")) == "already_stopped"
    assert classify_stop(rpm, pd.Timestamp("2017-01-01 00:12")) == "kept_running"
    assert classify_stop(rpm, pd.Timestamp("2016-12-31")) == "no_data"


# ------------------------------------------------------------------ evaluation


def days(start, n):
    return pd.date_range(start, periods=n, freq="D")


def test_episodes_bridge_one_day_gaps():
    a = pd.Series(False, index=days("2017-01-01", 12))
    a.iloc[[1, 2, 4, 8]] = True
    assert episodes_from_alarms(a) == [
        (pd.Timestamp("2017-01-02"), pd.Timestamp("2017-01-05")),
        (pd.Timestamp("2017-01-09"), pd.Timestamp("2017-01-09")),
    ]


def test_hit_windows_exclude_the_fault_day_and_need_history():
    idx = days("2017-01-01", 60)
    daily = pd.DataFrame(index=idx)
    alarm = pd.Series(False, index=idx)
    ev = pd.DataFrame({"t": [pd.Timestamp("2017-02-10 13:00"), pd.Timestamp("2017-01-10 09:00")]})
    alarm.loc["2017-02-10"] = True  # on the fault day itself: does not count
    r = evaluate_events(daily, alarm, ev, "t")
    assert r[0]["hit_7d"] is False and r[0]["lead_days"] is None
    alarm.loc["2017-02-03"] = True  # 7 days before
    r = evaluate_events(daily, alarm, ev, "t")
    assert r[0]["hit_7d"] is True and r[0]["hit_14d"] is True and r[0]["lead_days"] == 7
    # 9 days of history before the second event: evaluable at 7 d only
    assert r[1]["hit_7d"] is False and r[1]["hit_14d"] is None and r[1]["hit_30d"] is None


def test_healthy_days_margin_spans_the_whole_incident():
    idx = days("2016-01-01", 200)
    inc = pd.DataFrame({"start": [pd.Timestamp("2016-03-01 10:00")], "end": [pd.Timestamp("2016-04-10 12:00")]})
    h = pd.Series(healthy_days(idx, inc), index=idx)
    assert h["2016-01-30"] and not h["2016-01-31"]
    assert not h["2016-05-10"] and h["2016-05-11"]


def test_quiet_windows_only_use_fully_healthy_windows():
    idx = days("2017-01-01", 20)
    alarm = pd.Series(False, index=idx)
    alarm.iloc[3] = True
    healthy = pd.Series(True, index=idx)
    healthy.iloc[15:] = False
    w = quiet_windows(alarm, healthy, 5)
    # windows [end - 5, end) inside healthy days 0..14: end = day 5 .. day 15 -> 11 windows
    assert len(w) == 11
    assert sum(w) == 4  # the ones containing day 3: end = day 5, 6, 7, 8


def fake_daily():
    idx = days("2017-01-01", 120)
    rng = np.random.default_rng(0)
    d = pd.DataFrame(
        {
            "turbine_id": "T07",
            "cutoff": pd.Timestamp("2017-01-01"),
            "score_threshold_resid": rng.uniform(0, 2, len(idx)),
            "score_iforest_raw_s0": rng.uniform(0, 2, len(idx)),
            "z_sensor_13_avg": rng.normal(0, 1, len(idx)),
            "z_sensor_41_avg": rng.normal(0, 1, len(idx)),
        },
        index=idx,
    )
    d.loc["2017-03-05":"2017-03-07", "score_threshold_resid"] = 9.0  # 5-3 days before the fault
    d.loc["2017-03-05":"2017-03-07", "z_sensor_13_avg"] = 9.0
    d.loc["2017-01-20", "score_threshold_resid"] = 9.0  # a false alarm in a healthy period
    d.loc["2017-01-20", "z_sensor_41_avg"] = -9.0
    return d


def test_evaluate_detector_counts_hits_and_false_alarms():
    daily = fake_daily()
    faults = logbook([("T07", "2017-03-10 06:00", "generator_bearing", "")])
    inc = merge_incidents(faults)
    r = evaluate_detector(daily, "score_threshold_resid", 5.0, inc, faults)
    assert r["horizons"]["7d"]["incidents_hit"] == 1 and r["horizons"]["7d"]["incidents_evaluable"] == 1
    assert r["false_alarms"] == 1 and r["episodes"] == 2
    healthy_n = int(healthy_days(daily.index, inc).sum())
    assert r["false_alarms_per_turbine_month"] == round(1 / (healthy_n / 30.44), 3)
    assert score_columns(daily) == {"threshold_resid": ["score_threshold_resid"], "iforest_raw": ["score_iforest_raw_s0"]}


def test_episode_table_attribution_and_labels_are_separate():
    daily = fake_daily()
    ep = episode_table(daily, "score_threshold_resid", 5.0, "threshold_resid")
    assert list(ep.component_group) == ["hydraulic", "generator_bearing"]
    assert ep.iloc[1].top_signals.startswith("sensor_13_avg (generator bearing DE temp) +9.0")
    assert ep.iloc[0].top_signals.startswith("sensor_41_avg (hydraulic group oil temp) -9.0")
    # the agent-facing table carries no label columns
    assert not {"next_incident_id", "incident_component", "healthy_start"} & set(ep.columns)
    faults = logbook([("T07", "2017-03-10 06:00", "generator_bearing", "")])
    lab = label_episodes(ep, merge_incidents(faults))
    assert lab.iloc[1].days_before_incident == 5 and lab.iloc[1].incident_component == "generator_bearing"
    assert lab.iloc[0].healthy_start is True and pd.isna(lab.iloc[0].next_incident_id)
