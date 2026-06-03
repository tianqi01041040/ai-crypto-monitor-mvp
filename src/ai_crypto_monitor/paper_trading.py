from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from .models import MarketSnapshot
from .storage import LocalStorage


INITIAL_BALANCE_USDT = 1000.0
TRADE_SIZE_USDT = 20.0
MAX_DAILY_TRADES = 10
TAKE_PROFIT_PCT = 1.0
STOP_LOSS_PCT = -0.5
OPEN_SIGNAL_PCT = 2.0
RISK_OFF_BTC_DROP_PCT = -2.0
MAX_LOSS_STREAK = 3
MAX_HOLD_MINUTES = 30
REJECT_COOLDOWN_SECONDS = 5 * 60
SUPPORTED_SYMBOLS = ["BTC", "ETH", "SOL", "SUI", "DOGE"]


def run_auto_paper_trading(
    storage: LocalStorage,
    snapshots: list[MarketSnapshot],
    market_metrics: dict[str, dict[str, Any]],
) -> dict:
    """根据最新行情执行最小可运行版自动纸上模拟。"""
    account = storage.load_paper_account()
    now = datetime.now()
    # 每天第一次运行时，把“今日交易次数 / 今日盈亏 / 连亏次数”重新归零。
    _roll_daily_state(account, now)

    actions: list[dict[str, Any]] = []
    risk_state = build_risk_state(account, market_metrics)

    # 先处理平仓，保证 Risk-Off 时优先撤离，而不是继续开新仓。
    actions.extend(_maybe_close_positions(storage, account, market_metrics, risk_state, now))
    risk_state = build_risk_state(account, market_metrics)

    # 只有在风险允许时，才会继续检查新的自动开仓机会。
    if risk_state["allow_auto_open"]:
        actions.extend(_maybe_open_positions(storage, account, market_metrics, risk_state, now))

    _save_daily_stats_csv(storage, account)
    storage.save_paper_account(account)
    return {
        "actions": actions,
        "risk_state": risk_state,
    }


