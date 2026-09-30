#!/usr/bin/env bash
# Milestone 3 full evaluation, queued behind the compliance article's LLM jobs.
#
# Waits for the other article's QUEUE_DONE marker (it shares the one local
# mlx-lm server), checks that the server still answers, then runs 3 repeated
# agent pipelines at 5/10/20% budgets with Qwen3-8B (thinking off).
# It never starts a server: if none answers, it logs and exits 2.
#
# Start (survives the shell):
#   nohup scripts/run_after_queue.sh > runs/m3-queue.log 2>&1 &
set -euo pipefail

CODE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
QUEUE_DONE="${QUEUE_DONE:-/Users/ricardocunha/dev/personal/ensaios-worktrees/2026-10-compliance-document-agents/articles/2026-10-compliance-document-agents/code/runs/QUEUE_DONE}"
BASE_URL="${ROAD_AGENTS_BASE_URL:-http://localhost:8088/v1}"
POLL_S="${POLL_S:-120}"
OUT="${OUT:-$CODE_DIR/runs/m3-eval-local.jsonl}"

cd "$CODE_DIR"
mkdir -p runs
echo "$(date '+%F %T') waiting for $QUEUE_DONE (poll ${POLL_S}s), pid $$"
while [ ! -e "$QUEUE_DONE" ]; do
  sleep "$POLL_S"
done
echo "$(date '+%F %T') queue done"

for i in 1 2 3 4 5; do
  if curl -sf -m 10 "$BASE_URL/models" > /dev/null; then
    break
  fi
  if [ "$i" = 5 ]; then
    echo "$(date '+%F %T') no server at $BASE_URL; not starting one. Exiting." >&2
    exit 2
  fi
  sleep 60
done
echo "$(date '+%F %T') server answers at $BASE_URL; starting evaluation -> $OUT"

nice -n 10 uv run python scripts/evaluate_agents.py \
  --model local --runs 3 --budgets 0.05 0.10 0.20 --out "$OUT"
status=$?
echo "$(date '+%F %T') evaluation finished with status $status"
touch "$CODE_DIR/runs/M3_EVAL_DONE"
