# Data

Every dataset used by this code, with its license and how we get it. Nothing
under `data/` is committed; the code downloads and caches it.

Checked on 2026-09-30; licence, Anel and channel questions re-checked on 2026-10-01.

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

## Road condition / service requests

### Belo Horizonte: "Solicitações dos cidadãos, por meio dos canais de atendimento da PBH" (BH Digital) — in use since milestone 2

- **Where:** <https://dados.pbh.gov.br/dataset/solicitacoes-dos-cidadaos-por-meio-dos-canais-de-atendimento-da-pbh>
  (publisher SMPOG; maintainer SUMOG). Data dictionary: "SUMOG - Dicionário
  de dados - Solicitações BHDIGITAL.pdf" on the same page (dated 25/07/2023).
- **License:** Creative Commons Attribution. Checked 2026-09-30: the dataset
  page shows "Creative Commons Attribution" linking to
  `opendefinition.org/licenses/cc-by`, and the Open Definition badge. **No
  version number and no required attribution text** appear on the page or in
  the dictionary. We attribute as "Prefeitura de Belo Horizonte, BH Digital
  (SMPOG/SUMOG), dados.pbh.gov.br, CC-BY".
  **Version (checked 2026-10-01, not stated anywhere we could find):** the
  CKAN API (`dados.pbh.gov.br/api/3/action/package_show?id=solicitacoes-dos-cidadaos-por-meio-dos-canais-de-atendimento-da-pbh`,
  which answered with a browser user agent this time) returns
  `license_id: "cc-by"`, `license_title: "Creative Commons Attribution"`,
  `license_url: http://www.opendefinition.org/licenses/cc-by`: CKAN's
  generic, unversioned CC-BY entry. The portal's "Sobre" page
  (<https://dados.pbh.gov.br/about>) says only that conditions are "definidas
  em documento específico disponível em conjunto com os dados" and may
  change. Decreto 17.072/2019
  (<https://prefeitura.pbh.gov.br/sites/default/files/estrutura-de-governo/controladoria/2019/Decretos/Decreto_17072__.pdf>)
  requires an "licença aberta" and gives the Comitê Gestor the job to
  "definir termos de licenciamento de dados abertos" (art. 11, XIII), without
  naming a licence. Lei municipal 11.417/2022 (open-data policy,
  <https://www.cmbh.mg.gov.br/comunica%C3%A7%C3%A3o/not%C3%ADcias/2022/10/pol%C3%ADtica-de-dados-abertos-dos-poderes-p%C3%BAblicos-j%C3%A1-entrou-em-vigor-em-bh>)
  also says only "licença aberta". So the article says "CC-BY" with no
  version. [[VERIFY: CC-BY version; only PBH can answer (Fala BH / LAI);
  no published document states it]]
- **Access:** yearly (2020 May–Dec, 2021, 2022) and monthly (2023 Jan–Jul)
  CSVs, no account. The CKAN API at `dados.pbh.gov.br/api/3/...` returned
  HTTP 403 ("Acesso Bloqueado") to `curl`; the dataset HTML page and the
  direct resource downloads (`ckan.pbh.gov.br/dataset/.../download/...`)
  work with a browser user agent. `road_agents.potholes.download()` caches
  them in `data/pbh/` (git-ignored). The 2022 file is 143 MB.
- **Formats differ:** the 2022 file is Latin-1 with ISO dates; the 2023
  files are UTF-8 with a BOM and `dd/mm/yyyy` dates although the header says
  `YYYY-MM-DD`. Both `;`-separated, same 16 columns.
  `potholes.read_requests()` handles both.
- **Newer months (resolved):** on 2026-09-30 the dataset lists nothing after
  "2023 JUL", although its metadata says "Última Atualização: junho 10,
  2026". A portal search for "bhdigital" returns only this dataset; "bh
  digital" adds the ombudsman dataset (different content) and unrelated
  ones. So **Jul 2023 is the newest month published**; we use the 12 months
  Aug 2022 – Jul 2023.
- **`Nivel Acesso = Restrito` (resolved from the dictionary):** the field is
  the "nível de acesso às informações do serviço solicitado", classified as
  público, restrito or sigiloso, i.e. the access class of the ticket inside
  BH Digital, not a restriction on the published file. Across all rows of
  the 8 files we downloaded (Jan 2022 – Jul 2023, 951,808 requests of every
  service): 943,249 Restrito, 1,357 Público, 7,202 blank (all "IPTU - Revisão
  e Requerimentos"). All 198,991 Tapa-Buraco rows in our window are
  Restrito. The published rows carry no requester fields, but they do carry
  a street, a house number and coordinates, which is why we never publish
  anything per request.
- **"Integração entre Sistemas" (narrowed, not resolved):** the dictionary
  defines `Canal Captacao` only as the channel the citizen used ("Presencial,
  telefônico, Aplicativo PBH APP (Portal Mobile), Portal de Serviços, etc.")
  and does not list this value. In the same 8 files, 161,835 rows use it and
  158,106 of them (97.7%) are Tapa-Buraco (the rest: "Comunicação de Término
  de Obra/Baixa de Construção" 2,644, "Licenciamento/Regularização de
  Parcelamento do Solo" 1,084, 1 other). Only 18 Tapa-Buraco rows came by
  "Telefônico", while 71,490 requests of other services did. That pattern
  suggests pothole requests from another system (plausibly the 156 phone
  line or an internal SMOBI/SUDECAP system) are imported into BH Digital
  under this label, but nothing published says so. Searched again
  2026-10-01 (web search for the exact phrase with PBH / BH Digital /
  Tapa-Buraco / "canal de captação"): the only hits are the CSVs themselves
  (rows with this channel, service Tapa-Buraco, unit PMBH/SMOBI) and PBH
  pages about BH Digital as a "captador" and "tramitador" for urban-policy
  services, none of which defines the value. The article does not rely on
  it. [[VERIFY: meaning of "Integração entre Sistemas"; ask PBH via Fala BH
  / LAI]]
- **Personal data:** no requester fields. Coordinates (SIRGAS 2000,
  lat/lon) are occurrence addresses, which can sit in front of a home. We
  snap them in memory to road sections and keep only per-section counts;
  no point or per-request row is written to disk outside the raw cache,
  committed, or drawn on a map.
- **Use in this article:** the per-section condition score (below). Requests
  measure *reporting*, not pavement state: they depend on who uses the app
  or the 156 line, on traffic past the hole and on the city's own
  inspections. Measured bias in our window: 21.0 request locations per km on
  residential sections vs. 0.10 on motorway sections (Anel Rodoviário).
- **Who maintains the Anel Rodoviário (resolved 2026-10-01).** During our
  data window (Aug 2022 – Jul 2023) the Anel was a federal highway (the
  2026 tender lists stretches of BR-381 and BR-040) managed by DNIT, so its pavement
  was not the city's job and Tapa-Buraco requests would not cover it. On
  **3 June 2025** the Prefeitura took over: a "Termo de Transferência para a
  Municipalização de 22,4 quilômetros do Novo Anel", from Olhos D'Água
  (Barreiro) to Avenida Cristiano Machado; "Um trecho de 4,1 quilômetros
  continuará sob responsabilidade do Dnit" until the BR-381 works between
  Belo Horizonte and Caeté finish. Since then "caberá à Prefeitura de Belo
  Horizonte a gestão, manutenção, operação viária ... da rodovia", with
  maintenance under SMOBI (Sudecap, Suzurb). Sources:
  PBH, 2025-06-03 (updated 2025-10-09),
  <https://prefeitura.pbh.gov.br/noticias/pbh-assume-novo-anel-e-garante-mais-seguranca-melhorias-e-reducao-de-acidentes>;
  PBH, 2025-04-29, <https://prefeitura.pbh.gov.br/noticias/municipalizacao-do-anel-rodoviario>
  (the city "se prepara para assumir a operação e manutenção do Anel
  Rodoviário, atualmente sob responsabilidade do DNIT");
  O Tempo, 2025-06-03, <https://www.otempo.com.br/politica/2025/6/3/pbh-assume-anel-rodoviario-e-anuncia-tratamento-especial-da-via>
  (federal resurfacing money as part of the hand-over). In July 2026 PBH
  reopened a tender for pavement restoration on "o trecho municipalizado do
  Anel": O Tempo, 2026-07-02,
  <https://www.otempo.com.br/cidades/2026/7/2/pbh-reabre-edital-para-obras-acima-de-r-100-milhoes-no-anel-rodoviario>.
  The BR-040 concession auctioned in 2024 "vai do entroncamento com
  Cristalina (GO) até o Anel Rodoviário de Belo Horizonte" (Estado de
  Minas, 2024-09,
  <https://www.em.com.br/politica/2024/09/6948597-leilao-da-br-040-quatro-empresas-disputarao-trecho-de-bh-a-goias.html>);
  we found no source that puts the Anel itself in a concession. A 2025+
  request window could therefore start to include Anel requests; ours
  cannot.

### Belo Horizonte: "Trecho Logradouro"

- <https://dados.pbh.gov.br/dataset/trecho-logradouro-2>, CC-BY, CSV, EPSG:31983.
  Street segments with a `situação` field (real / interno / projetado). No
  pavement type or condition field found in the description.
  [[VERIFY: full data dictionary for any pavement attribute]]
- Related, found 2026-09-30: "Trecho com Pavimentação"
  (<https://dados.pbh.gov.br/dataset/trecho-com-pavimentacao-3>, monthly,
  latest file `20260901_trecho_pavimentacao`, EPSG:31983) gives pavement
  *availability* per street segment (paved or not), not condition. Not used;
  a possible filter for unpaved streets later. [[VERIFY: license and fields]]

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

## Derived tables (milestone 2)

Built by `scripts/section_pipeline.py`, written to `data/` (git-ignored, not
published: a published copy would be an ODbL derived database and would
also need the PBH CC-BY attribution).

### Road sections

`road_agents.sections.build_sections(D, max_length_m=1000)`:

1. Both directions of a street form one *link*.
2. Consecutive links are the same section when they share a `name` (or
   `ref` when unnamed; multi-valued names match if any value matches) and the
   same highway class (the highest-ranked of OSM's values, `*_link` kept
   apart), and neither forks at the shared node.
3. A section stops where a road of strictly higher class (motorway > trunk >
   primary > secondary > tertiary > residential/unclassified/living
   street/busway > links) that is not the same road touches the node.
   Residential streets therefore run across residential crossings; avenues
   run across side streets.
4. Unnamed links are never merged.
5. Chains longer than 1,000 m are cut at edge boundaries into
   `ceil(L / 1000)` pieces of about equal length (each link goes to the piece
   holding its midpoint). A single OSM edge longer than 1,000 m stays whole.
6. Ids `S00001`… sorted by (unnamed last, name, class, first link):
   deterministic for a given graph, not stable across OSM downloads.

Known limits: a dual carriageway is two sections (one per direction); a road
with two OSM names that never co-occur on one edge (e.g. "Anel Rodoviário
Celso Mello de Azevedo" and "Rodovia Anel Rodoviário Celso Mello Azevedo")
is not merged.

### `data/belo-horizonte-sections.csv` (one row per section; the agents read this)

| Column | Meaning |
|---|---|
| `section_id`, `name`, `highway`, `oneway` | identity; `name` = the name covering most of the length |
| `n_edges`, `length_m` | directed edges; length counting each link once |
| `lanes` | OSM `lanes` (length-weighted over tagged links) or the class default below |
| `area_m2` | `length_m × lanes × 3.5 m` |
| `betweenness_max`, `betweenness_mean` | link flow = betweenness u→v + v→u (k=2000, seed 42); max and length-weighted mean over links |
| `requests`, `request_points` | Tapa-Buraco requests Aug 2022 – Jul 2023 snapped within 30 m; distinct locations (lat/lon to 6 decimals) |
| `points_per_km` | raw density |
| `smoothed_rate_per_km` | `(points + r × 0.5) / (km + 0.5)`, r = network rate (17.4 / km): a Gamma-prior shrinkage so a 20 m section with one request does not top the list |
| `condition` | 0 without requests; otherwise the percentile rank (0, 1] of the smoothed rate among sections with requests |
| `criticality` | `betweenness_mean / max(betweenness_mean)` |
| `repair_cost` | synthetic, see below |
| `value` | `condition × criticality × length_km` (bad pavement × traffic that drives over it) |

`data/belo-horizonte-section-edges.csv` maps `section_id` to directed edges
`(u, v)` of the simplified DiGraph, for closure-impact calls.

### Synthetic repair cost (assumptions, all in `road_agents/condition.py`)

- Lanes when OSM has no tag (25.0% of sections have a tag on at least one
  link): two-way motorway/trunk/primary 4, secondary/tertiary 2, other 2;
  one-way motorway/trunk/primary/secondary 2, other 1. Lane width 3.5 m.
- `repair_cost = area_m2 × unit_cost × (0.3 + 0.7 × condition)`: a section at
  condition 0 needs spot patching (30% of full cost), one at condition 1
  full milling and overlay. `unit_cost = 1` cost unit per m²; **no currency**.
  The numbers are not prices. [[VERIFY: SINAPI/SUDECAP unit price per m² if
  the article wants reais]]
- Budgets are stated as a share of the total repair cost of candidate
  sections (value > 0), so they do not depend on the unit.

## Synthetic data

The condition score comes from real requests (above), not from a random
generator. Only the repair cost is synthetic.