def handle_paper_action(
    action: str,
    storage: LocalStorage,
    symbol: str | None,
    quantity: float | None,
    manual_price: float | None,
    reason: str | None,
    snapshots: list[MarketSnapshot],
) -> str:
    """保留手动模拟入口，方便网页里继续做可选手动记录。"""
    if action == "stats":
        stats = build_paper_stats(storage, snapshots)
        return (
            "今日自动纸上模拟统计\n"
            f"- total paper trades: {stats['total_paper_trades']}\n"
            f"- win rate: {stats['win_rate']}%\n"
            f"- average pnl: {stats['average_pnl']}\n"
            f"- max drawdown: {stats['max_drawdown']}\n"
            f"- reject reason: {', '.join(f'{k}: {v}' for k, v in stats['reject_reason'].items()) or '暂无'}"
        )

    if action == "reject":
        if not symbol or not reason:
            return "纸上模拟拒绝记录需要提供 --paper-symbol 和 --paper-reason。"
        _record_reject(
            storage=storage,
            account=storage.load_paper_account(),
            symbol=symbol,
            exchange="manual",
            reason=reason,
            detail="manual-reject",
            now=datetime.now(),
        )
        return f"已记录拒绝交易：{symbol}，原因：{reason}"

    if action not in {"buy", "sell"}:
        return "未知的纸上交易动作。"
    if not symbol or quantity is None or quantity <= 0:
        return "纸上模拟买卖需要提供 --paper-symbol 和大于 0 的 --paper-quantity。"
    if not reason:
        return "请提供 --paper-reason，帮助后面复盘。"

    account = storage.load_paper_account()
    _roll_daily_state(account, datetime.now())
    snapshot = next((item for item in snapshots if item.symbol == symbol), None)
    price = manual_price if manual_price is not None else (snapshot.price if snapshot else None)
    exchange = snapshot.exchange.upper() if snapshot else "MANUAL"
    if price is None or price <= 0:
        return "没有找到这个币的最新价格，请提供 --paper-price 或先抓一轮行情。"

    if action == "buy":
        quantity_value = quantity
        cost = quantity_value * price
        if account["cash_balance"] < cost:
            return "模拟买入失败：当前模拟现金余额不足。"
        if symbol in account["positions"]:
            return "模拟买入失败：当前已经持有该币种。"
        account["cash_balance"] = round(float(account["cash_balance"]) - cost, 6)
        account["positions"][symbol] = {
            "symbol": symbol,
            "pair": f"{symbol}/USDT",
            "quantity": quantity_value,
            "entry_price": price,
            "opened_at": int(datetime.now().timestamp()),
            "entry_reason": reason,
            "exchange": exchange,
        }
        account["daily"]["trade_count"] = int(account["daily"].get("trade_count", 0)) + 1
        snapshot_map = {item.symbol: item for item in snapshots}
        _record_trade_row(
            storage=storage,
            account=account,
            symbol=symbol,
            action="buy",
            price=price,
            quantity=quantity_value,
            pnl=None,
            trigger_reason=reason,
            exchange=exchange,
            now=datetime.now(),
            snapshots=snapshot_map,
        )
        storage.save_paper_account(account)
        _save_daily_stats_csv(storage, account)
        return f"已记录手动模拟买入：{symbol}，价格 {price:.6f}，数量 {quantity_value:.6f}。"

    position = account["positions"].get(symbol)
    if not position:
        return "模拟卖出失败：当前没有这个币的持仓。"
    if quantity > float(position["quantity"]):
        return "模拟卖出失败：当前持仓数量不足。"
    pnl = (price - float(position["entry_price"])) * quantity
    remaining_quantity = float(position["quantity"]) - quantity
    proceeds = price * quantity
    account["cash_balance"] = round(float(account["cash_balance"]) + proceeds, 6)
    account["daily"]["trade_count"] = int(account["daily"].get("trade_count", 0)) + 1
    account["daily"]["today_realized_pnl"] = round(
        float(account["daily"].get("today_realized_pnl", 0.0)) + pnl,
        6,
    )
    account["cumulative_realized_pnl"] = round(
        float(account.get("cumulative_realized_pnl", 0.0)) + pnl,
        6,
    )
    account["daily"]["consecutive_losses"] = (
        int(account["daily"].get("consecutive_losses", 0)) + 1 if pnl < 0 else 0
    )
    if remaining_quantity <= 0:
        account["positions"].pop(symbol, None)
    else:
        position["quantity"] = remaining_quantity
        account["positions"][symbol] = position
    snapshot_map = {item.symbol: item for item in snapshots}
    _record_trade_row(
        storage=storage,
        account=account,
        symbol=symbol,
        action="sell",
        price=price,
        quantity=quantity,
        pnl=pnl,
        trigger_reason=reason,
        exchange=exchange,
        now=datetime.now(),
        snapshots=snapshot_map,
    )
    _append_equity_point(account, datetime.now(), symbol)
    storage.save_paper_account(account)
    _save_daily_stats_csv(storage, account)
    return f"已记录手动模拟卖出：{symbol}，本次已实现盈亏 {pnl:.4f}。"


def build_risk_state(account: dict, market_metrics: dict[str, dict[str, Any]]) -> dict:
    btc_change = float(market_metrics.get("BTC", {}).get("change_5m_pct") or 0.0)
    risk_mode = "Risk-Off" if btc_change <= RISK_OFF_BTC_DROP_PCT else "Risk-On"
    allow_auto_open = (
        risk_mode == "Risk-On"
        and int(account["daily"].get("trade_count", 0)) < MAX_DAILY_TRADES
        and int(account["daily"].get("consecutive_losses", 0)) < MAX_LOSS_STREAK
    )
    stop_reason = ""
    if risk_mode == "Risk-Off":
        stop_reason = "btc-risk-off"
    elif int(account["daily"].get("trade_count", 0)) >= MAX_DAILY_TRADES:
        stop_reason = "daily-limit-reached"
    elif int(account["daily"].get("consecutive_losses", 0)) >= MAX_LOSS_STREAK:
        stop_reason = "max-loss-streak-reached"
    return {
        "mode": risk_mode,
        "btc_change_5m_pct": round(btc_change, 4),
        "allow_auto_open": allow_auto_open,
        "daily_trade_count": int(account["daily"].get("trade_count", 0)),
        "daily_trade_limit": MAX_DAILY_TRADES,
        "consecutive_losses": int(account["daily"].get("consecutive_losses", 0)),
        "max_loss_streak": MAX_LOSS_STREAK,
        "stop_reason": stop_reason,
    }


