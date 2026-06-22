from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pandas as pd

from quant_ai_system.cli import main
from quant_ai_system.config import load_config
from quant_ai_system.data.providers import ProviderCheck
from quant_ai_system.data_quality import (
    collect_data_quality_universe,
    data_quality_exit_code,
    evaluate_data_quality,
    write_data_quality_report,
)
from quant_ai_system.portfolio_store import upsert_position, upsert_symbol_alias


def _check(ticker: str, ok: bool = True, rows: int = 260, message: str = "ok") -> ProviderCheck:
    if not ok:
        return ProviderCheck(ticker, "fmp", rows, None, None, None, False, message)
    return ProviderCheck(
        ticker=ticker,
        provider="fmp",
        rows=rows,
        first_date=pd.Timestamp("2025-01-02", tz="UTC"),
        last_date=pd.Timestamp("2026-06-19", tz="UTC"),
        latest_close=123.45,
        ok=True,
        message=message,
    )


def test_open_positions_are_included_even_when_not_in_universe(tmp_path: Path, monkeypatch) -> None:
    config = load_config("config/default.yaml")
    db = tmp_path / "portfolio.sqlite3"
    upsert_position(db, "XYZ", 10, 50, 45, "outside universe")
    config = replace(config, storage=replace(config.storage, db_path=str(db)))

    seen: list[str] = []

    def fake_check(tickers, provider, data_config):
        seen.extend(tickers)
        return [_check(ticker) for ticker in tickers]

    monkeypatch.setattr("quant_ai_system.data_quality.check_provider_data", fake_check)

    report = evaluate_data_quality(config)

    xyz = next(record for record in report.records if record.ticker == "XYZ")
    assert "XYZ" in seen
    assert xyz.roles == ("open_position",)
    assert xyz.status == "tradable"
    assert xyz.retained_exposure


def test_alias_uses_data_symbol_for_provider_check_but_preserves_broker_symbol(tmp_path: Path, monkeypatch) -> None:
    config = load_config("config/default.yaml")
    db = tmp_path / "portfolio.sqlite3"
    upsert_position(db, "SNXX", 10, 100, 90, "broker symbol")
    upsert_symbol_alias(db, "SNXX", "NVDA", "broker alias")
    config = replace(config, storage=replace(config.storage, db_path=str(db)))

    requested: list[str] = []

    def fake_check(tickers, provider, data_config):
        requested.extend(tickers)
        return [_check(ticker) for ticker in tickers]

    monkeypatch.setattr("quant_ai_system.data_quality.check_provider_data", fake_check)

    report = evaluate_data_quality(config)
    record = next(item for item in report.records if item.ticker == "SNXX")

    assert "NVDA" in requested
    assert record.ticker == "SNXX"
    assert record.data_symbol == "NVDA"
    assert record.alias_status == "mapped"
    assert record.status == "tradable"


def test_missing_open_position_data_requires_data_fix(tmp_path: Path, monkeypatch) -> None:
    config = load_config("config/default.yaml")
    db = tmp_path / "portfolio.sqlite3"
    upsert_position(db, "AAOX", 20, 8, 7, "manual position")
    config = replace(config, storage=replace(config.storage, db_path=str(db)))

    def fake_check(tickers, provider, data_config):
        return [_check(ticker, ok=False, rows=0, message="download returned no usable rows") for ticker in tickers]

    monkeypatch.setattr("quant_ai_system.data_quality.check_provider_data", fake_check)

    report = evaluate_data_quality(config)
    record = next(item for item in report.records if item.ticker == "AAOX")

    assert record.status == "data_fix_required"
    assert "alias" in record.action.lower()
    assert "open position" in record.binding_constraint.lower()
    assert data_quality_exit_code(report) == 1


