"""Scope of the backtest: event window and the stations we care about.

Station codes were taken from the live inventories on 2026-09-30
(ANA ``ListaEstacoesTelemetricas``, INMET 2024 bulk file, CEMS EMSR720).
"""

from datetime import date

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
