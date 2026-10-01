"""LLM-only fusion: give the model the same per-hour signals the Bayesian fusion sees, ask it for the risk.

The comparison from the evaluation plan ("LLM-only fusion vs Bayesian fusion"):

- **Input** per (place, hour): exactly the warning signals ``fusion.fuse`` uses
  for that place at that replay hour (``backtest.replay`` → ``store.as_of(t)``,
  so nothing after ``t``), rendered by :func:`render_snapshot`: value, unit,
  status, age of the reading, the calibrated LR as used by fusion, reliability
  (with the freshness decay), the rule that put the signal in its band, the
  silent gauges, the place's prior and the static thresholds of each level
  gauge (p90, p99 of 2019-2024-04, official flood level). Not included: the
  fused probability, the log-odds, the weights, the risk level, anything about
  later hours, labels or Copernicus EMS products.
- **Prompt**: :data:`INSTRUCTIONS` + "Signals at this hour:" + the snapshot,
  identical for every hour (``PROMPT_VERSION``; its SHA-256 is written with the
  hour set). Fixed before any model call; no tuning on outcomes.
- **Output**: :class:`LLMRisk` ``{probability, level, reason}`` via a tool call.
- **Sampling**: temperature 0.7, ``SAMPLES`` = 3 samples per hour, Qwen3-8B
  4-bit on the local mlx-lm server, thinking off.

Pre-registered hour set (:func:`select_hours`, written to
``runs/m4/llm_fusion_hours.json`` before the first call):

- *event*: per place, every 3 h from 48 h before to 12 h after the 2024
  reference crossing (first ANA reading >= flood level), anchored on the
  replay hour at or before the crossing: 21 hours × 5 places;
- *quiet_fa*: the onset hour of every false-alarm episode of the calibrated
  fusion in TEST (2023-01 → 2024-04);
- *quiet_random*: the same number of hours per place, drawn with a fixed seed
  from TEST hours with label 0 and no reading >= flood level within ±72 h.

Commands (``make llm-fusion``)::

    python -m disaster_risk.llm_fusion prepare   # replays, fusion, hour set (no model)
    python -m disaster_risk.llm_fusion run       # model calls, resumable, appends JSONL
    python -m disaster_risk.llm_fusion score     # tables for RESULTS.md
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import statistics
import sys
import time
from collections.abc import Sequence
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field
from pydantic_ai import Agent, ToolOutput

from . import basin
from .backtest import RUNS_DIR
from .fusion import LEVEL_RANK, FusedState, risk_level
from .thresholds import LevelThresholds

OUT_DIR = RUNS_DIR / "m4"
HOURS_PATH = OUT_DIR / "llm_fusion_hours.json"
RUNS_PATH = OUT_DIR / "llm_fusion_runs.jsonl"
SUMMARY_PATH = OUT_DIR / "llm_fusion_summary.json"

PROMPT_VERSION = "llm-fusion-v1"
SAMPLES = 3
TEMPERATURE = 0.7
SEED = 20240501
GRID_BEFORE_H, GRID_AFTER_H, GRID_STEP_H = 48, 12, 3
QUIET_MARGIN = timedelta(hours=72)
HOUR = timedelta(hours=1)
SOURCE_LABEL = {"ana_level": "river level (ANA)", "ana_rain": "rain gauge (ANA)", "inmet_rain": "rain station (INMET)"}
ROLE_LABEL = {"gauge": "this place's own gauge", "upstream": "upstream/neighbour gauge", "rain": "rain in the catchment"}

INSTRUCTIONS = """\
You estimate flood risk for civil-defence staff in the Taquari valley and Porto Alegre (Rio Grande do Sul, Brazil).
For one place and one hour you get every signal available at that hour: river levels (own gauge and upstream
gauges), rain totals, how old each reading is, which gauges are silent, and for each signal a likelihood ratio (LR)
estimated from the 2019-2022 record (LR > 1 is evidence for a flood, LR < 1 evidence against) and a reliability
between 0 and 1 (lower when the reading is old or incomplete). You also get the prior: how often the hypothesis
was true in 2019-2022.

Hypothesis: the place's own river gauge reaches its official flood level within the next 24 hours.

Give:
- probability: your probability (0 to 1) that the hypothesis is true;
- level: normal if probability < 0.10, attention if 0.10 <= probability < 0.50, alert if 0.50 <= probability < 0.90,
  emergency if probability >= 0.90;
