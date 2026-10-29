#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
# Preserve the existing root environment; fresh checkouts create one here.
VENV_DIR="$PWD/.venv"
if [ ! -x "$VENV_DIR/bin/python" ] && [ -x ../.venv/bin/python ]; then
    VENV_DIR="$(cd .. && pwd)/.venv"
fi
export PIP_CACHE_DIR="$PWD/.uv-cache/pip"
export OMP_NUM_THREADS="${CHAT_THREADS:-2}"
export MKL_NUM_THREADS="${CHAT_THREADS:-2}"
export TOKENIZERS_PARALLELISM=false
if [ ! -x "$VENV_DIR/bin/python" ]; then
    python3.12 -m venv "$VENV_DIR"
    "$VENV_DIR/bin/python" -m ensurepip --upgrade
fi
if ! "$VENV_DIR/bin/python" -c 'import torch' >/dev/null 2>&1; then
    "$VENV_DIR/bin/python" -m pip install 'torch>=2.6' --index-url https://download.pytorch.org/whl/cpu
fi
if ! "$VENV_DIR/bin/python" -c 'import streamlit, transformers; from packaging.version import Version; assert Version(transformers.__version__) >= Version("4.56"); assert Version(streamlit.__version__) >= Version("1.66")' >/dev/null 2>&1; then
    "$VENV_DIR/bin/python" -m pip install --retries 1 --timeout 15 'streamlit>=1.66,<2' 'transformers>=4.56,<5'
fi
CHAT_PORT="$("$VENV_DIR/bin/python" server_port.py "${PORT:-8501}")"
echo "Starting Tiny Chat at http://localhost:$CHAT_PORT"
exec "$VENV_DIR/bin/python" -m streamlit run app.py \
    --server.address 127.0.0.1 --server.port "$CHAT_PORT" \
    --browser.gatherUsageStats false "$@"
