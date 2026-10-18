#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 3 ]]; then
  echo "Usage: bash scripts/qwen_vl_job/merge_script.sh <checkpoint_dir> <model_assets_dir> <output_dir>" >&2
  exit 2
fi
repo_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
python "$repo_root/scripts/merge_dcp_to_hf.py" \
  --load-dir "$1" --model-assets-dir "$2" --save-dir "$3"
