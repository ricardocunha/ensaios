"""INMET adapter: hourly rain at automatic stations → rolling-accumulation LR.

Same rule as ANA gauge rain (see ``_rain``). INMET stations are not on the
river, so their rain is evidence about the upstream catchment, not about the
place itself; the fusion step decides which municipality they inform.
"""

from __future__ import annotations

from .. import basin
from ..observations import Snapshot
from . import Signal, _rain, missing

RAIN_RELIABILITY = 0.8


class InmetAdapter:
    name = "inmet"

    def emit(self, snap: Snapshot) -> list[Signal]:
        out = []
        for station in snap.stations("inmet"):
            rows = snap.rows("inmet", station)
            place = basin.STATION_PLACE.get(station, "")
            if not rows:
                out.append(missing("inmet_rain", station, place, snap.t, "mm", "no data yet"))
                continue
            out.append(_rain.rain_signal("inmet_rain", station, place, snap.t, rows, RAIN_RELIABILITY))
        return out
