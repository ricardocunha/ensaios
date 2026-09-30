from datetime import datetime

from disaster_risk import reference
from disaster_risk.sources import sgb_sace
from disaster_risk.sources.ana import Reading

LISTING = """<a href='boletins/Taquari/20240501_22-20240502 - 002838.pdf'>Boletim 01/05/2024 (22h)</a>
<a href='boletins/Taquari/20240430_06-20240430 - 075404.pdf'>Boletim 30/04/2024 (06h)</a>
<a href='boletins/Taquari/20240430_06-20240430 - 075404.pdf'>dup</a>"""


def test_parse_listing_times_and_order():
    bs = sgb_sace.parse_listing(LISTING)
    assert [b.nominal for b in bs] == [datetime(2024, 4, 30, 6), datetime(2024, 5, 1, 22)]
    assert bs[0].uploaded == datetime(2024, 4, 30, 7, 54, 4)
    assert bs[1].uploaded == datetime(2024, 5, 2, 0, 28, 38)
    assert bs[0].url.endswith("20240430_06-20240430%20-%20075404.pdf")


def test_parse_bulletin_table(fixtures):
    stamp, rows = sgb_sace.parse_bulletin_text((fixtures / "sace_bulletin_20240501_22.txt").read_text())
    assert stamp == datetime(2024, 5, 1, 22)
    by = {r.station: r for r in rows}
    assert (by["Muçum"].level_cm, by["Muçum"].flood_level_cm, by["Muçum"].rain_24h_mm) == (2377, 1800, 202.4)
    assert by["Encantado"].level_cm is None and by["Encantado"].flood_level_cm == 1200  # equipment down
    assert by["Taquari"].change_24h_cm == 411 and by["Taquari"].flood_level_cm == 850
    assert by["Passo Tainhas"].flood_level_cm is None  # "#": not defined
    assert "Guaporé" not in by  # rain-only rows have no river


def test_bulletin_reference_first_at_flood(fixtures):
    _, rows = sgb_sace.parse_bulletin_text((fixtures / "sace_bulletin_20240501_22.txt").read_text())
    b = sgb_sace.parse_listing(LISTING)[1]
    ref = reference.bulletin_reference([(b, rows)])
    assert set(ref.first_at_flood) == {"86510000", "86879300", "86950000"}  # Encantado had no reading


def test_first_crossing_and_gap():
    rs = [Reading("x", datetime(2024, 5, 1, h), lv, None, None) for h, lv in [(0, 100), (1, 1800), (2, None), (5, 1900)]]
    assert reference.first_crossing(rs, 1800) == datetime(2024, 5, 1, 1)
    c = reference.crossing("x", rs, 1800)
    assert c.peak_cm == 1900 and c.peak_time == datetime(2024, 5, 1, 5)
    assert reference.longest_gap_h(rs, datetime(2024, 5, 1, 1), datetime(2024, 5, 1, 6)) == 4.0
