from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class MarketSnapshot:
    exchange: str
    symbol: str
    pair: str
    price: float
    volume_24h: float
    change_24h_pct: float
    timestamp: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "exchange": self.exchange,
            "symbol": self.symbol,
            "pair": self.pair,
            "price": self.price,
            "volume_24h": self.volume_24h,
            "change_24h_pct": self.change_24h_pct,
            "timestamp": self.timestamp,
        }


@dataclass(slots=True)
class AlertEvent:
    level: str
    category: str
    message: str
    exchange: str | None = None
    symbol: str | None = None


@dataclass(slots=True)
class SignalEvent:
    exchange: str
    symbol: str
    bias: str
    price: float
    entry_zone: str
    stop_loss: float
    take_profit_1: float
    take_profit_2: float
    risk_level: str
    trigger_reason: str
    timestamp: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "exchange": self.exchange,
            "symbol": self.symbol,
            "bias": self.bias,
            "price": self.price,
            "entry_zone": self.entry_zone,
            "stop_loss": self.stop_loss,
            "take_profit_1": self.take_profit_1,
            "take_profit_2": self.take_profit_2,
            "risk_level": self.risk_level,
            "trigger_reason": self.trigger_reason,
            "timestamp": self.timestamp,
        }


@dataclass(slots=True)
class RuntimeState:
    history: dict[str, list[dict[str, Any]]] = field(default_factory=dict)


@dataclass(slots=True)
class PaperTradeEvent:
    action: str
    symbol: str
    quantity: float
    price: float | None
    timestamp: int
    reason: str
    pnl: float | None = None
    exchange: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "symbol": self.symbol,
            "quantity": self.quantity,
            "price": self.price,
            "timestamp": self.timestamp,
            "reason": self.reason,
            "pnl": self.pnl,
            "exchange": self.exchange,
        }
