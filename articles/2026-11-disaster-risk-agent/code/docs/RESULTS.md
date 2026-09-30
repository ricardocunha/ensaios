# Results

Every number in the drafts must come from this file. Each section says which command produced it.
Times are UTC unless marked "local" (UTC-3).

## Milestone 2: dataset, signals, replay (2026-09-30)

### Hourly dataset (`make dataset` → `data/cache/hourly.csv`)

11,424 rows = 14 stations × 816 hours (72 h warm-up + the 744-hour window 2024-04-20 00Z → 2024-05-21 00Z).
Status of the primary variable per hour (ANA: level, 4 readings expected; INMET: rain, 1 expected):

| Station | Place | Window (744 h): ok / partial / missing | Longest silent run | Peak days 05-01 → 05-06 (144 h): ok / partial / missing |
|---|---|---|---|---|
| ANA 86510000 | Muçum | 744 / 0 / 0 | 0 h | 144 / 0 / 0 |
| ANA 86720000 | Encantado | 254 / 51 / 439 | 105 h from 05-01 01:00Z | 0 / 6 / 138 |
| ANA 86879300 | Estrela | 284 / 176 / 284 | 29 h from 05-17 11:00Z | 19 / 83 / 42 |
| ANA 86950000 | Taquari | 299 / 19 / 426 | 127 h from 05-02 12:00Z | 35 / 1 / 108 |
| ANA 87242000 | Guaíba (CatSul) | 744 / 0 / 0 | 0 h | 144 / 0 / 0 |
| ANA 87450004 | Porto Alegre, Cais Mauá | 314 / 1 / 429 | 429 h from 05-03 03:00Z (to the end) | 50 / 1 / 93 |
| ANA 87450020 | Porto Alegre, Gasômetro | 383 / 30 / 331 | 329 h from 04-20 00:00Z (not started) | 50 / 28 / 66 |
| INMET A840 | Bento Gonçalves | 744 / 0 / 0 | 0 h | 144 / 0 / 0 |
| INMET A882 | Teutônia | 742 / 0 / 2 | 1 h | 144 / 0 / 0 |
| INMET A837 | Soledade | 744 / 0 / 0 | 0 h | 144 / 0 / 0 |
| INMET A894 | Serafina Corrêa | 744 / 0 / 0 | 0 h | 144 / 0 / 0 |
| INMET A844 | Lagoa Vermelha | 743 / 0 / 1 | 1 h | 144 / 0 / 0 |
| INMET A879 | Canela | 744 / 0 / 0 | 0 h | 144 / 0 / 0 |
| INMET A801 | Porto Alegre | 741 / 0 / 3 | 1 h | 144 / 0 / 0 |

Every INMET station reported through the peak; three of five river gauges with a flood level did not.

### Station level thresholds (`make thresholds`; ANA record 2019-01-01 → 2024-04-19, local)

| Station | Level readings | Record from | p50 | p90 | p99 | p99.9 | Max (local time) | Official flood level |
|---|---|---|---|---|---|---|---|---|
| Muçum | 180,870 | 2019-01-01 | 175 | 407 | 1008 | 1980 | 2302 (2023-11-18 23:45) | 1800 |
| Encantado | 176,984 | 2019-01-01 | 197 | 335 | 832 | 1845 | 2073 (2023-09-04 22:15) | 1200 |
| Estrela | 105,534 | 2020-07-09 | 1293 | 1329 | 1703 | 2218 | 2765 (2020-07-09 04:00, first reading) | 1900 |
| Taquari | 80,193 | 2021-11-26 | 258 | 430 | 778 | 1243 | 1295 (2023-11-20 04:00) | 850 |
| CatSul Guaíba | 56,813 | 2020-05-04 | 85 | 160 | 236 | 257 | 275 (2023-11-22 08:30) | none found |
| Cais Mauá C6 | 172,729 | 2019-01-01 | 88 | 154 | 259 | 327 | 346 (2023-11-21 08:15) | 300 [[VERIFY]] |
| Gasômetro | 0 | — | — | — | — | — | — | none confirmed |

All values in cm. Telemetry misses real crests: Muçum's September 2023 record (26.11 m nivelled by SGB) is absent because the gauge's last level before a 3.8-day gap was 2179 cm at 2023-09-04 19:30 local.

### Rain bands in the historical record (scratch measurement, ANA gauge rain 2019-01 → 2024-04-19, hourly steps with a full 72 h window)

Share of hours falling in each rain LR band (rule in `signals/_rain.py`):

| Gauge | Hours | Rain coverage | LR 0.5 | LR 1 | LR 2 | LR 5 | LR 10 |
|---|---|---|---|---|---|---|---|
| Muçum | 46,394 | 0.978 | 75.63 % | 22.22 % | 1.94 % | 0.17 % | 0.04 % |
| Encantado | 46,394 | 0.952 | 77.06 % | 19.84 % | 2.63 % | 0.41 % | 0.06 % |
| Cais Mauá C6 | 46,394 | 0.930 | 81.04 % | 17.00 % | 1.79 % | 0.17 % | 0 |

Missing rain readings count as zero in this measurement.

### Reference times (`make reference`; local time, UTC-3)

SGB SACE Taquari: 43 bulletins in April–May 2024; 28 between 04-30 and 05-06 (the SGB technical note also says 28).
First bulletin: data time 2024-04-30 06:00, uploaded 07:54.

