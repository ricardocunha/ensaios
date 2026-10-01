#!/usr/bin/env bash
# Portuguese (pt-BR) alert texts for the 9 key hours x 3 modes, run sequentially on the local
# mlx-lm server (http://localhost:8088/v1, Qwen3-8B as "default_model", thinking off).
# Output: runs/m3/alerts_pt.jsonl, summary runs/m3/alerts_pt_summary.json. The English run of
# milestone 3 (runs/m3/alerts_queued.jsonl) is reproduced with --lang en.
set -euo pipefail

cd "$(dirname "$0")/.."
OUT="runs/m3/alerts_pt.jsonl"
export PYDANTIC_AI_NO_BANNER=1

curl -sf -m 10 http://localhost:8088/v1/models > /dev/null || { echo "server not answering"; exit 1; }
rm -f "$OUT"
echo "$(date '+%F %T') starting"
nice uv run python -m disaster_risk.alerts --lang pt --out "$OUT" --output-mode tool
nice uv run python -m disaster_risk.alerts --lang pt --out "$OUT" --output-mode tool --audit-retry
nice uv run python -m disaster_risk.alerts --lang pt --out "$OUT" --output-mode prompted
uv run python -m disaster_risk.alerts --out "$OUT" --summary | tee runs/m3/alerts_pt_summary.json
echo "$(date '+%F %T') finished"
