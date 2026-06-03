#!/bin/zsh

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

PID_FILE="$SCRIPT_DIR/logs/webapp.pid"

if [ ! -f "$PID_FILE" ]; then
  echo "没有找到运行中的服务。"
  exit 0
fi

PID="$(cat "$PID_FILE" 2>/dev/null || true)"

if [ -z "$PID" ]; then
  echo "PID 文件为空，正在清理。"
  rm -f "$PID_FILE"
  exit 0
fi

if kill -0 "$PID" 2>/dev/null; then
  echo "正在停止服务 PID: $PID"
  kill "$PID"
  sleep 2
  if kill -0 "$PID" 2>/dev/null; then
    echo "服务还在运行，继续强制停止..."
    kill -9 "$PID" 2>/dev/null || true
  fi
else
  echo "服务进程已经不存在，正在清理 PID 文件。"
fi

rm -f "$PID_FILE"
echo "已停止。"
