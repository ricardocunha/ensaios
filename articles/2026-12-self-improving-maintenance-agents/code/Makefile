.PHONY: sync data audit baseline detect detect-operating replay-dry replay replay-v2 replay-queued test

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

# milestone 3: harness dry run with the offline rule stand-in (no server, seconds)
replay-dry:
	PYDANTIC_AI_NO_BANNER=1 uv run python -m maintenance_agents.replay --model rule --tag m3_dryrun_rule

# milestone 3: full replay, 77 episodes x 3 arms, on the local OpenAI-compatible server ($$AGENT_BASE_URL)
replay:
	PYDANTIC_AI_NO_BANNER=1 nice uv run python -m maintenance_agents.replay --model local --tag m3 --resume

# milestone 3, v2 prompt (costs, track record, justification; PLAN.md), all three arms
replay-v2:
	PYDANTIC_AI_NO_BANNER=1 nice uv run python -m maintenance_agents.replay --model local --prompt v2 --tag m3v2 --resume

# the same, queued behind another job's QUEUE_DONE file (survives logout)
replay-queued:
	nohup scripts/run_after_queue.sh >/dev/null 2>&1 &

test:
	PYDANTIC_AI_NO_BANNER=1 uv run pytest -q
