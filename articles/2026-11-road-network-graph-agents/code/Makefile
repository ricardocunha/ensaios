CITY ?= belo-horizonte
K ?= 500
PAIRS ?= 1000

.PHONY: install test smoke bench bench-exact

install:
	uv sync

test:
	uv run pytest -q

# Downloads and caches the OSM graph and POIs on the first run (needs network).
smoke:
	uv run python scripts/smoke_city.py $(CITY) --k $(K) --pairs $(PAIRS)

bench:
	uv run python scripts/bench_betweenness.py $(CITY) --k 100 500 2000

# Exact betweenness: ~27 min on Porto Alegre, est. 69-86 min on Belo Horizonte (docs/RESULTS.md).
bench-exact:
	uv run python scripts/bench_betweenness.py $(CITY) --k 100 500 2000 --exact
