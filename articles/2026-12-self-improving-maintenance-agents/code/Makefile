.PHONY: sync data audit baseline detect detect-operating test

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

# milestone 2: walk-forward NBM residual detectors vs logbook incidents (~5 min; 5 single-thread jobs)
detect:
	OMP_NUM_THREADS=1 nice uv run python -m maintenance_agents.evaluate --jobs 5

# ablation: residual detectors on operating hours only (power > 0.1)
detect-operating:
	OMP_NUM_THREADS=1 nice uv run python -m maintenance_agents.evaluate --jobs 5 --tag m2_operating --operating-power-min 0.1

test:
	uv run pytest -q
