#!/usr/bin/env bash
# Run one Snitch Rate condition for one model (30 runs solo, 15 runs with 4 agents).
#   experiments/snitch_rate/run_one.sh <short name> <model> <condition>
set -euo pipefail
short=$1 model=$2 cond=$3
epochs=$([[ $cond == n1_* ]] && echo 30 || echo 15)
uv run inspect eval commons/tasks.py -T scenario=experiments/snitch_rate/scenarios/${short}__${cond}.yaml --model "$model" \
  --epochs "$epochs" --max-samples "${MAX_SAMPLES:-8}" --log-dir "logs/snitch/main/$short" --display plain
