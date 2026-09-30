"""Bayesian fusion of signals into a flood-risk probability per place (plain code, no LLM).

Hypothesis, per place and replay hour ``t``:

    H(place, t) = "the place's river gauge reads at or above its official
                   flood level at some time in (t - 1 h, t + 24 h]"

Formula (naive Bayes in log-odds, with weights):

    log_odds(t) = logit(prior) + sum_i  w_i * r_i * ln(LR_i)
    p(t)        = 1 / (1 + exp(-log_odds(t)))

- ``prior``: share of TRAIN hours (ANA record 2019-01-01 → 2022-12-31) for
  which H was true at that gauge (``labels.historical_prior``).
- ``LR_i``: the signal's likelihood ratio. Two modes:
  * ``handset``: the adapter's own LR (milestone 2 rules, round numbers);
  * ``calibrated`` (default): the adapter's LR only names a *band*; the LR used
    is the band's empirical ratio P(band | H) / P(band | not H), fitted on the
    TRAIN years 2019-2022 of the historical replay, pooled across places per
    (role, source, band) (``calibration.py``).
  Missing signals have LR 1 and add nothing.
- ``r_i``: the signal's reliability, which already includes its freshness
  decay (``signals.staleness``: halves every 6 h once the reading is > 1 h
  old, zero after 72 h). Ablation ``no_decay`` divides the decay back out.
- ``w_i``: the weight of the signal's *role* for this place (a priori, not
  fitted):

      own gauge level             1.0
      upstream / neighbour level  0.5 each (the river has to travel; evidence is indirect)
      rain (ANA gauges + INMET)   1.0 for the whole group, split evenly: 1/N per station,
                                  because rain stations in one storm are strongly correlated
                                  and naive Bayes would count the same storm N times.

  Ablation ``equal_weights`` sets every w_i = 1.

Risk levels (thresholds on p, fixed before the backtest, read as plain
statements about H):

    normal     p < 0.10
    attention  p >= 0.10   ("at least 1 in 10")
    alert      p >= 0.50   ("more likely than not")
    emergency  p >= 0.90

A place's gauge that is stale for more than ``SILENT_AFTER_H`` or missing is
reported as *silent*: its last value still counts, with decayed reliability,
and the alert text must say so.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime

from .signals import Signal, staleness

LEVELS: tuple[tuple[str, float], ...] = (("normal", 0.0), ("attention", 0.10), ("alert", 0.50), ("emergency", 0.90))
LEVEL_RANK = {name: i for i, (name, _) in enumerate(LEVELS)}
SILENT_AFTER_H = 3.0

OWN_WEIGHT = 1.0
UPSTREAM_WEIGHT = 0.5
RAIN_GROUP_WEIGHT = 1.0

WARNING_SOURCES = ("ana_level", "ana_rain", "inmet_rain")


@dataclass(frozen=True)
class Place:
    """A municipality with a river gauge that has an official flood level."""

    name: str
    gauge: str  # ANA code of the place's own gauge (the one H is about)
    upstream: tuple[str, ...]  # other ANA level gauges that inform this place
    rain: tuple[tuple[str, str], ...]  # (source, station) rain signals for this place's catchment

    def role(self, source: str, station: str) -> str | None:
        if source == "ana_level":
            if station == self.gauge:
                return "gauge"
            if station in self.upstream:
                return "upstream"
            return None
        if (source, station) in self.rain:
            return "rain"
        return None


# Station → place mapping (geography, fixed before the backtest):
# - upstream gauges: the next one or two gauges up the Taquari main stem;
#   for Porto Alegre, the Taquari outlet gauge and the two other Guaíba gauges;
# - rain: the place's own ANA gauge rain, the next gauge upstream, and the INMET
#   stations in the catchment above the place (upper Taquari-Antas: Bento
#   Gonçalves, Serafina Corrêa, Soledade, Lagoa Vermelha; lower Taquari:
#   Teutônia; Guaíba: Porto Alegre and Canela, upper Caí basin).
_UPPER = (("inmet_rain", "A840"), ("inmet_rain", "A894"), ("inmet_rain", "A837"), ("inmet_rain", "A844"))
PLACES: dict[str, Place] = {
    "Muçum": Place("Muçum", "86510000", (), (("ana_rain", "86510000"),) + _UPPER),
    "Encantado": Place(
        "Encantado", "86720000", ("86510000",), (("ana_rain", "86720000"), ("ana_rain", "86510000")) + _UPPER
    ),
    "Estrela": Place(
        "Estrela", "86879300", ("86720000", "86510000"),
        (("ana_rain", "86879300"), ("ana_rain", "86720000"), ("inmet_rain", "A882")) + _UPPER,
    ),
    "Taquari": Place(
        "Taquari", "86950000", ("86879300", "86720000"),
        (("ana_rain", "86950000"), ("ana_rain", "86879300"), ("inmet_rain", "A882")) + _UPPER,
    ),
    "Porto Alegre": Place(
        "Porto Alegre", "87450004", ("86950000", "87242000", "87450020"),
        (("ana_rain", "87450004"), ("ana_rain", "87242000"), ("inmet_rain", "A801"), ("inmet_rain", "A879"),
         ("inmet_rain", "A882")),
    ),
}


@dataclass(frozen=True)
class FusionConfig:
    name: str = "handset"
    drop_sources: frozenset[str] = frozenset()
    drop_roles: frozenset[str] = frozenset()
    freshness_decay: bool = True
    equal_weights: bool = False
    # {band key: LR} from calibration.fit_lr_table; None = use the adapters' hand-set LRs
    lr_table: dict[str, float] | None = field(default=None, compare=False, hash=False)


HANDSET = FusionConfig()


def ablations(lr_table: dict[str, float]) -> tuple[FusionConfig, ...]:
    """The calibrated fusion ("full") and one variant per ablation, all with the same LR table."""
    full = FusionConfig("full", lr_table=lr_table)
    return (
        full,
        replace(full, name="no_ana_level", drop_sources=frozenset({"ana_level"})),
        replace(full, name="no_upstream_level", drop_roles=frozenset({"upstream"})),
        replace(full, name="no_ana_rain", drop_sources=frozenset({"ana_rain"})),
        replace(full, name="no_inmet_rain", drop_sources=frozenset({"inmet_rain"})),
        replace(full, name="no_freshness_decay", freshness_decay=False),
        replace(full, name="equal_weights", equal_weights=True),
    )


def band_key(role: str, source: str, handset_lr: float) -> str:
    """The band a signal is in, as named by its hand-set LR (unique per band and rule)."""
    return f"{role}|{source}|{handset_lr:g}"


@dataclass(frozen=True)
class Contribution:
    """One signal's share of the log-odds, with everything needed to explain it."""

    source: str
    station: str
    station_place: str
    role: str  # "gauge" | "upstream" | "rain"
    value: float | None
    unit: str
    likelihood_ratio: float  # as used (calibrated or hand-set)
    handset_lr: float  # the adapter's own LR (names the band)
    reliability: float  # as used (after decay, or without it in the no-decay ablation)
    weight: float
    freshness_h: float | None
    status: str
    log_odds: float  # weight * reliability * ln(LR)
    reason: str


