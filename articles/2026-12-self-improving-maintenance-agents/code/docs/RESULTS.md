# Results

Every number in the drafts must come from this file. Each section gives the command and the run artifact (under the git-ignored `runs/`).

Environment: Python 3.12.12, scikit-learn 1.9.1, pandas 3.0.6, numpy 2.5.3, Apple M4 Pro. Data: CARE to Compare Wind Farm A (Zenodo 15846963) + EDP failure logbooks 2016/2017; see [DATA.md](DATA.md).

## Milestone 1 (2026-09-30): data audit

`make audit` → `runs/audit.json`

| Check | Result |
|---|---|
| Overlapping CARE file pairs (same turbine) that agree after the calendar fix | 38 / 38, 100 % of sensor values |
| Pairs that disagree on the raw CARE calendar | 8, all involving files 40 or 71 (13-17 % of values match) |
| Turbines / span | 5 turbines, 2016-01-01 → 2017-11-20 (23 months) |
| 10-minute rows per turbine | 75,281-98,632; missing 0.55-2.97 % |
| EDP logbook failures | 28 (2016: 16, 2017: 12) |
| … by component | hydraulic_group 8, generator 7, generator_bearing 6, gearbox 4, transformer 3 |
| … by turbine | T06 8, T07 7, T09 7, T11 4, T01 2 |
| … covered by the series | 27 of 28 |
| … with a CARE anomaly event | 11 of 28 (CARE has 12 anomaly events; 2 of them point to the same failure) |
| Farm A `status_type_id` codes present | 0, 3, 4 only. Code 4 = the 14 days before each logbook entry, code 3 = the 3 days after. It is a label, not a signal. |

## Milestone 1 (2026-09-30): Isolation Forest sanity check

`make baseline` → `runs/baseline_iforest_train{60,365}_seed{0,1,2}.json`

**Setup** (see the `baseline.py` docstring):

- One Isolation Forest per turbine (200 trees).
- Features: 42 ten-minute averages; angle sensors and Min/Max/Std are excluded.
- Training data: the first N days of each turbine's series, keeping only status-0 rows.
- An **alarm day** is a day whose mean anomaly score is above the 99th percentile of that turbine's daily scores in training.
- A fault is **hit at horizon H** if at least one alarm day falls in the H days before the fault's date.
- **Base rate** (the null): the share of *quiet* H-day windows (every day at least 30 days from any fault on that turbine) that contain an alarm day.
- The p-value is a one-sided binomial test of the hit count against the base rate. It is only indicative: sliding windows overlap, and faults on one turbine are not independent.

### A. Train on the first 60 days (seed 0)

At least 30 days of history are needed before a fault can be evaluated. Of the 28 faults, 24 are evaluated, 3 fall in the training period and 1 is before the data starts.

| Horizon | Faults hit | Hit rate | Quiet windows with an alarm | p |
|---|---|---|---|---|
| 7 d | 19 / 24 | 0.792 | 0.538 (of 1,415) | 0.0093 |
| 14 d | 21 / 24 | 0.875 | 0.663 (of 1,325) | 0.0184 |
| 30 d | 22 / 24 | 0.917 | 0.794 (of 1,161) | 0.102 |

Share of alarm days per turbine after training: T07 0.408, T09 0.431, T01 0.135, T11 0.343, T06 0.293.

Share of alarm days by month, all turbines:

| 2016-03 | 04 | 05 | 06 | 07 | 08 | 09 | 10 | 11 | 12 | 2017-01 | 02 | 03 | 04 | 05 | 06 | 07 | 08 | 09 | 10 | 11 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 0.000 | 0.017 | 0.174 | 0.350 | 0.701 | 0.740 | 0.480 | 0.232 | 0.148 | 0.084 | 0.245 | 0.136 | 0.110 | 0.253 | 0.245 | 0.500 | 0.513 | 0.665 | 0.317 | 0.375 | 0.000 |

CARE Farm A windows with at least one alarm day: 10 of 12 anomaly windows, 6 of 10 normal windows.

**Reading.** The detector learned winter and alarms on summer. Alarm days peak at 0.70-0.74 in July-August 2016, the first summer after a January-February training period. Because alarms are everywhere, the high hit rates mostly reflect how often the model alarms at all. At 30 days the hit rate is not distinguishable from the base rate (p = 0.10). At 7 days it is higher than the base rate (0.79 vs 0.54), but with this much seasonal confounding that margin is weak evidence.

### B. Train on the first 365 days (seed 0)

Only 2017 faults are left to evaluate: 11 evaluated, 16 in the training period, 1 before the data starts.

| Horizon | Faults hit | Hit rate | Quiet windows with an alarm | p |
|---|---|---|---|---|
| 7 d | 2 / 11 | 0.182 | 0.023 (of 556) | 0.0261 |
| 14 d | 3 / 11 | 0.273 | 0.053 (of 511) | 0.0177 |
| 30 d | 4 / 11 | 0.364 | 0.126 (of 420) | 0.0402 |

Share of alarm days per turbine after training: T07 0.010, T09 0.015, T01 0.024, T11 0.016, T06 0.000.

Faults hit (first alarm, days before the fault):

- T07 generator bearing 2017-08-20 (9 d)
- T07 generator 2017-08-21 (10 d; the same incident as the bearing entry)
- T11 hydraulic group 2017-04-26 (6 d)
- T01 transformer 2017-08-11 (25 d, at 30 d only)

Missed: all other hydraulic_group faults (5) and both gearbox faults.

CARE Farm A windows with at least one alarm day: 3 of 12 anomaly windows, 1 of 10 normal windows.

**Reading.** With a full year of training, the detector is quiet (0-2.4 % alarm days, close to the 1 % the threshold implies). Its few alarms fall before faults far more often than in quiet periods. But it sees only 2-4 of 11 faults, and its hits are the thermal ones (generator bearing, transformer). That fits the hypothesis in DATA.md that hydraulic faults leave little trace in 10-minute averages. The counts are too small to call this a result.

