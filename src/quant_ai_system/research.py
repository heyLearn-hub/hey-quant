from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
import json
import os
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen

from quant_ai_system.config import ResearchConfig


@dataclass(frozen=True)
class SerenityAlphaHypothesis:
    ticker: str
    observed_demand_change: str
    financial_transmission: str
    validation_metrics: list[str] = field(default_factory=list)
    falsification_condition: str = ""


def blank_research_hypothesis(ticker: str) -> SerenityAlphaHypothesis:
    return SerenityAlphaHypothesis(
        ticker=ticker,
        observed_demand_change="待输入新闻、财报电话会或供应链证据；无证据时仅保留观察。",
        financial_transmission="待映射到收入、毛利、经营杠杆或现金流项目。",
        validation_metrics=["收入增速/指引", "毛利率或产品组合", "订单/库存/产能利用率", "管理层主动提及需求驱动"],
        falsification_condition="若未来1-4个季度没有财务验证，降级为观察或移出股票池。",
    )


@dataclass(frozen=True)
class NewsItem:
    ticker: str
    title: str
    published_at: str
    site: str
    url: str
    text: str = ""


@dataclass(frozen=True)
class NewsBrief:
    ticker: str
    article_count: int
    latest_at: str | None
    headlines: list[str]
    catalyst_flags: list[str]
    risk_flags: list[str]
    summary: str
    provider: str = "fmp"
    data_issue: str = ""


_CATALYST_KEYWORDS = {
    "ai": "AI",
    "artificial intelligence": "AI",
    "data center": "data center",
    "accelerator": "accelerator",
    "gpu": "GPU",
    "cloud": "cloud",
    "partnership": "partnership",
    "collaboration": "partnership",
    "contract": "order/contract",
    "order": "order/contract",
    "upgrade": "analyst upgrade",
    "raises guidance": "guidance raise",
    "raises forecast": "guidance raise",
    "beat": "earnings beat",
    "beats": "earnings beat",
    "record revenue": "revenue strength",
    "buyback": "capital return",
}

_RISK_KEYWORDS = {
    "downgrade": "analyst downgrade",
    "cuts guidance": "guidance cut",
    "cuts forecast": "guidance cut",
    "miss": "earnings miss",
    "misses": "earnings miss",
    "investigation": "investigation",
    "probe": "investigation",
    "lawsuit": "lawsuit",
    "antitrust": "antitrust",
    "export control": "export control",
    "ban": "ban/restriction",
    "restriction": "ban/restriction",
    "delay": "delay",
    "recall": "recall",
    "accounting": "accounting risk",
    "fraud": "fraud",
    "tariff": "tariff",
    "margin pressure": "margin pressure",
    "competition": "competition",
    "bad news": "headline risk",
    "under pressure": "headline risk",
    "warning": "warning",
    "concern": "concern",
    "concerns": "concern",
    "slump": "price weakness",
    "plunge": "price weakness",
}


def _extract_ticker(raw: dict, requested: set[str]) -> str:
    candidates = [raw.get("symbol"), raw.get("ticker"), raw.get("tickers"), raw.get("symbols")]
    for value in candidates:
        if isinstance(value, str):
            parts = [part.strip().upper() for part in value.replace(";", ",").split(",") if part.strip()]
            for part in parts:
                if part in requested:
                    return part
        elif isinstance(value, list):
            for part in value:
                ticker = str(part).strip().upper()
                if ticker in requested:
                    return ticker
    return ""


def _normalize_fmp_news(raw_items: list[dict], tickers: list[str]) -> list[NewsItem]:
    requested = set(tickers)
    items: list[NewsItem] = []
    for raw in raw_items:
        ticker = _extract_ticker(raw, requested)
        if not ticker:
            continue
        title = str(raw.get("title") or "").strip()
        if not title:
            continue
        items.append(
            NewsItem(
                ticker=ticker,
                title=title,
                published_at=str(raw.get("publishedDate") or raw.get("date") or "").strip(),
                site=str(raw.get("site") or raw.get("publisher") or "").strip(),
                url=str(raw.get("url") or raw.get("link") or "").strip(),
                text=str(raw.get("text") or raw.get("content") or "").strip(),
            )
        )
    return items