def build_paper_stats(storage: LocalStorage, snapshots: list[MarketSnapshot]) -> dict:
    trade_rows = load_paper_trade_events(storage)
    reject_rows = storage.load_reject_reason_rows()
    today = datetime.now().strftime("%Y-%m-%d")
    today_trades = [row for row in trade_rows if str(row["time"]).startswith(today)]
    today_sells = [row for row in today_trades if row["action"] == "sell"]
    realized_pnls = [float(row["pnl"]) for row in today_sells if row["pnl"] not in ("", None)]
    win_count = len([value for value in realized_pnls if value > 0])
    win_rate = (win_count / len(realized_pnls) * 100.0) if realized_pnls else 0.0
    average_pnl = (sum(realized_pnls) / len(realized_pnls)) if realized_pnls else 0.0
    max_drawdown = _calculate_max_drawdown(realized_pnls)
    reject_counter: dict[str, int] = {}
    for row in reject_rows:
        if not str(row["time"]).startswith(today):
            continue
        reason = str(row.get("reason", "")).strip() or "unknown"
        reject_counter[reason] = reject_counter.get(reason, 0) + 1
    account = storage.load_paper_account()
    overview = build_account_overview(account, snapshots)
    return {
        "date": today,
        "total_paper_trades": len(today_trades),
        "win_rate": round(win_rate, 2),
        "average_pnl": round(average_pnl, 4),
        "max_drawdown": round(max_drawdown, 4),
        "reject_reason": reject_counter,
        "today_pnl": round(overview["today_pnl"], 4),
        "cumulative_pnl": round(overview["cumulative_pnl"], 4),
    }


def load_paper_trade_events(storage: LocalStorage) -> list[dict]:
    rows = storage.load_paper_trade_rows()
    events: list[dict] = []
    for row in rows:
        events.append(
            {
                "time": row.get("time", ""),
                "timestamp": int(float(row.get("timestamp", 0) or 0)),
                "exchange": row.get("exchange", ""),
                "symbol": row.get("symbol", ""),
                "pair": row.get("pair", ""),
                "action": row.get("action", ""),
                "price": _to_float(row.get("price")),
                "quantity": _to_float(row.get("quantity")) or 0.0,
                "pnl": _to_float(row.get("pnl")),
                "reason": row.get("trigger_reason", ""),
            }
        )
    return sorted(events, key=lambda item: item["timestamp"])


def build_equity_curve(events: list[dict], account: dict | None = None) -> list[dict]:
    points: list[dict] = []
    if account:
        for item in account.get("equity_curve", []):
            points.append(
                {
                    "timestamp": int(item["timestamp"]),
                    "label": str(item["label"]),
                    "equity": round(float(item["equity"]), 4),
                    "symbol": str(item["symbol"]),
                }
            )
        if points:
            return sorted(points, key=lambda item: item["timestamp"])

    equity = INITIAL_BALANCE_USDT
    for item in sorted(events, key=lambda row: row["timestamp"]):
        if item["action"] != "sell" or item["pnl"] is None:
            continue
        equity += float(item["pnl"])
        points.append(
            {
                "timestamp": item["timestamp"],
                "label": datetime.fromtimestamp(item["timestamp"]).strftime("%m-%d %H:%M"),
                "equity": round(equity, 4),
                "symbol": item["symbol"],
            }
        )
    return points


