#!/bin/bash
# Serve an open-weight model with vLLM on the cluster (OpenAI-compatible API, tool calling on).
# Usage: VLLM_VENV=/path/to/venv-with-vllm sbatch cluster/serve_vllm.sbatch   (run from a dir with logs/)
# The API key is read from ~/swarm/vllm_key. Reach it from a laptop with:
#   ssh -N -L 8011:<node>:8011 -p <port> <user>@<login-host>
#SBATCH --job-name=swarm-vllm
#SBATCH --wckey=commons
#SBATCH --gres=gpu:2
#SBATCH --cpus-per-task=16
#SBATCH --mem=200G
#SBATCH --time=06:00:00
#SBATCH --output=logs/vllm_%j.log
export PATH=$VLLM_VENV/bin:$PATH
export HF_HOME=$HOME/.cache/huggingface HF_HUB_OFFLINE=1
echo "HOST $(hostname) START $(date)"
exec $VLLM_VENV/bin/vllm serve Qwen/Qwen3.5-27B --served-model-name qwen3.5-27b \
  --tensor-parallel-size 2 --port 8011 --host 0.0.0.0 --api-key "$(cat $HOME/swarm/vllm_key)" \
  --enable-auto-tool-choice --tool-call-parser qwen3_coder --reasoning-parser qwen3 --max-model-len 65536
