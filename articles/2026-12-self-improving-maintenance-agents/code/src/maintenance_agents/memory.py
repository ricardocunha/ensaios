"""Episodic memory with outcomes that arrive only when they would in reality, plus context gating.

**When the outcome becomes known** (``resolve_outcome``), from the logbook only:
a row on the same turbine dated in ``[start, start + H]`` is known at its
``fault_time``; with no such row, "no failure" is known at ``start + (H + 1) days``.
The window includes the first alarm day, which the scoring labels exclude.
``MemoryStore.visible(now)`` hides an outcome until ``known_at <= now``. Scoring
labels are never used here. Retrieval and gating: docs/RESULTS.md, milestone 3 "Setup".
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field, replace
from typing import Literal

import pandas as pd

from .episodes import DAY, Situation, cosine

HORIZON_DAYS = 30


@dataclass(frozen=True)
class Outcome:
    kind: Literal["failure", "no_failure"]
    known_at: pd.Timestamp
    component: str | None = None
    remarks: str | None = None
    fault_time: pd.Timestamp | None = None
    days_after_start: int | None = None
    horizon_days: int = HORIZON_DAYS

    def text(self) -> str:
        if self.kind == "failure":
            return (
                f"logbook failure on {self.fault_time:%Y-%m-%d}, component {self.component} "
                f'("{self.remarks}"), {self.days_after_start} days after the first alarm'
            )
        return f"no logbook failure on this turbine within {self.horizon_days} days"


def resolve_outcome(s: Situation, faults: pd.DataFrame, horizon_days: int = HORIZON_DAYS) -> Outcome:
    """The outcome of an episode and the time it becomes known (see module docstring)."""
    f = faults[faults["turbine_id"] == s.turbine_id]
    day = f["fault_time"].dt.normalize()
    hit = f[(day >= s.start) & (day <= s.start + horizon_days * DAY)].sort_values("fault_time")
    if len(hit):
        r = hit.iloc[0]
        return Outcome(
            kind="failure",
            known_at=r.fault_time,
            component=r.component,
            remarks=str(r.remarks),
            fault_time=r.fault_time,
            days_after_start=int((r.fault_time.normalize() - s.start).days),
            horizon_days=horizon_days,
        )
    return Outcome(kind="no_failure", known_at=s.start + (horizon_days + 1) * DAY, horizon_days=horizon_days)


def lesson(diagnosis: dict, outcome: Outcome) -> str:
    """What the outcome says about the diagnosis, in one sentence. Deterministic, no model."""
    action, comp = diagnosis.get("action"), diagnosis.get("component")
    if outcome.kind == "failure":
        a = "inspecting was right" if action == "inspect" else f"'{action}' missed it; inspecting was warranted"
        c = "and the component was right" if comp == outcome.component else f"; the failed component was {outcome.component}, not {comp}"
        return f"{a} {c}.".replace(" ;", ";")
    if action == "inspect":
        return "no failure followed: the inspection would have found nothing logged."
    return f"no failure followed: '{action}' was fine."


@dataclass(frozen=True)
class MemoryRecord:
    situation: Situation
    diagnosis: dict  # Diagnosis.model_dump()
    decided_at: pd.Timestamp
    outcome: Outcome  # hidden until outcome.known_at


@dataclass(frozen=True)
class MemoryView:
    """A record as seen at time ``now``: outcome and lesson are None while pending."""

    record: MemoryRecord
    now: pd.Timestamp
    outcome: Outcome | None
    lesson: str | None

    @property
    def situation(self) -> Situation:
        return self.record.situation


@dataclass(frozen=True)
class Candidate:
    view: MemoryView
    similarity: float
    age_days: float


class MemoryStore:
    """Append-only; ``visible(now)`` is the only way to read it."""

    def __init__(self) -> None:
        self._records: list[MemoryRecord] = []

    def __len__(self) -> int:
        return len(self._records)

    def add(self, record: MemoryRecord) -> None:
        if self._records and record.decided_at < self._records[-1].decided_at:
            raise ValueError("memories must be added in time order")
        self._records.append(record)

    def visible(self, now: pd.Timestamp) -> list[MemoryView]:
        out = []
        for r in self._records:
            if r.decided_at > now:
                continue
            known = r.outcome.known_at <= now
            out.append(MemoryView(r, now, r.outcome if known else None, lesson(r.diagnosis, r.outcome) if known else None))
        return out

    def candidates(self, query: Situation, now: pd.Timestamp) -> list[Candidate]:
        """Every visible memory (other than the query itself), most similar first; ties: most recent first."""
        c = [
            Candidate(v, cosine(query.vector, v.situation.vector), (now - v.record.decided_at) / DAY)
            for v in self.visible(now)
            if v.situation.episode_id != query.episode_id
        ]
        return sorted(c, key=lambda x: (-x.similarity, x.age_days, x.view.situation.episode_id))


@dataclass(frozen=True)
class GatePolicy:
    """Which memories may enter the prompt. Values were fixed before any model run."""

    name: str = "gated"
    require_outcome: bool = True
    min_similarity: float = 0.5
    max_age_days: float | None = 365.0
    scope: Literal["any", "same_turbine", "same_turbine_or_group"] = "same_turbine_or_group"
    max_k: int = 3

    def with_(self, **kw) -> GatePolicy:
        return replace(self, **kw)


GATED = GatePolicy()
# "memory without gating": the k most similar past episodes, with no filter at all.
# Same k, so the arms differ only by the filters.
UNGATED = GatePolicy(name="ungated", require_outcome=False, min_similarity=-1.0, max_age_days=None, scope="any", max_k=3)


@dataclass
class GateResult:
    selected: list[Candidate]
    rejected: list[tuple[Candidate, str]] = field(default_factory=list)

    def reasons(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for _, r in self.rejected:
            out[r] = out.get(r, 0) + 1
        return out


def rejection_reason(c: Candidate, query: Situation, policy: GatePolicy) -> str | None:
    """The first rule a candidate fails, or None. Rules are checked in this fixed order."""
    s = c.view.situation
    if policy.require_outcome and c.view.outcome is None:
        return "outcome_pending"
    if c.similarity < policy.min_similarity:
        return "low_similarity"
    if policy.max_age_days is not None and c.age_days > policy.max_age_days:
        return "too_old"
    if policy.scope == "same_turbine" and s.turbine_id != query.turbine_id:
        return "other_turbine"
    if policy.scope == "same_turbine_or_group" and s.turbine_id != query.turbine_id and s.top_group != query.top_group:
        return "other_turbine_and_group"
    return None


def gate(candidates: Iterable[Candidate], query: Situation, policy: GatePolicy) -> GateResult:
    res = GateResult(selected=[])
    for c in candidates:
        why = rejection_reason(c, query, policy)
        if why is None and len(res.selected) >= policy.max_k:
            why = "over_k"
        if why is None:
            res.selected.append(c)
        else:
            res.rejected.append((c, why))
    return res


# ---------------------------------------------------------------- track record (v2 prompt)


@dataclass(frozen=True)
class TrackRecord:
    """What happened after similar past alarms, counted at decision time.

    The pool is the arm's gate without the k cap and the outcome requirement; outcomes not known yet are ``pending``.
    """

    scope: str
    known: int
    failures: int
    failure_components: dict[str, int]
    pending: int

    @property
    def nothing(self) -> int:
        return self.known - self.failures

    @property
    def mostly_nothing(self) -> bool:
        """At least 2 known outcomes and more than half of them followed by nothing."""
        return self.known >= 2 and self.nothing * 2 > self.known

    def text(self, horizon_days: int = HORIZON_DAYS) -> str:
        head = f"Track record of {self.scope}:"
        if self.known == 0:
            body = "no past alarm with a known outcome yet."
        else:
            comps = ", ".join(f"{c} {n}" for c, n in sorted(self.failure_components.items(), key=lambda x: (-x[1], x[0])))
            body = (
                f"{self.known} with a known outcome. {self.failures} of them were followed by a logbook failure on that turbine "
                f"within {horizon_days} days" + (f" ({comps})" if comps else "") + f"; {self.nothing} were followed by nothing."
            )
        if self.pending:
            body += f" {self.pending} more {'is' if self.pending == 1 else 'are'} still pending (outcome not known yet)."
        return f"{head} {body}"


def track_record_scope(policy: GatePolicy) -> str:
    if policy.scope == "any" and policy.min_similarity <= -1 and policy.max_age_days is None:
        return "all past alarms on this farm"
    parts = [f"similarity >= {policy.min_similarity:.2f}"]
    if policy.max_age_days is not None:
        parts.append(f"<= {policy.max_age_days:.0f} days old")
    if policy.scope == "same_turbine":
        parts.append("same turbine")
    elif policy.scope == "same_turbine_or_group":
        parts.append("same turbine or same top signal group")
    return "similar past alarms (" + ", ".join(parts) + ")"


def track_record(candidates: Iterable[Candidate], query: Situation, policy: GatePolicy) -> TrackRecord:
    """Count outcomes over the arm's pool (gate rules without the k cap; pending ones counted apart)."""
    pool_policy = policy.with_(require_outcome=False)
    known = failures = pending = 0
    comps: dict[str, int] = {}
    for c in candidates:
        if rejection_reason(c, query, pool_policy) is not None:
            continue
        o = c.view.outcome  # None while the outcome is not known at c.view.now
        if o is None:
            pending += 1
            continue
        known += 1
        if o.kind == "failure":
            failures += 1
            comps[o.component] = comps.get(o.component, 0) + 1
    return TrackRecord(track_record_scope(policy), known, failures, comps, pending)