def build_daily_pnl_summary(events: list[dict], reject_rows: list[dict]) -> list[dict]:
    daily: dict[str, dict[str, Any]] = {}
    for item in sorted(events, key=lambda row: row["timestamp"]):
        day = str(item["time"])[:10]
        bucket = daily.setdefault(
            day,
            {
                "date": day,
                "trade_count": 0,
                "realized_pnl": 0.0,
                "win_count": 0,
                "loss_count": 0,
                "reject_reason": {},
            },
        )
        bucket["trade_count"] += 1
        if item["action"] == "sell" and item["pnl"] is not None:
            pnl = float(item["pnl"])
            bucket["realized_pnl"] += pnl
            if pnl > 0:
                bucket["win_count"] += 1
            elif pnl < 0:
                bucket["loss_count"] += 1

    for row in reject_rows:
        day = str(row.get("time", ""))[:10]
        bucket = daily.setdefault(
            day,
            {
                "date": day,
                "trade_count": 0,
                "realized_pnl": 0.0,
                "win_count": 0,
                "loss_count": 0,
                "reject_reason": {},
            },
        )
        reason = str(row.get("reason", "")).strip() or "unknown"
        counter = bucket["reject_reason"]
        counter[reason] = counter.get(reason, 0) + 1

    summary = list(daily.values())
    for row in summary:
        row["realized_pnl"] = round(float(row["realized_pnl"]), 4)
    return sorted(summary, key=lambda row: row["date"], reverse=True)


def build_cumulative_metrics(events: list[dict], account: dict) -> dict:
    sell_events = [item for item in events if item["action"] == "sell" and item["pnl"] is not None]
    realized_pnls = [float(item["pnl"]) for item in sell_events]
    daily = build_daily_pnl_summary(events, [])
    best_day = max((float(row["realized_pnl"]) for row in daily), default=0.0)
    worst_day = min((float(row["realized_pnl"]) for row in daily), default=0.0)
    return {
        "cumulative_realized_pnl": round(float(account.get("cumulative_realized_pnl", 0.0)), 4),
        "cumulative_trade_count": len(events),
        "cumulative_win_count": len([pnl for pnl in realized_pnls if pnl > 0]),
        "cumulative_loss_count": len([pnl for pnl in realized_pnls if pnl < 0]),
        "best_day_pnl": round(best_day, 4),
        "worst_day_pnl": round(worst_day, 4),
    }


def build_account_overview(account: dict, snapshots: list[MarketSnapshot]) -> dict:
    latest_prices = {item.symbol: item.price for item in snapshots}
    position_value = 0.0
    unrealized_pnl = 0.0
    for symbol, position in account.get("positions", {}).items():
        current_price = latest_prices.get(symbol)
        if current_price is None:
            continue
        quantity = float(position["quantity"])
        entry_price = float(position["entry_price"])
        position_value += current_price * quantity
        unrealized_pnl += (current_price - entry_price) * quantity
    cash_balance = float(account.get("cash_balance", INITIAL_BALANCE_USDT))
    total_equity = cash_balance + position_value
    today_realized = float(account.get("daily", {}).get("today_realized_pnl", 0.0))
    cumulative_realized = float(account.get("cumulative_realized_pnl", 0.0))
    return {
        "initial_balance": round(float(account.get("initial_balance", INITIAL_BALANCE_USDT)), 4),
        "trade_size_usdt": round(float(account.get("trade_size_usdt", TRADE_SIZE_USDT)), 4),
        "cash_balance": round(cash_balance, 4),
        "position_value": round(position_value, 4),
        "total_equity": round(total_equity, 4),
        "today_pnl": round(today_realized + unrealized_pnl, 4),
        "cumulative_pnl": round(cumulative_realized + unrealized_pnl, 4),
        "today_realized_pnl": round(today_realized, 4),
        "unrealized_pnl": round(unrealized_pnl, 4),
    }


def build_position_rows(account: dict, snapshots: list[MarketSnapshot]) -> list[dict]:
    latest_prices = {item.symbol: item.price for item in snapshots}
    rows: list[dict] = []
    for symbol, position in account.get("positions", {}).items():
        entry_price = float(position["entry_price"])
        quantity = float(position["quantity"])
        current_price = latest_prices.get(symbol)
        pnl_pct = None
        pnl_value = None
        if current_price is not None and entry_price > 0:
            pnl_pct = ((current_price - entry_price) / entry_price) * 100.0
            pnl_value = (current_price - entry_price) * quantity
        rows.append(
            {
                "symbol": symbol,
                "pair": position.get("pair", f"{symbol}/USDT"),
                "entry_price": entry_price,
                "current_price": current_price,
                "quantity": quantity,
                "pnl_pct": round(pnl_pct, 4) if pnl_pct is not None else None,
                "pnl_value": round(pnl_value, 4) if pnl_value is not None else None,
                "holding_minutes": _holding_minutes(int(position["opened_at"])),
                "opened_at_text": datetime.fromtimestamp(int(position["opened_at"])).strftime("%m-%d %H:%M"),
                "entry_reason": position.get("entry_reason", ""),
                "exchange": position.get("exchange", ""),
            }
        )
    return sorted(rows, key=lambda item: item["symbol"])


