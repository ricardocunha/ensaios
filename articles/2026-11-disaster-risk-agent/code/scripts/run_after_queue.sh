#!/usr/bin/env bash
# Generate alert texts for the key hours once the shared local LLM server is free.
#
# The mlx-lm server at http://localhost:8088/v1 (Qwen3-8B as "default_model") is
# shared with other articles. This script waits for the compliance article's
# queue marker, then runs the alert agent sequentially on every key hour in
# runs/m3/key_hours.json (written by `make evaluate`) in three modes and runs
# the citation audit on every text. Output: runs/m3/alerts_queued.jsonl,
# summary: runs/m3/alerts_queued_summary.json. Start it with:
#
#   nohup scripts/run_after_queue.sh > logs/run_after_queue.log 2>&1 &
set -euo pipefail

cd "$(dirname "$0")/.."
QUEUE_DONE="${QUEUE_DONE:-/Users/ricardocunha/dev/personal/ensaios-worktrees/2026-10-compliance-document-agents/articles/2026-10-compliance-document-agents/code/runs/QUEUE_DONE}"
OUT="runs/m3/alerts_queued.jsonl"
export PYDANTIC_AI_NO_BANNER=1

echo "$(date '+%F %T') waiting for $QUEUE_DONE"
while [ ! -f "$QUEUE_DONE" ]; do
  sleep 60
done
echo "$(date '+%F %T') queue done; starting"

until curl -sf -m 10 http://localhost:8088/v1/models > /dev/null; do
  echo "$(date '+%F %T') server not answering; retrying in 60 s"
  sleep 60
done

if [ ! -f runs/m3/key_hours.json ]; then
  nice uv run python -m disaster_risk.evaluate > logs/evaluate_queued.log 2>&1
fi

rm -f "$OUT"
nice uv run python -m disaster_risk.alerts --out "$OUT" --output-mode tool
nice uv run python -m disaster_risk.alerts --out "$OUT" --output-mode tool --audit-retry
nice uv run python -m disaster_risk.alerts --out "$OUT" --output-mode prompted
uv run python -m disaster_risk.alerts --out "$OUT" --summary | tee runs/m3/alerts_queued_summary.json
echo "$(date '+%F %T') finished"
