#!/usr/bin/env bash
# Modified for MMProLong: use standard torchrun environment variables.
set -euo pipefail

if [[ $# -lt 2 ]]; then
  echo "Usage: bash train.sh <task_script> <config.yaml> [overrides...]" >&2
  echo "Set NPROC_PER_NODE; for multiple nodes also set NNODES, NODE_RANK, MASTER_ADDR and MASTER_PORT." >&2
  exit 2
fi

export TOKENIZERS_PARALLELISM=false
export TORCH_NCCL_AVOID_RECORD_STREAMS=1
export NCCL_DEBUG=${NCCL_DEBUG:-WARN}

NNODES=${NNODES:-1}
NODE_RANK=${NODE_RANK:-0}
MASTER_PORT=${MASTER_PORT:-29500}
if [[ -z "${NPROC_PER_NODE:-}" ]]; then
  if [[ -n "${CUDA_VISIBLE_DEVICES:-}" ]]; then
    IFS=',' read -r -a devices <<< "$CUDA_VISIBLE_DEVICES"
    NPROC_PER_NODE=${#devices[@]}
  elif command -v nvidia-smi >/dev/null 2>&1; then
    NPROC_PER_NODE=$(nvidia-smi --list-gpus | wc -l | tr -d ' ')
  elif [[ -n "${ASCEND_RT_VISIBLE_DEVICES:-}" ]]; then
    IFS=',' read -r -a devices <<< "$ASCEND_RT_VISIBLE_DEVICES"
    NPROC_PER_NODE=${#devices[@]}
  else
    echo "Cannot detect accelerators. Set NPROC_PER_NODE explicitly." >&2
    exit 2
  fi
fi
if ! [[ "$NPROC_PER_NODE" =~ ^[1-9][0-9]*$ ]]; then
  echo "NPROC_PER_NODE must be a positive integer." >&2
  exit 2
fi

if [[ "$NNODES" == 1 ]]; then
  rendezvous=(--standalone)
else
  : "${MASTER_ADDR:?Set MASTER_ADDR to the rank-0 node address for multi-node training}"
  rendezvous=(--master-addr "$MASTER_ADDR" --master-port "$MASTER_PORT")
fi

repo_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
export PYTHONPATH="$repo_root${PYTHONPATH:+:$PYTHONPATH}"

torchrun --nnodes "$NNODES" --nproc-per-node "$NPROC_PER_NODE" \
  --node-rank "$NODE_RANK" "${rendezvous[@]}" "$@" \
  2>&1 | tee "${LOG_FILE:-log.txt}"
