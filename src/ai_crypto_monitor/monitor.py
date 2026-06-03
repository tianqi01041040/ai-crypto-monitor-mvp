from __future__ import annotations

import sys
import time
from datetime import datetime
from pathlib import Path

from .alerts import evaluate_alerts, update_state
from .briefing import generate_daily_brief
from .clients import BinancePublicClient, ExchangeClientError, OkxPublicClient
from .config import AppConfig, build_config
from .models import AlertEvent, MarketSnapshot
from .news import build_news_state, detect_new_items, fetch_news_items, format_news_scan
from .paper_trading import handle_paper_action
from .storage import LocalStorage


CLIENTS = {
    "binance": BinancePublicClient,
    "okx": OkxPublicClient,
}


def main() -> None:
    config = build_config()
    root_dir = Path.cwd()
    data_dir = str(root_dir / config.data_dir)
    storage = LocalStorage(data_dir=data_dir)
    state = storage.load_state()
    news_state = storage.load_news_state()
    if config.daily_brief:
        snapshots = collect_snapshots(config)
        news_items = collect_news(config, storage, news_state, announce_new_items=False)
        brief = generate_daily_brief(snapshots, state, config, news_items=news_items)
        brief_date = datetime.now().strftime("%Y-%m-%d")
        brief_path = storage.save_daily_brief(brief_date, brief)
        print(brief)
        print(f"\n已保存到: {brief_path}")
        return
    if config.news_scan:
        news_items = collect_news(config, storage, news_state, announce_new_items=False)
        print(format_news_scan(news_items))
        return
    if config.paper_action:
        snapshots = collect_snapshots(config) if _paper_action_needs_market_data(config) else []
        result = handle_paper_action(
            action=config.paper_action,
            storage=storage,
            symbol=config.paper_symbol,
            quantity=config.paper_quantity,
            manual_price=config.paper_price,
            reason=config.paper_reason,
            snapshots=snapshots,
        )
        print(result)
        return

    print(_headline(config))
    while True:
        started_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"\n[{started_at}] 开始抓取行情...")
        snapshots = collect_snapshots(config)
        if snapshots:
            print_snapshot_table(snapshots)
            alerts = evaluate_alerts(snapshots, state, config)
            print_alerts(alerts)
            news_items = collect_news(config, storage, news_state, announce_new_items=True)
            if not news_items:
                print("\n新闻源暂时没有拿到新内容。")
            storage.append_snapshots(snapshots)
            state = update_state(snapshots, state)
            storage.save_state(state)
        else:
            print("这一轮没有拿到可用数据。")

        if config.once:
            break
        print(f"\n等待 {config.poll_interval_seconds} 秒后进行下一轮抓取...")
        time.sleep(config.poll_interval_seconds)


def collect_snapshots(config: AppConfig) -> list[MarketSnapshot]:
    all_snapshots: list[MarketSnapshot] = []
    for exchange in config.exchanges:
        client_cls = CLIENTS.get(exchange)
        if client_cls is None:
            print(f"跳过未知交易所: {exchange}")
            continue
        client = client_cls()
        try:
            snapshots = client.fetch_snapshots(
                symbols=config.symbols,
                timeout=config.request_timeout_seconds,
            )
            all_snapshots.extend(snapshots)
        except ExchangeClientError as exc:
            print(f"[ERROR] {exchange.upper()} 抓取失败: {exc}", file=sys.stderr)
    return all_snapshots


def print_snapshot_table(snapshots: list[MarketSnapshot]) -> None:
    print(
        f"{'Exchange':<10} {'Symbol':<6} {'Price':>14} {'24h Volume':>18} {'24h Change %':>14}"
    )
    print("-" * 68)
    for item in snapshots:
        print(
            f"{item.exchange:<10} {item.symbol:<6} "
            f"{item.price:>14.6f} {item.volume_24h:>18,.2f} {item.change_24h_pct:>14.2f}"
        )


def print_alerts(alerts: list[AlertEvent]) -> None:
    if not alerts:
        print("\n没有触发提醒，市场暂时平稳。")
        return
    print("\n提醒:")
    for alert in alerts:
        print(f"[ALERT][{alert.level.upper()}][{alert.category}] {alert.message}")


def collect_news(
    config: AppConfig,
    storage: LocalStorage,
    news_state: dict,
    announce_new_items: bool,
) -> list:
    news_items = fetch_news_items(config)
    if not news_items:
        return []
    new_items = detect_new_items(news_items, news_state.get("seen_ids", []))
    storage.append_news_items([item.to_dict() for item in new_items])
    updated_state = build_news_state(news_state, news_items)
    news_state.clear()
    news_state.update(updated_state)
    storage.save_news_state(news_state)
    if announce_new_items:
        print_news_alerts(new_items)
    return news_items


def print_news_alerts(news_items: list) -> None:
    if not news_items:
        print("\n新闻提醒: 这一轮没有发现新的标题。")
        return
    print("\n新闻提醒:")
    for item in news_items[:5]:
        topic_text = ", ".join(item.topics) if item.topics else "general"
        print(f"[NEWS][{item.source}] {item.title} | topics: {topic_text}")


def _headline(config: AppConfig) -> str:
    symbols = ", ".join(config.symbols)
    exchanges = ", ".join(item.upper() for item in config.exchanges)
    return (
        "AI + Crypto Market Monitor MVP\n"
        f"监控交易所: {exchanges}\n"
        f"监控币种: {symbols}\n"
        f"抓取间隔: {config.poll_interval_seconds} 秒"
    )


def _paper_action_needs_market_data(config: AppConfig) -> bool:
    if config.paper_action in {"reject", "stats"}:
        return False
    if config.paper_action in {"buy", "sell"} and config.paper_price is not None:
        return False
    return True