### Seed stability (Isolation Forest random_state 0 / 1 / 2)

| Train days | Seed | 7 d hit / base | 14 d hit / base | 30 d hit / base | CARE anomaly / normal windows with an alarm |
|---|---|---|---|---|---|
| 60 | 0 | 19/24 vs 0.538 | 21/24 vs 0.663 | 22/24 vs 0.794 | 10/12, 6/10 |
| 60 | 1 | 20/24 vs 0.565 | 21/24 vs 0.709 | 22/24 vs 0.842 | 10/12, 7/10 |
| 60 | 2 | 18/24 vs 0.539 | 21/24 vs 0.688 | 22/24 vs 0.818 | 10/12, 8/10 |
| 365 | 0 | 2/11 vs 0.023 | 3/11 vs 0.053 | 4/11 vs 0.126 | 3/12, 1/10 |
| 365 | 1 | 2/11 vs 0.025 | 3/11 vs 0.043 | 3/11 vs 0.090 | 3/12, 0/10 |
| 365 | 2 | 2/11 vs 0.023 | 3/11 vs 0.053 | 4/11 vs 0.140 | 3/12, 1/10 |

### What this means for milestone 2

- A naive Isolation Forest on raw averages mostly detects the **season**. The detector needs features that cancel weather and load, such as temperatures relative to ambient or residuals from a normal-behaviour model given wind speed and power. Otherwise it needs training data that covers a full year.
- The honest evaluation unit is "alarm before fault **versus** alarm in quiet periods". A hit rate on its own looks good even for a detector that alarms on 40 % of days.
- With a full year held out for training, only 11 faults remain for chronological evaluation. The agent replay (milestone 3) needs a plan for this, for example rolling or expanding-window retraining so that the 2016 faults can be scored too.

## Milestone 2 (2026-09-30): detectors on weather-normalised residuals, walk-forward

`make detect` → `runs/m2_eval.json`, `runs/m2_daily_scores.parquet`, `runs/m2_episodes.csv`, `runs/m2_episodes_eval.csv`. The walk-forward took 67 s (5 turbines in parallel, one thread each). The evaluation took about 3 min. Code: `features.py`, `detect.py`, `incidents.py`, `evaluate.py`.

### Features: normal-behaviour residuals (`features.py`)

- **Hourly means** of the 10-minute averages. An hour needs at least 3 of its 6 rows. `status_type_id` is dropped at this step.
- **Operating state** (the model inputs): ambient temperature, wind speed, grid power, rotor rpm, plus mean power over the past 6 h and 24 h (thermal inertia). The rolling means include only the current hour and earlier ones.
- **Targets**: 24 temperatures, each taken **minus ambient temperature**, in 8 groups:

  | Group | Signals |
  |---|---|
  | generator | stator windings L1-L3, split ring chamber |
  | generator_bearing | DE, NDE |
  | gearbox | HSS bearing, oil |
  | hydraulic | hydraulic oil |
  | hub | hub controller, nose cone |
  | transformer | HV L1-L3 |
  | converter | 7 signals |
  | nacelle | 3 signals |

  Farm A has no pressure signals.
- **Normal-behaviour model (NBM)**: one gradient-boosted regressor per target: `HistGradientBoostingRegressor`, 100 iterations, 15 leaves, min 40 samples per leaf, no early stopping, so it is deterministic. The residual is observed minus expected.
- **Alarms come only from the logbook's components.** The detectors score only the generator, generator_bearing, gearbox, hydraulic, hub and transformer residuals (14 signals). Converter and nacelle residuals appear only as context in the episode table.

### Walk-forward protocol (`detect.py`)

- **Retraining.** Per turbine, a model is retrained every 30 days on everything before the cutoff (an expanding window). The first cutoff is 60 days after the turbine's first row.
- **Fit and calibration split.** The last `max(21 d, 25 %)` of the training window is held out as **calibration**. Models are fitted on the rest. Score scales and alarm thresholds come from the calibration days.
- **Healthy training data.** Training drops the hours from 14 days before to 3 days after each logbook fault **recorded before the cutoff**. Farm A's `status_type_id` marks the same windows for every fault, including future ones, so it is not used at all.
- **Daily score.** Each detector's daily value becomes a robust z-score against the calibration days, (x − median) / (1.4826·MAD). A day is an alarm when that score is above k.
  - `iforest_raw`: the milestone-1 Isolation Forest on 42 raw hourly averages, 200 trees. Day value = mean anomaly score.
  - `iforest_resid`: an Isolation Forest (200 trees) on the 14 hourly residuals, each z-scaled by its hourly median/MAD on the calibration days.
  - `threshold_resid`: the per-signal daily mean residual, z-scored against the calibration days. Day value = max |z| over the 14 signals. There is no seed.
- **Scored days.** Every turbine-day from the first cutoff on, 2,687 in total:

  | Turbine | Scored from | Scored to | Retrains |
  |---|---|---|---|
  | T07 | 2016-03-01 | 2017-10-22 | 21 |
  | T09 | 2016-03-01 | 2017-11-20 | 21 |
  | T01 | 2016-06-03 | 2017-09-21 | 16 |
  | T11 | 2016-05-02 | 2017-09-13 | 17 |
  | T06 | 2016-06-29 | 2017-10-21 | 16 |

- **No look-ahead** is tested in `tests/test_detect.py::test_scores_before_a_date_do_not_depend_on_anything_after_it`. Three runs must give **identical** scores for every day before a split date:
  - the full series;
  - the series with a +40 °C fault injected after the split, different noise and an extra future logbook fault;
  - the series cut at the split.

  Other tests check that status codes never change the output and that faults after a cutoff are not used to clean the training data.

### Incidents (`incidents.py`)

**Rule.** Logbook rows on one turbine chain into one incident when a row has the same component as the incident's previous row and comes ≤ 45 days after it, or when it comes ≤ 7 days after the previous row, whatever the component. The incident starts at its first row, and detectors are scored against that time.

