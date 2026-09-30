"""Load CARE to Compare Wind Farm A as per-turbine series plus a fault table.

CARE ships one CSV per *event*, each holding about a year of 10-minute SCADA for
one turbine. Several files cover the same turbine and overlap in time, so the
per-turbine series is the de-duplicated union of those files.

Wind Farm A is the EDP open-data wind farm with CARE's timestamps shifted
forward. Two facts, both checked in ``audit.py`` and in docs/DATA.md:

* Most Farm A files are shifted by exactly 2191 days (2017-08-11 -> 2023-08-11).
  Files 40 and 71, the two that start on 2022-01-01, are shifted by 2192 days:
  their rows equal the other files' rows one day earlier.
* After undoing the shift, 11 of CARE's 12 anomaly-event ends sit 0-13 minutes
  after an EDP failure-logbook timestamp (the next 10-minute stamp), which also
  gives the CARE asset id -> EDP turbine id mapping. The 12th (event 51) ends
  7.5 h after the same T06 gearbox entry that event 72 already matches.

So Farm A can be put back on the EDP calendar and joined with the full EDP
failure logbooks (2016 + 2017), not only the 12 events CARE kept.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

import pandas as pd

from .download import DEFAULT_DATA_DIR, EDP_DIR

META_COLUMNS = ["time_stamp", "asset_id", "id", "train_test", "status_type_id"]
STATUS_NAMES = {0: "normal", 1: "derated", 2: "idling", 3: "service", 4: "downtime", 5: "other"}

# Farm A: days to subtract to go from CARE's anonymised calendar to EDP's.
FARM_A_SHIFT_DAYS = 2191
FARM_A_EXTRA_SHIFT_DAYS = {40: 1, 71: 1}  # files whose shift is 2192 days

# CARE Farm A asset_id -> EDP turbine id. Derived by matching anomaly-event ends
# to the EDP logbooks (see audit.py).
FARM_A_TURBINES = {0: "T07", 10: "T09", 11: "T01", 13: "T11", 21: "T06"}

COMPONENT_PATTERNS = [
    ("generator_bearing", r"generator bearing"),
    ("gearbox", r"gearbox|gear oil|\bgear\b"),
    ("generator", r"generator"),
    ("hydraulic", r"hydraulic"),
    ("transformer", r"transformer"),
    ("pitch", r"pitch|axis \d|blade"),
    ("converter", r"converter|inverter"),
    ("rotor_bearing", r"rotor ?bearing|main bearing"),
    ("yaw", r"\byaw\b"),
]


def farm_dir(farm: str, data_dir: Path = DEFAULT_DATA_DIR) -> Path:
    return data_dir / f"Wind Farm {farm}"


def normalise_component(text: str | float | None) -> str:
    """Map a free-text fault description to a coarse component name."""
    if not isinstance(text, str) or not text.strip():
        return "unknown"
    low = text.lower().replace("_", " ")
    for name, pattern in COMPONENT_PATTERNS:
        if re.search(pattern, low):
            return name
    return "other"


def read_event_info(farm: str = "A", data_dir: Path = DEFAULT_DATA_DIR, edp_calendar: bool = True) -> pd.DataFrame:
    """CARE event table, one row per dataset file (anomaly or normal)."""
    df = pd.read_csv(farm_dir(farm, data_dir) / "event_info.csv", sep=";")
    df = df.rename(columns={"asset": "asset_id"})
    for col in ("event_start", "event_end"):
        df[col] = pd.to_datetime(df[col])
    df["component"] = df["event_description"].map(normalise_component)
    df.loc[df["event_label"] == "normal", "component"] = None
    if farm == "A" and edp_calendar:
        shift = df["event_id"].map(lambda e: pd.Timedelta(days=FARM_A_SHIFT_DAYS + FARM_A_EXTRA_SHIFT_DAYS.get(e, 0)))
        df["event_start"] -= shift
        df["event_end"] -= shift
        df["turbine_id"] = df["asset_id"].map(FARM_A_TURBINES)
    return df.sort_values(["asset_id", "event_start"]).reset_index(drop=True)


def read_dataset(
    farm: str,
    event_id: int,
    data_dir: Path = DEFAULT_DATA_DIR,
    columns: list[str] | None = None,
    edp_calendar: bool = True,
) -> pd.DataFrame:
    """One CARE dataset file, with a parsed ``time_stamp``."""
    usecols = None if columns is None else list(dict.fromkeys(META_COLUMNS + columns))
    df = pd.read_csv(farm_dir(farm, data_dir) / "datasets" / f"{event_id}.csv", sep=";", usecols=usecols)
    df["time_stamp"] = pd.to_datetime(df["time_stamp"])
    if farm == "A" and edp_calendar:
        df["time_stamp"] -= pd.Timedelta(days=FARM_A_SHIFT_DAYS + FARM_A_EXTRA_SHIFT_DAYS.get(event_id, 0))
    df["source_event_id"] = event_id
    return df


def merge_datasets(frames: list[pd.DataFrame]) -> pd.DataFrame:
    """Union of overlapping files for one turbine, one row per timestamp.

    Overlapping files agree row-for-row once aligned, so which copy wins does not
    matter for sensor values; we keep the first. ``train_test`` is dropped
    because it is relative to each file's own event, not to the turbine.
    """
    df = pd.concat(frames, ignore_index=True)
    df = df.sort_values(["time_stamp", "source_event_id"]).drop_duplicates("time_stamp", keep="first")
    return df.drop(columns=["train_test", "id"], errors="ignore").set_index("time_stamp")


def turbine_series(
    asset_id: int,
    farm: str = "A",
    data_dir: Path = DEFAULT_DATA_DIR,
    columns: list[str] | None = None,
    cache: bool = True,
) -> pd.DataFrame:
    """Tidy 10-minute series for one turbine: index time_stamp, one row per timestamp."""
    cache_path = data_dir.parent / "cache" / f"farm{farm}_asset{asset_id}.parquet"
    if cache and columns is None and cache_path.exists():
        return pd.read_parquet(cache_path)
    events = read_event_info(farm, data_dir)
    ids = events.loc[events["asset_id"] == asset_id, "event_id"].tolist()
    if not ids:
        raise KeyError(f"no datasets for asset {asset_id} in farm {farm}")
    df = merge_datasets([read_dataset(farm, e, data_dir, columns) for e in ids])
    if farm == "A":
        df.insert(1, "turbine_id", FARM_A_TURBINES.get(asset_id))
    if cache and columns is None:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(cache_path)
    return df


def iter_turbines(farm: str = "A", data_dir: Path = DEFAULT_DATA_DIR, **kwargs) -> Iterator[tuple[int, pd.DataFrame]]:
    for asset_id in sorted(read_event_info(farm, data_dir)["asset_id"].unique()):
        yield int(asset_id), turbine_series(int(asset_id), farm, data_dir, **kwargs)


def read_edp_logbook(edp_dir: Path = EDP_DIR) -> pd.DataFrame:
    """EDP failure logbooks 2016 + 2017: one row per recorded failure."""
    frames = [pd.read_excel(p) for p in sorted(edp_dir.glob("failures-*.xlsx"))]
    if not frames:
        raise FileNotFoundError(f"no EDP logbooks in {edp_dir}; run the downloader")
    df = pd.concat(frames, ignore_index=True)
    df["Timestamp"] = pd.to_datetime(df["Timestamp"], utc=True).dt.tz_localize(None)
    return df.rename(columns={"Turbine_ID": "turbine_id", "Component": "component_edp", "Timestamp": "fault_time", "Remarks": "remarks"})


def fault_events(
    data_dir: Path = DEFAULT_DATA_DIR, edp_dir: Path = EDP_DIR, match_tolerance: pd.Timedelta = pd.Timedelta(hours=12)
) -> pd.DataFrame:
    """Fault table for Farm A on the EDP calendar.

    Columns: fault_id, asset_id, turbine_id, fault_time, component, component_edp,
    remarks, care_event_id (the CARE anomaly event that ends at this fault, if any).
    """
    log = read_edp_logbook(edp_dir)
    asset_of = {t: a for a, t in FARM_A_TURBINES.items()}
    log["asset_id"] = log["turbine_id"].map(asset_of)
    log["component"] = log["component_edp"].str.lower()
    care = read_event_info("A", data_dir)
    care = care[care["event_label"] == "anomaly"]
    log["care_event_id"] = pd.NA
    for i, row in log.iterrows():
        cands = care[(care["asset_id"] == row["asset_id"]) & ((care["event_end"] - row["fault_time"]).abs() <= match_tolerance)]
        if len(cands):
            log.at[i, "care_event_id"] = ",".join(str(e) for e in sorted(cands["event_id"]))
    log = log.sort_values(["fault_time", "turbine_id"]).reset_index(drop=True)
    log.insert(0, "fault_id", range(len(log)))
    return log[["fault_id", "asset_id", "turbine_id", "fault_time", "component", "component_edp", "remarks", "care_event_id"]]
