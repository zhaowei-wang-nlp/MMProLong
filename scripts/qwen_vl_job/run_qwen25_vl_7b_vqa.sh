#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
cd "$repo_root"
# Original NTK-aware 128K model config: mRoPE base 1,000,000 -> 4,000,000.
# User overrides follow this default, including the 3B config when using a 3B backbone.
exec bash train.sh tasks/omni/train_qwen_vl.py \
  configs/mmprolong/qwen25_vl_7b_128k.yaml \
  --model.config_path configs/model_configs/qwen/mmprolong_qwen25_vl_7b_128k.json \
  "$@"
