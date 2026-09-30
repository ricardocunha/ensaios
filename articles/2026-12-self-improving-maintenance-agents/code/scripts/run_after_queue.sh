#!/usr/bin/env bash
# Milestone 3 full replay (77 episodes x 3 arms) on the shared local mlx-lm server.
#
# The server at $AGENT_BASE_URL (default http://localhost:8088/v1) is busy with another
# article's evaluation. This script waits until that queue writes its QUEUE_DONE file,
# checks that the server still answers (it never starts a server itself), then runs the
# replay. Output: runs/m3_{none,ungated,gated}.jsonl, runs/m3_summary.json, logs/m3_replay.log,
# and runs/M3_REPLAY_DONE or runs/M3_REPLAY_FAILED at the end.
#
#   nohup scripts/run_after_queue.sh >/dev/null 2>&1 &
set -uo pipefail

CODE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
QUEUE_DONE="${QUEUE_DONE:-/Users/ricardocunha/dev/personal/ensaios-worktrees/2026-10-compliance-document-agents/articles/2026-10-compliance-document-agents/code/runs/QUEUE_DONE}"
BASE_URL="${AGENT_BASE_URL:-http://localhost:8088/v1}"
LOG="$CODE_DIR/logs/m3_replay.log"
PY="$CODE_DIR/.venv/bin/python"
mkdir -p "$CODE_DIR/logs" "$CODE_DIR/runs"
cd "$CODE_DIR" || exit 1
rm -f runs/M3_REPLAY_DONE runs/M3_REPLAY_FAILED
log() { echo "$(date '+%Y-%m-%d %H:%M:%S') $*" >> "$LOG"; }

log "pid $$ waiting for $QUEUE_DONE"
while [ ! -f "$QUEUE_DONE" ]; do sleep 60; done
log "queue done; checking $BASE_URL"

up=0
for _ in $(seq 1 30); do
  if curl -sf -m 10 "$BASE_URL/models" >/dev/null; then up=1; break; fi
  sleep 60
done
if [ "$up" != 1 ]; then
  log "server not reachable after 30 min; not starting one. Exiting."
  touch runs/M3_REPLAY_FAILED
  exit 1
fi

export PYDANTIC_AI_NO_BANNER=1
start=$(date +%s)
log "replay start"
nice -n 10 "$PY" -m maintenance_agents.replay --model local --arms none,ungated,gated --tag m3 --resume >> "$LOG" 2>&1
rc=$?
# one retry pass if any episode failed for infrastructure reasons (resume recomputes from the first gap)
if [ $rc -eq 0 ] && grep -q '"error": "' runs/m3_*.jsonl 2>/dev/null; then
  log "errors recorded; one resume pass"
  nice -n 10 "$PY" -m maintenance_agents.replay --model local --arms none,ungated,gated --tag m3 --resume >> "$LOG" 2>&1
  rc=$?
fi
log "replay exit $rc after $(( $(date +%s) - start )) s"
if [ $rc -eq 0 ]; then touch runs/M3_REPLAY_DONE; else touch runs/M3_REPLAY_FAILED; fi
exit $rc
