#!/bin/zsh

set -e

LAUNCH_AGENTS_DIR="$HOME/Library/LaunchAgents"
TARGET_PLIST="$LAUNCH_AGENTS_DIR/com.ai.crypto.monitor.plist"
APP_SUPPORT_DIR="$HOME/Library/Application Support/AI Crypto Monitor"

if launchctl print "gui/$(id -u)/com.ai.crypto.monitor" >/dev/null 2>&1; then
  launchctl bootout "gui/$(id -u)" "$TARGET_PLIST" >/dev/null 2>&1 || true
fi

rm -f "$TARGET_PLIST"
rm -rf "$APP_SUPPORT_DIR"

echo "已移除自动启动。"
