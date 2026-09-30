.PHONY: test fetch dataset thresholds reference backtest

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
