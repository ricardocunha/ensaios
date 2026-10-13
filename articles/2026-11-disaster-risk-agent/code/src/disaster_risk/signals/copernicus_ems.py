"""Copernicus EMS adapter: EMSR720 flood extent as a *label*, not a warning input.

The flood delineations were delivered after the Taquari peak, so these signals have ``kind="label"``
and ``likelihood_ratio=None``: the backtest may use them to score alerts, fusion must not use them as
evidence. A product becomes visible only at its delivery time, never at acquisition time.
"""

from __future__ import annotations

from datetime import datetime, timezone

from ..observations import Snapshot
from . import Signal, age_hours

LABEL_RELIABILITY = 0.9  # SAR delineation: misses flooding under canopy and in dense built-up areas


def _utc(iso: str | None) -> datetime | None:
    return None if not iso else datetime.fromisoformat(iso).replace(tzinfo=timezone.utc)


class CopernicusEmsAdapter:
    name = "copernicus_ems"

    def emit(self, snap: Snapshot) -> list[Signal]:
        out = []
        for p in snap.products():
            if p.kind != "DEL":
                continue  # grading (damage) products are not flood extent
            acquired = _utc(p.acquired)
            out.append(
                Signal(
                    source="copernicus_ems",
                    station=f"{p.activation}-AOI{p.aoi_number:02d}-{p.kind}{p.monitoring}",
                    place=p.aoi_name,
                    time=snap.t,
                    observed_at=acquired,
                    value=p.flooded_ha,
                    unit="ha flooded",
                    likelihood_ratio=None,
                    freshness_h=age_hours(snap.t, acquired),
                    reliability=LABEL_RELIABILITY,
                    status="fresh" if p.flooded_ha is not None else "missing",
                    kind="label",
                    reason=f"{p.sensor} image {p.acquired}Z, delivered {p.delivered}Z",
                    details={"delivered": p.delivered, "sensor": p.sensor},
                )
            )
        return out
