import json
from datetime import timedelta

import pytest
from helpers import T0, TH, ana_rows

from disaster_risk import dataset, fusion
from disaster_risk.backtest import replay, write_signals
from disaster_risk.evaluate import local_full, write_fused_csv
from disaster_risk.observations import Store
from disaster_risk.signals.ana import AnaAdapter
from disaster_risk.viewer import build, write

H = timedelta(hours=1)
LEVELS = [300, 350, None, 500, 900, 1300, 1900, 2400]
TABLE = {"gauge|ana_level|0.5": 0.1, "gauge|ana_level|1.5": 3.0, "gauge|ana_level|10": 1000.0}
ALERT_HOUR = T0 + 5 * H


def _fixture(tmp_path):
    runs, data = tmp_path / "runs", tmp_path / "data"
    rows = ana_rows(LEVELS)
    dataset.write_csv(rows, dataset.cache_path(data))
    steps = list(replay(Store(rows), [AnaAdapter({"86510000": TH}, {"86510000": 1800})], T0, T0 + len(LEVELS) * H))
    write_signals(steps, runs / "signals.csv")
    priors = {name: 0.01 for name in fusion.PLACES}
    write_fused_csv(steps, priors, fusion.FusionConfig("full", lr_table=TABLE), runs / "m3" / "fused_2024.csv")
    summary = {"priors": {k: {"prior": v} for k, v in priors.items()}, "lr_table": {k: {"lr": v} for k, v in TABLE.items()}}
    (runs / "m3" / "summary.json").write_text(json.dumps(summary))
    audit = {"ok": False, "numbers_checked": 2, "ungrounded_numbers": ["42"], "silent_not_mentioned": []}
    alert = {"headline": "Muçum: ALERTA", "explanation": "x", "silent_gauges": [], "audit": audit}
    row = {"place": "Muçum", "kind": "first_alert", "time_local": local_full(ALERT_HOUR), "output_mode": "tool", "audit_retry": True, "alert": alert}
    (runs / "m3" / "alerts_pt.jsonl").write_text(json.dumps(row) + "\n")
    return runs, data


def test_build_joins_the_run_files_per_place_and_hour(tmp_path):
    runs, data = _fixture(tmp_path)
    out = build(runs, data)
    assert [p["name"] for p in out["places"]] == list(fusion.PLACES)
    place = out["places"][0]
    hours = {h["t"]: h for h in place["hours"]}
    assert len(hours) == len(LEVELS) and place["flood_cm"] == 1800
    first = place["hours"][0]
    assert place["signals"][first["signals"][0][0]] == {"source": "ana_level", "station": "86510000", "place": "Muçum", "role": "gauge", "weight": 1.0}
    # hand-set LR 0.5 names the band; the LR used is the calibrated one from summary.json
    assert first["signals"][0][5:7] == [0.5, 0.1] and first["level"] == "normal"
    hit = hours[f"{ALERT_HOUR:%Y-%m-%dT%H:%MZ}"]
    assert hit["alert"]["kind"] == "first_alert"
    text = hit["alert"]["texts"]["pt"][0]
    assert text["mode"] == "tool+audit_retry" and text["audit_ok"] is False and text["problems"] == {"ungrounded_numbers": ["42"]}
    assert "alert" not in first and "llm" not in first and "llm_fusion" not in out["summary"]


def test_an_hour_shows_only_its_own_reading_and_the_next_24h_is_separate(tmp_path):
    out = build(*_fixture(tmp_path))
    hours = out["places"][0]["hours"]
    assert [h["cm"] for h in hours] == LEVELS
    # no reading in the third hour: the signal carries the previous reading and its age
    assert hours[2]["signals"][0][1:4] == ["fresh", 350.0, 1.0]
    assert hours[0]["next_24h"] == {"hours_with_reading": 6, "max_cm": 2400, "max_at": "2024-05-01T08:00Z", "reached_at": "2024-05-01T07:00Z", "verdict": "reached"}
    assert hours[-1]["next_24h"] == {"hours_with_reading": 0, "reached_at": None, "verdict": "unknown"}


def test_missing_evaluate_output_names_the_make_target_and_write_makes_one_file(tmp_path):
    with pytest.raises(FileNotFoundError, match="make evaluate"):
        build(tmp_path / "nothing", tmp_path / "data")
    path = write(build(*_fixture(tmp_path)), tmp_path / "public")
    assert path.name == "data.json" and len(json.loads(path.read_text())["places"]) == 5
