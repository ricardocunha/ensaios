.PHONY: sync data audit baseline test

sync:
	uv sync

# ~158 MB download (Wind Farm A only, via HTTP range reads) + EDP failure logbooks
data:
	uv run python -m maintenance_agents.download --farms A

audit:
	uv run python -m maintenance_agents.audit

baseline:
	uv run python -m maintenance_agents.baseline --train-days 60
	uv run python -m maintenance_agents.baseline --train-days 365

test:
	uv run pytest -q
