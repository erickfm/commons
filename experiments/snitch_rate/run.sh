#!/usr/bin/env bash
# Run every Snitch Rate condition for one model: 30 runs of each solo condition, 15 of each 4-agent one.
#   experiments/snitch_rate/run.sh claude-haiku-4-5-20251001 anthropic/claude-haiku-4-5-20251001
# Logs go to logs/snitch/main/<short name>/. MAX_SAMPLES caps concurrent runs (default 4).
set -euo pipefail
short=$1 model=$2
dir=experiments/snitch_rate/scenarios
for cond in n1_mentioned n1_available n4_mentioned n4_available; do
  epochs=$([[ $cond == n1_* ]] && echo 30 || echo 15)
  uv run inspect eval commons/tasks.py -T scenario=$dir/${short}__${cond}.yaml --model "$model" \
    --epochs "$epochs" --max-samples "${MAX_SAMPLES:-4}" --log-dir "logs/snitch/main/$short" --display plain
done
