CITY ?= belo-horizonte
K ?= 500
PAIRS ?= 1000

.PHONY: install test smoke bench bench-exact betweenness sections maps agents-dry agents-smoke agents-eval agents-queue agents-regrade

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

# Milestone 3. No LLM: the whole pipeline with a scripted FunctionModel.
agents-dry:
	nice uv run python scripts/evaluate_agents.py --model scripted --runs 1

# Needs the local mlx-lm server (Qwen3-8B) at http://localhost:8088/v1. At most 13 LLM requests.
agents-smoke:
	nice uv run python scripts/evaluate_agents.py --model local --runs 1 --budgets 0.10 --limits 5 6 2 --out runs/m3-smoke.jsonl

# Full evaluation: 3 runs x 5/10/20% budgets.
agents-eval:
	nice uv run python scripts/evaluate_agents.py --model local --runs 3 --budgets 0.05 0.10 0.20

# Re-score the prose-number audit of the full run (replays the logged tool calls, no LLM).
agents-regrade:
	nice uv run python scripts/regrade_text_audit.py runs/m3-eval-local.jsonl

# Same, but waits for the compliance article's queue to finish first (nohup, survives the shell).
agents-queue:
	nohup scripts/run_after_queue.sh > runs/m3-queue.log 2>&1 &