def _maybe_open_positions(
    storage: LocalStorage,
    account: dict,
    market_metrics: dict[str, dict[str, Any]],
    risk_state: dict,
    now: datetime,
) -> list[dict]:
    actions: list[dict] = []
    for symbol in SUPPORTED_SYMBOLS:
        metrics = market_metrics.get(symbol)
        if not metrics:
            continue

        # 开仓前按顺序检查风控和信号，如果不满足就写入 reject reason。
        reject_reason = _open_reject_reason(symbol, metrics, account, risk_state)
        if reject_reason:
            _record_reject(
                storage=storage,
                account=account,
                symbol=symbol,
                exchange=str(metrics.get("exchange", "")).upper(),
                reason=reject_reason,
                detail=_reject_detail_text(reject_reason, metrics),
                now=now,
            )
            continue
        price = float(metrics["price"])
        quantity = round(TRADE_SIZE_USDT / price, 8)
        if quantity <= 0:
            continue
        cost = quantity * price
        if float(account["cash_balance"]) < cost:
            _record_reject(
                storage=storage,
                account=account,
                symbol=symbol,
                exchange=str(metrics.get("exchange", "")).upper(),
                reason="daily-limit-reached",
                detail="cash-not-enough",
                now=now,
            )
            continue

        # 纸上模拟买入只扣模拟现金，不会连接真实账户。
        account["cash_balance"] = round(float(account["cash_balance"]) - cost, 6)
        account["positions"][symbol] = {
            "symbol": symbol,
            "pair": f"{symbol}/USDT",
            "quantity": quantity,
            "entry_price": price,
            "opened_at": int(now.timestamp()),
            "entry_reason": "auto-open-breakout",
            "exchange": str(metrics.get("exchange", "")).upper(),
        }
        account["daily"]["trade_count"] = int(account["daily"].get("trade_count", 0)) + 1
        snapshot_map = _market_snapshot_like(market_metrics)
        _record_trade_row(
            storage=storage,
            account=account,
            symbol=symbol,
            action="buy",
            price=price,
            quantity=quantity,
            pnl=None,
            trigger_reason="auto-open-breakout",
            exchange=str(metrics.get("exchange", "")).upper(),
            now=now,
            snapshots=snapshot_map,
        )
        actions.append({"action": "buy", "symbol": symbol})
    return actions


def _maybe_close_positions(
    storage: LocalStorage,
    account: dict,
    market_metrics: dict[str, dict[str, Any]],
    risk_state: dict,
    now: datetime,
) -> list[dict]:
    actions: list[dict] = []
    positions = list(account.get("positions", {}).items())
    snapshot_map = _market_snapshot_like(market_metrics)
    for symbol, position in positions:
        metrics = market_metrics.get(symbol)
        if not metrics:
            continue
        entry_price = float(position["entry_price"])
        current_price = float(metrics["price"])
        quantity = float(position["quantity"])
        pnl_pct = ((current_price - entry_price) / entry_price) * 100.0 if entry_price else 0.0
        held_minutes = _holding_minutes(int(position["opened_at"]))

        reason = None
        if risk_state["mode"] == "Risk-Off":
            reason = "btc-risk-off-close"
        elif pnl_pct >= TAKE_PROFIT_PCT:
            reason = "take-profit"
        elif pnl_pct <= STOP_LOSS_PCT:
            reason = "stop-loss"
        elif held_minutes >= MAX_HOLD_MINUTES:
            reason = "time-exit"

        if not reason:
            continue

        # 纸上模拟卖出后，把卖出金额加回模拟现金，并把已实现盈亏记到账户里。
        pnl = (current_price - entry_price) * quantity
        account["cash_balance"] = round(float(account["cash_balance"]) + current_price * quantity, 6)
        account["positions"].pop(symbol, None)
        account["daily"]["trade_count"] = int(account["daily"].get("trade_count", 0)) + 1
        account["daily"]["today_realized_pnl"] = round(
            float(account["daily"].get("today_realized_pnl", 0.0)) + pnl,
            6,
        )
        account["cumulative_realized_pnl"] = round(
            float(account.get("cumulative_realized_pnl", 0.0)) + pnl,
            6,
        )
        account["daily"]["consecutive_losses"] = (
            int(account["daily"].get("consecutive_losses", 0)) + 1 if pnl < 0 else 0
        )
        _record_trade_row(
            storage=storage,
            account=account,
            symbol=symbol,
            action="sell",
            price=current_price,
            quantity=quantity,
            pnl=pnl,
            trigger_reason=reason,
            exchange=str(position.get("exchange", metrics.get("exchange", ""))).upper(),
            now=now,
            snapshots=snapshot_map,
        )
        _append_equity_point(account, now, symbol)
        actions.append({"action": "sell", "symbol": symbol, "reason": reason})
    return actions


