#!/usr/bin/env bash
# Run every memetic immunity condition for one model, 10 runs each.
#   experiments/memetic_immunity/run.sh claude-haiku-4-5-20251001 anthropic/claude-haiku-4-5-20251001
set -uo pipefail
short=$1 model=$2
for f in experiments/memetic_immunity/scenarios/${short}__*.yaml; do
  uv run inspect eval commons/tasks.py -T scenario="$f" --model "$model" --epochs "${EPOCHS:-10}" \
    --max-samples "${MAX_SAMPLES:-5}" --log-dir "logs/memetic/main/$short" --display plain
done
