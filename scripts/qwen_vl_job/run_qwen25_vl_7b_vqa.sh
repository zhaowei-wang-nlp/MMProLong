#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
cd "$repo_root"
exec bash train.sh tasks/omni/train_qwen_vl.py \
  configs/mmprolong/qwen25_vl_7b_128k.yaml "$@"
