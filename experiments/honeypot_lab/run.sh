#!/usr/bin/env bash
# Run every honeypot lab condition for one model: 4 runs of 5 agents each.
#   experiments/honeypot_lab/run.sh claude-haiku-4-5-20251001 anthropic/claude-haiku-4-5-20251001
set -uo pipefail
short=$1 model=$2
for f in experiments/honeypot_lab/scenarios/${short}__*.yaml; do
  uv run inspect eval commons/tasks.py -T scenario="$f" --model "$model" --epochs "${EPOCHS:-4}" \
    --max-samples "${MAX_SAMPLES:-4}" --log-dir "logs/honeypot/main/$short" --display plain
done
