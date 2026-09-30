CITY ?= belo-horizonte
K ?= 500
PAIRS ?= 1000

.PHONY: install test smoke bench bench-exact betweenness sections maps

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

# Milestone 2. Sampled betweenness cached in data/ (~5 min for k=2000 on BH).
betweenness:
	nice uv run python scripts/cache_betweenness.py $(CITY) --k 500
	nice uv run python scripts/cache_betweenness.py $(CITY) --k 2000

# Downloads the BH Digital CSVs once (~250 MB) into data/pbh/.
sections:
	nice uv run python scripts/section_pipeline.py $(CITY) --k 2000

maps:
	uv run python scripts/maps.py $(CITY) --k 2000
