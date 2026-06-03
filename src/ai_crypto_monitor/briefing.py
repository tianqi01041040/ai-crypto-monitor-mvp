from __future__ import annotations

from datetime import datetime

from .alerts import evaluate_alerts
from .config import AppConfig
from .models import MarketSnapshot, RuntimeState
from .news import NewsItem, summarize_news


def generate_daily_brief(
    snapshots: list[MarketSnapshot],
    state: RuntimeState,
    config: AppConfig,
    news_items: list[NewsItem] | None = None,
) -> str:
    if not snapshots:
        return "今日早报生成失败：没有拿到可用行情数据。"

    selected = _select_preferred_snapshots(snapshots)
    alerts = evaluate_alerts(snapshots, state, config)
    now_text = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    btc_line = _trend_line(selected.get("BTC"), state)
    eth_line = _trend_line(selected.get("ETH"), state)
    strongest_line = _strongest_assets_line(selected)
    risk_line = _risk_line(selected, alerts)
    action_line = _action_line(selected, alerts)
    news_section = _news_section(news_items or [])

    lines = [
        "# 每日早报",
        "",
        f"生成时间：{now_text}",
        "",
        "## 今日概览",
        "- 数据来源：公开行情 API + 公开 RSS 新闻源",
        f"- 监控币种：{', '.join(config.symbols)}",
        "",
        "## BTC 趋势",
        f"- {btc_line}",
        "",
        "## ETH 趋势",
        f"- {eth_line}",
        "",
        "## 强势币",
        f"- {strongest_line}",
        "",
        "## 市场热点",
        *news_section,
        "",
        "## 风险提示",
        f"- {risk_line}",
        "",
        "## 今日判断",
        f"- {action_line}",
    ]
    return "\n".join(lines)


def _select_preferred_snapshots(
    snapshots: list[MarketSnapshot],
) -> dict[str, MarketSnapshot]:
    preferred: dict[str, MarketSnapshot] = {}
    for item in snapshots:
        existing = preferred.get(item.symbol)
        if existing is None:
            preferred[item.symbol] = item
            continue
        if existing.exchange != "okx" and item.exchange == "okx":
            preferred[item.symbol] = item
    return preferred


def _trend_line(
    snapshot: MarketSnapshot | None,
    state: RuntimeState,
) -> str:
    if snapshot is None:
        return "暂无数据。"
    change_24h = snapshot.change_24h_pct
    interval_change = _interval_change(snapshot, state)
    if change_24h >= 2:
        bias = "偏强"
    elif change_24h <= -2:
        bias = "偏弱"
    else:
        bias = "震荡"
    return (
        f"{snapshot.symbol} 当前价格 {snapshot.price:.6f}，24h 涨跌 {change_24h:.2f}% ，"
        f"最近一轮变化 {interval_change:.2f}% ，短线判断：{bias}。"
    )


def _strongest_assets_line(selected: dict[str, MarketSnapshot]) -> str:
    ranked = sorted(
        selected.values(),
        key=lambda item: item.change_24h_pct,
        reverse=True,
    )
    leaders = ranked[:3]
    if not leaders:
        return "暂无可比较数据。"
    return "，".join(
        f"{item.symbol} ({item.change_24h_pct:.2f}%)" for item in leaders
    )


def _risk_line(
    selected: dict[str, MarketSnapshot],
    alerts: list,
) -> str:
    btc = selected.get("BTC")
    eth = selected.get("ETH")
    if btc and eth and btc.change_24h_pct < -2 and eth.change_24h_pct < -2:
        return "BTC 和 ETH 同时偏弱，市场可能处于风险释放阶段，控制节奏更重要。"
    if any(alert.category == "btc_market_sync" for alert in alerts):
        return "BTC 正在带动全市场同步波动，短线风险和机会都会放大。"
    if any(abs(item.change_24h_pct) > 5 for item in selected.values()):
        return "部分币种 24h 波动很大，追涨杀跌的风险偏高。"
    return "当前没有看到特别极端的系统性风险，但仍建议轻仓观察。"


def _action_line(
    selected: dict[str, MarketSnapshot],
    alerts: list,
) -> str:
    btc = selected.get("BTC")
    eth = selected.get("ETH")
    positive_count = sum(1 for item in selected.values() if item.change_24h_pct > 0)
    if btc and eth and btc.change_24h_pct > 2 and eth.change_24h_pct > 2 and positive_count >= 3:
        return "今天更适合观察强势延续，但第一版系统仍建议只做纸上模拟，不做实盘。"
    if any(alert.level == "critical" for alert in alerts):
        return "今天更适合观察，不适合冲动交易，先看市场是否稳定。"
    return "今天以观察为主，等待更清晰的方向后再做纸上模拟记录。"


def _interval_change(snapshot: MarketSnapshot, state: RuntimeState) -> float:
    key = f"{snapshot.exchange}:{snapshot.symbol}"
    history = state.history.get(key, [])
    if not history:
        return 0.0
    old_price = float(history[-1]["price"])
    if old_price == 0:
        return 0.0
    return ((snapshot.price - old_price) / old_price) * 100.0


def _news_section(items: list[NewsItem]) -> list[str]:
    if not items:
        return ["- 当前没有抓到可用新闻，今天的热点判断主要基于行情。"]
    summary = summarize_news(items)
    topic_text = (
        "，".join(f"{topic}({count})" for topic, count in summary["top_topics"])
        if summary["top_topics"]
        else "暂无明显主题"
    )
    lines = [f"- 热点主题：{topic_text}"]
    for item in summary["headline_items"][:3]:
        lines.append(f"- [{item.source}] {item.title}")
    return lines