def fetch_fmp_stock_news(tickers: list[str], config: ResearchConfig) -> tuple[list[NewsItem], str]:
    tickers = list(dict.fromkeys(ticker.strip().upper() for ticker in tickers if ticker.strip()))
    if not tickers:
        return [], ""
    api_key = os.environ.get(config.news_api_key_env, "").strip()
    if not api_key:
        return [], f"{config.news_api_key_env} is not configured"

    limit = max(1, min(len(tickers) * max(config.news_limit_per_ticker, 1), 100))
    params = urlencode({"symbols": ",".join(tickers), "limit": limit, "apikey": api_key})
    url = f"https://financialmodelingprep.com/stable/news/stock?{params}"
    try:
        with urlopen(url, timeout=25) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:  # pragma: no cover - remote service
        fallback_params = urlencode({"tickers": ",".join(tickers), "limit": limit, "apikey": api_key})
        fallback_url = f"https://financialmodelingprep.com/api/v3/stock_news?{fallback_params}"
        try:
            with urlopen(fallback_url, timeout=25) as response:
                data = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, OSError) as fallback_exc:  # pragma: no cover - remote service
            return [], f"FMP news download failed: {fallback_exc or exc}"

    if isinstance(data, dict) and data.get("Error Message"):
        return [], str(data.get("Error Message"))
    if not isinstance(data, list):
        return [], "FMP news returned an unsupported payload"
    return _normalize_fmp_news(data, tickers), ""


def _flags(text: str, dictionary: dict[str, str]) -> list[str]:
    lowered = text.lower()
    labels: list[str] = []
    for keyword, label in dictionary.items():
        if keyword in lowered and label not in labels:
            labels.append(label)
    return labels


def _within_lookback(item: NewsItem, now: datetime, lookback_days: int) -> bool:
    if lookback_days <= 0 or not item.published_at:
        return True
    raw = item.published_at.replace("Z", "+00:00")
    try:
        published = datetime.fromisoformat(raw)
    except ValueError:
        return True
    if published.tzinfo is None:
        published = published.replace(tzinfo=UTC)
    return published >= now - timedelta(days=lookback_days)


def build_news_briefs(tickers: list[str], config: ResearchConfig) -> list[NewsBrief]:
    tickers = list(dict.fromkeys(ticker.strip().upper() for ticker in tickers if ticker.strip()))[: config.news_max_tickers]
    if not config.enabled or config.news_provider.lower() != "fmp":
        return []
    items, issue = fetch_fmp_stock_news(tickers, config)
    now = datetime.now(tz=UTC)
    grouped: dict[str, list[NewsItem]] = {ticker: [] for ticker in tickers}
    for item in items:
        if item.ticker in grouped and _within_lookback(item, now, config.news_lookback_days):
            grouped[item.ticker].append(item)

    briefs: list[NewsBrief] = []
    for ticker in tickers:
        group = grouped.get(ticker, [])[: max(config.news_limit_per_ticker, 1)]
        text_blob = " ".join([item.title + " " + item.text for item in group])
        catalysts = _flags(text_blob, _CATALYST_KEYWORDS)
        risks = _flags(text_blob, _RISK_KEYWORDS)
        headlines = [item.title for item in group[: config.news_limit_per_ticker]]
        if group:
            parts = [f"{len(group)} articles"]
            if catalysts:
                parts.append("catalyst: " + ", ".join(catalysts[:4]))
            if risks:
                parts.append("risk: " + ", ".join(risks[:4]))
            summary = "; ".join(parts)
            latest_at = group[0].published_at or None
        else:
            summary = issue or "no recent FMP stock news in configured lookback"
            latest_at = None
        briefs.append(
            NewsBrief(
                ticker=ticker,
                article_count=len(group),
                latest_at=latest_at,
                headlines=headlines,
                catalyst_flags=catalysts[:6],
                risk_flags=risks[:6],
                summary=summary,
                data_issue=issue if not group else "",
            )
        )
    return briefs
