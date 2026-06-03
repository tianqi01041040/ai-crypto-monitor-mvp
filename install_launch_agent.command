#!/bin/zsh

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

LAUNCH_AGENTS_DIR="$HOME/Library/LaunchAgents"
TARGET_PLIST="$LAUNCH_AGENTS_DIR/com.ai.crypto.monitor.plist"
APP_SUPPORT_DIR="$HOME/Library/Application Support/AI Crypto Monitor"
RUNTIME_DIR="$APP_SUPPORT_DIR/runtime"
SOURCE_PLIST="$APP_SUPPORT_DIR/com.ai.crypto.monitor.plist"

mkdir -p "$LAUNCH_AGENTS_DIR" "$SCRIPT_DIR/logs" "$APP_SUPPORT_DIR"

echo "正在同步运行文件到 Application Support..."
rm -rf "$RUNTIME_DIR"
mkdir -p "$RUNTIME_DIR"
cp -R "$SCRIPT_DIR/.vendor" "$RUNTIME_DIR/.vendor"
cp -R "$SCRIPT_DIR/src" "$RUNTIME_DIR/src"
cp -R "$SCRIPT_DIR/static" "$RUNTIME_DIR/static"
cp -R "$SCRIPT_DIR/templates" "$RUNTIME_DIR/templates"
cp -R "$SCRIPT_DIR/data" "$RUNTIME_DIR/data"
cp -R "$SCRIPT_DIR/logs" "$RUNTIME_DIR/logs"
cp "$SCRIPT_DIR/requirements.txt" "$RUNTIME_DIR/requirements.txt"
cp "$SCRIPT_DIR/run_webapp.sh" "$RUNTIME_DIR/run_webapp.sh"
chmod +x "$RUNTIME_DIR/run_webapp.sh"

cat > "$SOURCE_PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.ai.crypto.monitor</string>

  <key>ProgramArguments</key>
  <array>
    <string>/bin/zsh</string>
    <string>$RUNTIME_DIR/run_webapp.sh</string>
  </array>

  <key>WorkingDirectory</key>
  <string>$RUNTIME_DIR</string>

  <key>EnvironmentVariables</key>
  <dict>
    <key>AI_CRYPTO_MONITOR_HOST</key>
    <string>127.0.0.1</string>
    <key>AI_CRYPTO_MONITOR_PORT</key>
    <string>5180</string>
    <key>PYTHONPATH</key>
    <string>$RUNTIME_DIR/.vendor:$RUNTIME_DIR</string>
  </dict>

  <key>RunAtLoad</key>
  <true/>

  <key>KeepAlive</key>
  <true/>

  <key>StandardOutPath</key>
  <string>$RUNTIME_DIR/logs/launchd.out.log</string>

  <key>StandardErrorPath</key>
  <string>$RUNTIME_DIR/logs/launchd.err.log</string>
</dict>
</plist>
EOF

if launchctl print "gui/$(id -u)/com.ai.crypto.monitor" >/dev/null 2>&1; then
  echo "检测到旧的 launch agent，先卸载..."
  launchctl bootout "gui/$(id -u)" "$TARGET_PLIST" >/dev/null 2>&1 || true
fi

cp "$SOURCE_PLIST" "$TARGET_PLIST"
launchctl bootstrap "gui/$(id -u)" "$TARGET_PLIST"
launchctl enable "gui/$(id -u)/com.ai.crypto.monitor"
launchctl kickstart -k "gui/$(id -u)/com.ai.crypto.monitor"

echo "安装完成。"
echo "以后你重启 Mac 后，它会自动启动。"
echo "网页地址: http://127.0.0.1:5180"
