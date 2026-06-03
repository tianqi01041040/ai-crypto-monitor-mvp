from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path


DEFAULT_SYMBOLS = ["BTC", "ETH", "SOL", "SUI", "DOGE", "XAU"]
DEFAULT_EXCHANGES = ["binance", "okx"]
DEFAULT_NEWS_SOURCES = [
    {"name": "coindesk", "url": "https://www.coindesk.com/arc/outboundfeeds/rss/"},
    {"name": "cointelegraph", "url": "https://cointelegraph.com/rss.xml"},
]


@dataclass(slots=True)
class AppConfig:
    poll_interval_seconds: int = 300
    symbols: list[str] = None  # type: ignore[assignment]
    exchanges: list[str] = None  # type: ignore[assignment]
    preferred_exchange: str = "okx"
    price_move_alert_pct: float = 1.0
    volume_spike_multiplier: float = 1.3
    xau_price_move_alert_pct: float = 0.35
    xau_volume_spike_multiplier: float = 1.15
    btc_market_sync_min_assets: int = 3
    btc_market_sync_alt_move_pct: float = 1.0
    data_dir: str = "data"
    request_timeout_seconds: int = 10
    news_max_items_per_source: int = 10
    news_recent_hours: int = 24
    news_sources: list[dict] = None  # type: ignore[assignment]
    notifications_enabled: bool = False
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    discord_webhook_url: str = ""
    daily_brief_push_enabled: bool = False
    daily_brief_push_time: str = "09:00"
    bot_enabled: bool = False
    once: bool = False
    daily_brief: bool = False
    news_scan: bool = False
    paper_action: str | None = None
    paper_symbol: str | None = None
    paper_quantity: float | None = None
    paper_price: float | None = None
    paper_reason: str | None = None

    def __post_init__(self) -> None:
        if self.symbols is None:
            self.symbols = list(DEFAULT_SYMBOLS)
        if self.exchanges is None:
            self.exchanges = list(DEFAULT_EXCHANGES)
        if self.news_sources is None:
            self.news_sources = list(DEFAULT_NEWS_SOURCES)


def load_json_config(path: str | None) -> dict:
    if not path:
        return {}
    return json.loads(Path(path).read_text(encoding="utf-8"))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Monitor Binance and OKX public market data for crypto alerts."
    )
    parser.add_argument("--config", help="Path to JSON config file.")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run one polling cycle and exit.",
    )
    parser.add_argument(
        "--symbols",
        nargs="+",
        help="Override symbols, for example: BTC ETH SOL",
    )
    parser.add_argument(
        "--exchanges",
        nargs="+",
        choices=["binance", "okx"],
        help="Override exchanges, for example: binance okx",
    )
    parser.add_argument(
        "--interval",
        type=int,
        help="Polling interval in seconds. Default is 300.",
    )
    parser.add_argument(
        "--daily-brief",
        action="store_true",
        help="Generate a simple daily market brief and save it locally.",
    )
    parser.add_argument(
        "--news-scan",
        action="store_true",
        help="Fetch public crypto news and print a categorized summary.",
    )
    parser.add_argument(
        "--paper-action",
        choices=["buy", "sell", "reject", "stats"],
        help="Run a paper trading action.",
    )
    parser.add_argument("--paper-symbol", help="Symbol used for paper trading.")
    parser.add_argument(
        "--paper-quantity",
        type=float,
        help="Quantity used for a paper buy or sell action.",
    )
    parser.add_argument(
        "--paper-price",
        type=float,
        help="Manual price for a paper buy or sell action. If omitted, latest market price is used.",
    )
    parser.add_argument(
        "--paper-reason",
        help="Reason for a paper trade or rejected trade.",
    )
    return parser.parse_args()


def build_config() -> AppConfig:
    args = parse_args()
    raw = load_json_config(args.config)
    config = AppConfig(**raw)
    if args.symbols:
        config.symbols = [item.upper() for item in args.symbols]
    if args.exchanges:
        config.exchanges = [item.lower() for item in args.exchanges]
    if args.interval:
        config.poll_interval_seconds = args.interval
    if args.once:
        config.once = True
    if args.daily_brief:
        config.daily_brief = True
    if args.news_scan:
        config.news_scan = True
    if args.paper_action:
        config.paper_action = args.paper_action
    if args.paper_symbol:
        config.paper_symbol = args.paper_symbol.upper()
    if args.paper_quantity is not None:
        config.paper_quantity = args.paper_quantity
    if args.paper_price is not None:
        config.paper_price = args.paper_price
    if args.paper_reason:
        config.paper_reason = args.paper_reason
    return config
