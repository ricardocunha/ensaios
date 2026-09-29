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
# Load .env without overriding variables already set, so `VAR=... ./smithtune/run.sh` wins.
if [ -f .env ]; then
  while IFS='=' read -r key value; do
    [[ "$key" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] || continue
    [ -n "${!key+x}" ] || export "$key=$value"
  done < .env
fi

: "${LANGSMITH_WORKSPACE_ID:?set in .env}"
: "${LANGSMITH_PROJECT_ID:?set in .env (UUID of the cnh-extractor-teacher project)}"
PROVIDER="${SMITHTUNE_PROVIDER:-baseten}"
# Student: Baseten can train the 9B; Fireworks' smallest smithtune-supported model is the 27B.
if [ "$PROVIDER" = fireworks ]; then MODEL="${SMITHTUNE_MODEL_FIREWORKS:-qwen3p8-27b}"; else MODEL="${SMITHTUNE_MODEL:-Qwen/Qwen3.5-9B}"; fi
START="${TEACHER_START:-2026-09-25T00:00:00Z}"
END="${TEACHER_END:-$(date -u +%Y-%m-%dT%H:%M:%SZ)}"
GOLDEN_DIR=runs/smithtune/golden
TRIAGE_DIR=runs/smithtune/triage-sample
RUN_DIR="runs/smithtune/train-$PROVIDER"
# Replay-eval judge. smithtune's default is a Baseten model, so use a Fireworks judge there.
if [ "$PROVIDER" = fireworks ]; then JUDGE="${JUDGE_MODEL:-accounts/fireworks/models/deepseek-v4p1-flash}"; else JUDGE="${JUDGE_MODEL:-baseten/zai-org/GLM-5.3-Flash}"; fi
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
      --filter "$GOLDEN_FILTER" --target-count "${GOLDEN_TARGET:-1000}" --no-triage ;;
  push-golden)  # preview first, then upload as a new LangSmith dataset
    smithtune dataset push "$GOLDEN_DIR" --name cnh-extractor-golden
    confirm "Upload the golden trajectories to LangSmith as dataset cnh-extractor-golden." && \
      smithtune dataset push "$GOLDEN_DIR" --name cnh-extractor-golden --confirm ;;
  triage-sample)  # Experiment: does the agent council agree with our ground truth?
    smithtune dataset pull "$TRIAGE_DIR" --workspace-id "$LANGSMITH_WORKSPACE_ID" \
      --project-id "$LANGSMITH_PROJECT_ID" --start-time "$START" --end-time "$END" \
      --target-count 200
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
    smithtune plan --provider "$PROVIDER" --data-dir "$GOLDEN_DIR" --evaluate --judge-model "$JUDGE" --max-points-per-trajectory 2 ;;
  train)
    # Fireworks bills per training token and has no spend flag in smithtune: cap epochs instead.
    confirm "LoRA SFT of $MODEL on $PROVIDER (max ${MAX_EPOCHS:-5} epochs)." && \
      smithtune train --provider "$PROVIDER" --data-dir "$GOLDEN_DIR" --run-dir "$RUN_DIR" --evaluate \
        --judge-model "$JUDGE" --max-epochs "${MAX_EPOCHS:-5}" --confirm ;;
  evaluate)
    smithtune eval-plan --provider "$PROVIDER" --data-dir "$GOLDEN_DIR" --run-dir "$RUN_DIR"
    confirm "Replay evaluation (base vs tuned)." && \
      smithtune evaluate --provider "$PROVIDER" --data-dir "$GOLDEN_DIR" --run-dir "$RUN_DIR" --judge-model "$JUDGE" --confirm ;;
  deploy)
    if [ "$PROVIDER" = fireworks ]; then
      : "${FIREWORKS_ACCOUNT_ID:?set in .env}"
      confirm "Deploy the tuned model on Fireworks (billed until undeploy!)." && \
        smithtune deploy --provider fireworks --run-dir "$RUN_DIR" --account-id "$FIREWORKS_ACCOUNT_ID" \
          --output-model-id cnh-extractor-student --confirm
    else
      confirm "Deploy the tuned model on an H200 (billed per minute until undeploy!)." && \
        smithtune deploy --provider baseten --run-dir "$RUN_DIR" --accelerator H200:1 --max-seq-len 32768 --confirm
    fi ;;
  student-eval)
    : "${STUDENT_URL:?OpenAI-compatible URL printed by deploy}"; : "${STUDENT_MODEL:?model name printed by deploy}"
    uv run python -m cnh_ocr.extractor.run --role student --student-url "$STUDENT_URL" \
      --student-model "$STUDENT_MODEL" --data data/synth/test --project cnh-extractor-student ;;
  undeploy)
    if [ "$PROVIDER" = fireworks ]; then
      smithtune undeploy --provider fireworks --run-dir "$RUN_DIR" --account-id "$FIREWORKS_ACCOUNT_ID" --confirm
    else
      smithtune undeploy --provider baseten --run-dir "$RUN_DIR" --confirm
    fi ;;
  *)
    sed -n '2,8p' "$0"; exit 1 ;;
esac
