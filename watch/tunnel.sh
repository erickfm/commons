#!/usr/bin/env bash
# Keep an SSH tunnel open to the screening model (vLLM) and reconnect whenever it drops.
#
# Two ways the model gets served, so two ways to find it:
#
#  - Slurm cluster (default): the model runs as a Slurm job whose compute node changes
#    every time the job is requeued. An earlier version hardcoded the node, so when the
#    job moved the tunnel kept forwarding to a dead one: every screening round failed
#    with "connection reset", looked like "nothing found", and stayed that way for five
#    days before anyone noticed. So the node is rediscovered from squeue on every
#    (re)connection, and a node change heals itself within one retry.
#
#  - A single fixed box (e.g. a rented GPU): set SWARM_NODE to skip Slurm discovery and
#    forward straight to it. vLLM typically binds 127.0.0.1 on that box, so SWARM_NODE
#    is usually 127.0.0.1 (resolved on the box side of the ssh connection).
#
# Nothing here is specific to one machine or account; set the connection in the
# environment (no secrets live in this file):
#
#   SWARM_SSH    ssh connection arguments for the host, e.g. "-p 2222 user@host"
#                (required). Pass only connection flags + destination, no remote command.
#   SWARM_NODE   forward directly to this host (as seen from the ssh target) and skip
#                Slurm discovery; e.g. 127.0.0.1 for a single box. Unset = use Slurm.
#   SERVE_JOB    Slurm job name of the vLLM server (default: swarm-watch-qwen)
#   LOCAL_PORT   local port to listen on (default: 8011)
#   REMOTE_PORT  port vLLM listens on (default: 8011)
#
# The screening process reads the model at http://127.0.0.1:$LOCAL_PORT (QWEN_BASE_URL).
set -u

: "${SWARM_SSH:?set SWARM_SSH to the ssh args, e.g. \"-p 2222 user@host\"}"
SWARM_NODE="${SWARM_NODE:-}"
SERVE_JOB="${SERVE_JOB:-swarm-watch-qwen}"
LOCAL_PORT="${LOCAL_PORT:-8011}"
REMOTE_PORT="${REMOTE_PORT:-8011}"

# shellcheck disable=SC2086  # SWARM_SSH is intentionally word-split into ssh args
while true; do
  if [ -n "$SWARM_NODE" ]; then
    node="$SWARM_NODE"            # fixed box: forward straight to it, no Slurm lookup
  else
    node=$(ssh -o BatchMode=yes -o ConnectTimeout=15 $SWARM_SSH \
             "squeue -u \$USER -n $SERVE_JOB -t RUNNING -h -o %N" 2>/dev/null | head -1)
  fi
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
