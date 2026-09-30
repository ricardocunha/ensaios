# Data

Every dataset used by this code, with its license and how we get it. Nothing
under `data/` is committed; the code downloads and caches it.

Checked on 2026-09-30.

## In use

### OpenStreetMap: road network, hospitals, schools

- **What:** the drivable road graph (`network_type="drive"`, simplified) and
  `amenity=hospital` / `amenity=school` features, fetched with OSMnx 2.1.1
  from the Overpass API (graph) and Nominatim (city boundary).
- **License:** Open Database License (ODbL) 1.0.
- **Attribution (required wherever we show data or maps derived from it):**
  "© OpenStreetMap contributors", with a link to
  <https://www.openstreetmap.org/copyright>. Every map in the article and every
  figure built from the graph must carry this line.
- **Share-alike:** if we publish a derived *database* (e.g. the GraphML with
  our condition scores attached), it must be under ODbL too. Maps and figures
  are "produced works" and only need the attribution. For now we publish no
  derived database; the cache stays in `data/`.
- **Access:** no account, no key. `road_agents.graph.load_graph()` and
  `road_agents.pois.load_pois()` download once and cache to
  `data/<city>-drive.graphml` and `data/<city>-<kind>.csv`.
- **Caveats:** OSM completeness varies. `amenity=hospital` includes private
  hospitals and misses clinics/UPAs tagged differently
  (`amenity=clinic`, `healthcare=*`). Polygons are reduced to centroids and
  snapped to the nearest graph node. Speeds are OSMnx's imputed
  `speed_kph` (from `maxspeed` where tagged, otherwise the mean per highway
  type), so travel times are free-flow, not congested.

## Road condition / service requests (checked, not yet used)

### Belo Horizonte: "Solicitações dos cidadãos, por meio dos canais de atendimento da PBH" (BH Digital)

- **Where:** <https://dados.pbh.gov.br/dataset/solicitacoes-dos-cidadaos-por-meio-dos-canais-de-atendimento-da-pbh>
  (publisher SMPOG; maintainer SUMOG).
- **License:** Creative Commons Attribution (CC-BY), as shown on the portal.
  [[VERIFY: exact CC-BY version (4.0?) and attribution text PBH asks for]]
- **Access:** monthly CSV files, no account. The CKAN API at
  `dados.pbh.gov.br/api/3/...` returned HTTP 403 ("Acesso Bloqueado", a
  GoCache block) to `curl`, but the direct resource download
  (`ckan.pbh.gov.br/dataset/.../download/dadosabertos_bhdigital_2023_mai.csv`)
  worked.
- **What we saw in May 2023 (`2023 MAI`, 14 MiB, `;`-separated, UTF-8 with
  BOM):** 62,404 requests, of which **16,225 are "Tapa-Buraco"** (pothole
  repair), **all with coordinates** (10,739 distinct points), plus street
  name, number, neighbourhood, regional, created/closed dates and status
  (16,174 "Encerrado"). Channel: 11,696 "Integração entre Sistemas", 3,495
  "Portal", 1,027 "Portal Mobile". Dates are `dd/mm/yyyy` although the header
  says `YYYY-MM-DD`. Other road-related services exist ("Via Pública -
  Patrolamento", "Obra em Ruas, Calçadas e Vias Públicas - Fiscalização").
- **Coverage:** the portal lists files for 2020 (May–Dec), 2021, 2022 and
  2023 (Jan–Jul). [[VERIFY: whether newer months exist, maybe under another
  dataset; the ombudsman dataset "Dados gerais das manifestações processadas
  pela ouvidoria ... BH DIGITAL" has 2024–2025 files but is a different
  thing]]
- **Personal data:** no requester fields in the file. Coordinates are
  occurrence locations, which can still sit in front of a home, so we would
  only use them aggregated to road segments and never publish points.
  Every row is marked `Nivel Acesso = Restrito`. [[VERIFY: what "Restrito"
  means here, given the file is published openly]]
- **"Integração entre Sistemas":** most pothole rows come through this
  channel, which may be internal/inspection-generated rather than citizen
  reports. [[VERIFY: meaning of this channel]]
- **Use in this article:** a candidate for a realism check on the synthetic
  condition scores (milestone 2): does the synthetic "bad segment" map look
  anything like where potholes are reported? Not a ground truth of road
  condition: requests measure reporting, not pavement state.

### Belo Horizonte: "Trecho Logradouro"

- <https://dados.pbh.gov.br/dataset/trecho-logradouro-2>, CC-BY, CSV, EPSG:31983.
  Street segments with a `situação` field (real / interno / projetado). No
  pavement type or condition field found in the description.
  [[VERIFY: full data dictionary for any pavement attribute]]

### Porto Alegre: dadosabertos.poa.br

- The CKAN API works without an account (62 datasets listed on 2026-09-30).
  Searches for `156`, `buraco`, `pavimenta` returned nothing.
- **156POA requests are not published** as a dataset that we could find. The
  city's pothole service ("Via pública - conservação de vias com asfalto
  (Tapa-Buracos)", SMSURB, up to 45 days after the 156 registration) is
  requested via 156, but the service page links no data.
  [[VERIFY: no 156POA dataset elsewhere, e.g. on request via LAI]]
- **me-Ouv (ouvidoria) statistics** (`me-ouv`, CC-BY, CSV, 62,184 rows
  2019–2026): only protocol, theme (e.g. "SERVIÇOS URBANOS", "TRÂNSITO E
  TRANSPORTE"), agency, status and dates. **No location, no pothole
  category**, so it cannot be tied to road segments.
- Related, CC-BY, with locations: `acidentes-de-transito-acidentes` (EPTC
  traffic crashes), `sinalizacao-grafica` (EPTC signage),
  `eixos-de-logradouros` (street centre lines, shapefile). None describes
  pavement condition.

## Synthetic data

Road condition scores will be synthetic (milestone 2), generated from a fixed
seed. Documented here when they exist.
