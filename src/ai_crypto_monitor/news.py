from __future__ import annotations

import hashlib
import html
import json
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from email.utils import parsedate_to_datetime

from .config import AppConfig


TOPIC_KEYWORDS = {
    "btc": ["btc", "bitcoin"],
    "eth": ["eth", "ethereum", "ether"],
    "sol": ["sol", "solana"],
    "ai": ["ai", "artificial intelligence", "agent", "agents"],
    "regulation": ["sec", "regulation", "regulator", "etf", "policy", "compliance"],
    "security": ["hack", "exploit", "breach", "attack", "stolen", "phishing"],
    "defi": ["defi", "dex", "liquidity", "yield"],
    "memecoin": ["doge", "dogecoin", "memecoin", "meme coin"],
    "stablecoin": ["stablecoin", "usdt", "usdc"],
    "macro": ["fed", "interest rate", "inflation", "tariff", "cpi"],
}

RISK_KEYWORDS = {
    "security",
    "regulation",
}


@dataclass(slots=True)
class NewsItem:
    source: str
    title: str
    link: str
    published_at: int
    summary: str
    item_id: str
    topics: list[str]

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "title": self.title,
            "link": self.link,
            "published_at": self.published_at,
            "summary": self.summary,
            "item_id": self.item_id,
            "topics": self.topics,
        }


class NewsFetchError(RuntimeError):
    pass


def fetch_news_items(config: AppConfig) -> list[NewsItem]:
    items: list[NewsItem] = []
    for source in config.news_sources:
        source_name = source["name"]
        source_url = source["url"]
        try:
            items.extend(
                _fetch_rss_source(
                    source_name=source_name,
                    source_url=source_url,
                    timeout=config.request_timeout_seconds,
                    max_items=config.news_max_items_per_source,
                )
            )
        except NewsFetchError:
            continue
    deduped: dict[str, NewsItem] = {}
    for item in items:
        deduped[item.item_id] = item
    recent_cutoff = int(time.time()) - (config.news_recent_hours * 3600)
    return sorted(
        [item for item in deduped.values() if item.published_at >= recent_cutoff],
        key=lambda item: item.published_at,
        reverse=True,
    )


def summarize_news(items: list[NewsItem]) -> dict:
    topic_counts: dict[str, int] = {}
    risk_items: list[NewsItem] = []
    for item in items:
        for topic in item.topics:
            topic_counts[topic] = topic_counts.get(topic, 0) + 1
        if any(topic in RISK_KEYWORDS for topic in item.topics):
            risk_items.append(item)

    top_topics = sorted(
        topic_counts.items(),
        key=lambda entry: entry[1],
        reverse=True,
    )[:5]
    return {
        "top_topics": top_topics,
        "risk_items": risk_items[:5],
        "headline_items": items[:8],
    }


def format_news_scan(items: list[NewsItem]) -> str:
    if not items:
        return "新闻扫描完成，但最近没有抓到可用新闻。"
    summary = summarize_news(items)
    topic_text = (
        "，".join(f"{topic}: {count}" for topic, count in summary["top_topics"])
        if summary["top_topics"]
        else "暂无明显主题"
    )
    lines = [
        "新闻扫描结果",
        f"- 最近抓到新闻数量: {len(items)}",
        f"- 热点主题: {topic_text}",
        "- 最新标题:",
    ]
    for item in summary["headline_items"][:5]:
        published = datetime.fromtimestamp(item.published_at).strftime("%m-%d %H:%M")
        lines.append(f"  {published} [{item.source}] {item.title}")
    if summary["risk_items"]:
        lines.append("- 风险相关标题:")
        for item in summary["risk_items"][:3]:
            lines.append(f"  [{item.source}] {item.title}")
    return "\n".join(lines)


def detect_new_items(items: list[NewsItem], seen_ids: list[str]) -> list[NewsItem]:
    seen = set(seen_ids)
    return [item for item in items if item.item_id not in seen]


def build_news_state(existing_state: dict | None, items: list[NewsItem]) -> dict:
    state = dict(existing_state or {})
    state["seen_ids"] = [item.item_id for item in items[:200]]
    state["last_scan_at"] = int(time.time())
    return state


def _fetch_rss_source(
    source_name: str,
    source_url: str,
    timeout: int,
    max_items: int,
) -> list[NewsItem]:
    request = urllib.request.Request(
        source_url,
        headers={
            "User-Agent": "ai-crypto-monitor-mvp/1.0",
            "Accept": "application/rss+xml, application/xml, text/xml",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            content = response.read()
    except urllib.error.URLError as exc:
        raise NewsFetchError(str(exc)) from exc

    items: list[NewsItem] = []
    xml_text = content.decode("utf-8", errors="ignore")
    item_blocks = re.findall(r"<item\b.*?>.*?</item>", xml_text, flags=re.IGNORECASE | re.DOTALL)
    if not item_blocks:
        raise NewsFetchError(f"Unexpected RSS format from {source_name}")
    for block in item_blocks[:max_items]:
        title = _clean_text(_extract_tag(block, "title"))
        link = _clean_text(_extract_tag(block, "link"))
        description = _clean_text(_extract_tag(block, "description"))
        pub_date_raw = _clean_text(_extract_tag(block, "pubDate"))
        if not title or not link:
            continue
        published_at = _parse_pub_date(pub_date_raw)
        item_id = _build_item_id(source_name, title, link)
        topics = _infer_topics(f"{title} {description}")
        items.append(
            NewsItem(
                source=source_name,
                title=title,
                link=link,
                published_at=published_at,
                summary=description,
                item_id=item_id,
                topics=topics,
            )
        )
    return items


def _clean_text(value: str) -> str:
    value = html.unescape(value)
    value = value.replace("<![CDATA[", "").replace("]]>", "")
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def _parse_pub_date(value: str) -> int:
    if not value:
        return int(time.time())
    try:
        return int(parsedate_to_datetime(value).timestamp())
    except (TypeError, ValueError, OverflowError):
        return int(time.time())


def _build_item_id(source_name: str, title: str, link: str) -> str:
    raw = json.dumps({"source": source_name, "title": title, "link": link}, sort_keys=True)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _infer_topics(text: str) -> list[str]:
    normalized = text.lower()
    topics: list[str] = []
    for topic, keywords in TOPIC_KEYWORDS.items():
        if any(keyword in normalized for keyword in keywords):
            topics.append(topic)
    return topics


def _extract_tag(block: str, tag_name: str) -> str:
    pattern = rf"<{tag_name}\b[^>]*>(.*?)</{tag_name}>"
    match = re.search(pattern, block, flags=re.IGNORECASE | re.DOTALL)
    if not match:
        return ""
    return match.group(1).strip()
