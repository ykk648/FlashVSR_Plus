#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"
source scripts/configure_china_mirrors.sh >/dev/null
export UV_DEFAULT_INDEX="${UV_DEFAULT_INDEX:-${UV_INDEX_URL}}"
export UV_CACHE_DIR="${UV_CACHE_DIR:-$repo_root/.uv-cache}"
export UV_PYTHON_INSTALL_DIR="${UV_PYTHON_INSTALL_DIR:-$repo_root/.uv-python}"
export UV_HTTP_TIMEOUT="${UV_HTTP_TIMEOUT:-300}"

uv python install 3.11
uv sync --extra api
uv pip install --python .venv/bin/python 'setuptools>=68'
uv pip install --python .venv/bin/python --no-build-isolation --no-deps -e operators/flashvsr_attn
uv run python -m compileall -q inference model_io models flashvsr_plus flashvsr_plus_api scripts
uv run python - <<'PY'
import torch
print('torch', torch.__version__)
print('cuda_available', torch.cuda.is_available())
if torch.cuda.is_available():
    print('gpu', torch.cuda.get_device_name(0))
PY
printf 'uv environment ready\n'
