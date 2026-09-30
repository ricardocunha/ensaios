# Code: maintenance agents that learn from their own mistakes

This article's own project; it shares no dependencies with other articles.

## Quickstart

```bash
make sync       # uv sync (Python 3.12)
make test       # offline tests, no network
make data       # ~158 MB download: CARE to Compare Wind Farm A + EDP failure logbooks -> data/
make audit      # alignment, coverage and label checks -> runs/audit.json
make baseline   # Isolation Forest sanity check -> runs/baseline_*.json
make detect     # milestone 2: walk-forward detectors, incidents, episodes -> runs/m2_*
```

`data/`, `runs/` and `.venv/` are git-ignored. Keep data, weights, run outputs and `.env` out of git.

## Layout

| Module | What it does |
|---|---|
| `maintenance_agents.download` | Pulls only the Wind Farm A members out of CARE's 5.5 GB Zenodo zip with HTTP range reads, and fetches the two EDP failure logbooks (SHA-256 checked). |
| `maintenance_agents.data` | `turbine_series(asset_id)`: tidy 10-minute series per turbine on the real EDP calendar. `fault_events()`: one row per logbook failure, linked to CARE events. `read_event_info()`: CARE's event table. |
| `maintenance_agents.audit` | Checks that overlapping files agree, coverage, status leakage, label counts. |
| `maintenance_agents.baseline` | Milestone 1: per-turbine Isolation Forest, daily alarms, and an event-level check against a quiet-window base rate. |
| `maintenance_agents.features` | Hourly aggregation, operating-state regressors, temperature-rise targets, component groups. |
| `maintenance_agents.detect` | Walk-forward (expanding window) normal-behaviour model + three detectors: raw Isolation Forest, Isolation Forest on residuals, per-signal residual threshold. No future data. |
| `maintenance_agents.incidents` | Logbook rows → incidents (documented merge rule); what the logbook timestamp marks in the SCADA. |
| `maintenance_agents.evaluate` | Event-level scoring (7/14/30-day lead windows, false alarms per turbine-month, per component) and the anomaly episode table for the diagnosis agent. |

Docs: [docs/DATA.md](docs/DATA.md) (dataset choice, licenses, label audit) and [docs/RESULTS.md](docs/RESULTS.md) (measured numbers).

## Data licenses

- CARE to Compare (Zenodo, DOI 10.5281/zenodo.15846963), CC BY-SA 4.0, Gück & Roelofs.
- EDP Open Data wind farm failure logbooks 2016/2017, CC BY-SA 4.0, EDP.

Anything derived from them is shared under CC BY-SA 4.0 too. See [docs/DATA.md](docs/DATA.md).
