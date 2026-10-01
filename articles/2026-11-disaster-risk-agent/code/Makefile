.PHONY: test fetch dataset thresholds reference backtest evaluate alerts alerts-queued llm-fusion llm-fusion-score

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

# LLM-only fusion vs Bayesian fusion (milestone 4): pre-registered hour set, 3 samples per hour on the
# local mlx-lm server (shared: run it alone), then the comparison tables. Resumable.
llm-fusion: dataset thresholds
	nice uv run python -m disaster_risk.llm_fusion prepare
	PYDANTIC_AI_NO_BANNER=1 nice uv run python -m disaster_risk.llm_fusion run

llm-fusion-score:
	uv run python -m disaster_risk.llm_fusion score
