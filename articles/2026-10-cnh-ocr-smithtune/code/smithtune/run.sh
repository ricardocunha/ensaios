#!/usr/bin/env bash
# smithtune v0.1.0 walkthrough for the CNH Extractor (Stage 2).
#
# Usage: ./smithtune/run.sh <step>
# Steps, in order:
#   install doctor pull-golden push-golden triage-sample prepare plan train evaluate deploy student-eval undeploy
#
# Every step that spends money pauses for a y/N before it passes --confirm to smithtune.
set -euo pipefail
cd "$(dirname "$0")/.."
set -a; [ -f .env ] && . ./.env; set +a

: "${LANGSMITH_WORKSPACE_ID:?set in .env}"
: "${LANGSMITH_PROJECT_ID:?set in .env (UUID of the cnh-extractor-teacher project)}"
PROVIDER="${SMITHTUNE_PROVIDER:-baseten}"
MODEL="${SMITHTUNE_MODEL:-Qwen/Qwen3.5-9B}"
START="${TEACHER_START:-2026-09-25T00:00:00Z}"
END="${TEACHER_END:-$(date -u +%Y-%m-%dT%H:%M:%SZ)}"
GOLDEN_DIR=runs/smithtune/golden
TRIAGE_DIR=runs/smithtune/triage-sample
RUN_DIR=runs/smithtune/train-qwen35-9b
# Trusted quality signal: our own ground-truth grading, written as LangSmith feedback by extractor/run.py
GOLDEN_FILTER='and(eq(feedback_key, "exact"), eq(feedback_score, 1))'

confirm() { read -r -p "$1 This spends money. Continue? [y/N] " ok; [[ "$ok" == "y" ]]; }

case "${1:-}" in
  install)
    uv tool install --python 3.12 \
      --overrides https://raw.githubusercontent.com/langchain-ai/smithtune/v0.1.0/overrides.txt \
      'smithtune[deepagents] @ git+https://github.com/langchain-ai/smithtune.git@v0.1.0'
    smithtune acknowledge-data-rights ;;
  doctor)
    smithtune doctor
    smithtune models list || true ;;
  pull-golden)  # Golden Trajectories selected by feedback, no council
    smithtune dataset pull "$GOLDEN_DIR" --workspace-id "$LANGSMITH_WORKSPACE_ID" \
      --project-id "$LANGSMITH_PROJECT_ID" --start-time "$START" --end-time "$END" \
      --filter "$GOLDEN_FILTER" --target-count 1000 --no-triage --name cnh-extractor-golden ;;
  push-golden)
    smithtune dataset push "$GOLDEN_DIR" --confirm ;;
  triage-sample)  # Experiment: does the agent council agree with our ground truth?
    smithtune dataset pull "$TRIAGE_DIR" --workspace-id "$LANGSMITH_WORKSPACE_ID" \
      --project-id "$LANGSMITH_PROJECT_ID" --start-time "$START" --end-time "$END" \
      --target-count 200 --name cnh-extractor-triage-sample
    smithtune dataset triage "$TRIAGE_DIR" --rubric smithtune/rubric.md   # preview only
    confirm "Council triage on ~200 trajectories." && \
      smithtune dataset triage "$TRIAGE_DIR" --rubric smithtune/rubric.md --confirm
    echo "Now run: uv run python -m cnh_ocr.evaluation.council_agreement $TRIAGE_DIR" ;;
  prepare)
    # The dataset ID comes from push-golden's receipt; .env's GOLDEN_DATASET_ID only overrides it.
    GOLDEN_DATASET_ID="${GOLDEN_DATASET_ID:-$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["dataset_id"])' \
      "$GOLDEN_DIR/dataset-import.json" 2>/dev/null)}"
    : "${GOLDEN_DATASET_ID:?run ./smithtune/run.sh push-golden first (no dataset-import.json receipt yet)}"
    echo "Using golden dataset $GOLDEN_DATASET_ID"
    smithtune prepare --provider "$PROVIDER" --model "$MODEL" \
      --workspace-id "$LANGSMITH_WORKSPACE_ID" --dataset-id "$GOLDEN_DATASET_ID" --data-dir "$GOLDEN_DIR" ;;
  plan)
    smithtune plan --provider "$PROVIDER" --data-dir "$GOLDEN_DIR" --evaluate --max-points-per-trajectory 2 ;;
  train)
    confirm "LoRA SFT of $MODEL on $PROVIDER." && \
      smithtune train --provider "$PROVIDER" --data-dir "$GOLDEN_DIR" --run-dir "$RUN_DIR" --evaluate --confirm ;;
  evaluate)
    smithtune eval-plan --provider "$PROVIDER" --data-dir "$GOLDEN_DIR" --run-dir "$RUN_DIR"
    confirm "Replay evaluation (base vs tuned)." && \
      smithtune evaluate --provider "$PROVIDER" --data-dir "$GOLDEN_DIR" --run-dir "$RUN_DIR" --confirm ;;
  deploy)
    confirm "Deploy the tuned model on an H200 (billed per minute until undeploy!)." && \
      smithtune deploy --provider "$PROVIDER" --run-dir "$RUN_DIR" --accelerator H200:1 --max-seq-len 32768 --confirm ;;
  student-eval)
    : "${STUDENT_URL:?OpenAI-compatible URL printed by deploy}"; : "${STUDENT_MODEL:?model name printed by deploy}"
    uv run python -m cnh_ocr.extractor.run --role student --student-url "$STUDENT_URL" \
      --student-model "$STUDENT_MODEL" --data data/synth/test --project cnh-extractor-student ;;
  undeploy)
    smithtune undeploy --provider "$PROVIDER" --run-dir "$RUN_DIR" --confirm ;;
  *)
    sed -n '2,8p' "$0"; exit 1 ;;
esac