def test_non_held_missing_universe_ticker_is_blocked(tmp_path: Path, monkeypatch) -> None:
    config = load_config("config/default.yaml")
    config = replace(config, storage=replace(config.storage, db_path=str(tmp_path / "portfolio.sqlite3")))

    def fake_check(tickers, provider, data_config):
        return [_check(ticker, ok=False, rows=0, message="FMP_API_KEY is not configured") for ticker in tickers]

    monkeypatch.setattr("quant_ai_system.data_quality.check_provider_data", fake_check)

    report = evaluate_data_quality(config)
    nvda = next(item for item in report.records if item.ticker == "NVDA")

    assert nvda.status == "blocked"
    assert "block" in nvda.action.lower()
    assert data_quality_exit_code(report) == 1


def test_benchmarks_and_leveraged_etfs_are_classified_separately(tmp_path: Path) -> None:
    config = load_config("config/default.yaml")
    config = replace(
        config,
        storage=replace(config.storage, db_path=str(tmp_path / "portfolio.sqlite3")),
        universe=replace(config.universe, leveraged_tickers=["SOXL"], tactical_tickers=["SOXL"], benchmarks=["QQQ", "SMH"]),
    )

    targets = collect_data_quality_universe(config)
    by_ticker = {item.ticker: item for item in targets}

    assert by_ticker["QQQ"].asset_class == "benchmark"
    assert by_ticker["SOXL"].asset_class == "leveraged_etf"
    assert "benchmark" in by_ticker["SMH"].roles
    assert "leveraged_etf" in by_ticker["SOXL"].roles


def test_missing_fmp_key_creates_explicit_provider_failure_records(tmp_path: Path, monkeypatch) -> None:
    config = load_config("config/default.yaml")
    db = tmp_path / "portfolio.sqlite3"
    upsert_position(db, "LNOK", 10, 25, 22, "manual position")
    config = replace(config, storage=replace(config.storage, db_path=str(db)))

    def fake_check(tickers, provider, data_config):
        return [_check(ticker, ok=False, rows=0, message="FMP_API_KEY is not configured") for ticker in tickers]

    monkeypatch.setattr("quant_ai_system.data_quality.check_provider_data", fake_check)

    report = evaluate_data_quality(config)

    assert all("FMP_API_KEY" in item.provider_message for item in report.records)
    assert next(item for item in report.records if item.ticker == "LNOK").status == "data_fix_required"


def test_cli_returns_non_zero_when_open_positions_have_blocking_data_issue(tmp_path: Path, monkeypatch) -> None:
    config = load_config("config/default.yaml")
    db = tmp_path / "portfolio.sqlite3"
    upsert_position(db, "MUU", 10, 35, 30, "manual position")
    config = replace(config, storage=replace(config.storage, db_path=str(db)))

    def fake_load_config(path):
        return config

    def fake_check(tickers, provider, data_config):
        return [_check(ticker, ok=False, rows=0, message="download returned no usable rows") for ticker in tickers]

    monkeypatch.setattr("quant_ai_system.cli.load_config", fake_load_config)
    monkeypatch.setattr("quant_ai_system.data_quality.check_provider_data", fake_check)

    code = main(["data-quality", "--config", "ignored.yaml", "--out", str(tmp_path / "dq.html")])

    assert code == 1
    assert (tmp_path / "dq.html").exists()


def test_html_report_includes_blockers_alias_guidance_and_risk_fields(tmp_path: Path, monkeypatch) -> None:
    config = load_config("config/default.yaml")
    db = tmp_path / "portfolio.sqlite3"
    upsert_position(db, "SNXX", 10, 100, 90, "needs alias")
    config = replace(config, storage=replace(config.storage, db_path=str(db)))

    def fake_check(tickers, provider, data_config):
        return [_check(ticker, ok=False, rows=0, message="download returned no usable rows") for ticker in tickers]

    monkeypatch.setattr("quant_ai_system.data_quality.check_provider_data", fake_check)

    report = evaluate_data_quality(config)
    out = write_data_quality_report(report, tmp_path / "data_quality.html")
    html = out.read_text(encoding="utf-8")

    assert "Data Quality Report" in html
    assert "SNXX" in html
    assert "alias" in html.lower()
    assert "intended alpha" in html.lower()
    assert "unwanted risk" in html.lower()
    assert "liquidity/exit posture" in html.lower()
    assert "blocked tickers cannot support buy/add signals" in html.lower()
