"""Milestone 3: fusion backtest, false alarms, calibration and ablations.

``uv run python -m disaster_risk.evaluate`` (``make evaluate``):

1. replays 2024-04-20 → 05-20 (the event) and 2019-01 → 2024-04-19 (the record)
   with the milestone 2 adapters;
2. fits priors and the calibrated LR table on TRAIN (2019-2022, local);
3. fuses every hour for every place, with the hand-set LRs and with the
   calibrated table (plus one run per ablation);
4. prints the tables used in RESULTS.md and writes ``runs/m3/``:
   ``fused_2024.csv`` (every place and hour, calibrated fusion),
   ``summary.json``, ``lr_table.json`` and ``key_hours.json`` (inputs for the
   alert agent).

Definitions (also in RESULTS.md):

- alert episode: consecutive hours at level >= "alert"; episodes less than
  ``MERGE_H`` apart are merged.
- lead time for a flood onset c (first reading >= flood level after 7 days
  below it): c minus the onset of the episode that contains the first alert
  hour in [c - 72 h, c + 72 h]. Positive = the alert came first. No alert
  hour in that range = missed.
- false alarm: an episode with no reading >= flood level from its onset - 1 h
  to its end + 24 h, while the gauge did report in that span ("unverifiable"
  if it did not report at all).
"""

from __future__ import annotations

import csv
import json
import sys
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import basin, calibration, dataset, fusion, history, labels, reference, thresholds
from .backtest import RUNS_DIR, Step, default_adapters, first_crossings, replay
from .fusion import LEVEL_RANK, FusedState, FusionConfig
from .observations import Store
from .sources import copernicus_ems, sgb_sace

OUT_DIR = RUNS_DIR / "m3"
MERGE_H = 24
SEARCH = timedelta(hours=72)
HOUR = timedelta(hours=1)
YEAR_H = 8766.0
ALERT = LEVEL_RANK["alert"]
PROB_BINS = (0.0, 0.01, 0.1, 0.3, 0.5, 0.7, 0.9, 1.0000001)


@dataclass(frozen=True)
class Track:
    """Fused output of one place over a replay: parallel lists by hour."""

    times: list[datetime]
    probs: list[float]
    ranks: list[int]


def fuse_steps(steps: Sequence[Step], priors: dict[str, float], cfg: FusionConfig) -> dict[str, Track]:
    out = {p: Track([], [], []) for p in fusion.PLACES}
    for st in steps:
        for name, f in fusion.fuse_all(st.t, st.signals, priors, cfg).items():
            tr = out[name]
            tr.times.append(st.t)
            tr.probs.append(f.probability)
            tr.ranks.append(LEVEL_RANK[f.level])
    return out


def episodes(tr: Track, min_rank: int = ALERT, merge_h: int = MERGE_H) -> list[tuple[datetime, datetime]]:
    eps: list[list[datetime]] = []
    for t, r in zip(tr.times, tr.ranks):
        if r < min_rank:
            continue
        if eps and (t - eps[-1][1]) <= timedelta(hours=merge_h):
            eps[-1][1] = t
        else:
            eps.append([t, t])
    return [(a, b) for a, b in eps]


def first_at_or_above(tr: Track, min_rank: int, lo: datetime, hi: datetime) -> datetime | None:
    for t, r in zip(tr.times, tr.ranks):
        if lo <= t <= hi and r >= min_rank:
            return t
    return None


def lead_time_h(tr: Track, eps: list[tuple[datetime, datetime]], crossing: datetime) -> tuple[float | None, datetime | None]:
    first = first_at_or_above(tr, ALERT, crossing - SEARCH, crossing + SEARCH)
    if first is None:
        return None, None
    onset = next(a for a, b in eps if a <= first <= b)
    return (crossing - onset).total_seconds() / 3600, onset


def classify_episodes(eps, series: labels.LevelSeries) -> dict:
    """Hits / false / unverifiable; for false alarms, the highest reading as a share of the flood level."""
    out: dict = {"episodes": len(eps), "hits": 0, "false": 0, "unverifiable": 0, "false_peak_share": []}
    for a, b in eps:
        lo, hi = a - labels.LOOKBACK, b + labels.HORIZON
        if series.any_above(lo, hi):
            out["hits"] += 1
        elif series.count(lo, hi) == 0:
            out["unverifiable"] += 1
        else:
            out["false"] += 1
            out["false_peak_share"].append(round(series.max_level(lo, hi) / series.flood_cm, 3))
    return out


