#!/usr/bin/env bash
# Keep an SSH tunnel open to the screening model (vLLM) running on a Slurm GPU node,
# and reconnect whenever it drops.
#
# The model's compute node changes every time the serve job is requeued. An earlier
# version of this script hardcoded the node, so when the job moved to a new node the
# tunnel kept forwarding to a dead one: every screening round failed with
# "connection reset", looked like "nothing found", and stayed that way for five days
# before anyone noticed. This version asks Slurm for the current node on every
# (re)connection instead, so a node change heals itself within one retry.
#
# Nothing here is specific to one machine or account; set the connection in the
# environment (no secrets live in this file):
#
#   SWARM_SSH    ssh connection arguments for the login node, e.g. "-p 2222 user@login.example"
#                (required). Pass only connection flags + destination, no remote command.
#   SERVE_JOB    Slurm job name of the vLLM server (default: swarm-watch-qwen)
#   LOCAL_PORT   local port to listen on (default: 8011)
#   REMOTE_PORT  port vLLM listens on, on the compute node (default: 8011)
#
# The screening process reads the model at http://127.0.0.1:$LOCAL_PORT (QWEN_BASE_URL).
set -u

: "${SWARM_SSH:?set SWARM_SSH to the login-node ssh args, e.g. \"-p 2222 user@host\"}"
SERVE_JOB="${SERVE_JOB:-swarm-watch-qwen}"
LOCAL_PORT="${LOCAL_PORT:-8011}"
REMOTE_PORT="${REMOTE_PORT:-8011}"

# shellcheck disable=SC2086  # SWARM_SSH is intentionally word-split into ssh args
while true; do
  node=$(ssh -o BatchMode=yes -o ConnectTimeout=15 $SWARM_SSH \
           "squeue -u \$USER -n $SERVE_JOB -t RUNNING -h -o %N" 2>/dev/null | head -1)
  if [ -z "$node" ]; then
    echo "$(date -u) no RUNNING '$SERVE_JOB' job; waiting for the GPU" >&2
    sleep 30
    continue
  fi
  echo "$(date -u) tunnel up: 127.0.0.1:$LOCAL_PORT -> $node:$REMOTE_PORT" >&2
  ssh -o BatchMode=yes -o ExitOnForwardFailure=yes \
      -o ServerAliveInterval=30 -o ServerAliveCountMax=3 \
      $SWARM_SSH -N -L "$LOCAL_PORT:$node:$REMOTE_PORT"
  echo "$(date -u) tunnel to $node dropped, rediscovering node" >&2
  sleep 10
done
