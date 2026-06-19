from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
import hashlib
import json
import os
import threading
from pathlib import Path
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen

from quant_ai_system.config import AppConfig
from quant_ai_system.portfolio_store import (
    StoredPosition,
    get_data_symbol,
    insert_news_event,
    insert_monitor_alert,
    insert_pricing_snapshot,
    list_data_health,
    list_news_events,
    list_monitor_alerts,
    list_positions,
    list_pricing_snapshots,
    mark_news_event_pushed,
    upsert_data_health,
)
from quant_ai_system.research import NewsItem, _flags, _CATALYST_KEYWORDS, _RISK_KEYWORDS, fetch_fmp_stock_news


@dataclass(frozen=True)
class Quote:
    ticker: str
    data_symbol: str
    price: float
    change_pct: float | None
    provider: str = "fmp"
    session: str = "regular"


@dataclass(frozen=True)
class MonitorAlert:
    ticker: str
    priority: str
    category: str
    action: str
    message: str
    details: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class MonitorResult:
    alerts: list[MonitorAlert]
    checked_positions: int
    checked_news_tickers: int
    data_issues: list[str]


def _env_api_key(config: AppConfig) -> str:
    return os.environ.get(config.research.news_api_key_env, "").strip()


def _float(value: object) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_quote(raw: object, broker_symbol: str, data_symbol: str) -> Quote | None:
    item = raw[0] if isinstance(raw, list) and raw else raw
    if not isinstance(item, dict):
        return None
    price = _float(item.get("price") or item.get("bid") or item.get("lastSalePrice"))
    if price is None or price <= 0:
        return None
    change_pct = _float(item.get("changesPercentage") or item.get("changePercentage") or item.get("changePercent"))
    if change_pct is not None and abs(change_pct) > 1:
        change_pct = change_pct / 100
    return Quote(ticker=broker_symbol, data_symbol=data_symbol, price=price, change_pct=change_pct)


def fetch_fmp_quote(broker_symbol: str, data_symbol: str, config: AppConfig) -> tuple[Quote | None, str]:
    api_key = _env_api_key(config)
    if not api_key:
        return None, f"{config.research.news_api_key_env} is not configured"
    urls = [
        f"https://financialmodelingprep.com/stable/quote?{urlencode({'symbol': data_symbol, 'apikey': api_key})}",
        f"https://financialmodelingprep.com/api/v3/quote/{data_symbol}?{urlencode({'apikey': api_key})}",
    ]
    last_error = ""
    for url in urls:
        try:
            with urlopen(url, timeout=20) as response:
                parsed = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:  # pragma: no cover - remote service
            last_error = str(exc)
            continue
        quote = _normalize_quote(parsed, broker_symbol, data_symbol)
        if quote:
            return quote, ""
        last_error = "quote returned no usable price"
    return None, last_error or "quote download failed"


def evaluate_price_alert(position: StoredPosition, quote: Quote, config: AppConfig) -> MonitorAlert | None:
    pnl_pct = quote.price / position.average_cost - 1 if position.average_cost > 0 else None
    details = [
        f"当前价 {quote.price:.2f}",
        f"成本 {position.average_cost:.2f}",
        f"浮盈亏 {pnl_pct * 100:.1f}%" if pnl_pct is not None else "浮盈亏无法计算",
    ]
    if position.current_stop is not None:
        details.append(f"止损 {position.current_stop:.2f}")
        if quote.price <= position.current_stop:
            return MonitorAlert(position.ticker, "urgent", "price", "exit_candidate", "跌破手动止损价", details)
        near_line = position.current_stop * (1 + config.monitor.stop_near_pct)
        if quote.price <= near_line:
            return MonitorAlert(position.ticker, "high", "price", "trim_candidate", "接近手动止损价", details)
    if quote.change_pct is not None and quote.change_pct <= -config.monitor.large_drop_pct:
        return MonitorAlert(position.ticker, "high", "price", "risk_review", "价格出现大幅下跌", details + [f"变动 {quote.change_pct * 100:.1f}%"])
    return None


def _event_key(item: NewsItem) -> str:
    raw = item.url or f"{item.ticker}|{item.published_at}|{item.title}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _alert_key(alert: MonitorAlert) -> str:
    raw = f"{alert.ticker}|{alert.category}|{alert.action}|{alert.message}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def classify_news_priority(item: NewsItem) -> tuple[str, list[str]]:
    text = f"{item.title} {item.text}"
    risks = _flags(text, _RISK_KEYWORDS)
    catalysts = _flags(text, _CATALYST_KEYWORDS)
    if risks:
        return "high", risks
    if any(flag in catalysts for flag in ["guidance raise", "earnings beat", "order/contract", "AI", "data center"]):
        return "medium", catalysts
    return "low", catalysts


