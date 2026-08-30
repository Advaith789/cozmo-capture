#!/usr/bin/env bash
# Install the learned multi-view model used by tiers A and B.
#
# Tiers A and B reconstruct rooms from photographs with MASt3R. It is a 2.7 GB
# checkpoint and a vendored repository, so it is not part of the default
# install: tier C, the walk-in test and the whole test suite run without it.
# Everything degrades to the per-photo metric depth path if this is skipped.
#
#   bash scripts/setup_learned.sh
#
# Needs about 4 GB of disk and roughly 8 GB of RAM to run.

set -euo pipefail
cd "$(dirname "$0")/.."

if [ ! -d .venv ]; then
  echo "error: no .venv here. python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
  exit 1
fi
# shellcheck disable=SC1091
source .venv/bin/activate

echo "==> inference dependencies"
pip install -q torch torchvision roma einops opencv-python-headless scipy tqdm safetensors huggingface_hub

echo "==> vendored model code"
mkdir -p vendor
if [ ! -d vendor/mast3r ]; then
  git clone --recursive --depth 1 https://github.com/naver/mast3r.git vendor/mast3r
else
  echo "    already present"
fi
git -C vendor/mast3r submodule update --init --recursive --depth 1

echo "==> checkpoint (2.7 GB, cached in ~/.cache/huggingface)"
python - <<'PY'
from huggingface_hub import snapshot_download
p = snapshot_download("naver/MASt3R_ViTLarge_BaseDecoder_512_catmlpdpt_metric")
print("    at", p)
PY

echo "==> check"
python - <<'PY'
import sys
sys.path[:0] = ["vendor/mast3r", "vendor/mast3r/dust3r", "vendor/mast3r/dust3r/croco"]
import torch
from mast3r.model import AsymmetricMASt3R  # noqa: F401
dev = ("mps" if torch.backends.mps.is_available()
       else "cuda" if torch.cuda.is_available() else "cpu")
print(f"    ok, will run on {dev}")
PY

echo
echo "done. Tiers A and B now reconstruct:"
echo "    python -m cozmo run '<photo folder>' --name roomA"
