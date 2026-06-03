from __future__ import annotations

import os
import subprocess
from datetime import datetime
from pathlib import Path

from flask import Flask, jsonify, render_template, request

from .bot_engine import ensure_worker_started, load_runtime_config, run_cycle_now, set_bot_enabled
from .dashboard_service import build_dashboard_payload, build_settings_payload
from .notifier import send_test_message
from .storage import LocalStorage


PROJECT_ROOT = Path.cwd()
TEMPLATE_DIR = PROJECT_ROOT / "templates"
STATIC_DIR = PROJECT_ROOT / "static"

app = Flask(__name__, template_folder=str(TEMPLATE_DIR), static_folder=str(STATIC_DIR))
ensure_worker_started(PROJECT_ROOT)


def _schedule_service_restart() -> None:
    uid = os.getuid()
    launch_agent = Path.home() / "Library" / "LaunchAgents" / "com.ai.crypto.monitor.plist"
    if launch_agent.exists():
        command = f"sleep 1; launchctl kickstart -k gui/{uid}/com.ai.crypto.monitor >/dev/null 2>&1"
    else:
        command = f"sleep 1; '{PROJECT_ROOT / 'restart.command'}' >/dev/null 2>&1"
    subprocess.Popen(
        ["/bin/zsh", "-lc", command],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
    )


@app.route("/")
def index():
    return render_template(
        "index.html",
        payload=build_dashboard_payload(PROJECT_ROOT),
        settings=build_settings_payload(PROJECT_ROOT),
    )


@app.route("/api/dashboard")
def api_dashboard():
    return jsonify(build_dashboard_payload(PROJECT_ROOT))


@app.route("/healthz")
def healthz():
    return jsonify({"ok": True, "service": "ai-crypto-monitor", "status": "healthy"})


@app.route("/api/settings", methods=["GET", "POST"])
def api_settings():
    config = load_runtime_config(PROJECT_ROOT)
    storage = LocalStorage(data_dir=str(PROJECT_ROOT / config.data_dir))
    if request.method == "GET":
        return jsonify({"ok": True, "settings": build_settings_payload(PROJECT_ROOT)})

    raw = request.get_json(silent=True) or {}
    settings = storage.load_web_settings()
    settings["notifications_enabled"] = bool(raw.get("notifications_enabled", False))
    settings["telegram_bot_token"] = str(raw.get("telegram_bot_token", "")).strip()
    settings["telegram_chat_id"] = str(raw.get("telegram_chat_id", "")).strip()
    settings["preferred_exchange"] = str(raw.get("preferred_exchange", "okx")).strip().lower() or "okx"
    try:
        interval = int(raw.get("poll_interval_seconds", 300))
    except (TypeError, ValueError):
        interval = 300
    settings["poll_interval_seconds"] = max(300, interval)
    storage.save_web_settings(settings)
    return jsonify(
        {
            "ok": True,
            "message": "设置已保存。",
            "settings": build_settings_payload(PROJECT_ROOT),
        }
    )


@app.route("/api/bot/toggle", methods=["POST"])
def api_bot_toggle():
    raw = request.get_json(silent=True) or {}
    enabled = bool(raw.get("enabled", False))
    runtime = set_bot_enabled(PROJECT_ROOT, enabled)
    return jsonify(
        {
            "ok": True,
            "message": "机器人已开启。" if enabled else "机器人已关闭。",
            "runtime": runtime,
            "dashboard": build_dashboard_payload(PROJECT_ROOT),
        }
    )


@app.route("/api/bot/run-once", methods=["POST"])
def api_bot_run_once():
    try:
        run_cycle_now(PROJECT_ROOT)
    except Exception as exc:
        return jsonify({"ok": False, "message": str(exc)}), 500
    return jsonify(
        {
            "ok": True,
            "message": "已手动执行一轮检查。",
            "dashboard": build_dashboard_payload(PROJECT_ROOT),
        }
    )


@app.route("/api/service/restart", methods=["POST"])
def api_service_restart():
    _schedule_service_restart()
    return jsonify(
        {
            "ok": True,
            "message": "服务正在重启，页面会自动重新连接。",
        }
    )


@app.route("/api/notifications/test", methods=["POST"])
def api_notifications_test():
    raw = request.get_json(silent=True) or {}
    runtime_config = load_runtime_config(PROJECT_ROOT)
    storage = LocalStorage(data_dir=str(PROJECT_ROOT / runtime_config.data_dir))
    settings = storage.load_web_settings()
    token = str(raw.get("telegram_bot_token", settings.get("telegram_bot_token", ""))).strip()
    chat_id = str(raw.get("telegram_chat_id", settings.get("telegram_chat_id", ""))).strip()
    enabled = bool(raw.get("notifications_enabled", settings.get("notifications_enabled", False)))
    from .config import AppConfig

    config = AppConfig(
        notifications_enabled=enabled,
        telegram_bot_token=token,
        telegram_chat_id=chat_id,
        preferred_exchange=runtime_config.preferred_exchange,
        poll_interval_seconds=int(runtime_config.poll_interval_seconds),
    )
    results = send_test_message(
        config,
        "AI Crypto Monitor 测试提醒\n如果你收到了这条消息，说明 Telegram 已经接通。",
    )
    if not results:
        return jsonify({"ok": False, "message": "请先填写 Token 和 Chat ID。"}), 400
    telegram = results.get("telegram", {})
    if telegram.get("ok"):
        runtime = storage.load_bot_runtime()
        runtime["last_test_push_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        storage.save_bot_runtime(runtime)
        return jsonify({"ok": True, "message": "Telegram 测试消息发送成功。", "results": results})
    return jsonify(
        {
            "ok": False,
            "message": telegram.get("error") or "Telegram 测试发送失败。",
            "results": results,
        }
    ), 400


def main() -> None:
    host = os.environ.get("AI_CRYPTO_MONITOR_HOST", "127.0.0.1")
    port = int(os.environ.get("AI_CRYPTO_MONITOR_PORT") or os.environ.get("PORT", "5180"))
    app.run(host=host, port=port, debug=False)


if __name__ == "__main__":
    main()