@dataclass(frozen=True)
class FusedState:
    place: str
    t: datetime
    prior: float
    prior_log_odds: float
    log_odds: float
    probability: float
    level: str
    contributions: tuple[Contribution, ...] = field(default=())
    silent_gauges: tuple[str, ...] = ()  # level gauges (own or upstream) stale > SILENT_AFTER_H or missing


def logit(p: float) -> float:
    return math.log(p / (1 - p))


def sigmoid(x: float) -> float:
    if x >= 0:
        return 1 / (1 + math.exp(-x))
    e = math.exp(x)
    return e / (1 + e)


def risk_level(p: float) -> str:
    out = LEVELS[0][0]
    for name, lo in LEVELS:
        if p >= lo:
            out = name
    return out


def _reliability(s: Signal, cfg: FusionConfig) -> float:
    if cfg.freshness_decay or s.status != "stale":
        return s.reliability
    mult = staleness(s.freshness_h)[1]
    return s.reliability / mult if mult > 0 else 0.0


def fuse(place: Place, t: datetime, signals: Iterable[Signal], prior: float, cfg: FusionConfig = HANDSET) -> FusedState:
    """Fuse the warning signals available at ``t`` for one place. Labels (EMS) are ignored."""
    relevant = []
    for s in signals:
        if s.kind != "warning" or s.likelihood_ratio is None or s.source in cfg.drop_sources:
            continue
        role = place.role(s.source, s.station)
        if role is None or role in cfg.drop_roles:
            continue
        relevant.append((role, s))
    n_rain = len(place.rain)
    contribs = []
    for role, s in relevant:
        if cfg.equal_weights:
            w = 1.0
        else:
            w = {"gauge": OWN_WEIGHT, "upstream": UPSTREAM_WEIGHT, "rain": RAIN_GROUP_WEIGHT / n_rain}[role]
        r = _reliability(s, cfg)
        lr = s.likelihood_ratio
        if cfg.lr_table is not None and s.status != "missing":
            lr = cfg.lr_table.get(band_key(role, s.source, s.likelihood_ratio), 1.0)
        lo = w * r * math.log(lr)
        contribs.append(Contribution(
            s.source, s.station, s.place, role, s.value, s.unit, lr, s.likelihood_ratio, round(r, 4), round(w, 4),
            s.freshness_h, s.status, lo, s.reason,
        ))
    silent = tuple(
        c.station for c in contribs
        if c.source == "ana_level" and (c.status == "missing" or (c.freshness_h or 0) > SILENT_AFTER_H)
    )
    prior_lo = logit(prior)
    total = prior_lo + sum(c.log_odds for c in contribs)
    p = sigmoid(total)
    return FusedState(place.name, t, prior, prior_lo, total, p, risk_level(p), tuple(contribs), silent)


def fuse_all(
    t: datetime, signals: Sequence[Signal], priors: dict[str, float], cfg: FusionConfig = HANDSET,
    places: dict[str, Place] = PLACES,
) -> dict[str, FusedState]:
    return {name: fuse(pl, t, signals, priors[name], cfg) for name, pl in places.items()}


def without_contributions(state: FusedState) -> FusedState:
    """Compact copy for long runs (history): drops the per-signal breakdown."""
    return replace(state, contributions=())
