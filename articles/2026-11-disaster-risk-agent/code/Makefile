.PHONY: test fetch dataset thresholds reference backtest evaluate alerts alerts-queued

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
