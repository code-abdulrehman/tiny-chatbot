#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
VENV_DIR="$PWD/.venv"
if [ ! -x "$VENV_DIR/bin/python" ] && [ -x ../.venv/bin/python ]; then
    VENV_DIR="$(cd .. && pwd)/.venv"
fi

if [ ! -x "$VENV_DIR/bin/python" ]; then
    python3.12 -m venv "$VENV_DIR"
fi
"$VENV_DIR/bin/python" -m ensurepip --upgrade --default-pip
export PIP_CACHE_DIR="$PWD/.uv-cache/pip"
# Use the CPU wheel to avoid downloading NVIDIA GPU runtime packages.
"$VENV_DIR/bin/python" -m pip install 'torch>=2.6' --index-url https://download.pytorch.org/whl/cpu
"$VENV_DIR/bin/python" -m pip install -e '.[chat]'
"$VENV_DIR/bin/python" chat.py --download-only
echo "Setup complete. Start chat: $VENV_DIR/bin/python chat.py"
