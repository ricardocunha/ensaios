"""Copernicus EMS adapter: EMSR720 flood extent as a *label*, not a warning input.

The first EMSR720 flood delineation was acquired on 2024-05-04 09:48 UTC and
delivered later, two days after the Taquari peak. It can confirm that an area
flooded; it cannot have warned anyone. So these signals have
``kind="label"`` and ``likelihood_ratio=None``: the backtest may use them to
score alerts, fusion must not use them as evidence.

A product becomes visible only at its delivery time (``version.deliveryTime``
in the activation JSON), never at acquisition time.
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
