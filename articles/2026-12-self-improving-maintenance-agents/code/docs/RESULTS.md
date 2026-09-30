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
