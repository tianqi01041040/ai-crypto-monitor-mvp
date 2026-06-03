from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path

from .models import MarketSnapshot, PaperTradeEvent, RuntimeState, SignalEvent


class LocalStorage:
    def __init__(self, data_dir: str) -> None:
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.history_file = self.data_dir / "market_history.jsonl"
        self.state_file = self.data_dir / "runtime_state.json"
        self.briefs_dir = self.data_dir / "daily_briefs"
        self.paper_trade_file = self.data_dir / "paper_trades.jsonl"
        self.paper_state_file = self.data_dir / "paper_state.json"
        self.daily_stats_dir = self.data_dir / "paper_stats"
        self.paper_account_file = self.data_dir / "paper_account.json"
        self.paper_trades_csv_file = self.data_dir / "paper_trades.csv"
        self.reject_reasons_csv_file = self.data_dir / "reject_reasons.csv"
        self.daily_stats_csv_file = self.data_dir / "daily_stats.csv"
        self.news_history_file = self.data_dir / "news_history.jsonl"
        self.news_state_file = self.data_dir / "news_state.json"
        self.notification_state_file = self.data_dir / "notification_state.json"
        self.web_settings_file = self.data_dir / "web_settings.json"
        self.signal_history_file = self.data_dir / "signal_history.jsonl"
        self.bot_runtime_file = self.data_dir / "bot_runtime.json"
        self.briefs_dir.mkdir(parents=True, exist_ok=True)
        self.daily_stats_dir.mkdir(parents=True, exist_ok=True)

    def append_snapshots(self, snapshots: list[MarketSnapshot]) -> None:
        with self.history_file.open("a", encoding="utf-8") as handle:
            for snapshot in snapshots:
                handle.write(json.dumps(snapshot.to_dict(), ensure_ascii=False) + "\n")

    def load_state(self) -> RuntimeState:
        if not self.state_file.exists():
            return RuntimeState()
        raw = json.loads(self.state_file.read_text(encoding="utf-8"))
        return RuntimeState(history=raw.get("history", {}))

    def save_state(self, state: RuntimeState) -> None:
        payload = {"history": state.history}
        self.state_file.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def save_daily_brief(self, brief_date: str, content: str) -> Path:
        path = self.briefs_dir / f"{brief_date}.md"
        path.write_text(content, encoding="utf-8")
        return path

    def append_paper_trade(self, event: PaperTradeEvent) -> None:
        with self.paper_trade_file.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event.to_dict(), ensure_ascii=False) + "\n")

    def load_paper_state(self) -> dict:
        if not self.paper_state_file.exists():
            return {"open_positions": {}, "equity_curve": []}
        return json.loads(self.paper_state_file.read_text(encoding="utf-8"))

    def save_paper_state(self, state: dict) -> None:
        self.paper_state_file.write_text(
            json.dumps(state, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def save_daily_paper_stats(self, stats_date: str, payload: dict) -> Path:
        path = self.daily_stats_dir / f"{stats_date}.json"
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return path

    def load_paper_account(self) -> dict:
        if not self.paper_account_file.exists():
            return {
                "initial_balance": 1000.0,
                "trade_size_usdt": 20.0,
                "cash_balance": 1000.0,
                "positions": {},
                "cumulative_realized_pnl": 0.0,
                "equity_curve": [],
                "daily": {
                    "date": None,
                    "trade_count": 0,
                    "consecutive_losses": 0,
                    "today_realized_pnl": 0.0,
                },
                "last_rejects": {},
            }
        data = json.loads(self.paper_account_file.read_text(encoding="utf-8"))
        data.setdefault("initial_balance", 1000.0)
        data.setdefault("trade_size_usdt", 20.0)
        data.setdefault("cash_balance", 1000.0)
        data.setdefault("positions", {})
        data.setdefault("cumulative_realized_pnl", 0.0)
        data.setdefault("equity_curve", [])
        data.setdefault(
            "daily",
            {
                "date": None,
                "trade_count": 0,
                "consecutive_losses": 0,
                "today_realized_pnl": 0.0,
            },
        )
        data.setdefault("last_rejects", {})
        return data

    def save_paper_account(self, account: dict) -> None:
        self.paper_account_file.write_text(
            json.dumps(account, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def append_csv_row(self, path: Path, fieldnames: list[str], row: dict) -> None:
        needs_header = not path.exists() or path.stat().st_size == 0
        with path.open("a", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            if needs_header:
                writer.writeheader()
            writer.writerow({key: row.get(key, "") for key in fieldnames})

    def load_csv_rows(self, path: Path) -> list[dict]:
        if not path.exists() or path.stat().st_size == 0:
            return []
        with path.open("r", encoding="utf-8", newline="") as handle:
            return list(csv.DictReader(handle))

    def append_paper_trade_csv(self, row: dict) -> None:
        self.append_csv_row(
            self.paper_trades_csv_file,
            [
                "time",
                "timestamp",
                "exchange",
                "symbol",
                "pair",
                "action",
                "price",
                "quantity",
                "trade_value_usdt",
                "pnl",
                "trigger_reason",
                "cash_balance",
                "position_value",
                "total_equity",
            ],
            row,
        )

    def load_paper_trade_rows(self) -> list[dict]:
        return self.load_csv_rows(self.paper_trades_csv_file)

    def append_reject_reason_csv(self, row: dict) -> None:
        self.append_csv_row(
            self.reject_reasons_csv_file,
            [
                "time",
                "timestamp",
                "exchange",
                "symbol",
                "pair",
                "reason",
                "detail",
            ],
            row,
        )

    def load_reject_reason_rows(self) -> list[dict]:
        return self.load_csv_rows(self.reject_reasons_csv_file)

    def save_daily_stats_csv(self, rows: list[dict]) -> None:
        path = self.daily_stats_csv_file
        fieldnames = [
            "date",
            "total_paper_trades",
            "win_rate",
            "average_pnl",
            "max_drawdown",
            "today_pnl",
            "cumulative_pnl",
            "reject_reason_stats",
        ]
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                writer.writerow({key: row.get(key, "") for key in fieldnames})

    def append_news_items(self, items: list[dict]) -> None:
        with self.news_history_file.open("a", encoding="utf-8") as handle:
            for item in items:
                handle.write(json.dumps(item, ensure_ascii=False) + "\n")

    def load_news_state(self) -> dict:
        if not self.news_state_file.exists():
            return {"seen_ids": [], "last_scan_at": None}
        return json.loads(self.news_state_file.read_text(encoding="utf-8"))

    def save_news_state(self, state: dict) -> None:
        self.news_state_file.write_text(
            json.dumps(state, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def load_notification_state(self) -> dict:
        if not self.notification_state_file.exists():
            return {"sent_ids": [], "cooldowns": {}}
        data = json.loads(self.notification_state_file.read_text(encoding="utf-8"))
        data.setdefault("sent_ids", [])
        data.setdefault("cooldowns", {})
        return data

    def save_notification_state(self, state: dict) -> None:
        self.notification_state_file.write_text(
            json.dumps(state, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def append_signal(self, signal: SignalEvent) -> None:
        with self.signal_history_file.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(signal.to_dict(), ensure_ascii=False) + "\n")

    def load_signal_rows(self, limit: int = 30) -> list[dict]:
        if not self.signal_history_file.exists():
            return []
        rows: list[dict] = []
        with self.signal_history_file.open("r", encoding="utf-8") as handle:
            for line in handle:
                text = line.strip()
                if not text:
                    continue
                rows.append(json.loads(text))
        return rows[-limit:][::-1]

    def load_bot_runtime(self) -> dict:
        if not self.bot_runtime_file.exists():
            return {
                "enabled": False,
                "status": "stopped",
                "message": "机器人尚未启动。",
                "last_cycle_at": None,
                "last_success_at": None,
                "last_push_at": None,
                "last_test_push_at": None,
                "last_push_symbols": [],
                "last_error": "",
                "last_signal_count": 0,
                "latest_market": [],
            }
        data = json.loads(self.bot_runtime_file.read_text(encoding="utf-8"))
        data.setdefault("enabled", False)
        data.setdefault("status", "stopped")
        data.setdefault("message", "机器人尚未启动。")
        data.setdefault("last_cycle_at", None)
        data.setdefault("last_success_at", None)
        data.setdefault("last_push_at", None)
        data.setdefault("last_test_push_at", None)
        data.setdefault("last_push_symbols", [])
        data.setdefault("last_error", "")
        data.setdefault("last_signal_count", 0)
        data.setdefault("latest_market", [])
        return data

    def save_bot_runtime(self, payload: dict) -> None:
        payload = dict(payload)
        payload.setdefault("updated_at", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        self.bot_runtime_file.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def load_web_settings(self) -> dict:
        if not self.web_settings_file.exists():
            return {}
        data = json.loads(self.web_settings_file.read_text(encoding="utf-8"))
        data.setdefault("saved_news_keywords", [])
        data.setdefault("bot_enabled", False)
        data.setdefault("preferred_exchange", "okx")
        return data

    def save_web_settings(self, settings: dict) -> None:
        settings = dict(settings)
        settings.setdefault("saved_news_keywords", [])
        settings.setdefault("bot_enabled", False)
        settings.setdefault("preferred_exchange", "okx")
        self.web_settings_file.write_text(
            json.dumps(settings, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def reset_paper_account_files(self) -> None:
        for path in [
            self.paper_account_file,
            self.paper_trades_csv_file,
            self.reject_reasons_csv_file,
            self.daily_stats_csv_file,
            self.paper_trade_file,
            self.paper_state_file,
        ]:
            if path.exists():
                path.unlink()
