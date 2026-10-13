"""What the diagnosis agent may know about one anomaly episode, at the moment it decides.

Everything is cut at ``decision_time = start + 1 day`` (the end of the first
alarm day): the ``Situation`` summary is rebuilt from that day alone, and the
maintenance log holds only rows with ``fault_time < decision_time``.
Labels (``runs/m2_episodes_eval.csv``) are never read here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from .evaluate import episode_attribution
from .features import DETECTOR_SIGNALS, SIGNAL_GROUPS, SIGNAL_LABEL

DAY = pd.Timedelta(days=1)
DETECTOR = "iforest_resid"
SCORE_COL = "score_iforest_resid_s0"  # the detector/seed the m2 episode table was built from

# The agent answers in the logbook's vocabulary.
COMPONENTS = ("generator", "generator_bearing", "gearbox", "hydraulic_group", "transformer")
GROUP_COMPONENT = {
    "generator": "generator",
    "generator_bearing": "generator_bearing",
    "gearbox": "gearbox",
    "hydraulic": "hydraulic_group",
    "hub": "hydraulic_group",  # the hydraulic group sits in the hub (see features.LOGBOOK_GROUP)
    "transformer": "transformer",
}
CONTEXT_SIGNALS = [s for g in ("converter", "nacelle") for s in SIGNAL_GROUPS[g]]
VECTOR_SIGNALS = DETECTOR_SIGNALS + CONTEXT_SIGNALS  # 14 + 10 = 24 dimensions


def signal_vector(z: pd.Series) -> np.ndarray:
    """Similarity features: sign(z) * log1p(|z|) per signal, missing = 0 (as expected).

    The log compresses the heavy tail but keeps direction (hot and cold are different situations).
    """
    v = np.array([z.get(f"z_{s}", np.nan) for s in VECTOR_SIGNALS], dtype=float)
    v = np.nan_to_num(v, nan=0.0)
    return np.sign(v) * np.log1p(np.abs(v))


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    na, nb = float(np.linalg.norm(a)), float(np.linalg.norm(b))
    if na == 0 or nb == 0:
        return 0.0
    return float(a @ b / (na * nb))


def fmt_z(signal: str, z: float) -> str:
    return f"{SIGNAL_LABEL.get(signal, signal)} {z:+.1f}"


@dataclass(frozen=True)
class Situation:
    """One episode as known at its decision time (first alarm day, end of day)."""

    episode_id: int
    turbine_id: str
    start: pd.Timestamp  # first alarm day (00:00)
    decision_time: pd.Timestamp
    score: float
    top_group: str | None
    top_signals: str
    context_signal: str
    vector: np.ndarray = field(repr=False, compare=False)

    @property
    def top_component(self) -> str | None:
        return GROUP_COMPONENT.get(self.top_group) if self.top_group else None

    def summary(self) -> str:
        """One line, used both in the prompt and in memory."""
        comp = f" (logbook component {self.top_component})" if self.top_component else ""
        return (
            f"{self.turbine_id} {self.start.date()}: detector score {self.score:.1f}; "
            f"top group {self.top_group}{comp}; top signals {self.top_signals or 'n/a'}"
        )


@dataclass
class ReplayData:
    """Daily scores, logbook rows and episodes (no labels)."""

    daily: pd.DataFrame  # index: day; columns turbine_id, score_*, z_*
    faults: pd.DataFrame  # logbook rows: fault_id, turbine_id, fault_time, component, remarks
    episodes: pd.DataFrame  # episode_id, turbine_id, start (no label columns)
    score_col: str = SCORE_COL
    alarm_k: float = 2.5
    _by_turbine: dict = field(default_factory=dict, init=False, repr=False)

    def __post_init__(self) -> None:
        label_cols = {"next_incident_id", "days_before_incident", "incident_component", "healthy_start"}
        if label_cols & set(self.episodes.columns):
            raise ValueError("ReplayData must not hold episode labels")
        self.episodes = self.episodes.copy()
        self.episodes["start"] = pd.to_datetime(self.episodes["start"])
        self.faults = self.faults.sort_values("fault_time").reset_index(drop=True)
        for t, g in self.daily.groupby("turbine_id"):
            self._by_turbine[t] = g.sort_index()

    @classmethod
    def load(cls, runs_dir: Path, tag: str = "m2") -> ReplayData:
        from .data import fault_events

        daily = pd.read_parquet(runs_dir / f"{tag}_daily_scores.parquet")
        ep = pd.read_csv(runs_dir / f"{tag}_episodes.csv")
        ep = ep[ep["detector"] == DETECTOR].reset_index(drop=True)
        k = float(ep["k"].iloc[0])
        f = fault_events()[["fault_id", "turbine_id", "fault_time", "component", "remarks"]]
        return cls(daily=daily, faults=f, episodes=ep[["episode_id", "turbine_id", "start"]], alarm_k=k)

    # ------------------------------------------------------------ situations

    def turbine_days(self, turbine: str, until: pd.Timestamp) -> pd.DataFrame:
        """Daily rows of one turbine for days < ``until`` (a day's row is complete at day + 1)."""
        d = self._by_turbine[turbine]
        return d[d.index + DAY <= until]

    def situation(self, episode_id: int) -> Situation:
        e = self.episodes.loc[self.episodes["episode_id"] == episode_id].iloc[0]
        start = pd.Timestamp(e.start).normalize()
        decision = start + DAY
        d_t = self.turbine_days(e.turbine_id, decision)
        if start not in d_t.index:
            raise KeyError(f"no score for {e.turbine_id} on {start.date()}")
        att = episode_attribution(d_t, start, start)
        row = d_t.loc[start]
        return Situation(
            episode_id=int(episode_id),
            turbine_id=e.turbine_id,
            start=start,
            decision_time=decision,
            score=float(row[self.score_col]),
            top_group=att["component_group"],
            top_signals=att["top_signals"],
            context_signal=att.get("context_signal", ""),
            vector=signal_vector(row),
        )

    def situations(self) -> list[Situation]:
        """All episodes in replay order: decision time, then episode id."""
        s = [self.situation(int(i)) for i in self.episodes["episode_id"]]
        return sorted(s, key=lambda x: (x.decision_time, x.episode_id))

    # ------------------------------------------------------------ tools

    def residual_series(self, s: Situation, group: str, days: int = 14) -> str:
        """Daily residual z of one component group's signals, last ``days`` days up to the first alarm day."""
        if group not in SIGNAL_GROUPS:
            return f"unknown group {group!r}; choose one of {sorted(SIGNAL_GROUPS)}"
        days = int(min(max(days, 1), 60))
        d_t = self.turbine_days(s.turbine_id, s.decision_time)
        d_t = d_t[d_t.index > s.start - days * DAY]
        cols = [f"z_{c}" for c in SIGNAL_GROUPS[group] if f"z_{c}" in d_t.columns]
        if d_t.empty or not cols:
            return "no data"
        out = d_t[cols + [self.score_col]].rename(
            columns={f"z_{c}": SIGNAL_LABEL.get(c, c) for c in SIGNAL_GROUPS[group]} | {self.score_col: "detector score"}
        )
        out.index = out.index.strftime("%Y-%m-%d")
        return f"{group} residual z (0 = as the normal-behaviour model expects), turbine {s.turbine_id}:\n" + out.round(1).to_string(na_rep="-")

    def context(self, s: Situation) -> str:
        """Converter/nacelle residuals and operating context on the first alarm day."""
        d_t = self.turbine_days(s.turbine_id, s.decision_time)
        row = d_t.loc[s.start]
        ctx = [(c, row.get(f"z_{c}", np.nan)) for c in CONTEXT_SIGNALS]
        ctx = sorted([(c, float(v)) for c, v in ctx if pd.notna(v)], key=lambda x: -abs(x[1]))
        others = []
        for t, g in self._by_turbine.items():
            if t == s.turbine_id or s.start not in g.index:
                continue
            v = g.loc[s.start, self.score_col]
            if pd.notna(v):
                others.append(f"{t} {float(v):.1f}" + (" (alarm)" if v > self.alarm_k else ""))
        lines = [
            f"Hours with data on {s.start.date()}: {int(row.get('n_hours', 0))}",
            "Converter/nacelle residual z (context, not alarmed on): " + (", ".join(fmt_z(c, v) for c, v in ctx[:5]) or "n/a"),
            f"Other turbines' detector score the same day (alarm above {self.alarm_k}): " + (", ".join(others) or "n/a"),
        ]
        return "\n".join(lines)

    def maintenance_log(self, s: Situation, max_rows: int = 5) -> str:
        """Logbook rows on this turbine recorded before the decision time (most recent last)."""
        f = self.faults[(self.faults["turbine_id"] == s.turbine_id) & (self.faults["fault_time"] < s.decision_time)]
        if f.empty:
            return f"No logbook entries on {s.turbine_id} before {s.decision_time.date()}."
        f = f.tail(max_rows)
        return "\n".join(
            f"{r.fault_time:%Y-%m-%d %H:%M} {r.component}: {r.remarks} ({(s.start - r.fault_time.normalize()).days} days before the first alarm)"
            for r in f.itertuples()
        )