def _open_reject_reason(
    symbol: str,
    metrics: dict[str, Any],
    account: dict,
    risk_state: dict,
) -> str | None:
    if risk_state["mode"] == "Risk-Off":
        return "btc-risk-off"
    if symbol in account.get("positions", {}):
        return "already-in-position"
    if int(account["daily"].get("trade_count", 0)) >= MAX_DAILY_TRADES:
        return "daily-limit-reached"
    if int(account["daily"].get("consecutive_losses", 0)) >= MAX_LOSS_STREAK:
        return "max-loss-streak-reached"
    if float(metrics.get("change_5m_pct") or 0.0) <= OPEN_SIGNAL_PCT:
        return "signal-too-weak"
    if not bool(metrics.get("volume_spike")):
        return "volume-too-low"
    return None


def _record_trade_row(
    storage: LocalStorage,
    account: dict,
    symbol: str,
    action: str,
    price: float,
    quantity: float,
    pnl: float | None,
    trigger_reason: str,
    exchange: str,
    now: datetime,
    snapshots: dict[str, dict[str, Any]],
) -> None:
    overview = build_account_overview_from_snapshot_map(account, snapshots)
    storage.append_paper_trade_csv(
        {
            "time": now.strftime("%Y-%m-%d %H:%M:%S"),
            "timestamp": int(now.timestamp()),
            "exchange": exchange,
            "symbol": symbol,
            "pair": f"{symbol}/USDT",
            "action": action,
            "price": round(price, 8),
            "quantity": round(quantity, 8),
            "trade_value_usdt": round(price * quantity, 8),
            "pnl": "" if pnl is None else round(pnl, 8),
            "trigger_reason": trigger_reason,
            "cash_balance": overview["cash_balance"],
            "position_value": overview["position_value"],
            "total_equity": overview["total_equity"],
        }
    )


def _record_reject(
    storage: LocalStorage,
    account: dict,
    symbol: str,
    exchange: str,
    reason: str,
    detail: str,
    now: datetime,
) -> None:
    key = f"{symbol}:{reason}"
    last_timestamp = int(account.get("last_rejects", {}).get(key, 0))
    current_timestamp = int(now.timestamp())
    # 同一种拒绝原因加一个冷却时间，避免每 30 秒刷满一堆重复记录。
    if current_timestamp - last_timestamp < REJECT_COOLDOWN_SECONDS:
        return
    account.setdefault("last_rejects", {})[key] = current_timestamp
    storage.append_reject_reason_csv(
        {
            "time": now.strftime("%Y-%m-%d %H:%M:%S"),
            "timestamp": current_timestamp,
            "exchange": exchange,
            "symbol": symbol,
            "pair": f"{symbol}/USDT",
            "reason": reason,
            "detail": detail,
        }
    )


def _append_equity_point(account: dict, now: datetime, symbol: str) -> None:
    equity = float(account.get("initial_balance", INITIAL_BALANCE_USDT)) + float(
        account.get("cumulative_realized_pnl", 0.0)
    )
    curve = account.setdefault("equity_curve", [])
    curve.append(
        {
            "timestamp": int(now.timestamp()),
            "label": now.strftime("%m-%d %H:%M"),
            "equity": round(equity, 4),
            "symbol": symbol,
        }
    )
    account["equity_curve"] = curve[-200:]


