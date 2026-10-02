# Code: disaster-risk agent

This article's own uv project (`disaster_risk`); it shares no dependencies with other articles.

```bash
make test        # offline tests (network access is blocked inside tests)
make fetch       # download the raw data into data/ (git-ignored): audit files, ANA history, SGB bulletins
make dataset     # build data/cache/hourly.csv (tidy hourly dataset) and print coverage
make thresholds  # station level thresholds from the 2019-2024 ANA record
make reference   # official bulletin times and flood-level crossings per gauge
make backtest    # replay 2024-04-20 -> 05-20 hour by hour, write runs/signals.csv
make evaluate    # milestone 3: fusion, lead times, false alarms, calibration, ablations -> runs/m3/
make alerts      # alert agent on 2 key hours (needs the local LLM server at localhost:8088)
make alerts-queued  # scripts/run_after_queue.sh: English alert texts (--lang en), all key hours, 3 modes, after the shared server's queue
make alerts-pt   # pt-BR alert texts (the default language): 9 key hours x 3 modes -> runs/m3/alerts_pt.jsonl
make llm-fusion  # LLM-only fusion on the pre-registered hours (3 samples each, local LLM server) -> runs/m4/
make llm-fusion-score  # LLM-only vs Bayesian fusion: leads, quiet-hour alerts, Brier, run-to-run spread
```

`make evaluate` also downloads the INMET yearly files 2019-2023 (about 100 MB each) for the historical replay.
The alert agent uses Pydantic AI against any OpenAI-compatible server (`ALERT_BASE_URL`, `ALERT_MODEL`);
tests use Pydantic AI's `TestModel`/`FunctionModel` and never call a model.

Reading the SGB bulletins needs `pdftotext` (poppler) and `curl`; everything else is the Python standard library.

Milestone 1 (data audit) is done: see [docs/DATA.md](docs/DATA.md) for every source, its endpoint,
access, license and what actually worked. Two sources need a manual browser download (CEMADEN: CAPTCHA;
S2iD: the server rejects scripted downloads). `make fetch` tells you where to save them.

Milestone 2 (signal adapters + cached dataset + replay skeleton) is done: results in
[docs/RESULTS.md](docs/RESULTS.md), clock/unit verification and alert-time sources in DATA.md.

Milestone 3 (fusion + backtest + alert agent) is done: results in [docs/RESULTS.md](docs/RESULTS.md);
the queued alert-agent run (9 key hours x 3 modes) is in RESULTS.md.

Milestone 4 (LLM-only fusion vs Bayesian fusion) is done: results in [docs/RESULTS.md](docs/RESULTS.md).

Layout:

- `src/disaster_risk/basin.py`: event window, station lists, time conventions, official flood levels.
- `src/disaster_risk/dataset.py`: tidy hourly dataset (UTC, hour-ending, explicit staleness, no interpolation).
- `src/disaster_risk/thresholds.py`: per-station level quantiles from the historical record.
- `src/disaster_risk/observations.py`: point-in-time snapshots; the no-look-ahead boundary.
- `src/disaster_risk/signals/`: one adapter per source (`ana`, `inmet`, `copernicus_ems`) emitting `Signal` records; the scoring rules are in each module's docstring.
- `src/disaster_risk/backtest.py`: hour-by-hour replay.
- `src/disaster_risk/fusion.py`: places, the log-odds fusion formula, risk levels, ablation configs.
- `src/disaster_risk/labels.py`: "flood level within 24 h" labels and priors (scoring only; they look ahead by design).
- `src/disaster_risk/history.py`: the 2019-2024-04 record as an hourly dataset, replayed in chunks.
- `src/disaster_risk/calibration.py`: empirical LR per signal band, fitted on 2019-2022.
- `src/disaster_risk/evaluate.py`: lead times vs references and SACE bulletins, false alarms, Brier, ablations.
- `src/disaster_risk/alerts.py`: the alert agent (Pydantic AI, typed output) and the deterministic citation audit.
- `src/disaster_risk/llm_fusion.py`: LLM-only fusion baseline (same per-hour signals, fixed prompt, pre-registered hours) and its scoring.
- `scripts/run_after_queue.sh`: waits for the shared LLM server's queue, then writes alert texts for the key hours.
- `src/disaster_risk/reference.py`: "in time" references (SACE bulletins, flood-level crossings).
- `src/disaster_risk/sources/`: one downloader + parser per source (`ana`, `inmet`, `copernicus_ems`, `ufrgs_impact`, `cemaden`, `s2id`, `sgb_sace`).
- `src/disaster_risk/fetch.py`: runs all of them and prints the samples used in DATA.md.

Keep data, weights, run outputs and `.env` out of git (see `.gitignore`).
