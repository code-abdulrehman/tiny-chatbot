#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if ! command -v node >/dev/null || ! command -v npm >/dev/null; then
  echo 'Node.js and npm are required. Install Node.js 20.19+ first.' >&2
  exit 1
fi
if [ ! -x node_modules/.bin/vite ] && [ ! -x ../node_modules/.bin/vite ]; then
  (cd .. && npm install)
fi
npm run dev -- --port "${PORT:-5173}"
