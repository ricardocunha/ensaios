"""Point-in-time access to observations: the no-look-ahead boundary.

Signal adapters never see the dataset directly. They get a :class:`Snapshot`
taken at time ``t``, which only returns what was *available* at ``t``:

- an hourly row is available at ``hour_end + latency`` (its last reading
  cannot be known before the hour closes; ``latency`` models transmission);
- a Copernicus EMS product is available at its delivery (publication) time,
  not at the time the image was acquired.

Anything the snapshot does not return cannot leak into a signal.
"""

from __future__ import annotations

from bisect import bisect_right
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from .dataset import HourRow
from .sources.copernicus_ems import Product


def product_available_at(p: Product) -> datetime | None:
    """Delivery time (UTC) of an EMS product; None if it was never delivered."""
    if not p.delivered:
        return None
    return datetime.fromisoformat(p.delivered).replace(tzinfo=timezone.utc)


class Store:
    """All observations of a replay, indexed by availability time."""

    def __init__(
        self,
        rows: Iterable[HourRow],
        products: Iterable[Product] = (),
        *,
        latency: timedelta = timedelta(0),
    ):
        self.latency = latency
        series: dict[tuple[str, str], list[HourRow]] = {}
        for r in rows:
            series.setdefault((r.source, r.station), []).append(r)
        self._series = {k: sorted(v, key=lambda r: r.hour_end) for k, v in series.items()}
        self._avail = {k: [r.available_at + latency for r in v] for k, v in self._series.items()}
        prods = [(product_available_at(p), p) for p in products]
        prods = sorted(((t, p) for t, p in prods if t is not None), key=lambda x: x[0])
        self._products = [p for _, p in prods]
        self._product_avail = [t for t, _ in prods]

    def keys(self) -> list[tuple[str, str]]:
        return sorted(self._series)

    def as_of(self, t: datetime) -> Snapshot:
        return Snapshot(self, t)


@dataclass(frozen=True)
class Snapshot:
    store: Store
    t: datetime

    def rows(self, source: str, station: str) -> Sequence[HourRow]:
        """Rows of one station available at ``t``, oldest first."""
        key = (source, station)
        avail = self.store._avail.get(key)
        if avail is None:
            return []
        return self.store._series[key][: bisect_right(avail, self.t)]

    def stations(self, source: str) -> list[str]:
        return [st for src, st in self.store.keys() if src == source]

    def products(self) -> list[Product]:
        """EMS products delivered at or before ``t``."""
        return self.store._products[: bisect_right(self.store._product_avail, self.t)]
