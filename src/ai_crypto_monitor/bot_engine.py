from __future__ import annotations

import os
import threading
import time
from datetime import datetime
from pathlib import Path

from .alerts import update_state
from .config import AppConfig
from .models import MarketSnapshot, SignalEvent
from .monitor import collect_snapshots
from .notifier import notify_messages
from .storage import LocalStorage
from .trend_learning import build_trend_learning_payload


_WORKER_LOCK = threading.Lock()
_WORKER_STARTED = False


def load_runtime_config(project_root: Path) -> AppConfig:
    config = AppConfig()
    storage = LocalStorage(data_dir=str(project_root / config.data_dir))
    saved = storage.load_web_settings()
    for key, value in saved.items():
        if hasattr(config, key):
            setattr(config, key, value)
    env_token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    env_chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if env_token:
        config.telegram_bot_token = env_token
    if env_chat_id:
        config.telegram_chat_id = env_chat_id
    config.symbols = [symbol.upper() for symbol in config.symbols]
    config.exchanges = [exchange.lower() for exchange in config.exchanges]
    config.preferred_exchange = config.preferred_exchange.lower().strip() or "okx"
    ordered_exchanges = [config.preferred_exchange]
    for exchange in config.exchanges:
        if exchange not in ordered_exchanges:
            ordered_exchanges.append(exchange)
    config.exchanges = ordered_exchanges
    return config


def ensure_worker_started(project_root: Path) -> None:
    global _WORKER_STARTED
    with _WORKER_LOCK:
        if _WORKER_STARTED:
            return
        thread = threading.Thread(
            target=_worker_loop,
            args=(project_root,),
            name="ai-crypto-monitor-worker",
            daemon=True,
        )
        thread.start()
        _WORKER_STARTED = True


def set_bot_enabled(project_root: Path, enabled: bool) -> dict:
    config = load_runtime_config(project_root)
    storage = LocalStorage(data_dir=str(project_root / config.data_dir))
    settings = storage.load_web_settings()
    settings["bot_enabled"] = enabled
    storage.save_web_settings(settings)
    runtime = storage.load_bot_runtime()
    runtime["enabled"] = enabled
    runtime["status"] = "running" if enabled else "stopped"
    runtime["message"] = "机器人已开启，等待下一轮检查。" if enabled else "机器人已关闭。"
    storage.save_bot_runtime(runtime)
    return runtime


def run_cycle_now(project_root: Path) -> dict:
    config = load_runtime_config(project_root)
    storage = LocalStorage(data_dir=str(project_root / config.data_dir))
    runtime = storage.load_bot_runtime()
    runtime["enabled"] = bool(config.bot_enabled)
    runtime["status"] = "running"
    runtime["message"] = "正在执行检查..."
    storage.save_bot_runtime(runtime)
    return run_monitor_cycle(project_root, config=config)


