.PHONY: test fetch dataset thresholds reference backtest evaluate alerts alerts-queued alerts-pt llm-fusion llm-fusion-score viewer

test:
	uv run pytest -q

fetch:
	uv run python -m disaster_risk.fetch

dataset:
	nice uv run python -m disaster_risk.dataset --rebuild

thresholds:
	nice uv run python -m disaster_risk.thresholds --rebuild

reference:
	nice uv run python -m disaster_risk.reference

backtest: dataset thresholds
	nice uv run python -m disaster_risk.backtest

evaluate: dataset thresholds
	nice uv run python -m disaster_risk.evaluate

alerts:
	PYDANTIC_AI_NO_BANNER=1 uv run python -m disaster_risk.alerts --limit 2

alerts-queued:
	nohup scripts/run_after_queue.sh > logs/run_after_queue.log 2>&1 &

# pt-BR alert texts (the default language), 9 key hours x 3 modes, sequential on the local server.
alerts-pt:
	scripts/run_alerts_pt.sh 2>&1 | tee logs/alerts_pt.log

# LLM-only fusion vs Bayesian fusion (milestone 4): pre-registered hour set, 3 samples per hour on the
# local mlx-lm server (shared: run it alone), then the comparison tables. Resumable.
llm-fusion: dataset thresholds
	nice uv run python -m disaster_risk.llm_fusion prepare
	PYDANTIC_AI_NO_BANNER=1 nice uv run python -m disaster_risk.llm_fusion run

llm-fusion-score:
	uv run python -m disaster_risk.llm_fusion score

# React page that walks one place and hour through the pipeline, from the run files (needs Node) -> http://localhost:5177
viewer:
	uv run python -m disaster_risk.viewer
	npm --prefix viewer install --no-audit --no-fund
	npm --prefix viewer run dev
