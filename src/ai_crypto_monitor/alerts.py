from __future__ import annotations

from .config import AppConfig
from .models import AlertEvent, MarketSnapshot, RuntimeState


def evaluate_alerts(
    snapshots: list[MarketSnapshot],
    state: RuntimeState,
    config: AppConfig,
) -> list[AlertEvent]:
    alerts: list[AlertEvent] = []
    grouped_by_exchange: dict[str, list[MarketSnapshot]] = {}
    for snapshot in snapshots:
        history = _history_for(state, snapshot.exchange, snapshot.symbol)
        alerts.extend(_price_alerts(snapshot, history, config))
        alerts.extend(_volume_alerts(snapshot, history, config))
        grouped_by_exchange.setdefault(snapshot.exchange, []).append(snapshot)

    for exchange, exchange_snapshots in grouped_by_exchange.items():
        alerts.extend(_market_sync_alerts(exchange, exchange_snapshots, state, config))
    return alerts


def update_state(
    snapshots: list[MarketSnapshot],
    state: RuntimeState,
    max_points_per_symbol: int = 24,
) -> RuntimeState:
    for snapshot in snapshots:
        history = _history_for(state, snapshot.exchange, snapshot.symbol)
        history.append(snapshot.to_dict())
        state.history[_state_key(snapshot.exchange, snapshot.symbol)] = history[
            -max_points_per_symbol:
        ]
    return state


def _price_alerts(
    snapshot: MarketSnapshot,
    history: list[dict],
    config: AppConfig,
) -> list[AlertEvent]:
    if not history:
        return []
    baseline = history[-1]
    old_price = float(baseline["price"])
    if old_price == 0:
        return []
    change_pct = ((snapshot.price - old_price) / old_price) * 100.0
    if abs(change_pct) < config.price_move_alert_pct:
        return []
    direction = "上涨" if change_pct > 0 else "下跌"
    window_label = _window_label(config.poll_interval_seconds)
    return [
        AlertEvent(
            level="warning",
            category="price_move",
            exchange=snapshot.exchange,
            symbol=snapshot.symbol,
            message=(
                f"{snapshot.exchange.upper()} {snapshot.symbol} 近 {window_label}{direction}"
                f" {abs(change_pct):.2f}% ，超过阈值 {config.price_move_alert_pct:.2f}%"
            ),
        )
    ]


def _volume_alerts(
    snapshot: MarketSnapshot,
    history: list[dict],
    config: AppConfig,
) -> list[AlertEvent]:
    if len(history) < 2:
        return []
    previous = history[-1]
    earlier = history[-2]
    current_delta = max(0.0, snapshot.volume_24h - float(previous["volume_24h"]))
    previous_delta = max(
        0.0,
        float(previous["volume_24h"]) - float(earlier["volume_24h"]),
    )
    if previous_delta <= 0:
        return []
    if current_delta < previous_delta * config.volume_spike_multiplier:
        return []
    window_label = _window_label(config.poll_interval_seconds)
    return [
        AlertEvent(
            level="warning",
            category="volume_spike",
            exchange=snapshot.exchange,
            symbol=snapshot.symbol,
            message=(
                f"{snapshot.exchange.upper()} {snapshot.symbol} 近 {window_label}成交量增量"
                f" 放大到上一轮的 {current_delta / previous_delta:.2f} 倍"
            ),
        )
    ]


def _market_sync_alerts(
    exchange: str,
    snapshots: list[MarketSnapshot],
    state: RuntimeState,
    config: AppConfig,
) -> list[AlertEvent]:
    btc_snapshot = next((item for item in snapshots if item.symbol == "BTC"), None)
    if btc_snapshot is None:
        return []
    btc_history = _history_for(state, exchange, "BTC")
    if not btc_history:
        return []
    btc_old_price = float(btc_history[-1]["price"])
    if btc_old_price == 0:
        return []
    btc_change_pct = ((btc_snapshot.price - btc_old_price) / btc_old_price) * 100.0
    if abs(btc_change_pct) < config.price_move_alert_pct:
        return []
    window_label = _window_label(config.poll_interval_seconds)

    direction = 1 if btc_change_pct > 0 else -1
    followed_assets: list[str] = []
    for snapshot in snapshots:
        if snapshot.symbol == "BTC":
            continue
        history = _history_for(state, exchange, snapshot.symbol)
        if not history:
            continue
        old_price = float(history[-1]["price"])
        if old_price == 0:
            continue
        change_pct = ((snapshot.price - old_price) / old_price) * 100.0
        if abs(change_pct) < config.btc_market_sync_alt_move_pct:
            continue
        if (change_pct > 0 and direction > 0) or (change_pct < 0 and direction < 0):
            followed_assets.append(snapshot.symbol)

    if len(followed_assets) < config.btc_market_sync_min_assets:
        return []

    return [
        AlertEvent(
            level="critical",
            category="btc_market_sync",
            exchange=exchange,
            symbol="BTC",
            message=(
                f"{exchange.upper()} BTC 近 {window_label}波动 {btc_change_pct:.2f}% ，并带动"
                f" {', '.join(followed_assets)} 同向波动"
            ),
        )
    ]


def _history_for(
    state: RuntimeState,
    exchange: str,
    symbol: str,
) -> list[dict]:
    return list(state.history.get(_state_key(exchange, symbol), []))


def _state_key(exchange: str, symbol: str) -> str:
    return f"{exchange}:{symbol}"


def _window_label(poll_interval_seconds: int) -> str:
    if poll_interval_seconds % 60 == 0:
        return f"{poll_interval_seconds // 60} 分钟"
    return f"{poll_interval_seconds} 秒"
