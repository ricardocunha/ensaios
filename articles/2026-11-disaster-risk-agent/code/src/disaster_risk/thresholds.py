"""Station-specific river-level thresholds from the historical ANA record.

Each ANA gauge has its own datum (Estrela sits at ~13 m in low water because of
the lock; Muçum at ~2 m), so a level only means something against that gauge's
own history. We take quantiles of every 15-min level reading from
``basin.HISTORY_START`` to ``basin.HISTORY_END`` (2019-01-01 → 2024-04-19,
i.e. strictly before the event window) and cache them in
``data/cache/level_thresholds.json``.

``uv run python -m disaster_risk.thresholds`` recomputes and prints them.
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from . import basin
from .sources import ana
from .sources._http import DATA_DIR

CACHE_NAME = "level_thresholds.json"


@dataclass(frozen=True)
class LevelThresholds:
    station: str
    n: int  # level readings in the historical record
    first: str  # first/last reading (local time, as served)
    last: str
    p50: float
    p90: float
    p99: float
    p999: float
    max: float
    max_time: str


def quantile(sorted_values: list[float], q: float) -> float:
    """Nearest-rank on the sorted sample (no interpolation between readings)."""
    return sorted_values[int(q * (len(sorted_values) - 1))]


def from_readings(station: str, readings: list[ana.Reading]) -> LevelThresholds | None:
    lv = [r for r in readings if r.level_cm is not None]
    if not lv:
        return None
    s = sorted(r.level_cm for r in lv)
    peak = max(lv, key=lambda r: r.level_cm)
    return LevelThresholds(
        station=station,
        n=len(s),
        first=f"{lv[0].time:%Y-%m-%d %H:%M}",
        last=f"{lv[-1].time:%Y-%m-%d %H:%M}",
        p50=quantile(s, 0.5),
        p90=quantile(s, 0.9),
        p99=quantile(s, 0.99),
        p999=quantile(s, 0.999),
        max=peak.level_cm,
        max_time=f"{peak.time:%Y-%m-%d %H:%M}",
    )


def compute(data_dir: Path = DATA_DIR) -> dict[str, LevelThresholds]:
    out = {}
    for code in basin.ANA_STATIONS:
        th = from_readings(code, ana.load_telemetry(code, basin.HISTORY_START, basin.HISTORY_END, data_dir))
        if th is not None:
            out[code] = th
    return out


def cache_path(data_dir: Path = DATA_DIR) -> Path:
    return data_dir / "cache" / CACHE_NAME


def load_or_compute(data_dir: Path = DATA_DIR, *, rebuild: bool = False) -> dict[str, LevelThresholds]:
    path = cache_path(data_dir)
    if path.exists() and not rebuild:
        return {k: LevelThresholds(**v) for k, v in json.loads(path.read_text()).items()}
    th = compute(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({k: asdict(v) for k, v in th.items()}, indent=1, ensure_ascii=False))
    return th


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    th = load_or_compute(rebuild="--rebuild" in argv)
    for code, (name, _) in basin.ANA_STATIONS.items():
        t = th.get(code)
        if t is None:
            print(f"{code} {name}: no level in the historical record")
            continue
        print(
            f"{code} {name}: n={t.n} {t.first}..{t.last} p50={t.p50:g} p90={t.p90:g} "
            f"p99={t.p99:g} p99.9={t.p999:g} max={t.max:g} at {t.max_time}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
