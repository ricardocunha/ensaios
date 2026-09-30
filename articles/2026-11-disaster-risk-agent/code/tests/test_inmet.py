import io
import zipfile
from datetime import date, datetime, timezone

from disaster_risk._summary import rain_total
from disaster_risk.sources import inmet


def _text(fixtures):
    return (fixtures / "inmet_A840_sample.csv").read_bytes().decode("latin-1")


def test_parse_station_csv(fixtures):
    meta, rows = inmet.parse_station_csv(_text(fixtures))
    assert meta.code == "A840"
    assert meta.name == "BENTO GONCALVES"
    assert round(meta.lat, 4) == -29.1646
    assert rows[0].time_utc == datetime(2024, 5, 1, 10, tzinfo=timezone.utc)
    assert [r.rain_mm for r in rows[:3]] == [7.4, 8.2, 17.0]


def test_missing_values_become_none(fixtures):
    text = _text(fixtures) + "2024/05/02;0000 UTC;-9999;;;;;;;;;;;;;;;;;\n"
    _, rows = inmet.parse_station_csv(text)
    assert rows[-1].rain_mm is None


def test_rain_total_window_and_missing(fixtures):
    text = _text(fixtures) + "2024/05/02;0000 UTC;-9999;;;;;;;;;;;;;;;;;\n"
    _, rows = inmet.parse_station_csv(text)
    total, missing = rain_total(rows, date(2024, 4, 20), date(2024, 5, 20))
    assert round(total, 1) == 32.6  # 7.4 + 8.2 + 17; the 2024-04-19 row is outside
    assert missing == 1


def test_read_station_from_zip(tmp_path, fixtures):
    zpath = tmp_path / "2024.zip"
    with zipfile.ZipFile(zpath, "w") as z:
        z.writestr(
            "INMET_S_RS_A840_BENTO GONCALVES_01-01-2024_A_31-12-2024.CSV",
            (fixtures / "inmet_A840_sample.csv").read_bytes(),
        )
    meta, rows = inmet.read_station(zpath, "A840")
    assert meta.code == "A840" and len(rows) == 4
