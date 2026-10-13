import json

import pandas as pd
import pytest

from maintenance_agents.viewer import build, write

MEMORY = (
    "Past episodes from this farm, most similar first (similarity = cosine of the first-day residual patterns, 1 = identical):\n"
    "1. Episode #1, T01 2016-04-01: detector score 3.0; top group gearbox (logbook component gearbox); top signals sensor_11_avg (gearbox HSS bearing temp) +3.0. "
    "Similarity 0.80, 9 days ago.\n"
    "   Diagnosis then: inspect gearbox (urgency high, confidence 0.90).\n"
    '   Outcome: logbook failure on 2016-04-05, component gearbox ("oil leak"), 4 days after the first alarm. Lesson: inspecting was right and the component was right.'
)


def _row(arm, episode, start, memories=(), block="Past episodes: none yet."):
    prompt = (
        f"Anomaly episode #{episode} on turbine T01. First alarm day: {start}. You are deciding at {start} 24:00, with data up to then.\n"
        "Detector score that day: 3.1 (alarm above 2.5).\n"
        "Top residual signals that day (z): sensor_11_avg (gearbox HSS bearing temp) +4.0; sensor_12_avg (gearbox oil temp) -2.5.\n"
        "Top signal group: gearbox -> logbook component gearbox.\n"
        "Top context signal: sensor_9_avg (VCP-board temp) -1.2.\n"
        f"{block}\nGive your diagnosis."
    )
    return {
        "arm": arm,
        "episode_id": episode,
        "turbine_id": "T01",
        "start": start,
        "decision_time": f"{pd.Timestamp(start) + pd.Timedelta(days=1)}",
        "top_group": "gearbox",
        "detector_component": "gearbox",
        "diagnosis": {"component": "gearbox", "action": "inspect", "urgency": "high", "evidence": "e", "confidence": 0.8},
        "error": None,
        "memories": list(memories),
        "memories_visible": len(memories),
        "gate_rejections": {"low_similarity": 2} if arm == "gated" else {},
        "usage": {"input_tokens": 10, "output_tokens": 5, "requests": 2, "tool_calls": 1, "tools_called": ["residual_series", "final_diagnosis"]},
        "seconds": 1.5,
        "prompt": prompt,
    }


def _fixture(tmp_path):
    runs = tmp_path / "runs"
    runs.mkdir()
    shown = [{"episode_id": 1, "similarity": 0.8, "age_days": 9.0, "outcome_known": True}]
    # written out of time order: episode 2 starts after episode 1
    none = [_row("none", 2, "2016-04-10"), _row("none", 1, "2016-04-01")]
    gated = [_row("gated", 1, "2016-04-01", block="Past episodes: none passed the memory filter for this case."), _row("gated", 2, "2016-04-10", shown, MEMORY)]
    (runs / "m3_none.jsonl").write_text("\n".join(map(json.dumps, none)))
    (runs / "m3_gated.jsonl").write_text("\n".join(map(json.dumps, gated)))
    arm = {
        "episodes": 2,
        "component_accuracy_pre_incident": "1/1",
        "ignore_on_false_alarm": "0/1",
        "actions_pre_incident": {"inspect": 1},
        "actions_false_alarm": {"inspect": 1},
        "mean_memories_in_prompt": 0.5,
        "per_episode": [
            {"episode_id": 1, "klass": "pre_incident", "action": "inspect", "component_ok": True, "appropriate": True, "n_memories": 0},
            {"episode_id": 2, "klass": "false_alarm", "action": "inspect", "component_ok": False, "appropriate": False, "n_memories": 1},
        ],
    }
    (runs / "m3_summary.json").write_text(json.dumps({"model": "local", "horizon_days": 30, "policies": {"none": None}, "arms": {"none": arm, "gated": arm}}))
    labels = pd.DataFrame(
        {
            "episode_id": [1, 2, 1],
            "detector": ["iforest_resid", "iforest_resid", "threshold_resid"],
            "end": ["2016-04-03", "2016-04-10", "2016-04-01"],
            "n_days": [3, 1, 1],
            "peak_score": [5.5, 3.1, 9.9],
            "days_before_incident": [4, None, None],
            "incident_component": ["gearbox", None, None],
        }
    )
    labels.to_csv(runs / "m2_episodes_eval.csv", index=False)
    labels.drop(columns=["days_before_incident", "incident_component"]).to_csv(runs / "m2_episodes.csv", index=False)
    days = pd.date_range("2016-03-25", "2016-04-12", name="day")
    pd.DataFrame({"turbine_id": "T01", "z_sensor_11_avg": [float(i) for i in range(len(days))]}, index=days).to_parquet(runs / "m2_daily_scores.parquet")
    return runs


def test_build_joins_the_arms_per_episode_in_time_order(tmp_path):
    data = build(_fixture(tmp_path))
    assert data["versions"] == ["v1"] and [e["id"] for e in data["episodes"]] == [1, 2]
    first, second = data["episodes"]
    assert first["score"] == 3.1 and first["context_signal"] == "sensor_9_avg (VCP-board temp) -1.2"
    assert first["signals"][1] == {"signal": "sensor_12_avg", "label": "gearbox oil temp", "z": -2.5}
    assert set(second["runs"]["v1"]) == {"none", "gated"}
    gated = second["runs"]["v1"]["gated"]
    assert gated["tools"] == ["residual_series", "final_diagnosis"] and gated["gate_rejections"] == {"low_similarity": 2}
    memory = gated["memories"][0]
    assert memory["similarity"] == 0.8 and memory["diagnosis_then"] == "inspect gearbox (urgency high, confidence 0.90)"
    assert memory["outcome"].startswith("logbook failure on 2016-04-05") and memory["lesson"].startswith("inspecting was right")
    assert data["summary"]["v1"]["classes"] == {"pre_incident": 1, "false_alarm": 1}
    assert data["summary"]["v1"]["arms"]["gated"]["inspect"] == 2
    assert "logbook" not in data


def test_outcomes_sit_only_under_hindsight_and_the_chart_stops_at_the_alarm_day(tmp_path):
    first, second = build(_fixture(tmp_path))["episodes"]
    hindsight = first.pop("hindsight")
    assert hindsight["klass"] == "pre_incident" and hindsight["days_before_incident"] == 4 and hindsight["incident_component"] == "gearbox"
    assert hindsight["n_days"] == 3 and hindsight["peak_score"] == 5.5
    assert hindsight["scored"]["v1"]["none"]["component_ok"] is True
    assert second["hindsight"]["days_before_incident"] is None
    text = json.dumps(first)
    assert "pre_incident" not in text and "peak_score" not in text and "2016-04-03" not in text
    assert first["series"]["days"][-1] == "2016-04-01" and first["series"]["z"][-1] == 7.0 and len(first["series"]["days"]) == 8


def test_missing_replay_names_the_make_target_and_write_makes_the_folder(tmp_path):
    with pytest.raises(FileNotFoundError, match="make replay"):
        build(tmp_path)
    path = write(build(_fixture(tmp_path)), tmp_path / "viewer" / "public")
    assert path.name == "data.json" and len(json.loads(path.read_text())["episodes"]) == 2
