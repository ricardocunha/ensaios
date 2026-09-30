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
