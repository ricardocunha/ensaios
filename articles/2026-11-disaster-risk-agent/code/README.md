# Code: disaster-risk agent

This article's own uv project (`disaster_risk`); it shares no dependencies with other articles.

```bash
make test    # offline tests (network access is blocked inside tests)
make fetch   # download the audit dataset (~150 MB) into data/, which is git-ignored
```

Milestone 1 (data audit) is done: see [docs/DATA.md](docs/DATA.md) for every source, its endpoint,
access, license and what actually worked. Two sources need a manual browser download (CEMADEN: CAPTCHA;
S2iD: the server rejects scripted downloads). `make fetch` tells you where to save them.

Layout:

- `src/disaster_risk/basin.py`: event window and station lists.
- `src/disaster_risk/sources/`: one downloader + parser per source (`ana`, `inmet`, `copernicus_ems`, `ufrgs_impact`, `cemaden`, `s2id`).
- `src/disaster_risk/fetch.py`: runs all of them and prints the samples used in DATA.md.

Keep data, weights, run outputs and `.env` out of git (see `.gitignore`).
