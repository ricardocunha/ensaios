"""Scope of the backtest: event window and the stations we care about.

Station codes were taken from the live inventories on 2026-09-30
(ANA ``ListaEstacoesTelemetricas``, INMET 2024 bulk file, CEMS EMSR720).
"""

from datetime import date, datetime, timedelta, timezone

EVENT_START = date(2024, 4, 20)
EVENT_END = date(2024, 5, 20)

# ANA telemetric stations (code -> name, river). Taquari main stem from
# upstream to downstream, then the Guaíba at Porto Alegre.
ANA_STATIONS: dict[str, tuple[str, str]] = {
    "86510000": ("Muçum", "Rio Taquari"),
    "86720000": ("Encantado", "Rio Taquari"),
    "86879300": ("Estrela", "Rio Taquari"),
    "86950000": ("Taquari", "Rio Taquari"),
    "87242000": ("Terminal CatSul Guaíba", "Lago Guaíba"),
    "87450004": ("Cais Mauá C6", "Rio Guaíba"),
    "87450020": ("Usina do Gasômetro", "Rio Guaíba"),
}

# INMET automatic stations in or next to the Taquari-Antas / Guaíba basins.
INMET_STATIONS: dict[str, str] = {
    "A840": "Bento Gonçalves",
    "A882": "Teutônia",
    "A837": "Soledade",
    "A894": "Serafina Corrêa",
    "A844": "Lagoa Vermelha",
    "A879": "Canela",
    "A801": "Porto Alegre - Jardim Botânico",
}

# Copernicus EMS Rapid Mapping activation for this event.
EMS_ACTIVATION = "EMSR720"

# --- Milestone 2: time conventions and the replay window -------------------

# ANA ``DataHora`` is local legal time, UTC-3 (Brazil has had no DST since
# 2019). Verified empirically: see docs/DATA.md, "Time conventions".
ANA_UTC_OFFSET = timedelta(hours=-3)

# Backtest window in UTC days (INMET's native clock): 744 hourly steps.
WINDOW_START_UTC = datetime(2024, 4, 20, tzinfo=timezone.utc)
WINDOW_END_UTC = datetime(2024, 5, 21, tzinfo=timezone.utc)
# Rolling 72 h rain needs three days of history before the window opens.
WARMUP = timedelta(hours=72)

# Historical ANA record used for station thresholds. It ends the day before
# the event window, so no event reading leaks into a threshold.
HISTORY_START = date(2019, 1, 1)
HISTORY_END = date(2024, 4, 19)

# Where each station is (municipality). ANA: gauge location; INMET: station name.
STATION_PLACE: dict[str, str] = {
    "86510000": "Muçum",
    "86720000": "Encantado",
    "86879300": "Estrela",
    "86950000": "Taquari",
    "87242000": "Guaíba",
    "87450004": "Porto Alegre",
    "87450020": "Porto Alegre",
    "A840": "Bento Gonçalves",
    "A882": "Teutônia",
    "A837": "Soledade",
    "A894": "Serafina Corrêa",
    "A844": "Lagoa Vermelha",
    "A879": "Canela",
    "A801": "Porto Alegre",
}

# Official flood levels ("cota de inundação", cm, on each gauge's own datum).
# Taquari stations: SGB SACE Taquari bulletins (column "Nível de Inundação"); sources in docs/DATA.md.
# Cais Mauá: [[VERIFY: primary source for the Cais Mauá 300 cm flood level]].
# Gasômetro: none confirmed [[VERIFY: Gasômetro flood level]]; Terminal CatSul: none found.
FLOOD_LEVEL_CM: dict[str, float] = {
    "86510000": 1800.0,  # Muçum
    "86720000": 1200.0,  # Encantado
    "86879300": 1900.0,  # Estrela (gauge section in Lajeado)
    "86950000": 850.0,  # Taquari
    "87450004": 300.0,  # Cais Mauá C6, Porto Alegre [[VERIFY]]
}
