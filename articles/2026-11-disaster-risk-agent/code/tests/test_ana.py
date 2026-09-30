from datetime import date, datetime

from disaster_risk._summary import summarize_ana
from disaster_risk.sources import ana


def test_parse_telemetry_sorts_and_keeps_empty_rows(fixtures):
    rows = ana.parse_telemetry((fixtures / "ana_telemetry.xml").read_bytes())
    assert [r.time for r in rows] == [
        datetime(2024, 4, 20, 0, 0),
        datetime(2024, 5, 2, 7, 30),
        datetime(2024, 5, 6, 12, 0),
    ]
    assert rows[1].level_cm == 2557.0 and rows[1].flow_m3s == 1103.8 and rows[1].rain_mm == 0.0
    gap = rows[2]
    assert gap.station == "86879300"
    assert gap.level_cm is None and gap.flow_m3s is None and gap.rain_mm is None


def test_parse_inventory(fixtures):
    (st,) = ana.parse_inventory((fixtures / "ana_inventory.xml").read_bytes())
    assert st.code == "86510000"
    assert st.river == "RIO TAQUARI"
    assert st.lat == -29.1672


def test_telemetry_url_uses_brazilian_dates():
    url = ana.telemetry_url("86510000", date(2024, 4, 20), date(2024, 5, 20))
    assert "codEstacao=86510000" in url
    assert "dataInicio=20/04/2024" in url and "dataFim=20/05/2024" in url


def test_summary_reports_peak(fixtures):
    rows = ana.parse_telemetry((fixtures / "ana_telemetry.xml").read_bytes())
    s = summarize_ana("86510000", rows)
    assert "max_level_cm=2557 at 2024-05-02 07:30" in s
    assert "level_rows=2" in s
