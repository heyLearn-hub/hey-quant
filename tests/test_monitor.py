from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from quant_ai_system.config import load_config
from quant_ai_system.monitor import Quote, evaluate_price_alert, run_monitor_once
from quant_ai_system.portfolio_store import StoredPosition, list_data_health, list_news_events, list_pricing_snapshots, upsert_position, upsert_symbol_alias
from quant_ai_system.research import NewsItem


def _config(tmp_path: Path):
    config = load_config("config/default.yaml")
    return replace(config, storage=replace(config.storage, db_path=str(tmp_path / "portfolio.sqlite3")))


def test_price_watch_triggers_stop_alert(tmp_path: Path) -> None:
    config = _config(tmp_path)
    position = StoredPosition("MSFT", 2, 400, "2026-01-01", 380, "", "open")
    quote = Quote("MSFT", "MSFT", 379, -0.02)

    alert = evaluate_price_alert(position, quote, config)

    assert alert is not None
    assert alert.priority == "urgent"
    assert alert.action == "exit_candidate"


def test_monitor_once_records_alias_pricing_snapshot(tmp_path: Path, monkeypatch) -> None:
    config = _config(tmp_path)
    db = Path(config.storage.db_path)
    upsert_position(db, "SNXX", 2, 100, 90, "alias position")
    upsert_symbol_alias(db, "SNXX", "NVDA", "broker alias")

    def fake_quote(broker_symbol, data_symbol, config):
        assert broker_symbol == "SNXX"
        assert data_symbol == "NVDA"
        return Quote("SNXX", "NVDA", 95, -0.01), ""

    monkeypatch.setattr("quant_ai_system.monitor.fetch_fmp_quote", fake_quote)
    monkeypatch.setattr("quant_ai_system.monitor.fetch_fmp_stock_news", lambda tickers, config: ([], ""))

    result = run_monitor_once(config)

    assert result.checked_positions == 1
    snapshot = list_pricing_snapshots(db)[0]
    assert snapshot.ticker == "SNXX"
    assert snapshot.data_symbol == "NVDA"


def test_monitor_once_marks_missing_quote_as_data_health(tmp_path: Path, monkeypatch) -> None:
    config = _config(tmp_path)
    db = Path(config.storage.db_path)
    upsert_position(db, "AAOX", 1, 50, None, "unknown symbol")
    monkeypatch.setattr("quant_ai_system.monitor.fetch_fmp_quote", lambda broker, data, config: (None, "no data"))
    monkeypatch.setattr("quant_ai_system.monitor.fetch_fmp_stock_news", lambda tickers, config: ([], "missing key"))

    result = run_monitor_once(config)
    second = run_monitor_once(config)

    assert result.alerts[0].action == "data_fix_required"
    assert second.alerts == []
    assert any(not item.ok and item.ticker == "AAOX" for item in list_data_health(db))


def test_news_watch_dedupes_and_flags_high_value_news(tmp_path: Path, monkeypatch) -> None:
    config = _config(tmp_path)
    db = Path(config.storage.db_path)
    item = NewsItem("MSFT", "Microsoft faces antitrust investigation", "2026-06-19T12:00:00Z", "Example", "https://example.com/msft")
    monkeypatch.setattr("quant_ai_system.monitor.fetch_fmp_quote", lambda broker, data, config: (None, "no positions"))
    monkeypatch.setattr("quant_ai_system.monitor.fetch_fmp_stock_news", lambda tickers, config: ([item], ""))

    first = run_monitor_once(config)
    second = run_monitor_once(config)

    assert [alert for alert in first.alerts if alert.category == "news"]
    assert not [alert for alert in second.alerts if alert.category == "news"]
    events = list_news_events(db)
    assert len(events) == 1
    assert events[0].priority == "high"
    assert events[0].pushed is True
