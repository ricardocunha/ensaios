# Code: disaster-risk agent

This article's own uv project (`disaster_risk`); it shares no dependencies with other articles.

```bash
make test        # offline tests (network access is blocked inside tests)
make fetch       # download the raw data into data/ (git-ignored): audit files, ANA history, SGB bulletins
make dataset     # build data/cache/hourly.csv (tidy hourly dataset) and print coverage
make thresholds  # station level thresholds from the 2019-2024 ANA record
make reference   # official bulletin times and flood-level crossings per gauge
make backtest    # replay 2024-04-20 -> 05-20 hour by hour, write runs/signals.csv
```

Reading the SGB bulletins needs `pdftotext` (poppler) and `curl`; everything else is the Python standard library.

Milestone 1 (data audit) is done: see [docs/DATA.md](docs/DATA.md) for every source, its endpoint,
access, license and what actually worked. Two sources need a manual browser download (CEMADEN: CAPTCHA;
S2iD: the server rejects scripted downloads). `make fetch` tells you where to save them.

Milestone 2 (signal adapters + cached dataset + replay skeleton) is done: results in
[docs/RESULTS.md](docs/RESULTS.md), clock/unit verification and alert-time sources in DATA.md.

Layout:

- `src/disaster_risk/basin.py`: event window, station lists, time conventions, official flood levels.
- `src/disaster_risk/dataset.py`: tidy hourly dataset (UTC, hour-ending, explicit staleness, no interpolation).
- `src/disaster_risk/thresholds.py`: per-station level quantiles from the historical record.
- `src/disaster_risk/observations.py`: point-in-time snapshots; the no-look-ahead boundary.
- `src/disaster_risk/signals/`: one adapter per source (`ana`, `inmet`, `copernicus_ems`) emitting `Signal` records; the scoring rules are in each module's docstring.
- `src/disaster_risk/backtest.py`: hour-by-hour replay (fusion comes in milestone 3).
- `src/disaster_risk/reference.py`: "in time" references (SACE bulletins, flood-level crossings).
- `src/disaster_risk/sources/`: one downloader + parser per source (`ana`, `inmet`, `copernicus_ems`, `ufrgs_impact`, `cemaden`, `s2id`, `sgb_sace`).
- `src/disaster_risk/fetch.py`: runs all of them and prints the samples used in DATA.md.

Keep data, weights, run outputs and `.env` out of git (see `.gitignore`).
