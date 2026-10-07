#!/usr/bin/env bash
# Full run: 4 frontier models x 2 block conditions x 20 runs, basic runtime, provider-default settings.
cd "$(dirname "$0")/../.."
uv run python -m commons.batch experiments/blocked_access/scenarios/rule.yaml experiments/blocked_access/scenarios/glitch.yaml \
  --model anthropic/claude-opus-5-5 --model anthropic/claude-sonnet-5-5 --model openai/gpt-6.1-sol --model openai/gpt-5.5 \
  --epochs 20 --log-dir logs/blocked/main --workers 8
