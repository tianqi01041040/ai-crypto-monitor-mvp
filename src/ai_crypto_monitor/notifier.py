from __future__ import annotations

import hashlib
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from .config import AppConfig
from .storage import LocalStorage


def notify_messages(
    config: AppConfig,
    storage: LocalStorage,
    messages: list[str | dict[str, Any]],
) -> list[str]:
    if not config.notifications_enabled:
        return []
    if not messages:
        return []

    state = storage.load_notification_state()
    sent_ids = set(state.get("sent_ids", []))
    cooldowns = dict(state.get("cooldowns", {}))
    sent_now: list[str] = []
    now = int(time.time())

    for raw_message in messages:
        payload = _normalize_message(raw_message)
        message = payload["text"]
        message_id = _message_id(message)
        cooldown_key = payload.get("key")
        cooldown_seconds = int(payload.get("cooldown_seconds", 0))
        if message_id in sent_ids:
            continue
        if cooldown_key and cooldown_seconds > 0:
            last_sent_at = int(cooldowns.get(cooldown_key, 0))
            if now - last_sent_at < cooldown_seconds:
                continue
        _send_to_telegram(config, message)
        _send_to_discord(config, message)
        sent_ids.add(message_id)
        if cooldown_key:
            cooldowns[cooldown_key] = now
        sent_now.append(message)

    state["sent_ids"] = list(sent_ids)[-500:]
    state["cooldowns"] = cooldowns
    storage.save_notification_state(state)
    return sent_now


def _send_to_telegram(config: AppConfig, message: str) -> None:
    if not config.telegram_bot_token or not config.telegram_chat_id:
        return
    _post_telegram_message(config, message)


def _send_to_discord(config: AppConfig, message: str) -> None:
    if not config.discord_webhook_url:
        return
    _post_discord_message(config, message)


def send_test_message(config: AppConfig, message: str) -> dict[str, Any]:
    results: dict[str, Any] = {}

    if config.telegram_bot_token or config.telegram_chat_id:
        telegram_ok, telegram_error = _post_telegram_message(config, message)
        results["telegram"] = {
            "ok": telegram_ok,
            "error": telegram_error,
        }

    if config.discord_webhook_url:
        discord_ok, discord_error = _post_discord_message(config, message)
        results["discord"] = {
            "ok": discord_ok,
            "error": discord_error,
        }

    return results


def send_message_now(config: AppConfig, message: str) -> dict[str, Any]:
    return send_test_message(config, message)


def _normalize_message(message: str | dict[str, Any]) -> dict[str, Any]:
    if isinstance(message, str):
        return {"text": message}
    return {
        "text": str(message.get("text", "")),
        "key": message.get("key"),
        "cooldown_seconds": int(message.get("cooldown_seconds", 0)),
    }


def _post_telegram_message(config: AppConfig, message: str) -> tuple[bool, str | None]:
    if not config.telegram_bot_token or not config.telegram_chat_id:
        return False, "请先填写 Telegram Bot Token 和 Chat ID。"
    url = f"https://api.telegram.org/bot{config.telegram_bot_token}/sendMessage"
    payload = urllib.parse.urlencode(
        {
            "chat_id": config.telegram_chat_id,
            "text": message,
        }
    ).encode("utf-8")
    request = urllib.request.Request(url, data=payload, method="POST")
    try:
        urllib.request.urlopen(request, timeout=10).read()
        return True, None
    except urllib.error.HTTPError as exc:
        return False, f"Telegram 返回错误 {exc.code}"
    except urllib.error.URLError:
        return False, "Telegram 网络连接失败"


def _post_discord_message(config: AppConfig, message: str) -> tuple[bool, str | None]:
    if not config.discord_webhook_url:
        return False, "请先填写 Discord Webhook URL。"
    payload = json.dumps({"content": message}).encode("utf-8")
    request = urllib.request.Request(
        config.discord_webhook_url,
        data=payload,
        headers={
            "Content-Type": "application/json",
            # Discord/Cloudflare may reject the default Python urllib user agent.
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AI-Crypto-Monitor/1.0",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        urllib.request.urlopen(request, timeout=10).read()
        return True, None
    except urllib.error.HTTPError as exc:
        return False, f"Discord 返回错误 {exc.code}"
    except urllib.error.URLError:
        return False, "Discord 网络连接失败"


def _message_id(message: str) -> str:
    return hashlib.sha1(message.encode("utf-8")).hexdigest()