| Gauge | Flood level (cm) | First ANA reading ≥ flood level | First SACE bulletin printing level ≥ flood (data / upload) | Telemetry max in window | Longest level gap in the 72 h after crossing |
|---|---|---|---|---|---|
| Muçum | 1800 | 05-01 12:45 | 05-01 22:00 / 05-02 00:28 | 2557 at 05-02 07:30 | 0.2 h |
| Encantado | 1200 | 04-30 14:15 | 05-12 13:00 / 05-12 14:51 (no reading printed during the first wave) | 1873 at 05-12 22:00 (second wave; the first-wave crest of 23.14 m was not recorded) | 64.8 h |
| Estrela | 1900 | 04-30 08:15 | 04-30 10:00 / 04-30 11:49 | 3366 at 05-02 13:30 | 7.8 h |
| Taquari | 850 | 05-01 04:15 | 05-01 06:00 / 05-01 07:39 | 1376 at 05-02 08:45 | 43.5 h |
| Cais Mauá C6 | 300 [[VERIFY]] | 05-02 13:15 | — (no SACE for the Guaíba in 2024) | 369 at 05-02 23:15 (last reading; SGB crest 5.37 m on 05-05) | 62.0 h |

### Replay (`make backtest`, 744 hourly steps, 18,184 signals)

First replay hour at which a *single* warning signal reached LR ≥ 4 and LR ≥ 10 (no fusion yet):

| Signal | Place | LR ≥ 4 (local) | LR ≥ 10 (local) |
|---|---|---|---|
| ana_level 86510000 | Muçum | 04-30 11:00 | 05-01 13:00 |
| ana_level 86720000 | Encantado | 04-30 08:00 | 04-30 15:00 |
| ana_level 86879300 | Estrela | 04-30 04:00 | 04-30 09:00 |
| ana_level 86950000 | Taquari | 04-30 22:00 | 05-01 05:00 |
| ana_level 87242000 | Guaíba (CatSul) | 05-02 19:00 | 05-02 22:00 |
| ana_level 87450004 | Porto Alegre, Cais Mauá | 05-02 06:00 | 05-02 14:00 |
| ana_level 87450020 | Porto Alegre, Gasômetro | never (no thresholds) | never |
| ana_rain 86510000 | Muçum | 04-29 23:00 | 04-30 07:00 |
| ana_rain 86720000 | Encantado | 04-30 04:00 | 04-30 05:00 |
| ana_rain 86879300 | Estrela | 04-30 04:00 | 04-30 11:00 |
| ana_rain 86950000 | Taquari | 04-30 10:00 | never |
| ana_rain 87242000 | Guaíba | 04-30 08:00 | never |
| ana_rain 87450004 | Porto Alegre | 04-30 10:00 | 05-02 13:00 |
| inmet_rain A840 | Bento Gonçalves | 04-30 05:00 | 04-30 10:00 |
| inmet_rain A879 | Canela | 04-30 04:00 | 04-30 10:00 |
| inmet_rain A837 | Soledade | 04-30 18:00 | 05-01 12:00 |
| inmet_rain A894 | Serafina Corrêa | 05-01 12:00 | 05-01 19:00 |
| inmet_rain A801 | Porto Alegre | 04-30 08:00 | never |
| inmet_rain A882 | Teutônia | 05-12 08:00 | never |
| inmet_rain A844 | Lagoa Vermelha | never | never |

The hourly replay reports a crossing at the end of the hour that contains the reading, so it lags the 15-min crossing by up to 1 h (Estrela: reading 08:15, replay 09:00).

Level signal status during 05-01 → 05-06 (144 UTC hours): Muçum 144 fresh; Encantado 8 fresh / 102 stale / 34 missing (max age 71.5 h); Estrela 107 / 37 / 0 (max age 9.0 h); Taquari 36 / 71 / 37 (71.2 h); CatSul 144 fresh; Cais Mauá 51 / 71 / 22 (71.8 h); Gasômetro 79 fresh / 65 missing.

Copernicus EMS labels become visible at delivery: first one Guaporé DEL0 (image 05-04 09:48Z, delivered 05-04 19:29Z, 34.3 ha), Encantado DEL0 on 05-05 09:28Z (163.5 ha), Roca Sales DEL0 on 05-06 19:18Z (199.1 ha). The first label is delivered 103.5 h after the replay hour in which the Estrela level signal reached LR ≥ 10 (04-30 12:00Z).

### Clock checks (scratch measurements, 2024-04-20 → 05-20)

- ANA vs INMET rain, best shift of ANA time towards UTC (Pearson r): Cais Mauá–A801 +2:45 (0.95; 0.42 at 0 h); CatSul–B807 +2:15 (0.93); CatSul–A801 +2:30 (0.91); Muçum–A840 +1:30 (0.86); Estrela–A882 +2:30 (0.58); Muçum–A894 +2:15 (0.54); Encantado–A882 +3:15 (0.33).
- INMET radiation-weighted mean row label vs solar noon (UTC h): A840 15.88 vs 15.44; A882 15.75 vs 15.45; A801 15.89 vs 15.41.
- SACE bulletin levels equal ANA readings at the same local clock time (6 of 6 values on 04-30 06:00 and 05-01 22:00 where both had a reading; at 05-01 22:00 the bulletin printed Estrela 3015 cm while ANA has no Estrela reading).
