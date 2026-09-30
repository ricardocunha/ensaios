# Data: choice, licenses, label audit

Checked on 2026-09-30 against the live sources (Zenodo API, edp.com), by reading the actual files. Anything not confirmed is marked `[[VERIFY: …]]`.

## Candidates

| Dataset | Where | License | Size | Turbines | Span | Interval | Fault / event labels | Sign-up? |
|---|---|---|---|---|---|---|---|---|
| **EDP Open Data, "Wind Farm 1"** | [edp.com/en/innovation/data](https://edp.com/en/innovation/data) | CC BY-SA 4.0 (stated on each dataset page) | Logbooks ~18 kB each. SCADA size not checked (download failed). | 5 in the logbooks (T01, T06, T07, T09, T11) | 2016-01 to 2017-12 | 10 min | **Failure logbook**: `Turbine_ID, Component, Timestamp, Remarks`. 16 rows in 2016, 12 in 2017. Components: GEARBOX, GENERATOR, GENERATOR_BEARING, HYDRAULIC_GROUP, TRANSFORMER. Also has turbine event logs and met-mast data. | The 2017 failures/logs/met-mast `.xlsx` links download directly. The "Download data" links for the 2016/2017 **SCADA** and the 2016 logbook redirect to `/en/admin/...` and return **HTTP 403**. The 2016 logbook *is* reachable at a direct `/sites/default/files/document/2025-04/Historical-Failure-Logbook-2016.xlsx` URL. [[VERIFY: whether the SCADA files work after logging in; we did not create an account]] |
| **CARE to Compare** | [Zenodo 15846963](https://doi.org/10.5281/zenodo.15846963) (concept 10958774, latest version as of today). Paper: arXiv 2404.10320 | CC BY-SA 4.0 | One zip, 5.50 GB. Per farm, compressed / extracted: A 158 MB / 803 MB, B 400 MB / 1.37 GB, C 4.95 GB / 17.8 GB | 36 in 3 farms: A 5 (onshore, Portugal, **built from EDP**), B 9 and C 22 (offshore, Germany) | ~1 year per file. Timestamps are anonymised (shown as 2021-2024). | 10 min | `event_info.csv` per farm: `event_id, event_label (anomaly/normal), event_start, event_end, event_description` (free text). 45 anomaly and 50 normal events (A 12/10, B 6/9, C 27/31). Each row also has a per-row `status_type_id` (0-5). | No. Zenodo supports HTTP range requests, so single farms can be pulled out of the zip. |
| **Kelmarsh** | [Zenodo 16807551](https://doi.org/10.5281/zenodo.16807551) | CC BY 4.0 | 3.84 GB (yearly SCADA zips of 98-716 MB) | 6 × Senvion MM92 | 2016 to end of 2024 | 10 min | **Status/alarm log**, not a failure logbook. Greenbyte export: `Timestamp start, Timestamp end, Duration, Status (Stop/Warning/Informational/Communication), Code, Message, Service contract category, IEC category` (e.g. "Forced outage"). Turbine 1 in 2016 alone has 2,122 rows: 1,797 Informational, 168 Warning, 129 Stop, 28 Communication. 56 of them are IEC "Forced outage". There are no component failure labels, so faults would have to be inferred from stop codes. | No |
| **Penmanshiel** | [Zenodo 16807304](https://doi.org/10.5281/zenodo.16807304) | CC BY 4.0 | 7.49 GB | 14 × Senvion MM82 (there is no WT03) | 2016 to end of 2024 | 10 min | Same Greenbyte "events" export as Kelmarsh [[VERIFY: we only opened a Kelmarsh status file]]. No failure logbook. | No |
| **Hill of Towie** | [Zenodo 22662930](https://doi.org/10.5281/zenodo.22662930) v2.1.0 | CC BY 4.0 | 29.67 GB total; yearly zips of 1.39-1.61 GB | 21 × Siemens SWT-2.3-VS-82 | 2016-01 to 2026-04 | 10 min (+ ~1 Hz fastlog for Jan-Apr 2026) | `tblAlarmLog` (stopping and non-stopping alarms, with an alarm-code dictionary) and a `ShutdownDuration` table built from SCADA and RES operator logs. The description does not mention component failure labels. [[VERIFY: not opened beyond the description CSVs]] | No |
| Others we saw but did not audit | Aventa AV-7 (Zenodo 15700928, CC BY 4.0, 1 research turbine, 3.1 GB CSV with a status mapping); Björkö 45 kW (Zenodo 8213270, CC BY 4.0, 16 GB); Fuhrländer FL2500 (GitHub alecuba16/fuhrlander, EPL-2.0 per OpenWindSCADA, has alarms); a 10-turbine farm in Greece (Zenodo 14546480, CC BY 4.0, 181 MB xlsx) | | | | | | [[VERIFY: labels not inspected]] | |

## Choice: CARE to Compare Wind Farm A, put back on the EDP calendar, plus the EDP failure logbooks

What we use:

- **Time series**: the 22 CARE Wind Farm A files, downloaded on their own (158 MB) with HTTP range reads from the Zenodo zip.
- **Fault table**: the two EDP failure logbooks (2016 + 2017, 28 rows), joined to the series through a verified calendar mapping. CARE's own `event_info.csv` is kept as a second label source.

Why:

1. **Real, component-level failure records.** An operator wrote each logbook row with a component and a remark. Kelmarsh, Penmanshiel and Hill of Towie only have alarm/status logs, so "fault" labels would have to be invented from stop codes. That is a different (and harder to defend) article.
2. **This is the only copy of the EDP SCADA we could get without an account.** EDP's own SCADA download links return 403.
3. **Small and open.** 158 MB download, ~0.8 GB on disk, no sign-up, CC BY-SA 4.0 (share-alike applies to derived *data*; our code is separate).
4. **It can be replayed in real time order.** Once aligned, the five turbines give one continuous calendar from 2016-01-01 to 2017-11-20 (23 months), with 28 faults spread across it. The agent replay needs exactly that.

Why not the rest of CARE: Farms B and C have anonymised, normalised features and no external logbook to cross-check against, and Farm C alone is 4.95 GB compressed (above the 3 GB budget). Farm B (400 MB, 6 anomaly events: 3 rotor/main bearing, 3 transformer) is a possible second farm later. The downloader supports `--farms A B`.

Brazilian angle: the farm is in Portugal. We found no public Brazilian turbine-level SCADA with fault labels. [[VERIFY: ONS/ANEEL publish plant-level generation, not turbine SCADA with failures]]

## How Farm A maps to EDP (checked in `audit.py`)

- **Calendar.** CARE moved Farm A forward by **2191 days**. For example, the EDP logbook has T01 "Transformer fan damaged" at 2017-08-11 13:14, and CARE event 68 ends at 2023-08-11 13:10. Two files, **40 and 71** (the two that start on 2022-01-01 in CARE time), were moved by **2192 days**. With the raw CARE timestamps, 8 overlapping file pairs disagree (only 13-17 % of values match). After taking 1 extra day off files 40 and 71, all **38 overlapping file pairs agree on 100 % of sensor values**. The loader applies both shifts.
- **Turbines.** CARE asset → EDP turbine: 0 → T07, 10 → T09, 11 → T01, 13 → T11, 21 → T06. We derived this by matching CARE anomaly-event ends to logbook timestamps: 11 of the 12 CARE anomaly events end 0-13 minutes after a logbook entry on the mapped turbine (the next 10-minute stamp).
- **Per-turbine series** (after merging overlapping files):

| Turbine | CARE asset | First row | Last row | Rows | Missing | Gaps > 1 day |
|---|---|---|---|---|---|---|
| T07 | 0 | 2016-01-01 00:00 | 2017-10-22 10:20 | 94,578 | 0.55 % | 0 |
| T09 | 10 | 2016-01-01 00:00 | 2017-11-20 00:40 | 98,632 | 0.59 % | 0 |
| T01 | 11 | 2016-04-04 02:30 | 2017-09-21 00:50 | 76,484 | 0.71 % | 0 |
| T11 | 13 | 2016-03-03 14:00 | 2017-09-13 15:30 | 80,048 | 0.57 % | 0 |
| T06 | 21 | 2016-04-30 13:20 | 2017-10-21 08:40 | 75,281 | 2.97 % | 2 (2016-07-10 20:40 → 07-20 09:30, covering the 07-11 generator replacement; 2016-11-02 14:30 → 11-03 20:20) |

CARE only includes about a year of data before each of its events, so T01, T11 and T06 start partway through 2016. EDP's full 2016 SCADA would fill this in, but we could not download it.

## Label quality notes

**EDP logbook (the primary labels): 28 failures.**

- By year: 2016: 16, 2017: 12.
- By component: hydraulic_group 8, generator 7, generator_bearing 6, gearbox 4, transformer 3.
- By turbine: T06 8, T07 7, T09 7, T11 4, T01 2.
- Covered by the series: 27 of 28. T06's 2016-04-04 entry is before T06's first row. T11's 2016-03-03 19:00 entry has only 28 rows (about 5 h) of data before it.
- Linked to a CARE anomaly event: 11 of 28. All 16 failures from 2016 have **no** CARE event. The 2017 T07 "Generator damaged" (08-21) has none either; it came 1.4 days after the generator-bearing entry that CARE event 0 covers.

**The remarks mix hardware failures with sensor and alarm issues.** Examples: "High temperature in generator bearing (replaced sensor)", "Generator temperature sensor failure", "Gearbox noise", "Pitch position error related GH". A diagnosis agent scored on `component` will be scored against this mix. It is worth keeping `remarks` in the agent's view.

**Several rows describe the same incident.**

- T06 generator: 5 entries between 2016-07-11 and 2016-10-27, gaps of 12.9 to 41.6 days ("Generator replaced" appears twice).
- T09: gearbox 2016-10-11, then generator bearing 6.1 days later.
- T07: generator bearing 2017-08-20, then generator 1.4 days later.

The replay should treat these as possibly one incident when scoring "did the agent learn". Otherwise a repeat gets counted as a new success.

**Incidents (milestone 2, `incidents.py`).** Rows on one turbine are chained into one incident when:

- a row has the same component as the incident's previous row and comes ≤ 45 days after it, or
- it comes ≤ 7 days after the previous row, whatever the component.

The result is **28 rows → 21 incidents**. The four merges are the three clusters above plus T07 transformer 2016-07-10 / 08-23 ("High temperature transformer", then "... refrigeration repaired", 43.9 days apart). The 45 days were set after reading the gaps: same-component gaps are either ≤ 43.9 d or ≥ 76.1 d. Counts for other gap values are in RESULTS.md.

**Logbook timestamp meaning.** EDP gives timestamps in GMT and does not say whether they mark detection, stop or repair. We checked it against the SCADA: generator rpm in the 10-minute rows around each timestamp (`incidents.timestamp_context`, numbers in RESULTS.md).

- **Trip (12 of 28).** The turbine was running at wind ≥ 5 m/s and stopped within the 10 minutes containing the timestamp.
- **Already stopped (8).** 6 of these restart within 2 h after the timestamp.
- **Other (4)**, **no data (3)**, **kept running (1)**. The last is T06's second "Generator replaced".

So the timestamp marks a **stop event**: the fault stop, or the moment the fault was cleared. It is not the start of degradation, and not a work-order date. This is our reading of the SCADA; EDP does not document it.

The partial power in the row that contains a trip also shows that CARE rows are stamped at the **end** of their 10-minute interval.

**CARE Farm A event table.**

- 12 anomaly and 10 normal events.
- The 12 anomaly events cover only **11 distinct failures**. Events 51 and 72 both point to T06's 2017-10-17 gearbox entry. Event 72 ends 2 min after the logbook entry; event 51 ends 7 h 32 min after it.
- Anomaly window lengths (event_start → event_end): 7 days for 8 events, 14 days for 2 (events 0, 68), 11.6 days (51), 31.5 days (40). These are CARE's labelling choices. They are not evidence that the anomaly is visible that far ahead.
- Normalised components in CARE's descriptions: hydraulic 6, gearbox 3, generator_bearing 2, transformer 1.
- The README inside the zip says 44 anomaly / 51 normal events. The `event_info.csv` files and the Zenodo description both say 45 / 50. We use the files.

**`status_type_id` in Farm A is the label, not a sensor.**

- Only codes 0, 3 and 4 appear.
- Code 4 ("downtime") covers exactly the **14 days before** each logbook entry.
- Code 3 ("service") covers the **3 days after**.
- Each such run lasts 16.99 days, and the fault sits 14.0 days after its start, for every covered fault.

CARE says the Farm A status comes from the logbook and is meant for filtering training data. We use it only for that. It is never a feature and never a test-time filter, because using it would leak the answer.

**Sensor caveats**, from the Zenodo "Known Data Issues" and our own checks:

- Min/Max/Std columns contain implausible values, so we use only the 10-minute averages.
- Pitch angle wraps around.
- Power is scaled to 0-1 for anonymisation (`power_30_avg` max 0.976).

**How far ahead could anomalies show?** These are hypotheses to test in milestone 2, not findings.

- Bearing and gearbox faults plausibly show up as temperature drift days to weeks ahead.
- Hydraulic/brake-circuit errors and "oil leakage in hub" may be sudden and show little in 10-minute averages.
- Transformer-fan damage should show up in the transformer temperatures (sensors 38-40).

[[VERIFY: lead-time claims per component against the literature / CARE paper]].

Milestone 2 measured this on our data (RESULTS.md). Generator-bearing incidents are the most visible: 4 of 5 have an alarm in the 14 days before, for the best detector. Hydraulic incidents are the least: 0-2 of 7 for every detector. With 18 evaluable incidents, this supports the hypotheses but does not settle them.

## Attribution

- Gück, C., Roelofs, C. *Wind Turbine SCADA Data For Early Fault Detection* (CARE to Compare), Zenodo, DOI 10.5281/zenodo.15846963, CC BY-SA 4.0.
- EDP, *Wind Farm 1: Historical failure logbook 2016* and *Opendata wind failures 2017*, EDP Open Data, CC BY-SA 4.0.
