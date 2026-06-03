from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Iterable

from .models import MarketSnapshot


class ExchangeClientError(RuntimeError):
    pass


BINANCE_SYMBOL_MAP = {
    "BTC": "BTCUSDT",
    "ETH": "ETHUSDT",
    "SOL": "SOLUSDT",
    "SUI": "SUIUSDT",
    "DOGE": "DOGEUSDT",
}

OKX_SYMBOL_MAP = {
    "BTC": "BTC-USDT",
    "ETH": "ETH-USDT",
    "SOL": "SOL-USDT",
    "SUI": "SUI-USDT",
    "DOGE": "DOGE-USDT",
    "XAU": "XAU-USDT-SWAP",
}


def _get_json(url: str, timeout: int) -> object:
    last_error: urllib.error.URLError | None = None
    for _ in range(3):
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": "ai-crypto-monitor-mvp/1.0",
                "Accept": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            last_error = exc
            time.sleep(0.6)
    raise ExchangeClientError(str(last_error)) from last_error


class BinancePublicClient:
    # The data domain is usually more reliable for public market reads.
    base_url = "https://data-api.binance.vision"

    def fetch_snapshots(
        self,
        symbols: Iterable[str],
        timeout: int,
    ) -> list[MarketSnapshot]:
        snapshots: list[MarketSnapshot] = []
        for symbol in symbols:
            pair = BINANCE_SYMBOL_MAP.get(symbol.upper())
            if not pair:
                continue
            query = urllib.parse.urlencode({"symbol": pair})
            url = f"{self.base_url}/api/v3/ticker/24hr?{query}"
            payload = _get_json(url, timeout)
            if not isinstance(payload, dict):
                raise ExchangeClientError(f"Unexpected Binance response for {pair}")
            snapshots.append(
                MarketSnapshot(
                    exchange="binance",
                    symbol=symbol,
                    pair=pair,
                    price=float(payload["lastPrice"]),
                    volume_24h=float(payload["quoteVolume"]),
                    change_24h_pct=float(payload["priceChangePercent"]),
                    timestamp=int(time.time()),
                )
            )
        return snapshots


class OkxPublicClient:
    base_url = "https://www.okx.com"

    def fetch_snapshots(
        self,
        symbols: Iterable[str],
        timeout: int,
    ) -> list[MarketSnapshot]:
        snapshots: list[MarketSnapshot] = []
        for symbol in symbols:
            pair = OKX_SYMBOL_MAP.get(symbol.upper())
            if not pair:
                continue
            query = urllib.parse.urlencode({"instId": pair})
            url = f"{self.base_url}/api/v5/market/ticker?{query}"
            payload = _get_json(url, timeout)
            if not isinstance(payload, dict) or "data" not in payload:
                raise ExchangeClientError(f"Unexpected OKX response for {pair}")
            data = payload["data"]
            if not isinstance(data, list) or not data:
                raise ExchangeClientError(f"No OKX ticker data for {pair}")
            item = data[0]
            snapshots.append(
                MarketSnapshot(
                    exchange="okx",
                    symbol=symbol,
                    pair=pair,
                    price=float(item["last"]),
                    volume_24h=float(item["volCcy24h"]),
                    change_24h_pct=_safe_pct_change(
                        current=float(item["last"]),
                        open_24h=float(item["open24h"]),
                    ),
                    timestamp=int(time.time()),
                )
            )
        return snapshots


def fetch_binance_candles(
    pair: str,
    interval: str,
    limit: int,
    timeout: int,
) -> list[dict]:
    query = urllib.parse.urlencode({"symbol": pair, "interval": interval, "limit": limit})
    url = f"{BinancePublicClient.base_url}/api/v3/klines?{query}"
    payload = _get_json(url, timeout)
    if not isinstance(payload, list):
        raise ExchangeClientError(f"Unexpected Binance kline response for {pair}")

    candles: list[dict] = []
    for item in payload:
        if not isinstance(item, list) or len(item) < 6:
            continue
        candles.append(
            {
                "timestamp": int(item[0]) // 1000,
                "open": float(item[1]),
                "high": float(item[2]),
                "low": float(item[3]),
                "close": float(item[4]),
                "volume": float(item[5]),
            }
        )
    return candles


def fetch_okx_candles(
    pair: str,
    bar: str,
    limit: int,
    timeout: int,
) -> list[dict]:
    query = urllib.parse.urlencode({"instId": pair, "bar": bar, "limit": limit})
    url = f"{OkxPublicClient.base_url}/api/v5/market/candles?{query}"
    payload = _get_json(url, timeout)
    if not isinstance(payload, dict) or "data" not in payload:
        raise ExchangeClientError(f"Unexpected OKX kline response for {pair}")
    data = payload["data"]
    if not isinstance(data, list):
        raise ExchangeClientError(f"Unexpected OKX candle list for {pair}")

    candles: list[dict] = []
    for item in reversed(data):
        if not isinstance(item, list) or len(item) < 6:
            continue
        candles.append(
            {
                "timestamp": int(item[0]) // 1000,
                "open": float(item[1]),
                "high": float(item[2]),
                "low": float(item[3]),
                "close": float(item[4]),
                "volume": float(item[5]),
            }
        )
    return candles


def _safe_pct_change(current: float, open_24h: float) -> float:
    if open_24h == 0:
        return 0.0
    return ((current - open_24h) / open_24h) * 100.0
