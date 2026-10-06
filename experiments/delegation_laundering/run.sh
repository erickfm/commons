#!/usr/bin/env bash
# Run every delegation laundering condition for one model, 10 runs each.
#   experiments/delegation_laundering/run.sh claude-haiku-4-5-20251001 anthropic/claude-haiku-4-5-20251001
set -uo pipefail
short=$1 model=$2
for f in experiments/delegation_laundering/scenarios/${short}__*.yaml; do
  uv run inspect eval commons/tasks.py -T scenario="$f" --model "$model" --epochs "${EPOCHS:-10}" \
    --max-samples "${MAX_SAMPLES:-5}" --log-dir "logs/deleg/main/$short" --display plain
done