def run_monitor_cycle(project_root: Path, config: AppConfig | None = None) -> dict:
    config = config or load_runtime_config(project_root)
    storage = LocalStorage(data_dir=str(project_root / config.data_dir))
    runtime = storage.load_bot_runtime()
    state = storage.load_state()
    started_at = int(time.time())

    try:
        raw_snapshots = collect_snapshots(config)
        selected = select_preferred_snapshots(raw_snapshots, config.symbols, config.preferred_exchange)
        if not selected:
            raise RuntimeError("没有拿到可用行情，请检查网络或交易所接口。")

        metrics = build_market_metrics(selected, state.history)
        sync_context = build_market_sync_context(metrics, config)
        signals = build_signal_events(metrics, sync_context, config, started_at)

        storage.append_snapshots(list(selected.values()))
        state = update_state(list(selected.values()), state, max_points_per_symbol=120)
        storage.save_state(state)

        sent_messages = notify_messages(
            config,
            storage,
            [
                {
                    "text": format_signal_message(signal),
                    "key": f"signal:{signal.symbol}:{signal.bias}",
                    "cooldown_seconds": config.poll_interval_seconds * 3,
                }
                for signal in signals
            ],
        )
        for signal in signals:
            storage.append_signal(signal)

        now_text = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            trend_learning = build_trend_learning_payload(config)
        except Exception:
            trend_learning = runtime.get("trend_learning", {})

        runtime.update(
            {
                "enabled": bool(config.bot_enabled),
                "status": "running" if config.bot_enabled else "idle",
                "message": f"最近一次检查完成于 {now_text}。",
                "last_cycle_at": now_text,
                "last_success_at": now_text,
                "last_error": "",
                "last_signal_count": len(signals),
                "latest_market": summarize_market(metrics, sync_context, config.symbols),
                "latest_market_bias": sync_context["market_bias"],
                "last_sent_count": len(sent_messages),
                "trend_learning": trend_learning,
            }
        )
        if sent_messages:
            runtime["last_push_at"] = now_text
            runtime["last_push_symbols"] = [signal.symbol for signal in signals]
        storage.save_bot_runtime(runtime)
        return runtime
    except Exception as exc:
        runtime.update(
            {
                "enabled": bool(config.bot_enabled),
                "status": "error",
                "message": "最近一次检查失败。",
                "last_error": str(exc),
                "last_cycle_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
        )
        storage.save_bot_runtime(runtime)
        raise


def select_preferred_snapshots(
    snapshots: list[MarketSnapshot],
    symbols: list[str],
    preferred_exchange: str,
) -> dict[str, MarketSnapshot]:
    selected: dict[str, MarketSnapshot] = {}
    for symbol in symbols:
        match = next(
            (
                item
                for item in snapshots
                if item.symbol == symbol and item.exchange == preferred_exchange
            ),
            None,
        )
        if match is not None:
            selected[symbol] = match
            continue
        fallback = next((item for item in snapshots if item.symbol == symbol), None)
        if fallback is not None:
            selected[symbol] = fallback
    return selected


def build_market_metrics(
    selected: dict[str, MarketSnapshot],
    history_map: dict[str, list[dict]],
) -> dict[str, dict]:
    metrics: dict[str, dict] = {}
    for symbol, snapshot in selected.items():
        history = history_map.get(f"{snapshot.exchange}:{snapshot.symbol}", [])
        change_5m_pct = calculate_change_5m_pct(history, snapshot)
        volume_ratio = calculate_volume_ratio(history, snapshot)
        metrics[symbol] = {
            "symbol": snapshot.symbol,
            "exchange": snapshot.exchange,
            "pair": snapshot.pair,
            "price": snapshot.price,
            "change_5m_pct": change_5m_pct,
            "change_24h_pct": snapshot.change_24h_pct,
            "volume_ratio": volume_ratio,
            "timestamp": snapshot.timestamp,
        }
    return metrics


def calculate_change_5m_pct(history: list[dict], snapshot: MarketSnapshot) -> float | None:
    if not history:
        return None
    baseline = None
    for item in reversed(history):
        if snapshot.timestamp - int(item.get("timestamp", snapshot.timestamp)) >= 300:
            baseline = item
            break
    if baseline is None:
        baseline = history[0]
    old_price = float(baseline.get("price", 0))
    if old_price <= 0:
        return None
    return ((snapshot.price - old_price) / old_price) * 100.0


def calculate_volume_ratio(history: list[dict], snapshot: MarketSnapshot) -> float | None:
    if len(history) < 2:
        return None
    previous = history[-1]
    earlier = history[-2]
    current_delta = max(0.0, snapshot.volume_24h - float(previous.get("volume_24h", 0)))
    previous_delta = max(0.0, float(previous.get("volume_24h", 0)) - float(earlier.get("volume_24h", 0)))
    if previous_delta <= 0:
        return None
    return current_delta / previous_delta


def build_market_sync_context(metrics: dict[str, dict], config: AppConfig) -> dict:
    btc = metrics.get("BTC")
    if not btc or btc.get("change_5m_pct") is None:
        return {"btc_change_5m_pct": None, "market_sync": False, "followers": [], "market_bias": "观望"}
    btc_change = float(btc["change_5m_pct"])
    direction = 1 if btc_change > 0 else -1
    followers: list[str] = []
    for symbol, item in metrics.items():
        if symbol == "BTC":
            continue
        change = item.get("change_5m_pct")
        if change is None or abs(change) < config.btc_market_sync_alt_move_pct:
            continue
        if (change > 0 and direction > 0) or (change < 0 and direction < 0):
            followers.append(symbol)
    market_sync = abs(btc_change) >= config.price_move_alert_pct and len(followers) >= config.btc_market_sync_min_assets
    market_bias = "偏多" if btc_change > 0 else "偏空"
    if abs(btc_change) < 0.5:
        market_bias = "观望"
    return {
        "btc_change_5m_pct": btc_change,
        "market_sync": market_sync,
        "followers": followers,
        "market_bias": market_bias,
    }


def build_signal_events(
    metrics: dict[str, dict],
    sync_context: dict,
    config: AppConfig,
    timestamp: int,
) -> list[SignalEvent]:
    signals: list[SignalEvent] = []
    for symbol, item in metrics.items():
        change_5m = item.get("change_5m_pct")
        if change_5m is None:
            continue
        price_threshold = get_price_move_threshold(symbol, config)
        volume_threshold = get_volume_spike_threshold(symbol, config)
        price_trigger = abs(change_5m) >= price_threshold
        volume_trigger = bool(
            item.get("volume_ratio") is not None
            and float(item["volume_ratio"]) >= volume_threshold
        )
        sync_trigger = bool(
            symbol != "XAU"
            and symbol != "XAG"
            and
            sync_context.get("market_sync")
            and (
                (change_5m > 0 and float(sync_context.get("btc_change_5m_pct") or 0) > 0)
                or (change_5m < 0 and float(sync_context.get("btc_change_5m_pct") or 0) < 0)
            )
        )
        hard_trigger = abs(change_5m) >= get_hard_trigger_threshold(symbol, config)

        reasons: list[str] = []
        if price_trigger:
            reasons.append(f"5分钟涨跌幅达到 {change_5m:.2f}%")
        if volume_trigger:
            reasons.append(f"成交量增量放大到前一轮的 {float(item['volume_ratio']):.2f} 倍")
        if sync_trigger:
            followers = ", ".join(sync_context.get("followers", [])) or "主流币"
            reasons.append(f"BTC 带动全市场同步波动，联动币种包括 {followers}")

        if not (hard_trigger or len(reasons) >= 2):
            continue

        bias = "偏多" if change_5m > 0 else "偏空"
        levels = build_trade_levels(float(item["price"]), bias)
        risk_level = score_risk(change_5m, volume_trigger, sync_trigger)
        signals.append(
            SignalEvent(
                exchange=str(item["exchange"]).upper(),
                symbol=symbol,
                bias=bias,
                price=float(item["price"]),
                entry_zone=levels["entry_zone"],
                stop_loss=levels["stop_loss"],
                take_profit_1=levels["take_profit_1"],
                take_profit_2=levels["take_profit_2"],
                risk_level=risk_level,
                trigger_reason="；".join(reasons),
                timestamp=timestamp,
            )
        )
    return signals


def get_price_move_threshold(symbol: str, config: AppConfig) -> float:
    if symbol.upper() == "XAU":
        return float(config.xau_price_move_alert_pct)
    return float(config.price_move_alert_pct)


def get_volume_spike_threshold(symbol: str, config: AppConfig) -> float:
    if symbol.upper() == "XAU":
        return float(config.xau_volume_spike_multiplier)
    return float(config.volume_spike_multiplier)


def get_hard_trigger_threshold(symbol: str, config: AppConfig) -> float:
    base = get_price_move_threshold(symbol, config)
    if symbol.upper() == "XAU":
        return base + 0.35
    return base + 1.0


def build_trade_levels(price: float, bias: str) -> dict[str, float | str]:
    if bias == "偏多":
        return {
            "entry_zone": f"{price * 0.997:.4f} - {price * 1.003:.4f}",
            "stop_loss": round(price * 0.988, 6),
            "take_profit_1": round(price * 1.010, 6),
            "take_profit_2": round(price * 1.020, 6),
        }
    return {
        "entry_zone": f"{price * 0.997:.4f} - {price * 1.003:.4f}",
        "stop_loss": round(price * 1.012, 6),
        "take_profit_1": round(price * 0.990, 6),
        "take_profit_2": round(price * 0.980, 6),
    }


def score_risk(change_5m: float, volume_trigger: bool, sync_trigger: bool) -> str:
    score = 1
    if abs(change_5m) >= 3.0:
        score += 1
    if volume_trigger:
        score += 1
    if sync_trigger:
        score += 1
    if score >= 4:
        return "高"
    if score >= 3:
        return "中"
    return "低"


def summarize_market(metrics: dict[str, dict], sync_context: dict, symbols: list[str]) -> list[dict]:
    rows: list[dict] = []
    for symbol in symbols:
        item = metrics.get(symbol)
        if item is None:
            continue
        change_5m = item.get("change_5m_pct")
        if change_5m is None:
            market_state = "等待历史数据"
        elif sync_context.get("market_sync") and symbol in {"BTC", *sync_context.get("followers", [])}:
            market_state = "联动中"
        elif change_5m > 0:
            market_state = "偏强"
        elif change_5m < 0:
            market_state = "偏弱"
        else:
            market_state = "观望"
        rows.append(
            {
                "symbol": symbol,
                "exchange": str(item["exchange"]).upper(),
                "pair": item["pair"],
                "price": round(float(item["price"]), 6),
                "change_5m_pct": round(float(change_5m), 4) if change_5m is not None else None,
                "change_24h_pct": round(float(item["change_24h_pct"]), 4),
                "volume_ratio": round(float(item["volume_ratio"]), 4) if item.get("volume_ratio") is not None else None,
                "market_state": market_state,
            }
        )
    return rows


def format_signal_message(signal: SignalEvent) -> str:
    market_type = classify_signal_market(signal.symbol)
    headline = classify_signal_headline(signal.symbol)
    return (
        f"{headline}\n"
        f"类型: {market_type}\n"
        f"标的: {signal.symbol}\n"
        f"交易所: {signal.exchange}\n"
        f"当前价格: {signal.price:.6f}\n"
        f"方向: {signal.bias}\n"
        f"入场观察区: {signal.entry_zone}\n"
        f"止损位: {signal.stop_loss:.6f}\n"
        f"止盈1: {signal.take_profit_1:.6f}\n"
        f"止盈2: {signal.take_profit_2:.6f}\n"
        f"风险等级: {signal.risk_level}\n"
        f"触发原因: {signal.trigger_reason}"
    )


def classify_signal_market(symbol: str) -> str:
    if symbol.upper() == "XAU":
        return "黄金信号"
    return "加密信号"


def classify_signal_headline(symbol: str) -> str:
    if symbol.upper() == "XAU":
        return "【黄金提醒】"
    return "【加密提醒】"


def _worker_loop(project_root: Path) -> None:
    while True:
        try:
            config = load_runtime_config(project_root)
            storage = LocalStorage(data_dir=str(project_root / config.data_dir))
            runtime = storage.load_bot_runtime()
            if not config.bot_enabled:
                if runtime.get("enabled"):
                    runtime["enabled"] = False
                    runtime["status"] = "stopped"
                    runtime["message"] = "机器人已关闭。"
                    storage.save_bot_runtime(runtime)
                time.sleep(5)
                continue

            last_success = runtime.get("last_success_at")
            due = True
            if last_success:
                last_ts = int(datetime.strptime(last_success, "%Y-%m-%d %H:%M:%S").timestamp())
                due = int(time.time()) - last_ts >= config.poll_interval_seconds
            if due:
                run_monitor_cycle(project_root, config=config)
            time.sleep(5)
        except Exception as exc:
            try:
                config = load_runtime_config(project_root)
                storage = LocalStorage(data_dir=str(project_root / config.data_dir))
                runtime = storage.load_bot_runtime()
                runtime["enabled"] = bool(config.bot_enabled)
                runtime["status"] = "error"
                runtime["message"] = "后台检查失败，稍后会自动重试。"
                runtime["last_error"] = str(exc)
                runtime["last_cycle_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                storage.save_bot_runtime(runtime)
            except Exception:
                pass
            time.sleep(10)
