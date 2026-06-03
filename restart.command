#!/bin/zsh

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

"$SCRIPT_DIR/stop.command" || true
sleep 1
"$SCRIPT_DIR/start.command"
