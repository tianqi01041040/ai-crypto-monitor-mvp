#!/bin/zsh

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

PID_FILE="$SCRIPT_DIR/logs/webapp.pid"
URL="http://127.0.0.1:5180/api/dashboard"

if [ -f "$PID_FILE" ]; then
  PID="$(cat "$PID_FILE" 2>/dev/null || true)"
  if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
    echo "本地服务进程正在运行: PID $PID"
  else
    echo "PID 文件存在，但进程不在运行。"
  fi
else
  echo "没有 PID 文件。"
fi

if curl -s "$URL" >/dev/null 2>&1; then
  echo "网页接口可访问: $URL"
else
  echo "网页接口当前不可访问: $URL"
fi