def _save_daily_stats_csv(storage: LocalStorage, account: dict) -> None:
    trade_rows = load_paper_trade_events(storage)
    reject_rows = storage.load_reject_reason_rows()
    summary_rows = build_daily_pnl_summary(trade_rows, reject_rows)
    cumulative = build_cumulative_metrics(trade_rows, account)
    csv_rows = []
    for row in summary_rows:
        reject_text = " | ".join(
            f"{key}:{value}" for key, value in sorted(row["reject_reason"].items())
        )
        csv_rows.append(
            {
                "date": row["date"],
                "total_paper_trades": row["trade_count"],
                "win_rate": _row_win_rate(row),
                "average_pnl": _row_average_pnl(row),
                "max_drawdown": _row_max_drawdown_for_day(trade_rows, row["date"]),
                "today_pnl": row["realized_pnl"],
                "cumulative_pnl": cumulative["cumulative_realized_pnl"],
                "reject_reason_stats": reject_text,
            }
        )
    storage.save_daily_stats_csv(csv_rows)


def build_account_overview_from_snapshot_map(
    account: dict,
    snapshot_map: dict[str, dict[str, Any]],
) -> dict:
    position_value = 0.0
    unrealized_pnl = 0.0
    for symbol, position in account.get("positions", {}).items():
        current_price = _to_float(snapshot_map.get(symbol, {}).get("price"))
        if current_price is None:
            continue
        quantity = float(position["quantity"])
        entry_price = float(position["entry_price"])
        position_value += current_price * quantity
        unrealized_pnl += (current_price - entry_price) * quantity
    cash_balance = float(account.get("cash_balance", INITIAL_BALANCE_USDT))
    return {
        "cash_balance": round(cash_balance, 4),
        "position_value": round(position_value, 4),
        "total_equity": round(cash_balance + position_value, 4),
        "unrealized_pnl": round(unrealized_pnl, 4),
    }


def _market_snapshot_like(market_metrics: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        symbol: {
            "price": metrics.get("price"),
        }
        for symbol, metrics in market_metrics.items()
    }


def _roll_daily_state(account: dict, now: datetime) -> None:
    daily = account.setdefault("daily", {})
    today = now.strftime("%Y-%m-%d")
    if daily.get("date") == today:
        return
    # 跨天后重置“今日统计”，但不清空累计盈亏和历史交易。
    daily["date"] = today
    daily["trade_count"] = 0
    daily["consecutive_losses"] = 0
    daily["today_realized_pnl"] = 0.0


def _holding_minutes(opened_at: int) -> int:
    opened = datetime.fromtimestamp(opened_at)
    delta = datetime.now() - opened
    return max(0, int(delta.total_seconds() // 60))


def _calculate_max_drawdown(realized_pnls: list[float]) -> float:
    if not realized_pnls:
        return 0.0
    equity = 0.0
    peak = 0.0
    max_drawdown = 0.0
    for pnl in realized_pnls:
        equity += pnl
        peak = max(peak, equity)
        max_drawdown = max(max_drawdown, peak - equity)
    return max_drawdown


def _row_win_rate(row: dict) -> float:
    total_closed = int(row["win_count"]) + int(row["loss_count"])
    if total_closed == 0:
        return 0.0
    return round(int(row["win_count"]) / total_closed * 100.0, 2)


def _row_average_pnl(row: dict) -> float:
    total_closed = int(row["win_count"]) + int(row["loss_count"])
    if total_closed == 0:
        return 0.0
    return round(float(row["realized_pnl"]) / total_closed, 4)


def _row_max_drawdown_for_day(trade_rows: list[dict], day: str) -> float:
    pnls = [
        float(item["pnl"])
        for item in trade_rows
        if item["action"] == "sell" and item["pnl"] is not None and str(item["time"]).startswith(day)
    ]
    return round(_calculate_max_drawdown(pnls), 4)


def _reject_detail_text(reason: str, metrics: dict[str, Any]) -> str:
    if reason == "signal-too-weak":
        return f"5m change {round(float(metrics.get('change_5m_pct') or 0.0), 4)}%"
    if reason == "volume-too-low":
        return f"volume ratio {round(float(metrics.get('volume_ratio') or 0.0), 4)}"
    return reason


def _to_float(value: Any) -> float | None:
    if value in ("", None):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