def restrict(tr: Track, lo: datetime, hi: datetime) -> Track:
    idx = [i for i, t in enumerate(tr.times) if lo < t <= hi]
    return Track([tr.times[i] for i in idx], [tr.probs[i] for i in idx], [tr.ranks[i] for i in idx])


# --- inputs ----------------------------------------------------------------------


def level_series() -> dict[str, labels.LevelSeries]:
    return {
        name: labels.LevelSeries.from_readings(dataset.ana_readings(pl.gauge), basin.FLOOD_LEVEL_CM[pl.gauge])
        for name, pl in fusion.PLACES.items()
    }


def train_records(steps: Sequence[Step], series: dict[str, labels.LevelSeries]):
    for st in steps:
        if not (history.REPLAY_START < st.t <= history.TRAIN_END):
            continue
        for name in fusion.PLACES:
            yield name, series[name].label(st.t), st.signals


def bulletin_times() -> dict:
    """First SACE bulletin and first bulletin at flood level per ANA code, as UTC upload times."""
    bl = reference.load_bulletins()
    ref = reference.bulletin_reference(bl)

    def utc(t: datetime) -> datetime:
        return (t - basin.ANA_UTC_OFFSET).replace(tzinfo=timezone.utc)

    first = ref.first_bulletin
    return {
        "first": None if first is None else {"data": utc(first.nominal), "uploaded": utc(first.uploaded)},
        "at_flood": {c: {"data": utc(b.nominal), "uploaded": utc(b.uploaded)} for c, b in ref.first_at_flood.items()},
    }


# --- output helpers --------------------------------------------------------------------


def local(t: datetime | None) -> str:
    return "—" if t is None else f"{t + basin.ANA_UTC_OFFSET:%m-%d %H:%M}"


def local_full(t: datetime | None) -> str:
    return "—" if t is None else f"{t + basin.ANA_UTC_OFFSET:%Y-%m-%d %H:%M}"


def hours_between(a: datetime | None, b: datetime | None) -> float | None:
    """b - a in hours (positive when a is earlier)."""
    return None if a is None or b is None else (b - a).total_seconds() / 3600


def fmt_h(x: float | None) -> str:
    return "—" if x is None else f"{x:+.0f} h"


def state_json(f: FusedState) -> dict:
    d = asdict(f)
    d["t"] = f.t.isoformat()
    d["t_local"] = local_full(f.t)
    return d


def write_fused_csv(steps: Sequence[Step], priors, cfg, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["time_utc", "time_local", "place", "prior", "log_odds", "probability", "level", "silent_gauges",
                    "top_contributions"])
        for st in steps:
            for name, f in fusion.fuse_all(st.t, st.signals, priors, cfg).items():
                top = sorted(f.contributions, key=lambda c: -abs(c.log_odds))[:3]
                w.writerow([f"{st.t:%Y-%m-%dT%H:%MZ}", local_full(st.t), name, round(f.prior, 5), round(f.log_odds, 3),
                            round(f.probability, 4), f.level, " ".join(f.silent_gauges),
                            "; ".join(f"{c.source}:{c.station} {c.log_odds:+.2f}" for c in top)])


def key_hours(steps: Sequence[Step], priors, cfg, tracks: dict[str, Track]) -> list[dict]:
    """Hours the alert agent is run on: each place's first alert, and its first silent-gauge hour at >= attention."""
    by_t = {st.t: st for st in steps}
    picks: list[tuple[str, str, datetime]] = []
    for name, tr in tracks.items():
        eps = episodes(tr)
        if eps:
            picks.append((name, "first_alert", eps[0][0]))
    for st in steps:
        for name, f in fusion.fuse_all(st.t, st.signals, priors, cfg).items():
            if f.silent_gauges and LEVEL_RANK[f.level] >= LEVEL_RANK["attention"] and fusion.PLACES[name].gauge in f.silent_gauges:
                if not any(n == name and k == "own_gauge_silent" for n, k, _ in picks):
                    picks.append((name, "own_gauge_silent", st.t))
    out = []
    for name, kind, t in sorted(picks, key=lambda x: (x[2], x[0])):
        f = fusion.fuse(fusion.PLACES[name], t, by_t[t].signals, priors[name], cfg)
        out.append({"place": name, "kind": kind, "state": state_json(f)})
    return out


