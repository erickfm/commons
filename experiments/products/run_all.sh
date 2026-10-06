#!/usr/bin/env bash
# Full run: Snitch Rate (30 runs per condition) and peer pressure (15 per condition) on four product/model pairs.
set -u
S=experiments/products/scenarios
B="uv run python -m commons.batch --max-samples 5 --log-dir logs/products/main --workers 4"
$B $S/claude_code__snitch_*.yaml --model anthropic/claude-sonnet-5-5 --model anthropic/claude-opus-5-5 --epochs 30 &
$B $S/codex__snitch_*.yaml --model openai/gpt-6.1-sol --model openai/gpt-5.5 --epochs 30 &
$B $S/claude_code__peer_*.yaml --model anthropic/claude-sonnet-5-5 --model anthropic/claude-opus-5-5 --epochs 15 &
$B $S/codex__peer_*.yaml --model openai/gpt-6.1-sol --model openai/gpt-5.5 --epochs 15 &
wait
echo all done