- reason: one or two sentences on what drove your estimate.
Use only the information given.
"""


class LLMRisk(BaseModel):
    probability: float = Field(ge=0.0, le=1.0, description="Probability (0 to 1) that the own gauge reaches its flood level within 24 h")
    level: Literal["normal", "attention", "alert", "emergency"] = Field(description="Risk level from the probability")
    reason: str = Field(description="One or two sentences: what drove the estimate")


# --- the snapshot the model sees ------------------------------------------------------------


def _num(x: float | None, nd: int = 1) -> str:
    if x is None:
        return "n/a"
    return f"{x:.{nd}f}".rstrip("0").rstrip(".") if nd else f"{x:.0f}"


def render_snapshot(state: FusedState, thresholds: dict[str, LevelThresholds],
                    flood_levels: dict[str, float] = basin.FLOOD_LEVEL_CM) -> str:
    """The per-hour input: what fusion used, minus everything fusion computed from it."""
    t_local = state.t + basin.ANA_UTC_OFFSET
    lines = [
        f"Place: {state.place}",
        f"Time: {t_local:%Y-%m-%d %H:%M} local (UTC-3)",
        f"Prior (share of 2019-2022 hours with the hypothesis true): {100 * state.prior:.2f}%",
        "",
        "Signals:",
    ]
    order = {"gauge": 0, "upstream": 1, "rain": 2}
    for c in sorted(state.contributions, key=lambda c: (order[c.role], c.source, c.station)):
        if c.value is None:
            val = "no reading"
        elif c.unit == "cm":
            val = f"{_num(c.value, 0)} cm"
        else:
            val = f"{_num(c.value)} {c.unit}"
        age = "no reading in 72 h" if c.freshness_h is None else f"reading {_num(c.freshness_h)} h old"
        line = (f"- {SOURCE_LABEL.get(c.source, c.source)} {c.station} at {c.station_place} ({ROLE_LABEL[c.role]}): "
                f"{val}; {c.status}, {age}; LR {_num(c.likelihood_ratio, 2)}; reliability {_num(c.reliability, 2)}")
        if c.reason:
            line += f"; rule: {c.reason}"
        if c.source == "ana_level":
            th, fl = thresholds.get(c.station), flood_levels.get(c.station)
            ref = []
            if th is not None:
                ref.append(f"p90 {_num(th.p90, 0)} cm, p99 {_num(th.p99, 0)} cm")
            ref.append(f"official flood level {_num(fl, 0)} cm" if fl else "no official flood level")
            line += f"; station reference: {', '.join(ref)}"
        lines.append(line)
    if state.silent_gauges:
        lines += ["", "Silent river gauges (no reading for more than 3 h, or none in 72 h): " + ", ".join(state.silent_gauges)]
    else:
        lines += ["", "Silent river gauges: none."]
    return "\n".join(lines)


def prompt(snapshot: str) -> str:
    return f"Signals at this hour:\n\n{snapshot}"


def prompt_sha() -> str:
    return hashlib.sha256((PROMPT_VERSION + INSTRUCTIONS + prompt("")).encode()).hexdigest()[:16]


# --- agent ------------------------------------------------------------------------------------


def model_settings() -> dict:
    return {
        "temperature": TEMPERATURE,
        "max_tokens": 400,
        "timeout": 900,
        "extra_body": {"chat_template_kwargs": {"enable_thinking": False}},
    }


def build_agent(model=None, retries: int = 2) -> Agent[None, LLMRisk]:
    if model is None:
        from .alerts import local_model

        model = local_model()
    return Agent(model, output_type=ToolOutput(LLMRisk, name="risk_estimate"), instructions=INSTRUCTIONS,
                 retries=retries, model_settings=model_settings())


def estimate(snapshot: str, agent: Agent[None, LLMRisk]) -> tuple[LLMRisk, dict]:
    t0 = time.monotonic()
    res = agent.run_sync(prompt(snapshot))
    usage = res.usage() if callable(res.usage) else res.usage
    return res.output, {"seconds": round(time.monotonic() - t0, 1), "requests": usage.requests,
                        "input_tokens": usage.input_tokens, "output_tokens": usage.output_tokens}


# --- the pre-registered hour set ------------------------------------------------------------------


def event_grid(crossing: datetime) -> list[tuple[int, datetime]]:
    """(offset h, replay hour) every GRID_STEP_H from -GRID_BEFORE_H to +GRID_AFTER_H around the crossing hour."""
    anchor = crossing.replace(minute=0, second=0, microsecond=0)  # last replay hour at or before the crossing
    return [(k, anchor + timedelta(hours=k)) for k in range(-GRID_BEFORE_H, GRID_AFTER_H + 1, GRID_STEP_H)]


def quiet_candidates(times: Sequence[datetime], series, lo: datetime, hi: datetime) -> list[datetime]:
    """TEST hours with label 0 and no reading >= flood level within ±72 h."""
    return [t for t in times if lo < t <= hi and series.label(t) == 0
            and not series.any_above(t - QUIET_MARGIN, t + QUIET_MARGIN)]


def draw_quiet(candidates: dict[str, list[datetime]], counts: dict[str, int], seed: int = SEED) -> dict[str, list[datetime]]:
    rng = random.Random(seed)
    return {p: sorted(rng.sample(candidates[p], counts[p])) for p in sorted(counts) if counts[p]}


def prepare(out: Path = HOURS_PATH) -> list[dict]:
    from . import calibration, dataset, history, thresholds
    from .backtest import default_adapters, replay
    from .evaluate import episodes, fuse_steps, level_series, restrict, train_records
    from .fusion import PLACES, FusionConfig, fuse
    from .labels import load_or_compute_priors
    from .observations import Store
    from .sources import copernicus_ems

    th = thresholds.load_or_compute()
    adapters = default_adapters(th)
    store = Store(dataset.load_or_build(), copernicus_ems.list_products(basin.EMS_ACTIVATION))
    ev_steps = {st.t: st for st in replay(store, adapters, basin.WINDOW_START_UTC, basin.WINDOW_END_UTC)}
    hist_steps = list(history.chunked_replay(history.load_or_build(), adapters, history.REPLAY_START, history.END))
    series = level_series()
    priors = {k: v["prior"] for k, v in load_or_compute_priors(series).items()}
    table = calibration.as_table(calibration.fit_lr_table(calibration.count_bands(train_records(hist_steps, series))))
    cfg = FusionConfig("full", lr_table=table)
    hist_by_t = {st.t: st for st in hist_steps}

    picks: list[dict] = []
    for name in PLACES:
        c = series[name].first_at_or_above(basin.WINDOW_START_UTC, basin.WINDOW_END_UTC)
        for k, t in event_grid(c):
            picks.append({"set": "event", "place": name, "t": t, "offset_h": k, "crossing": c, "step": ev_steps[t]})
    tracks = fuse_steps(hist_steps, priors, cfg)
    counts = {}
    for name in PLACES:
        tr = restrict(tracks[name], history.TEST_START, history.END)
        n = 0
        for a, b in episodes(tr):
            s = series[name]
            lo, hi = a - HOUR, b + timedelta(hours=24)
            if not s.any_above(lo, hi) and s.count(lo, hi) > 0:  # evaluate.classify_episodes: "false"
                picks.append({"set": "quiet_fa", "place": name, "t": a, "step": hist_by_t[a]})
                n += 1
        counts[name] = n
    cands = {n: quiet_candidates(tracks[n].times, series[n], history.TEST_START, history.LABEL_END) for n in PLACES}
    for name, ts in draw_quiet(cands, counts).items():
        for t in ts:
            picks.append({"set": "quiet_random", "place": name, "t": t, "step": hist_by_t[t]})

    hours = []
    for i, p in enumerate(picks):
        f = fuse(PLACES[p["place"]], p["t"], p["step"].signals, priors[p["place"]], cfg)
        rec = {"id": i, "set": p["set"], "place": p["place"], "t": p["t"].isoformat(),
               "t_local": f"{p['t'] + basin.ANA_UTC_OFFSET:%Y-%m-%d %H:%M}", "label": series[p["place"]].label(p["t"]),
               "fusion_p": f.probability, "fusion_level": f.level, "silent_gauges": list(f.silent_gauges),
               "snapshot": render_snapshot(f, th)}
        if p["set"] == "event":
            rec["offset_h"] = p["offset_h"]
            rec["crossing"] = p["crossing"].isoformat()
        hours.append(rec)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"prompt_version": PROMPT_VERSION, "prompt_sha": prompt_sha(), "instructions": INSTRUCTIONS,
                               "samples": SAMPLES, "temperature": TEMPERATURE, "seed": SEED, "hours": hours},
                              indent=1, ensure_ascii=False))
    print(f"{len(hours)} hours -> {out}: " + ", ".join(
        f"{s} {sum(h['set'] == s for h in hours)}" for s in ("event", "quiet_fa", "quiet_random")))
    return hours


# --- run ----------------------------------------------------------------------------------------------


def run(hours_path: Path = HOURS_PATH, out: Path = RUNS_PATH, limit: int = 0, agent=None) -> int:
    spec = json.loads(hours_path.read_text())
    if spec["prompt_sha"] != prompt_sha():
        raise SystemExit("prompt changed since the hour set was prepared; re-run prepare")
    done = set()
    if out.exists():
        for line in out.read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            done.add((r["id"], r["sample"]))
    agent = agent or build_agent()
    todo = [(h, k) for k in range(SAMPLES) for h in spec["hours"] if (h["id"], k) not in done]
    if limit:
        todo = todo[:limit]
    print(f"{len(done)} done, {len(todo)} to run", flush=True)
    t_start = time.monotonic()
    for n, (h, k) in enumerate(todo, 1):
        rec = {"id": h["id"], "sample": k, "set": h["set"], "place": h["place"], "t_local": h["t_local"],
               "prompt_sha": spec["prompt_sha"]}
        try:
            r, meta = estimate(h["snapshot"], agent)
            rec |= {"probability": r.probability, "level": r.level, "reason": r.reason, **meta}
        except Exception as e:  # noqa: BLE001 - record and keep going
            rec["error"] = f"{type(e).__name__}: {e}"[:500]
        with open(out, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        el = time.monotonic() - t_start
        print(f"[{n}/{len(todo)} {el / n:.1f} s/call, eta {el / n * (len(todo) - n) / 60:.0f} min] {h['place']:12} "
              f"{h['set']:12} {h['t_local']} s{k} -> {rec.get('probability')} {rec.get('level')} {rec.get('error', '')[:80]}",
              flush=True)
    return 0


# --- score --------------------------------------------------------------------------------------------


def brier(ps: Sequence[float], ys: Sequence[int]) -> float | None:
    return sum((p - y) ** 2 for p, y in zip(ps, ys)) / len(ps) if ps else None


def first_alert_lead(rows: list[tuple[int, datetime, datetime, str]]) -> float | None:
    """rows: (offset, t, crossing, level) for one place; lead (h) of the first hour at >= alert, None if never."""
    for _, t, c, lv in sorted(rows):
        if LEVEL_RANK[lv] >= LEVEL_RANK["alert"]:
            return (c - t).total_seconds() / 3600
    return None


def score(hours_path: Path = HOURS_PATH, runs_path: Path = RUNS_PATH, out: Path = SUMMARY_PATH) -> dict:
    spec = json.loads(hours_path.read_text())
    hours = {h["id"]: h for h in spec["hours"]}
    runs: dict[int, dict[int, dict]] = {}
    errors = 0
    secs = []
    for line in runs_path.read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        if "error" in r:
            errors += 1
            continue
        runs.setdefault(r["id"], {})[r["sample"]] = r
        secs.append(r["seconds"])
    complete = [i for i in hours if len(runs.get(i, {})) == SAMPLES]
    summ: dict = {"hours": len(hours), "complete_hours": len(complete), "calls_ok": len(secs), "errors": errors,
                  "seconds_per_call_median": statistics.median(secs) if secs else None,
                  "seconds_total": round(sum(secs), 1), "prompt_sha": spec["prompt_sha"]}

    # level/probability consistency of the model's own answers
    incons = sum(1 for i in complete for r in runs[i].values() if risk_level(r["probability"]) != r["level"])
    summ["level_inconsistent_with_probability"] = incons

    def llm_p(i, k=None):
        rs = runs[i]
        return statistics.mean(r["probability"] for r in rs.values()) if k is None else rs[k]["probability"]

    def llm_level(i, k):
        return runs[i][k]["level"]

    # lead times on the 3-hourly grid
    leads: dict = {}
    for place in dict.fromkeys(h["place"] for h in hours.values()):
        ev = [h for h in hours.values() if h["set"] == "event" and h["place"] == place and h["id"] in complete]
        def rows(level_of):
            return [(h["offset_h"], datetime.fromisoformat(h["t"]), datetime.fromisoformat(h["crossing"]), level_of(h)) for h in ev]
        leads[place] = {
            "fusion": first_alert_lead(rows(lambda h: h["fusion_level"])),
            "llm_samples": [first_alert_lead(rows(lambda h, k=k: llm_level(h["id"], k))) for k in range(SAMPLES)],
            "llm_mean_p": first_alert_lead(rows(lambda h: risk_level(llm_p(h["id"])))),
            "crossing_local": f"{datetime.fromisoformat(ev[0]['crossing']) + basin.ANA_UTC_OFFSET:%m-%d %H:%M}" if ev else None,
        }
    summ["leads"] = leads

    # false alerts on the quiet set
    fa: dict = {}
    for s in ("quiet_fa", "quiet_random"):
        ids = [i for i in complete if hours[i]["set"] == s]
        fa[s] = {"hours": len(ids),
                 "fusion_alert": sum(LEVEL_RANK[hours[i]["fusion_level"]] >= LEVEL_RANK["alert"] for i in ids),
                 "fusion_attention": sum(LEVEL_RANK[hours[i]["fusion_level"]] >= LEVEL_RANK["attention"] for i in ids),
                 "llm_alert_per_sample": [sum(LEVEL_RANK[llm_level(i, k)] >= LEVEL_RANK["alert"] for i in ids) for k in range(SAMPLES)],
                 "llm_attention_per_sample": [sum(LEVEL_RANK[llm_level(i, k)] >= LEVEL_RANK["attention"] for i in ids) for k in range(SAMPLES)],
                 "llm_alert_any_sample": sum(any(LEVEL_RANK[llm_level(i, k)] >= LEVEL_RANK["alert"] for k in range(SAMPLES)) for i in ids),
                 "llm_alert_mean_p": sum(llm_p(i) >= 0.5 for i in ids)}
    summ["quiet"] = fa

    # Brier vs the fusion's label
    br: dict = {}
    for name, sel in (("event", ("event",)), ("quiet", ("quiet_fa", "quiet_random")), ("all", ("event", "quiet_fa", "quiet_random"))):
        ids = [i for i in complete if hours[i]["set"] in sel and hours[i]["label"] is not None]
        ys = [hours[i]["label"] for i in ids]
        br[name] = {"n": len(ids), "positives": sum(ys),
                    "fusion": brier([hours[i]["fusion_p"] for i in ids], ys),
                    "llm_mean_p": brier([llm_p(i) for i in ids], ys),
                    "llm_per_sample": [brier([llm_p(i, k) for i in ids], ys) for k in range(SAMPLES)]}
    summ["brier"] = br

    # run-to-run consistency
    spreads = sorted(max(llm_p(i, k) for k in range(SAMPLES)) - min(llm_p(i, k) for k in range(SAMPLES)) for i in complete)
    sds = [statistics.pstdev([llm_p(i, k) for k in range(SAMPLES)]) for i in complete]
    disagree = sum(len({llm_level(i, k) for k in range(SAMPLES)}) > 1 for i in complete)
    alert_flip = sum(len({LEVEL_RANK[llm_level(i, k)] >= LEVEL_RANK["alert"] for k in range(SAMPLES)}) > 1 for i in complete)
    summ["consistency"] = {
        "hours": len(complete),
        "spread_median": statistics.median(spreads) if spreads else None,
        "spread_p90": spreads[int(0.9 * (len(spreads) - 1))] if spreads else None,
        "spread_max": spreads[-1] if spreads else None,
        "sd_mean": statistics.mean(sds) if sds else None,
        "hours_levels_disagree": disagree,
        "hours_alert_flips": alert_flip,
        "distinct_probabilities": len({round(llm_p(i, k), 4) for i in complete for k in range(SAMPLES)}),
    }
    out.write_text(json.dumps(summ, indent=1, ensure_ascii=False, default=str))
    print(json.dumps(summ, indent=1, ensure_ascii=False, default=str))
    return summ


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("command", choices=["prepare", "run", "score"])
    ap.add_argument("--limit", type=int, default=0, help="run: at most N calls (0 = all)")
    args = ap.parse_args(argv)
    os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")
    if args.command == "prepare":
        prepare()
    elif args.command == "run":
        run(limit=args.limit)
    else:
        score()
    return 0


if __name__ == "__main__":
    sys.exit(main())