# --- main ------------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    th = thresholds.load_or_compute()
    adapters = default_adapters(th)
    rows = dataset.load_or_build()
    store = Store(rows, copernicus_ems.list_products(basin.EMS_ACTIVATION))
    ev_steps = list(replay(store, adapters, basin.WINDOW_START_UTC, basin.WINDOW_END_UTC))
    print(f"event replay: {len(ev_steps)} steps", flush=True)
    hist_rows = history.load_or_build()
    hist_steps = list(history.chunked_replay(hist_rows, adapters, history.REPLAY_START, history.END))
    print(f"history replay: {len(hist_steps)} steps, {sum(len(s.signals) for s in hist_steps)} signals", flush=True)

    series = level_series()
    pri = labels.load_or_compute_priors(series)
    priors = {k: v["prior"] for k, v in pri.items()}
    stats = calibration.fit_lr_table(calibration.count_bands(train_records(hist_steps, series)))
    table = calibration.as_table(stats)
    configs = (fusion.HANDSET,) + fusion.ablations(table)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "lr_table.json").write_text(json.dumps({k: asdict(v) for k, v in sorted(stats.items())}, indent=1))
    summary: dict = {"priors": pri, "lr_table": {k: asdict(v) for k, v in sorted(stats.items())}}

    print("\n## Priors (TRAIN 2019-2022)")
    for k, v in pri.items():
        print(f"| {k} | {v['positives']} / {v['labelled']} | {v['prior']:.4f} |")
    print("\n## Calibrated LR table (TRAIN): key | n(H=1) | n(H=0) | LR")
    for k, v in sorted(stats.items()):
        print(f"| {k} | {v.n_pos} | {v.n_neg} | {v.lr:.3g} |")

    ev_tracks = {c.name: fuse_steps(ev_steps, priors, c) for c in configs}
    hist_tracks = {c.name: fuse_steps(hist_steps, priors, c) for c in configs}
    print("fusion done", flush=True)

    # --- 2024 lead times -----------------------------------------------------------
    bl = bulletin_times()
    fc = first_crossings(ev_steps, levels=(10.0,))
    crossings = {n: series[n].first_at_or_above(basin.WINDOW_START_UTC, basin.WINDOW_END_UTC) for n in fusion.PLACES}
    summary["event"] = {}
    print("\n## 2024 lead times (local times; lead = reference crossing - alert onset)")
    print("| Place | Flood-level crossing | Fusion attention | Fusion alert (calibrated) | Lead | Hand-set LRs alert | Lead | Own gauge LR>=10 | Lead | Any place signal LR>=10 | Lead | First SACE bulletin (upload) | Lead of alert vs it | SACE at flood (upload) | Lead of alert vs it |")
    for name, pl in fusion.PLACES.items():
        c = crossings[name]
        full, hand = ev_tracks["full"][name], ev_tracks["handset"][name]
        att = first_at_or_above(full, LEVEL_RANK["attention"], basin.WINDOW_START_UTC, basin.WINDOW_END_UTC)
        lead, onset = lead_time_h(full, episodes(full), c) if c else (None, None)
        hlead, honset = lead_time_h(hand, episodes(hand), c) if c else (None, None)
        own = fc.get(("ana_level", pl.gauge), {}).get(10.0)
        anyt = min((d[10.0] for (src, stn), d in fc.items() if d[10.0] is not None and pl.role(src, stn)), default=None)
        fb = bl["first"]["uploaded"] if bl["first"] and name != "Porto Alegre" else None
        fl = bl["at_flood"].get(pl.gauge, {}).get("uploaded")
        row = {
            "crossing": c, "attention": att, "alert_onset": onset, "lead_h": lead, "handset_alert_onset": honset,
            "handset_lead_h": hlead, "own_lr10": own, "own_lr10_lead_h": hours_between(own, c), "any_lr10": anyt,
            "any_lr10_lead_h": hours_between(anyt, c), "first_bulletin_uploaded": fb,
            "alert_vs_first_bulletin_h": hours_between(onset, fb), "bulletin_at_flood_uploaded": fl,
            "alert_vs_bulletin_at_flood_h": hours_between(onset, fl),
        }
        summary["event"][name] = row
        print(f"| {name} | {local(c)} | {local(att)} | {local(onset)} | {fmt_h(lead)} | {local(honset)} | {fmt_h(hlead)} | "
              f"{local(own)} | {fmt_h(row['own_lr10_lead_h'])} | {local(anyt)} | {fmt_h(row['any_lr10_lead_h'])} | "
              f"{local(fb)} | {fmt_h(row['alert_vs_first_bulletin_h'])} | {local(fl)} | {fmt_h(row['alert_vs_bulletin_at_flood_h'])} |")

    # --- historical floods: lead times -----------------------------------------------
    print("\n## Historical flood onsets (record 2019-01 → 2024-04; TRAIN ≤ 2022, TEST 2023+): lead of the alert")
    print("| Place | Onset (local) | Split | Calibrated alert onset | Lead | Hand-set lead | First SACE bulletin upload in ±72 h | SACE lead | Alert vs bulletin |")
    summary["history_events"] = []
    uploads = sorted((b.uploaded - basin.ANA_UTC_OFFSET).replace(tzinfo=timezone.utc) for b in sgb_sace.list_bulletins())
    for name in fusion.PLACES:
        for c in series[name].flood_onsets(history.REPLAY_START, history.END):
            split = "TRAIN" if c <= history.TRAIN_END else "TEST"
            full, hand = hist_tracks["full"][name], hist_tracks["handset"][name]
            lead, onset = lead_time_h(full, episodes(full), c)
            hlead, _ = lead_time_h(hand, episodes(hand), c)
            bul = None
            if name != "Porto Alegre":  # SACE Taquari does not cover the Guaíba
                bul = next((u for u in uploads if c - SEARCH <= u <= c + SEARCH), None)
            ev = {"place": name, "onset": c, "split": split, "alert_onset": onset, "lead_h": lead,
                  "handset_lead_h": hlead, "sace_upload": bul, "sace_lead_h": hours_between(bul, c),
                  "alert_vs_sace_h": hours_between(onset, bul)}
            summary["history_events"].append(ev)
            print(f"| {name} | {local_full(c)} | {split} | {local(onset)} | {fmt_h(lead) if lead is not None else 'missed'} | "
                  f"{fmt_h(hlead) if hlead is not None else 'missed'} | {local(bul)} | {fmt_h(ev['sace_lead_h'])} | "
                  f"{fmt_h(ev['alert_vs_sace_h'])} |")

    # --- false alarms + calibration, per config ---------------------------------------
    periods = {"TEST": (history.TEST_START, history.END), "TRAIN": (history.REPLAY_START, history.TRAIN_END),
               "2024 window": (basin.WINDOW_START_UTC, basin.WINDOW_END_UTC)}
    summary["configs"] = {}
    for cfg in configs:
        cs: dict = {"false_alarms": {}, "calibration": {}, "event_leads": {}}
        for pname, (lo, hi) in periods.items():
            src = ev_tracks if pname == "2024 window" else hist_tracks
            years = (hi - lo).total_seconds() / 3600 / YEAR_H
            tot: dict = {"episodes": 0, "hits": 0, "false": 0, "unverifiable": 0, "false_peak_share": []}
            per_place = {}
            for name in fusion.PLACES:
                tr = restrict(src[cfg.name][name], lo, hi)
                k = classify_episodes(episodes(tr), series[name])
                per_place[name] = k
                for kk in tot:
                    tot[kk] += k[kk]
            cs["false_alarms"][pname] = {"years": years, "place_years": years * len(fusion.PLACES),
                                         "per_place": per_place, "total": tot,
                                         "false_per_place_year": tot["false"] / (years * len(fusion.PLACES))}
            if pname != "TRAIN":
                allp = [], []
                for name in fusion.PLACES:
                    tr = restrict(src[cfg.name][name], lo, min(hi, history.LABEL_END) if pname == "TEST" else hi)
                    ys = [series[name].label(t) for t in tr.times]
                    for p, y in zip(tr.probs, ys):
                        if y is not None:
                            allp[0].append(p)
                            allp[1].append(y)
                cs["calibration"][pname] = pooled_calibration(allp[0], allp[1], [
                    (priors[n], series[n].label(t)) for n in fusion.PLACES
                    for t in restrict(src[cfg.name][n], lo, min(hi, history.LABEL_END) if pname == "TEST" else hi).times])
        for name in fusion.PLACES:
            c = crossings[name]
            tr = ev_tracks[cfg.name][name]
            cs["event_leads"][name] = lead_time_h(tr, episodes(tr), c)[0] if c else None
        summary["configs"][cfg.name] = cs

    print("\n## Ablations: 2024 lead time per place (h), false alarms per place-year (TEST, 2023-01 → 2024-04), Brier (TEST / 2024)")
    names = list(fusion.PLACES)
    print("| Config | " + " | ".join(names) + " | False alarms TEST (per place-year) | Alert episodes TEST (hits / false / unverif.) | Brier TEST | BSS TEST | Brier 2024 | BSS 2024 |")
    for cfg in configs:
        cs = summary["configs"][cfg.name]
        fa = cs["false_alarms"]["TEST"]
        ct, ce = cs["calibration"]["TEST"], cs["calibration"]["2024 window"]
        print(f"| {cfg.name} | " + " | ".join(fmt_h(cs["event_leads"][n]) if cs["event_leads"][n] is not None else "missed" for n in names)
              + f" | {fa['total']['false']} ({fa['false_per_place_year']:.2f}) | {fa['total']['hits']} / {fa['total']['false']} / {fa['total']['unverifiable']}"
              + f" | {ct['brier']:.4f} | {ct['bss']:.2f} | {ce['brier']:.4f} | {ce['bss']:.2f} |")

    print("\n## Alert episodes per place: hits/false/unverifiable (calibrated full and hand-set; TEST, TRAIN, 2024 window)")
    for cfg_name in ("full", "handset"):
        for pname in ("TEST", "TRAIN", "2024 window"):
            fa = summary["configs"][cfg_name]["false_alarms"][pname]
            shares = sorted(fa["total"]["false_peak_share"])
            print(f"{cfg_name} {pname} ({fa['years']:.2f} y): " + "; ".join(
                f"{n} {v['hits']}/{v['false']}/{v['unverifiable']}" for n, v in fa["per_place"].items())
                + (f"; false-alarm peak / flood level: min {shares[0]:.2f}, median {shares[len(shares) // 2]:.2f}, max {shares[-1]:.2f}" if shares else ""))

    print("\n## Reliability table (calibrated full), TEST and 2024 window")
    for pname in ("TEST", "2024 window"):
        c = summary["configs"]["full"]["calibration"][pname]
        print(f"-- {pname}: n={c['n']} positives={c['positives']} brier={c['brier']:.4f} climatology={c['brier_climatology']:.4f}")
        for b in c["bins"]:
            print(f"| {b['bin']} | {b['n']} | {b['mean_p']:.3f} | {b['observed']:.3f} |")
    c = summary["configs"]["handset"]["calibration"]
    print(f"-- handset: TEST brier={c['TEST']['brier']:.4f}, 2024 brier={c['2024 window']['brier']:.4f}")
    for b in c["2024 window"]["bins"]:
        print(f"| handset 2024 {b['bin']} | {b['n']} | {b['mean_p']:.3f} | {b['observed']:.3f} |")

    # --- artefacts ----------------------------------------------------------------------
    full_cfg = next(c for c in configs if c.name == "full")
    write_fused_csv(ev_steps, priors, full_cfg, OUT_DIR / "fused_2024.csv")
    kh = key_hours(ev_steps, priors, full_cfg, ev_tracks["full"])
    (OUT_DIR / "key_hours.json").write_text(json.dumps(kh, indent=1, ensure_ascii=False, default=str))
    (OUT_DIR / "summary.json").write_text(json.dumps(summary, indent=1, ensure_ascii=False, default=str))
    print(f"\nkey hours: {len(kh)} -> {OUT_DIR / 'key_hours.json'}")
    for k in kh:
        s = k["state"]
        print(f"{k['place']:12} {k['kind']:17} {s['t_local']} p={s['probability']:.3f} {s['level']} silent={s['silent_gauges']}")
    return 0


def pooled_calibration(ps: list[float], ys: list[int], clim_pairs: list[tuple[float, int | None]]) -> dict:
    if not ps:
        return {"n": 0}
    n = len(ps)
    brier = sum((p - y) ** 2 for p, y in zip(ps, ys)) / n
    cp = [(p, y) for p, y in clim_pairs if y is not None]
    clim = sum((p - y) ** 2 for p, y in cp) / len(cp)
    bins = []
    for lo, hi in zip(PROB_BINS, PROB_BINS[1:]):
        sel = [(p, y) for p, y in zip(ps, ys) if lo <= p < hi]
        if sel:
            bins.append({"bin": f"[{lo:g}, {min(hi, 1):g})", "n": len(sel),
                         "mean_p": sum(p for p, _ in sel) / len(sel), "observed": sum(y for _, y in sel) / len(sel)})
    return {"n": n, "positives": sum(ys), "brier": brier, "brier_climatology": clim,
            "bss": 1 - brier / clim if clim > 0 else None, "bins": bins}


if __name__ == "__main__":
    sys.exit(main())