def run_monitor_once(config: AppConfig, *, send_text: Callable[[str], None] | None = None) -> MonitorResult:
    db_path = Path(config.storage.db_path)
    alerts: list[MonitorAlert] = []
    data_issues: list[str] = []
    positions = list_positions(db_path)
    for position in positions:
        data_symbol = get_data_symbol(db_path, position.ticker)
        quote, issue = fetch_fmp_quote(position.ticker, data_symbol, config)
        if quote is None:
            message = f"{position.ticker}: FMP quote unavailable for {data_symbol}; 需要添加 alias 或确认数据源覆盖 ({issue})"
            upsert_data_health(db_path, position.ticker, "price", "fmp", False, message)
            data_issues.append(message)
            alert = MonitorAlert(position.ticker, "high", "data", "data_fix_required", "需要添加 alias 或确认数据源覆盖", [message])
            if insert_monitor_alert(db_path, _alert_key(alert), alert.ticker, alert.category, alert.priority, alert.message):
                alerts.append(alert)
            continue
        insert_pricing_snapshot(db_path, position.ticker, data_symbol, "fmp", quote.price, quote.change_pct, quote.session)
        upsert_data_health(db_path, position.ticker, "price", "fmp", True, f"ok {quote.price:.2f}")
        alert = evaluate_price_alert(position, quote, config)
        if alert and insert_monitor_alert(db_path, _alert_key(alert), alert.ticker, alert.category, alert.priority, alert.message):
            alerts.append(alert)

    news_tickers = list(dict.fromkeys([position.ticker for position in positions] + config.universe.tickers + config.universe.leveraged_tickers + config.universe.tactical_tickers))[: config.research.news_max_tickers]
    data_symbols = [get_data_symbol(db_path, ticker) for ticker in news_tickers]
    news_items, news_issue = fetch_fmp_stock_news(data_symbols, config.research)
    if news_issue:
        upsert_data_health(db_path, "*", "news", "fmp", False, news_issue)
        data_issues.append(news_issue)
    else:
        upsert_data_health(db_path, "*", "news", "fmp", True, f"ok {len(news_items)} items")
    reverse_alias = {get_data_symbol(db_path, ticker): ticker for ticker in news_tickers}
    for item in news_items:
        broker_ticker = reverse_alias.get(item.ticker, item.ticker)
        priority, flags = classify_news_priority(item)
        event_key = _event_key(item)
        inserted = insert_news_event(db_path, event_key, broker_ticker, item.title, item.url, item.published_at, priority, pushed=False)
        if inserted and priority in {"urgent", "high"}:
            details = flags[:4]
            if config.monitor.ai_review_enabled:
                details.append("AI复核队列: 规则预筛为高价值；AI失败时按规则降级")
            alert = MonitorAlert(broker_ticker, priority, "news", "news_review", item.title, details)
            alerts.append(alert)
            mark_news_event_pushed(db_path, event_key)

    push_alerts = alerts[: config.monitor.max_pushes_per_session]
    if send_text:
        for alert in push_alerts:
            send_text(format_monitor_alert(alert))
    return MonitorResult(alerts=alerts, checked_positions=len(positions), checked_news_tickers=len(news_tickers), data_issues=data_issues)


def format_monitor_alert(alert: MonitorAlert) -> str:
    lines = [f"Quant AI Monitor · {alert.priority.upper()}", f"{alert.ticker}: {alert.message}", f"动作: {alert.action}"]
    lines.extend(f"- {detail}" for detail in alert.details)
    return "\n".join(lines)


def format_monitor_status(config: AppConfig) -> str:
    db_path = Path(config.storage.db_path)
    health = list_data_health(db_path, limit=8)
    prices = list_pricing_snapshots(db_path, limit=5)
    news = list_news_events(db_path, limit=5)
    alerts = list_monitor_alerts(db_path, limit=5)
    lines = ["Monitor status", "Data health:"]
    lines.extend(f"- {item.ticker}/{item.check_type}/{item.provider}: {'OK' if item.ok else 'CHECK'} {item.message}" for item in health)
    lines.append("Pricing:")
    lines.extend(f"- {item.ticker}: {item.price:.2f} ({item.provider}, {item.checked_at})" for item in prices)
    lines.append("News:")
    lines.extend(f"- {item.ticker}: {item.priority} {item.title}" for item in news)
    lines.append("Alerts:")
    lines.extend(f"- {item.ticker}: {item.priority} {item.category} {item.message}" for item in alerts)
    return "\n".join(lines)


class MonitorListener:
    def __init__(self, config: AppConfig, send_text: Callable[[str], None] | None = None) -> None:
        self.config = config
        self.send_text = send_text
        minutes = min(config.monitor.price_check_interval_minutes, config.monitor.news_check_interval_minutes)
        self.interval_seconds = max(60.0, minutes * 60)
        self._stop = threading.Event()
        self.thread = threading.Thread(target=self._run, name="quant-monitor-listener", daemon=True)

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                run_monitor_once(self.config, send_text=self.send_text)
            except Exception:
                pass
            self._stop.wait(self.interval_seconds)