The 45 days were chosen after reading the gaps. Same-component gaps are either ≤ 43.9 d (T06 generator ×5, T07 transformer ×2) or ≥ 76.1 d.

**28 logbook rows → 21 incidents.**

- The merges:
  - T06 generator, 5 rows (2016-07-11 → 10-27)
  - T07 transformer, 2 rows (2016-07-10, 08-23)
  - T09 gearbox + generator bearing (2016-10-11, 10-17)
  - T07 generator bearing + generator (2017-08-20, 08-21)
- Incidents by first component: hydraulic_group 8, generator_bearing 5, gearbox 4, generator 2, transformer 2.
- Sensitivity to the rule (same-component gap, with the 7-day any-component rule): 0 d → 26, 15 d → 25, 30 d → 23, **45 d → 21**, 60 d → 21, 90 d → 20. Without the 7-day rule: 28 / 27 / 25 / 23 / 23 / 22.

**Evaluable incidents:**

| Horizon | Evaluable | Out of |
|---|---|---|
| 7 d | 19 | 21 |
| 14 d | 18 | 21 |
| 30 d | 18 | 21 |

- 2 incidents are never evaluable: T11 2016-03-03 (before scoring starts) and T06 2016-04-04 (before T06's data).
- The T06 generator incident (2016-07-11) is evaluable at 7 d only.
- All 16 faults from 2016 were outside milestone 1's evaluation. With walk-forward, 2016 incidents are now scored.

### What the logbook timestamp marks

We checked the generator rpm (`sensor_18`) in the 10-minute rows around each of the 28 timestamps (`incidents.timestamp_context`).

| What the SCADA shows at the timestamp | Rows |
|---|---|
| **Trip**: running in the row before, stopped (rpm < 100) in the row after the one containing the timestamp. All 12 at wind ≥ 5.1 m/s, so not a low-wind stop. | 12 |
| **Already stopped** (last production 0.8 h to more than 3 days earlier). 6 of the 8 restart within 0.3-1.6 h of the timestamp, so the timestamp sits at the end of a stop, when the fault was cleared. | 8 |
| **Other**: partial rpm around a low-wind period | 4 |
| **No data at the timestamp**: T06 2016-04-04 and 2016-07-11 (during the 10-day gap for the generator replacement); T01 2017-08-11 (full power at 13:10, row missing, restarts at 14:40) | 3 |
| **Kept running** (T06 "Generator replaced", 2016-10-27) | 1 |

**Conclusion.** The timestamp marks a stop event, either the fault stop itself or its clearance. It does not mark the start of degradation, and it is not a work-order date. The trips line up with the row whose power is partial: T09 2016-06-07 16:59 trips in the row stamped 17:00. That fits CARE rows being stamped at the **end** of their 10-minute interval. All detection windows end the day before the fault's date, so the trip day never counts as a hit.

### Scoring

- **Hit at H**: an alarm day in [D − H, D), where D is the incident's first-row date.
- **Healthy day**: from 30 days before an incident's first row to 30 days after its last row is excluded; every other scored day is healthy. There are 49.64 healthy turbine-months.
- **Episode**: consecutive alarm days, bridging one-day gaps. A **false alarm** is an episode that starts on a healthy day.
- **Quiet-window base rate** (the null): the share of H-day windows made only of healthy days that contain an alarm. The binomial p compares the hit rate with it. Treat p as indicative: windows overlap, and incidents on one turbine are not independent.
- **Comparing detectors.** Each detector is compared at the **smallest k whose healthy alarm-day rate is ≤ 1 per turbine-month** (k grid 1.5-30). The rate is monotone in k. The episode count is not: at a low k, alarms merge into a few long episodes.
  - This operating point is chosen with the healthy-period labels, so it is an oracle comparison, not a deployable threshold.
  - Results at an a-priori k = 5 are given too.

### Detector comparison: matched budget of ≤ 1 healthy alarm-day per turbine-month

Isolation Forest seeds are shown as s0 / s1 / s2. The Isolation Forest is the only random step.

| Detector | k | Alarm days / healthy turbine-month | False-alarm episodes / turbine-month | Hits 7 d (of 19) | Hits 14 d (of 18) | Hits 30 d (of 18) | Quiet-window rate 7 / 14 / 30 d (s0) | p at 14 d | Dates with ≥ 3 of 5 turbines alarming |
|---|---|---|---|---|---|---|---|---|---|
| iforest_raw | 3.5 | 0.83 / 0.97 / 0.89 | 0.36 / 0.42 / 0.44 | 5 / 4 / 6 | 5 / 4 / 6 | 8 / 7 / 9 | 0.091 / 0.143 / 0.227 | 0.103 / 0.327 / 0.066 | 12 / 12 / 13 |
| **iforest_resid** | 2.5 | 0.87 / 0.79 / 0.89 | 0.58 / 0.54 / 0.63 | 4 / 5 / 5 | **7 / 7 / 7** | 9 / 10 / 9 | 0.127 / 0.192 / 0.299 | 0.043 / 0.028 / 0.056 | **4 / 3 / 4** |
| threshold_resid | 8 | 0.77 | 0.54 | 5 | 5 | 8 | 0.130 / 0.218 / 0.393 | 0.354 | 3 |

The same budget on the 28 raw logbook rows (hits at 14 d, of 25 evaluable): iforest_raw 8 / 8 / 9, iforest_resid 9 / 9 / 11, threshold_resid 9.

**Other operating points (seed 0):**

| Detector | ≤ 0.5 alarm-days / tm: k, hits 7 / 14 / 30 d, base 14 d | ≤ 2 alarm-days / tm: k, hits 7 / 14 / 30 d, base 14 d | A-priori k = 5: alarm-days / tm, hits 7 / 14 / 30 d, base 14 d |
|---|---|---|---|
| iforest_raw | 5, 3 / 3 / 3, 0.043 | 3, 6 / 6 / 10, 0.238 | 0.24, 3 / 3 / 3, 0.043 |
| iforest_resid | 3, 4 / 6 / 9, 0.101 (p 14 d = 0.007, 30 d = 0.001) | 2, 5 / 7 / 12, 0.356 | 0.04, 2 / 2 / 3, 0.021 |
| threshold_resid | 10, 2 / 3 / 6, 0.114 | 6, 9 / 9 / 13, 0.369 | 2.60, 11 / 11 / 15, 0.547 |

At the ≤ 0.5 point, iforest_resid seeds 1 and 2 give 4 / 5 / 8 (k 3) and 4 / 4 / 6 (k 3.5).

**Per component**: hits at 14 d, matched ≤ 1 budget, seed 0 (evaluable incidents in brackets):

| Component | iforest_raw | iforest_resid | threshold_resid |
|---|---|---|---|
| generator_bearing (5) | 3 | 4 | 2 |
| transformer (2) | 1 | 1 | 1 |
| gearbox (4) | 1 | 1 | 0 |
| hydraulic_group (7) | 0 | 1 | 2 |
| generator (0 at 14 d; 1 at 7 d) | – | – | – |

At 30 d, iforest_resid seeds 0/1/2 hit generator_bearing 4/5/4 of 5, transformer 2/2/2 of 2, gearbox 1/1/1 of 4 and hydraulic 2/2/2 of 7.

**Share of scored days that are alarms, per month (matched budget, seed 0):**

| | 2016-03 | 04 | 05 | 06 | 07 | 08 | 09 | 10 | 11 | 12 | 2017-01 | 02 | 03 | 04 | 05 | 06 | 07 | 08 | 09 | 10 | 11 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| iforest_raw | 0.000 | 0.117 | 0.196 | 0.042 | 0.206 | 0.110 | 0.000 | 0.052 | 0.187 | 0.006 | 0.077 | 0.000 | 0.000 | 0.013 | 0.000 | 0.033 | 0.019 | 0.039 | 0.000 | 0.000 | 0.000 |
| iforest_resid | 0.016 | 0.367 | 0.141 | 0.108 | 0.103 | 0.161 | 0.007 | 0.039 | 0.047 | 0.032 | 0.155 | 0.036 | 0.006 | 0.000 | 0.026 | 0.060 | 0.077 | 0.090 | 0.016 | 0.000 | 0.000 |
| threshold_resid | 0.016 | 0.067 | 0.098 | 0.050 | 0.084 | 0.187 | 0.027 | 0.065 | 0.073 | 0.013 | 0.174 | 0.114 | 0.058 | 0.007 | 0.013 | 0.027 | 0.032 | 0.129 | 0.032 | 0.000 | 0.050 |

These shares include the days near incidents, so they are not false-alarm rates.

### Reading

1. **Most of the fix for season came from walk-forward retraining with recent calibration, not from the residual features.**
   - In milestone 1, the raw Isolation Forest trained once on 60 days alarmed on 13-43 % of days per turbine.
   - The same model, retrained every 30 days and z-scored against its last 21+ days, alarms on 0.8-1.2 % of healthy days at k = 5.
   - At the matched budget (k 3.5), its July / August 2016 alarm-day shares are 0.21 / 0.11, against 0.70 / 0.74 in milestone 1.
2. **The residuals remove farm-wide alarms.** At the matched budget, raw-feature alarms hit 3 or more turbines on the same date 12-13 times. Residual alarms do so 3-4 times.
   - Most of the raw-feature dates fall in May and July 2016 (2016-05-02 to 05-04, 07-14 to 07-18, 07-24/25). Weather and grid events hit every turbine at once; a component fault does not.
3. **Isolation Forest on residuals is the best of the three, by a small margin.**
   - At the matched budget it hits 7 / 18 incidents at 14 d (all 3 seeds) against a quiet-window rate of 0.18-0.20, with p = 0.03-0.06.
   - The raw Isolation Forest hits 4-6 / 18 against 0.14-0.17 (p = 0.07-0.33).
   - At the tighter ≤ 0.5 budget, seed 0 of iforest_resid gives 6 / 18 at 14 d vs 0.10 (p = 0.007) and 9 / 18 at 30 d vs 0.17 (p = 0.001). Seeds 1 and 2 give 5 / 18 and 4 / 18 at 14 d.
   - With 18 incidents, a difference of 1-2 hits between detectors is within the seed spread. Treat this as a direction, not a result.
4. **The per-signal threshold on residuals does not work as built.** At the same alarm budget, its hits are indistinguishable from its quiet-window rate (5 / 18 vs 0.22 at 14 d, p = 0.35).
   - At the a-priori k = 5 it alarms on 8.5 % of healthy days (1.7 false-alarm episodes per turbine-month).
   - Taking the maximum |z| over 14 heavy-tailed signals every day produces too many chance extremes.
5. **What the detectors see and miss:**
   - **Seen:** generator bearing incidents (4 / 5 at 14 d for iforest_resid), e.g. T09 2017-01-25 "Generator bearings replaced". In an 18-day episode starting 9 days before, NDE bearing residual z reached +31.7.
   - **Missed:** hydraulic incidents, 0-2 of 7 at 14 d for every detector. That fits the milestone-1 hypothesis that brake-circuit and pitch hydraulic errors leave little trace in hourly temperatures. Gearbox incidents are also missed (1 / 4).
6. **30-day hits are weak evidence.** At ~0.9 alarm-days per turbine-month, a 30-day window has a 0.23-0.30 chance of holding an alarm anyway. Several 30-day "hits" are single alarms 26-30 days before the fault.
7. **Component attribution is poor.** For iforest_resid episodes that start within 30 days before an incident, the top residual group matches the logbook component in **3 of 22** (threshold_resid: 3 of 15). This is the baseline the diagnosis agent in milestone 3 has to beat.

### What didn't work, or needs care

- **Operating hours only** (`--operating-power-min 0.1 --tag m2_operating`): fitting and scoring the residuals only on hours with mean power > 0.1.
  - The threshold detector got worse: 2.06 false-alarm episodes per turbine-month at k = 5, against 1.71 for all hours.
  - Only 25.8 healthy turbine-months were scored, because low-wind days drop below 12 hours.
  - The gaps also make the quiet-window null undefined at 14 and 30 d. We kept all hours.
- **Early models are hard to read.** The first cutoffs train on 39 days and calibrate on 21.
  - April 2016 has the highest alarm share for iforest_resid (0.367). Most of it is T07 in the 30 days before its 2016-04-30 generator-bearing entry (hydraulic-oil and transformer residuals of ±13-15 z), and some is T09 in a healthy period.
  - With so little training data, we cannot tell how much of this is signal.
- **Regime changes after repairs.**
  - After T06's generator replacement (2016-07-11), and around the entry "Generator temperature sensor failure", stator-winding residuals reach z +75 to +83 for weeks.
  - T09's hydraulic-oil residual sits at z −13 to −31 from December 2016 to February 2017.
  - These fall inside the incident margins, so they are not counted as false alarms. The diagnosis agent will still see them.
- **Recent calibration absorbs step changes.** A +40 °C step is flagged until the next retrain and then partly absorbed (see the look-ahead test). Slow drifts that are older than the calibration window will fade the same way.
- **Choices made after looking at this data:**
  - the 45-day incident gap;
  - the operating point (it uses healthy-period labels);
  - scoring only the logbook-covered component groups.

  Seeds, k grid, horizons and margins were fixed before the runs.

### Anomaly episode table (for milestone 3)

`runs/m2_episodes.csv`: one row per episode. There are **no label columns**; `runs/m2_episodes_eval.csv` adds them for scoring only.

- **Columns:**
  - `episode_id`, `turbine_id`, `start`, `end`, `n_days`, `alarm_days`
  - `peak_score`
  - `component_group`: the group of the signal with the largest peak |z|
  - `top_signals`: the top 3 logbook-group signals, with label and signed peak z
  - `context_signal`: the top converter/nacelle signal
  - `model_cutoff`, `detector`, `k`
- **Contents:** each residual detector at its matched ≤ 1 budget.

| | iforest_resid (k 2.5, seed 0) | threshold_resid (k 8) |
|---|---|---|
| Episodes | 77 | 66 |
| By turbine | T01 12, T06 15, T07 22, T09 15, T11 13 | T01 13, T06 10, T07 19, T09 19, T11 5 |
| Start on a healthy day (false alarm) | 29 | 27 |
| Start within 30 d before an incident | 22 (covering 9 incidents) | 15 (8 incidents) |
| Near an incident otherwise (mostly after one) | 26 | 24 |
| Top component group | transformer 18, generator 18, gearbox 14, generator_bearing 11, hydraulic 9, hub 7 | transformer 27, hydraulic 15, generator 11, gearbox 9, generator_bearing 4 |
| Length | median 1 day, max 18 | median 1 day, max 30 |

## Milestone 3 (2026-09-30): diagnosis agent, episodic memory, context gating, replay harness

Code: `episodes.py`, `memory.py`, `agent.py`, `replay.py`; tests in `tests/test_memory_replay.py`. Environment adds pydantic-ai-slim 2.52.0. Model: Qwen3-8B 4-bit on the local mlx-lm server (mlx-lm 0.31.3, `default_model`), thinking off, temperature 0.

**Framing (decision, see PLAN.md):** a case study on 21 incidents. With 22 pre-incident episodes and 29 false alarms, no difference between arms can be claimed statistically; the point is to show what memory changes, episode by episode.

### Setup

- **Episodes:** the 77 `iforest_resid` episodes of `runs/m2_episodes.csv`. Scoring labels come only from `runs/m2_episodes_eval.csv`: 22 **pre-incident** (start ≤ 30 d before an incident, covering 9 incidents), 29 **false alarms** (start on a healthy day), 26 **near incidents** (neither; mostly after repairs).
- **Decision time:** the end of the first alarm day (`start + 1 day`). The m2 episode summary covers the whole episode (up to 18 days), so the agent's summary is rebuilt from the first day only. The agent's tools (residual series of any group, converter/nacelle context and other turbines' scores, maintenance log) return only data before the decision time.
- **Agent output** (`Diagnosis`): `component` (a logbook component or `none`), `action` (inspect / monitor / ignore), `urgency`, `evidence`, `confidence`.
- **Memory record:** (first-day summary + residual vector, diagnosis, outcome). **Outcome** from the logbook only: the first logbook row on the same turbine dated within `[start, start + 30 d]`, known at its `fault_time`; otherwise "no logbook failure within 30 days", known at `start + 31 d`. A deterministic lesson compares the diagnosis with the outcome. Before `known_at`, the memory shows "Outcome: not known yet".
- **Retrieval:** cosine similarity of first-day residual vectors, `sign(z)·log1p(|z|)` over 24 signals (14 scored + 10 context). No embedding model. Pairwise similarity among the 77 episodes (no labels used): median 0.07, 90th percentile 0.55, 95th 0.66.
- **Arms**, each with its own memory, replayed in decision-time order:
  - `none`: no memory block.
  - `ungated`: the 3 most similar past episodes, any age, turbine or similarity, outcome known or not.
  - `gated`: outcome known; similarity ≥ 0.5; ≤ 365 days old; same turbine or same first-day top group; at most 3. Values fixed before any model run.
- **Metrics:** component accuracy on the 22 pre-incident episodes (correct if the component is any of the incident's logbook components, the m2 rule); action appropriateness (inspect on pre-incident, ignore on false alarm; "not inspect" on false alarms is also reported); per-month curve; tokens, requests, tool calls, seconds.

### Detector-only baselines (component, 22 pre-incident episodes)

| Baseline | Correct |
|---|---|
| Top residual group over the whole episode (milestone 2) | 3 / 22 |
| Top residual group on the first alarm day (what the agent sees) | 1 / 22 |

### No look-ahead (tests)

`test_replay_before_a_date_does_not_depend_on_anything_after_it` (one per arm) replays a synthetic farm three times: the base data; the same with the future changed after a split date (a logbook row changes component, a new row appears, residuals are scrambled, an episode is added); and the data cut at the split. A recording `FunctionModel` calls every tool and derives its diagnosis from a hash of everything it read. For every episode decided before the split, the prompt, every tool result, the memories, the gate decisions and the diagnosis are identical in all three runs. The test also checks that the change is visible after the split, and that pre-split prompts hold known outcomes (and, in `ungated`, pending ones). Breaking the store (outcomes always visible) fails 3 tests; letting tools read the first alarm day's next day fails all 3 replay tests.

Test count: 67 (22 new in milestone 3), all offline.

### What the gate lets through (model-independent)

Which memories exist and which pass the gate depend only on the episodes and the logbook, not on what the model answers (as long as no episode errors). From the offline dry run (`make replay-dry`, 77 episodes):

| | ungated | gated |
|---|---|---|
| Memories shown, total (mean per prompt) | 225 (2.92) | 75 (0.97) |
| … with outcome known / pending | 154 / 71 | 75 / 0 |
| … whose outcome is a logbook failure | 70 | 28 |
| Episodes with at least one memory | 76 | 39 |
| … of the 22 pre-incident episodes | 21 | 8 |
| Pre-incident episodes whose prompt shows a past failure of the *right* component | 4 | 1 |
| Similarity of memories shown: min / median | 0.002 / 0.64 | 0.505 / 0.66 |

Gate rejections (candidate-episode pairs, first failing rule): low similarity 2,340, outcome pending 278, other turbine and group 155, too old 58, over k 20.

**Reading.** On this farm, memory can rarely hand the agent the answer: in only 1 (gated) or 4 (ungated) of the 22 pre-incident episodes does a shown memory record a failure of the component that later failed. Whatever memory changes must mostly come from the other direction: past alarms that were followed by nothing.

### Smoke calls (2026-09-30, shared server): NOT the result

6 agent runs (30 chat requests) while the server was also running another article's evaluation. Episodes 0 and 1 in the `none` arm (`runs/m3_smoke1_none.jsonl`); episodes 23 and 47 in `ungated` and `gated` (`runs/m3_smoke2_*.jsonl`). **In the memory smoke runs, the earlier episodes were diagnosed by the offline rule stand-in, not the LLM, so the memory contents differ from the full run.** These runs also preceded two changes: the outcome window now includes the first alarm day, and runs are capped at 12 requests.

| Run | Label | Diagnosis | Requests / tool calls | Input / output tokens | Seconds |
|---|---|---|---|---|---|
| none, ep 0 | pre-incident, generator_bearing | inspect transformer | 4 / 3 | 6,536 / 212 | 20.6 |
| none, ep 1 | pre-incident, generator_bearing | inspect hydraulic_group | 4 / 3 | 6,252 / 237 | 17.0 |
| gated, ep 23 | false alarm | inspect generator | 7 / 5 | 20,649 / 276 | 34.7 |
| ungated, ep 23 | false alarm | inspect generator_bearing | 5 / 3 | 12,663 / 248 | 20.7 |
| gated, ep 47 | pre-incident, generator_bearing | inspect hydraulic_group | 5 / 3 | 9,751 / 239 | 15.8 |
| ungated, ep 47 | pre-incident, generator_bearing | inspect generator_bearing | 5 / 3 | 10,596 / 227 | 14.7 |

- Tool calling and the typed output worked in all 6 runs (0 errors). The model called the tools every time, 3-5 times per episode. Input tokens are summed over the requests of a run.
- Median 18.8 s per episode (14.7-34.7), mean 11,075 input and 240 output tokens.
- All 6 answers were "inspect", including the false alarm. Six runs are far too few to call this a bias; watch for it in the full run.

### Full run, m3 (v1) (2026-09-30)

Ran with `scripts/run_after_queue.sh` (waited for the other job's `QUEUE_DONE`, then `python -m maintenance_agents.replay --model local --arms none,ungated,gated --tag m3 --resume`), 21:27-22:13, 2,725 s for 231 agent runs. Output: `runs/m3_{none,ungated,gated}.jsonl`, `runs/m3_summary.json`, `logs/m3_replay.log`. This is the v1 prompt (`agent.INSTRUCTIONS`, `Diagnosis` without a justification field, memories as a plain list). It is a result, kept as is.

| Arm | Component (of 22) | Inspect on pre-incident (of 22) | Ignore on false alarm (of 29) | Not inspect on false alarm (of 29) | Appropriate (of 51) | Errors | Input / output tokens (mean input per episode) | Requests / tool calls | Median s / episode |
|---|---|---|---|---|---|---|---|---|---|
| none | 1 / 22 | 22 / 22 | 0 / 29 | 0 / 29 | 22 / 51 | 0 | 517,273 / 17,094 (6,718) | 305 / 244 | 12.1 |
| ungated | 2 / 22 | 22 / 22 | 0 / 29 | 0 / 29 | 22 / 51 | 0 | 719,362 / 16,379 (9,342) | 331 / 239 | 13.0 |
| gated | 1 / 22 | 22 / 22 | 0 / 29 | 0 / 29 | 22 / 51 | 0 | 590,892 / 16,417 (7,674) | 322 / 230 | 8.1 |
| detector only | 3 / 22 (whole episode), 1 / 22 (first day) | – | – | – | – | – | 0 | – | – |

**The agent answered "inspect" on all 77 episodes in all three arms** (22 pre-incident, 29 false alarms, 26 near incidents). Urgency was "medium" or "high" every time (none: 64 / 13; ungated: 69 / 8; gated: 70 / 7), confidence 0.75-0.92 (median 0.85 in every arm). "Appropriate" is therefore exactly the 22 pre-incident episodes, in every arm.

**The component was the detector's first-day top group** in 77 / 77 episodes (none), 71 / 77 (ungated) and 72 / 77 (gated). The one episode right in all three arms is episode 66 (T01, transformer), where the detector's top group was already right. So in v1 the agent is the detector plus "inspect"; memory changed nothing that the metrics can see.

**Per-month cumulative curve (v1).** Cumulative appropriate = cumulative pre-incident episodes in every arm (5, 7, 11, 13, 13, 13, 13, 13, 15, 16, 16, 16, 17, 18, 21, 22, 22 from 2016-04 to 2017-09). Cumulative component hits: none and gated 0 until 2017-06, 1 from 2017-07; ungated 1 from 2016-12, 2 from 2017-07. No curve separates.

**Episodes where the arms disagree (v1).** Only the component differs, in 9 episodes (action is "inspect" everywhere):

| Episode | Class | Incident component | none | ungated | gated |
|---|---|---|---|---|---|
| 15 (T09, 2016-06-07) | near incident | – | hydraulic_group | hydraulic_group | generator_bearing |
| 19 (T07, 2016-06-22) | pre-incident | transformer | generator | generator_bearing | generator |
| 25 (T09, 2016-07-16) | false alarm | – | generator | generator_bearing | generator |
| 28 (T06, 2016-08-02) | near incident | – | generator | generator | generator_bearing |
| 33 (T07, 2016-08-31) | near incident | – | generator | generator | generator_bearing |
| 36 (T11, 2016-10-23) | near incident | – | hydraulic_group | generator_bearing | generator_bearing |
| 45 (T09, 2016-12-30) | pre-incident | generator_bearing | generator | **generator_bearing** | generator |
| 52 (T09, 2017-02-17) | near incident | – | hydraulic_group | generator_bearing | generator_bearing |
| 76 (T07, 2017-09-12) | near incident | – | hydraulic_group | generator_bearing | hydraulic_group |

- **Episode 45, the ungated arm's extra hit, is right for a weak reason.** Its three memories were T07 episodes from April 2016 (similarity 0.45, 0.37, 0.34; 245-274 days old), all followed by a T07 generator-bearing failure. The gate would have rejected all three (similarity < 0.5, other turbine and group). The agent wrote "the similarity to past episodes with generator_bearing failures supports this diagnosis".
- **Episode 19 shows the same pull going the wrong way.** The ungated prompt showed episode 15 (similarity 0.77, T09), whose outcome was a generator-bearing failure logged the same day; the agent switched from generator to generator_bearing. The incident was a transformer.
- In all 9 disagreements, the arm that differs from `none` switched to `generator_bearing`: the agent copies the component of a past failure it was shown. Generator bearings dominate the failures memory shows: 44 of 70 failure memories in the ungated prompts, 14 of 28 in the gated prompts.

**Reading.** Memory could not change the decision because the decision never moved from its default. With no cost on an inspection and no explicit base rate, "inspect" is always the safe-looking answer for this model. That is the problem the v2 prompt addresses (see PLAN.md, "Milestone 3, v2").

Seconds are measured on a shared server, so compare arms on tokens, not seconds.

### Full run, m3 (v2) (2026-10-01): one round of fixes

`make replay-v2` = `python -m maintenance_agents.replay --model local --prompt v2 --tag m3v2 --resume`, all three arms in sequence on the shared server. Output: `runs/m3v2_{none,ungated,gated}.jsonl`, `runs/m3v2_summary.json`, `logs/m3v2_replay.log`. Wall time 1,108.7 + 1,401.5 + 731.0 s (about 54 min). The fixes were written into PLAN.md ("Milestone 3, v2") before this run and were not changed after it:

1. **Track record first.** Before the individual memories, the prompt counts what followed similar past alarms, using only outcomes known at decision time (`memory.track_record`). Pool: the arm's gate rules without the k cap (gated: similarity ≥ 0.5, ≤ 365 days, same turbine or top group; ungated: every past alarm on the farm). The `none` arm gets no record.
2. **Justification against the record.** New output field `differs_from_record`. When the record has ≥ 2 known outcomes and more than half were followed by nothing, an "inspect" answer with an empty / "n/a" field is sent back with `ModelRetry`.
3. **Costs and actions in the instructions.** Inspect ≈ one crew-day (cost 1); a failure a timely inspection would have caught ≈ 10; monitor costs nothing now and the detector keeps watching; ignore = explained by something else. An assumption from the domain, not fitted to this data.

A 2-episode plumbing check (episodes 0 and 23, arms none and gated, `runs/m3v2_plumb_*`) ran first: 0 errors; nothing was changed after it.

**v1 vs v2, per arm** (77 episodes each, 0 errors in all six runs):

| Arm | Prompt | Component (of 22) | Inspect on pre-incident (of 22) | Not inspect on false alarm (of 29) | Appropriate (of 51) | Input tokens / episode (mean) | Requests / tool calls | Median s / episode |
|---|---|---|---|---|---|---|---|---|
| none | v1 | 1 / 22 | 22 / 22 | 0 / 29 | 22 / 51 | 6,718 | 305 / 244 | 12.1 |
| none | v2 | 1 / 22 | 22 / 22 | 0 / 29 | 22 / 51 | 8,144 | 325 / 231 | 14.2 |
| ungated | v1 | 2 / 22 | 22 / 22 | 0 / 29 | 22 / 51 | 9,342 | 331 / 239 | 13.0 |
| ungated | v2 | 2 / 22 | 22 / 22 | 0 / 29 | 22 / 51 | 10,738 | 321 / 243 | 16.5 |
| gated | v1 | 1 / 22 | 22 / 22 | 0 / 29 | 22 / 51 | 7,674 | 322 / 230 | 8.1 |
| gated | v2 | 1 / 22 | 22 / 22 | 0 / 29 | 22 / 51 | 7,819 | 282 / 193 | 8.7 |

Total input / output tokens, v2: none 627,075 / 17,954; ungated 826,792 / 21,516; gated 602,023 / 18,165.

**What changed, and what didn't.**

- **Actions: 1 change in 231 decisions.** v2 answered "inspect" in 230 of 231 runs. The only other answer is gated episode 73 (near incident), "monitor". Every pre-incident and false-alarm episode was inspected in every arm, as in v1.
- **Prompt effect (v1 none → v2 none): none on the decisions.** Same 77 / 77 "inspect", same components (the detector's first-day top group in 77 / 77). Urgency moved from 64 medium / 13 high to 56 / 21; confidence 0.80-0.90 (median 0.85).
- **Memory effect (v2 none → v2 ungated / gated): one action, the same two component swaps as v1.** The component differs between arms in 7 episodes (v1: 9). The ungated hit on episode 45 is still there, with the same three low-similarity T07 memories (0.45 / 0.37 / 0.34, 245-274 days old).
- **Components stay the detector's.** The component equals the detector's first-day top group in 77 (none), 73 (ungated) and 73 (gated) of 77 episodes. Component hits: episode 66 in every arm, plus episode 45 in ungated.
- **The record rarely said "mostly nothing", and was overridden when it did.**
  - Gated: the pool had a known outcome in 39 of 77 prompts and included a failure in 25. "Mostly nothing" held in 15 prompts (1 pre-incident, 7 false alarms, 7 near incidents); the agent inspected in 14 of them, each time with a `differs_from_record` text.
  - Ungated: the farm-wide record said "mostly nothing" in 41 prompts (9 pre-incident, 15 false alarms, 17 near incidents); the agent inspected in all 41. Once at least 10 outcomes were known, the farm-wide share of alarms followed by a logbook failure within 30 days ranged from 0.34 to 0.62 (last prompt: 27 of 73).
  - Validator retries were not logged separately; every inspect-against-record answer in the output has a filled justification.
- **Urgency rose in the ungated arm**: "high" in 62 of 77 (v1: 8 of 77), across all classes (17 / 22 pre-incident, 22 / 29 false alarms, 23 / 26 near incidents). Gated: 5 high, 71 medium, 1 low.
- **Cost:** the v2 instructions add about 1.4k input tokens per episode (none 6,718 → 8,144; ungated 9,342 → 10,738). Gated v2 used fewer requests and tool calls than gated v1 (282 / 193 vs 322 / 230), 7,819 input tokens per episode.

**Per-month cumulative curve (v2).** Identical in shape to v1. Cumulative appropriate = cumulative pre-incident episodes in all three arms: 5, 7, 11, 13, 13, 13, 13, 13, 15, 16, 16, 16, 17, 18, 21, 22, 22 (2016-04 → 2017-09; cumulative scored episodes 8, 14, 20, 24, 24, 27, 27, 27, 31, 36, 37, 38, 40, 44, 50, 51, 51). Cumulative component hits: none and gated 0 until 2017-06, 1 from 2017-07; ungated 1 from 2016-12, 2 from 2017-07. The curves do not separate, by arm or by prompt version.

**Episodes (v2).**

- **Episode 73 (T01, 2017-08-25, near incident): the one decision memory changed.** Gated record: 3 similar past transformer alarms (T11 2016-12-23, T01 2017-05-08, T01 2016-08-31; similarity 0.61-0.69), 0 followed by a failure. The gated agent chose monitor / transformer / low urgency: "Similar past alarms … did not result in logbook failures. The residuals suggest a temporary deviation …". The none arm inspected, citing the 2017-08-11 "transformer fan damaged" logbook row 14 days earlier. The ungated arm (farm-wide record) inspected too. Two weeks after a transformer repair, monitor is the defensible call; this episode is not scored as pre-incident or false alarm.
- **Episode 50 (T11, 2017-01-27, false alarm): a justification that contradicts itself.** Gated record: 2 similar past alarms on T11, both followed by nothing. The agent inspected and wrote in `differs_from_record`: "a higher detector score (2.9) compared to past alarms (2.6 and 2.9), and the residual in generator_bearing is higher (+3.1 vs. +3.3 and +3.8)". Both comparisons are false by its own numbers. The validator checks that the field is filled, not that it is true.
- **Episode 17 (T07, 2016-06-13, pre-incident, transformer): the record pointed the wrong way.** Gated record: 2 similar alarms (T11, T09), both followed by nothing. The agent inspected ("more pronounced residuals and a broader thermal anomaly"), named the generator, and a transformer incident followed. Inspect was right here; an agent that obeyed the record would have missed it. This is the 1 pre-incident episode where the gated record said "mostly nothing".
- **Episode 45 (T09, 2016-12-30, pre-incident, generator bearing): unchanged from v1.** The ungated arm still names the generator bearing because of three dissimilar T07 memories that ended in a bearing failure; the gated and none arms still say generator.

**Reading.** On this model and farm, the three fixes did not move the decision. The track record was shown, read and cited, and in 14 of 15 gated "mostly nothing" cases it was overruled with a justification of uneven quality (episode 50). The farm-wide record also undercuts the cost argument: with 34-62 % of alarms followed by a logbook failure within 30 days and a 1 : 10 cost ratio, inspecting every alarm is close to the expected-cost answer, so "inspect" is not obviously wrong for this farm. The memory's outcome agrees with the scoring classes: of the 77 episodes, 27 are followed by a logbook row within 30 days (all 22 pre-incident and 5 near-incident ones) and 50 are not (all 29 false alarms and 21 near-incident ones). That is 35 % overall, and more in the early months, which held most pre-incident episodes (5 of the 8 in April 2016).

**What ~20 incidents can support.** Nothing statistical. 22 pre-incident episodes (9 incidents) and 29 false alarms; the arms differ by at most one component hit and one action, in either version. This is a case study: it shows what memory put in front of the agent and what the agent did with it.
