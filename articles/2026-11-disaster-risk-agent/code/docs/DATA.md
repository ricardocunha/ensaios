# Data sources (audit of 2026-09-30)

Event: Rio Grande do Sul floods, window **2024-04-20 to 2024-05-20**, Taquari-Antas and Guaíba basins.
Every row below was checked by querying the endpoint on 2026-09-30, not from memory.
Anything not confirmed is marked `[[VERIFY: …]]`.

Re-run the whole audit with `make fetch` (about 150 MB into `data/`, which is git-ignored).

| Source | Endpoint | Access | Resolution | Coverage 2024-04-20 → 05-20 (basin) | License / terms | Status |
|---|---|---|---|---|---|---|
| **ANA telemetry** (river level, flow, rain) | `http://telemetriaws1.ana.gov.br/ServiceANA.asmx/DadosHidrometeorologicos?codEstacao=…&dataInicio=dd/mm/yyyy&dataFim=dd/mm/yyyy` (XML); inventory: `…/ListaEstacoesTelemetricas?statusEstacoes=0&origem=` | No key | 15 min | Yes, but with gaps **exactly at the peak** at some gauges (see notes) | [[VERIFY: ANA data license; public data, no license text found on the endpoint]] | **works** |
| ANA HidroWebService (new REST) | `https://www.ana.gov.br/hidrowebservice/EstacoesTelemetricas/…` | HTTP 401 without credentials; needs registration | — | not tested | — | **needs key** (not used; legacy endpoint above serves the same telemetry) |
| **INMET** automatic stations | `https://portal.inmet.gov.br/uploads/dadoshistoricos/2024.zip` (102,772,199 bytes, one CSV per station) | No key; server resets connections without a browser-like User-Agent | Hourly, UTC | Yes, 7 basin stations with 0–3 missing hours in the window | [[VERIFY: INMET terms of use; no license text in the file]] | **works** |
| INMET API | `https://apitempo.inmet.gov.br/estacao/<start>/<end>/<code>` | HTTP 204 (empty) without token | Hourly | — | — | **needs key** (not used) |
| **CEMADEN** rain gauges, history | Form `https://mapainterativo.cemaden.gov.br/download/download_form.php` → `download_file.php` (monthly file per UF, optional municipality) | No account, but **CAPTCHA** on every download | [[VERIFY: 10 min when raining / 1 h otherwise, per CEMADEN docs; not seen in a file]] | 2024 is offered in the year list (`getperiodos.php`); file content not seen | [[VERIFY: CEMADEN terms]] | **blocked** (manual download only) |
| CEMADEN REST (PED) | `https://sws.cemaden.gov.br/PED/rest/…` | `{"Alerta": "O parâmetro token não pode ser vazio!"}`: needs token/registration | — | — | — | **needs key** |
| CEMADEN live snapshot | `https://resources.cemaden.gov.br/graficos/interativo/getJson2.php?uf=RS` | No key | Current accumulations (1–96 h) only | **No history**; 455 RS stations listed on 2026-09-30 | [[VERIFY]] | works, but useless for 2024 |
| **Copernicus EMS Rapid Mapping EMSR720** (precomputed flood extent) | Activation JSON: `https://rapidmapping.emergency.copernicus.eu/backend/dashboard-api/public-activations/?code=EMSR720`; product zips: `https://rapidmapping.emergency.copernicus.eu/backend/EMSR720/AOI0N/DEL_…/…_v1.zip` (302 to public S3) | No key | Vector polygons (GeoJSON CRS84 + shapefile) and flood-depth GeoTIFF, from VHR SAR images (RADARSAT-2, COSMO-SkyMed 2nd Gen, PAZ) | 5 AOIs, all in the **Taquari valley** (Guaporé, Encantado, Roca Sales, Das Antas Dam, Santa Tereza). Images 2024-05-04 09:48 → 2024-05-05 22:15 for flood delineation. **Porto Alegre / Guaíba not covered** | [CEMS terms](https://mapping.emergency.copernicus.eu/terms-and-conditions/): free access; reproduction, distribution and adaptation allowed; must cite the source per the Citation Guidelines; EU keeps the IP | **works** |
| Sentinel-1 / Sentinel-2 raw scenes (Copernicus Data Space) | Catalogue: `https://catalogue.dataspace.copernicus.eu/odata/v1/Products?$filter=…`; download: `https://zipper.dataspace.copernicus.eu/odata/v1/Products(<id>)/$value` | Catalogue open; **download needs a CDSE account** (`"Token not found"`, HTTP 401) | S1 GRD ~1–2 GB per scene | Over Encantado (-51.87, -29.24): S1 GRDH only on 2024-05-08 and 2024-05-11 (S1A). S2 L2A every 5 days, cloud cover 0.01 % on 04-21, 99.47 % on 04-26, 99.99 % on 05-01, 0.02 % on 05-06, 100 % on 05-11 and 05-16 | [[VERIFY: Copernicus Sentinel data terms]] | **needs key** (not used; EMSR720 replaces it) |
| **UFRGS flood database, Guaíba hydrographic region** (Zenodo 10.5281/zenodo.11177244) | `https://zenodo.org/api/records/11177244/files/analise_ada_rhguaiba_municipios.csv/content` | No key | One row per municipality, flood observed on **2024-05-06** | 139 municipalities of the Guaíba region, incl. Taquari valley and Porto Alegre | **CC-BY-4.0** (Zenodo metadata) | **works** (CSV only; the 471,748,608-byte GeoPackage is not downloaded) |
| **S2iD / Atlas Digital** (historical disaster records) | CKAN API `https://dadosabertos.mdr.gov.br/api/3/action/package_show?id=s2id_sedec` lists "1991 a 2025 - Danos Informados - Histórico de Desastres no Brasil" (CSV, modified 2026-08-19) | API works; every `/download/` URL returns an F5 **"Request Rejected"** page (HTTP 200, 246 bytes) to scripted clients, with or without session cookies. `atlasdigital.mdr.gov.br` serves a bot-protection script. S2iD `paginas/series/` is a JSF form | Per disaster record (municipality, date, COBRADE type, damages) [[VERIFY: columns; the data dictionary is behind the same block]] | 1991–2025 per resource name [[VERIFY: 2024 RS records present]] | "Creative Commons Atribuição" (CKAN `license_title`) | **blocked** (manual browser download) |

## Samples of real values

All retrieved on 2026-09-30 by `uv run python -m disaster_risk.fetch`.

**ANA, 15-min telemetry, 2024-04-20 → 2024-05-20.** Level in cm on each gauge's own datum
(values are not comparable across gauges). [[VERIFY: ANA timestamps are local time (BRT) — not stated in the response]]

| Station | Rows | Rows with level | Level from → to | Max level (cm) at |
|---|---|---|---|---|
| 86510000 Muçum (Taquari) | 2976 | 2976 | 04-20 00:00 → 05-20 23:45 | 2557 at 05-02 07:30 |
| 86720000 Encantado (Taquari) | 2979 | 1063 | 04-20 00:00 → 05-20 09:00 | 1873 at 05-12 22:00 |
| 86879300 Estrela (Taquari) | 1840 | 1400 | 04-20 00:00 → 05-20 08:00 | 3366 at 05-02 13:30 |
| 86950000 Taquari (Taquari) | 1206 | 1206 | 04-20 00:00 → 05-18 07:00 | 1376 at 05-02 08:45 |
| 87242000 Terminal CatSul Guaíba | 2976 | 2976 | 04-20 00:00 → 05-20 23:45 | 405 at 05-05 04:00 |
| 87450004 Cais Mauá C6 (Porto Alegre) | 1248 | 1246 | 04-20 00:00 → **05-02 23:15** | 369 at 05-02 23:15 (last reading) |
| 87450020 Usina do Gasômetro (Porto Alegre) | 1677 | 1576 | **05-03 15:00** → 05-20 23:45 | 417 at 05-05 05:30 |

Daily view for Muçum (max level cm / rain mm from the same gauge): 04-29 619 / 101.6, 04-30 1498 / 236.4,
05-01 2381 / 209.2, 05-02 2557 / 178.0, 05-03 2292 / 3.6.
Estrela readings per day (96 expected): 05-01 68, 05-02 47, 05-04 26, 05-05 15, 05-06 5, 05-08 2, 05-09 2.

**INMET, hourly rain, total 2024-04-20 → 2024-05-20 (UTC days).**

| Station | Rain (mm) | Missing hours |
|---|---|---|
| A840 Bento Gonçalves | 889.6 | 0 |
| A879 Canela | 878.2 | 0 |
| A837 Soledade | 794.4 | 0 |
| A894 Serafina Corrêa | 775.2 | 0 |
| A882 Teutônia | 582.4 | 2 |
| A801 Porto Alegre - Jardim Botânico | 555.0 | 3 |
| A844 Lagoa Vermelha | 385.0 | 1 |

Bento Gonçalves daily (UTC): 04-29 77.0, 04-30 148.6, 05-01 159.6, 05-02 148.6, 05-03 0.4 mm.

**Copernicus EMS EMSR720.** Activated 2024-05-03 09:04 (event time 2024-05-02), closed. Flood delineation (DEL) products:

| Product | AOI | Sensor | Image time (UTC) [[VERIFY: UTC]] | Flood polygons |
|---|---|---|---|---|
| AOI01_DEL_PRODUCT | Guaporé | COSMO-SkyMed 2nd Gen | 2024-05-04 09:48 | 53 |
| AOI01_DEL_MONIT01 | Guaporé | RADARSAT-2 | 2024-05-04 22:10 | 68 |
| AOI02_DEL_PRODUCT | Encantado | RADARSAT-2 | 2024-05-04 22:10 | 245 |
| AOI02_DEL_MONIT01 | Encantado | PAZ | 2024-05-05 09:05 | 125 |
| AOI03_DEL_PRODUCT | Roca Sales | PAZ | 2024-05-05 22:15 | 56 |
| AOI05_DEL_PRODUCT | Santa Tereza | COSMO-SkyMed 2nd Gen | 2024-05-04 20:36 | 61 |
| AOI05_DEL_MONIT01 | Santa Tereza | PAZ | 2024-05-05 22:15 | 25 |

The Das Antas Dam AOI has a DEL entry (COSMO-SkyMed, 05-04 10:00) with no download path; its status reason is "Not produced because of remote sensing limitations". Its grading (GRA) products exist.
Each zip is 4.5–7.1 MB. Example polygon properties: `{'event_type': '5-Flood', 'obj_desc': 'Riverine flood', 'det_method': 'Semi-automatic extraction', 'notation': 'Flooded area'}`.

**UFRGS municipal impact (observed 2024-05-06).** 139 rows. First rows: Canoas 154,002 people affected (44.3 %),
48.6 % of the municipal area directly affected; Porto Alegre 151,141 people (11.3 %), 24.95 % of area.

## Notes

1. **The gauges fail when you need them.** Cais Mauá (Porto Alegre) stops at 2024-05-02 23:15 and the Gasômetro gauge only starts reporting on 05-03 15:00; Estrela (Taquari) drops from 96 readings a day to 2–5 after the peak; Encantado has level in only 1063 of 2979 rows. This is the "signals it can't fully trust" story in raw form; missingness has to be a first-class input to fusion.
2. **The satellite signal is structurally late.** The CDSE catalogue has no Sentinel-1 GRDH scene over Encantado between 04-20 and 05-08 (the first ones are S1A on 05-08 and 05-11); Sentinel-2 on 05-01 is 99.99 % cloud. The earliest precomputed extent (EMSR720) comes from commercial SAR on 05-04, two days after the Taquari peak at Muçum/Estrela. So satellite can confirm, not warn, for the Taquari; that is a finding, not a bug to hide.
3. **Rainfall does not need CEMADEN.** ANA telemetry gauges also report 15-min rain (Muçum 236.4 mm on 04-30), and INMET gives hourly rain at 7 basin stations. CEMADEN would add density (live snapshot lists 3 gauges in Muçum, 3 in Roca Sales, 1 in Encantado, 12 in Porto Alegre) but needs a manual, CAPTCHA-gated download per month (April and May 2024 → `data/cemaden/RS_2024_04.csv`, `RS_2024_05.csv`).
4. **History (S2iD) is a manual step.** The CSV is published under CC-BY but the server rejects scripted downloads. Save it by hand from <https://dadosabertos.mdr.gov.br/dataset/s2id_sedec> into `data/s2id/`. Base dos Dados also mirrors S2iD but requires BigQuery (Google account), so it was not used. [[VERIFY: Base dos Dados S2iD coverage through 2024]]
5. **Ground truth for "who flooded".** UFRGS municipal table (2024-05-06) + EMSR720 polygons. Neither gives *when* each municipality flooded; for alert timing we still need official alert times. [[VERIFY: source for official alerts per municipality — CEMADEN/Defesa Civil RS — not audited here]]
6. Other records seen but not used: CEMS Risk & Recovery activation EMSN194 (requested on behalf of UFRGS) [[VERIFY: products and license]]; IPH/UFRGS operational Guaíba level forecasts (Zenodo 10.5281/zenodo.13237006, CC-BY-4.0), a possible baseline to compare against.
7. Level units: ANA `Nivel` treated as cm. [[VERIFY: unit from ANA documentation]] INMET rain at `HHMM UTC` treated as the total of the hour ending then. [[VERIFY]]
