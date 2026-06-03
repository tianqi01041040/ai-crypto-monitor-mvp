from __future__ import annotations

from datetime import datetime
from pathlib import Path

from .bot_engine import load_runtime_config
from .storage import LocalStorage
from .trend_learning import build_trend_learning_payload


def build_dashboard_payload(project_root: Path) -> dict:
    config = load_runtime_config(project_root)
    storage = LocalStorage(data_dir=str(project_root / config.data_dir))
    runtime = storage.load_bot_runtime()
    recent_signals = storage.load_signal_rows(limit=20)
    formatted_signals = [format_signal_row(row) for row in recent_signals]
    plain_status = build_plain_status_message(runtime)
    last_push_recorded = runtime.get("last_push_at")
    last_push_at = last_push_recorded or (formatted_signals[0]["time"] if formatted_signals else None)
    last_push_symbols_recorded = list(runtime.get("last_push_symbols", []))
    last_push_symbols = last_push_symbols_recorded or infer_last_push_symbols(
        formatted_signals,
        last_push_at,
    )
    try:
        trend_learning = runtime.get("trend_learning") or build_trend_learning_payload(config)
    except Exception:
        trend_learning = runtime.get("trend_learning", {})

    return {
        "status_message": runtime.get("message", "等待启动"),
        "updated_at": runtime.get("updated_at") or runtime.get("last_cycle_at") or "尚未执行",
        "bot": {
            "enabled": bool(config.bot_enabled),
            "status": runtime.get("status", "stopped"),
            "last_cycle_at": runtime.get("last_cycle_at"),
            "last_success_at": runtime.get("last_success_at"),
            "last_push_at": last_push_at,
            "last_test_push_at": runtime.get("last_test_push_at"),
            "last_push_is_estimated": bool(last_push_at and not last_push_recorded),
            "last_push_symbols": last_push_symbols,
            "last_push_symbols_is_estimated": bool(last_push_symbols and not last_push_symbols_recorded),
            "last_error": runtime.get("last_error", ""),
            "last_signal_count": int(runtime.get("last_signal_count", 0)),
            "last_sent_count": int(runtime.get("last_sent_count", 0)),
            "plain_status_message": plain_status["text"],
            "plain_status_level": plain_status["level"],
        },
        "settings": {
            "preferred_exchange": config.preferred_exchange.upper(),
            "symbols": list(config.symbols),
            "display_symbols": [format_symbol_label(symbol) for symbol in config.symbols],
            "interval_minutes": max(1, config.poll_interval_seconds // 60),
            "notifications_enabled": bool(config.notifications_enabled),
            "telegram_configured": bool(config.telegram_bot_token and config.telegram_chat_id),
            "price_move_alert_pct": float(config.price_move_alert_pct),
            "volume_spike_multiplier": float(config.volume_spike_multiplier),
            "xau_price_move_alert_pct": float(config.xau_price_move_alert_pct),
            "xau_volume_spike_multiplier": float(config.xau_volume_spike_multiplier),
            "stock_token_watchlist": ["AAPL", "TSLA", "NVDA"],
        },
        "market_overview": runtime.get("latest_market", []),
        "trend_learning": trend_learning,
        "recent_signals": formatted_signals,
        "stats_placeholder": {
            "win_rate": "预留",
            "total_signals": len(recent_signals),
            "last_generated_at": formatted_signals[0]["time"] if formatted_signals else "暂无",
        },
    }


def build_plain_status_message(runtime: dict) -> dict:
    status = str(runtime.get("status", "stopped"))
    last_sent_count = int(runtime.get("last_sent_count", 0) or 0)
    last_success_at = runtime.get("last_success_at")
    last_error = str(runtime.get("last_error", "") or "")

    if status == "error":
        return {
            "text": "刚才检查失败了，建议点击“一键重启服务”。",
            "level": "error",
        }
    if last_sent_count > 0 and last_success_at:
        return {
            "text": "刚刚达到发送标准，已推送 Telegram。",
            "level": "success",
        }
    if status == "running" and last_success_at:
        return {
            "text": "这一轮暂时没有达到发送标准，所以没有推送 Telegram。",
            "level": "info",
        }
    if runtime.get("enabled"):
        return {
            "text": "机器人已开启，正在等待下一轮自动检查。",
            "level": "info",
        }
    if last_error:
        return {
            "text": "服务目前没有正常工作，请先检查状态。",
            "level": "error",
        }
    return {
        "text": "机器人当前未启动。",
        "level": "info",
    }


def infer_last_push_symbols(formatted_signals: list[dict], last_push_at: str | None) -> list[str]:
    if not last_push_at:
        return []
    symbols: list[str] = []
    for row in formatted_signals:
        if row.get("time") != last_push_at:
            continue
        symbol = str(row.get("symbol", "")).strip().upper()
        if symbol and symbol not in symbols:
            symbols.append(symbol)
    return symbols


def build_settings_payload(project_root: Path) -> dict:
    config = load_runtime_config(project_root)
    return {
        "bot_enabled": bool(config.bot_enabled),
        "notifications_enabled": bool(config.notifications_enabled),
        "telegram_bot_token": config.telegram_bot_token,
        "telegram_chat_id": config.telegram_chat_id,
        "preferred_exchange": config.preferred_exchange,
        "poll_interval_seconds": config.poll_interval_seconds,
    }


def format_symbol_label(symbol: str) -> str:
    if symbol.upper() == "XAU":
        return "XAUUSDT"
    return symbol.upper()


def format_signal_row(row: dict) -> dict:
    timestamp = int(row.get("timestamp", 0) or 0)
    time_text = datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S") if timestamp else "未知"
    return {
        "time": time_text,
        "exchange": row.get("exchange", ""),
        "symbol": row.get("symbol", ""),
        "price": float(row.get("price", 0) or 0),
        "bias": row.get("bias", ""),
        "entry_zone": row.get("entry_zone", ""),
        "stop_loss": float(row.get("stop_loss", 0) or 0),
        "take_profit_1": float(row.get("take_profit_1", 0) or 0),
        "take_profit_2": float(row.get("take_profit_2", 0) or 0),
        "risk_level": row.get("risk_level", ""),
        "trigger_reason": row.get("trigger_reason", ""),
    }
