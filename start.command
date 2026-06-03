#!/bin/zsh

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

RUNTIME_PYTHON="/Users/mac/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3"
PORT="5180"
HOST="127.0.0.1"
URL="http://${HOST}:${PORT}"
LOG_DIR="$SCRIPT_DIR/logs"
PID_FILE="$LOG_DIR/webapp.pid"
LOG_FILE="$LOG_DIR/webapp.log"

mkdir -p "$LOG_DIR" .vendor

echo "AI Crypto Monitor 正在准备启动..."
echo "项目目录: $SCRIPT_DIR"

if [ -x "$RUNTIME_PYTHON" ]; then
  PYTHON_BIN="$RUNTIME_PYTHON"
else
  PYTHON_BIN="python3"
fi

if [ -f "$PID_FILE" ]; then
  EXISTING_PID="$(cat "$PID_FILE" 2>/dev/null || true)"
  if [ -n "$EXISTING_PID" ] && kill -0 "$EXISTING_PID" 2>/dev/null; then
    echo "检测到服务已经在运行，直接打开网页..."
    open "$URL"
    exit 0
  fi
  echo "检测到旧的 PID 文件，但进程已经不存在，正在清理..."
  rm -f "$PID_FILE"
fi

if [ ! -d ".vendor/flask" ]; then
  echo "首次运行，正在安装网页依赖..."
  "$PYTHON_BIN" -m pip install --target .vendor -r requirements.txt
else
  echo "依赖已存在，跳过安装。"
fi

echo "正在启动网页服务..."
export AI_CRYPTO_MONITOR_PORT="$PORT"
export AI_CRYPTO_MONITOR_HOST="$HOST"

nohup "$SCRIPT_DIR/run_webapp.sh" >"$LOG_FILE" 2>&1 </dev/null &
SERVER_PID=$!
disown "$SERVER_PID" 2>/dev/null || true
echo "$SERVER_PID" > "$PID_FILE"

echo "正在等待服务就绪..."
for _ in {1..60}; do
  if curl -s "$URL/api/dashboard" >/dev/null 2>&1; then
    echo "启动成功，正在打开网页..."
    open "$URL"
    exit 0
  fi
  sleep 1
done

echo "启动失败，浏览器没有检测到服务。"
echo "你可以把下面这份日志发给我："
echo "$LOG_FILE"
tail -n 40 "$LOG_FILE" || true
exit 1
