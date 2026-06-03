#!/bin/zsh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

RUNTIME_PYTHON="/Users/mac/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3"
PORT="${AI_CRYPTO_MONITOR_PORT:-5180}"
HOST="${AI_CRYPTO_MONITOR_HOST:-127.0.0.1}"

if [ -x "$RUNTIME_PYTHON" ]; then
  PYTHON_BIN="$RUNTIME_PYTHON"
else
  PYTHON_BIN="python3"
fi

mkdir -p "$SCRIPT_DIR/logs" "$SCRIPT_DIR/.vendor"

if [ ! -d "$SCRIPT_DIR/.vendor/flask" ]; then
  "$PYTHON_BIN" -m pip install --target "$SCRIPT_DIR/.vendor" -r "$SCRIPT_DIR/requirements.txt"
fi

export AI_CRYPTO_MONITOR_PORT="$PORT"
export AI_CRYPTO_MONITOR_HOST="$HOST"
export PYTHONPATH="$SCRIPT_DIR/.vendor:$SCRIPT_DIR"

exec "$PYTHON_BIN" -m src.ai_crypto_monitor.webapp
