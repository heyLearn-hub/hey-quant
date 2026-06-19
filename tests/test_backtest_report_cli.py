from __future__ import annotations

from pathlib import Path
from dataclasses import replace

from quant_ai_system.backtest import run_backtest
from quant_ai_system.cli import main
from quant_ai_system.config import AccountConfig, BacktestConfig, RiskConfig, load_config
from quant_ai_system.data.providers import make_sample_market_data
from quant_ai_system.engine import run_system
from quant_ai_system.portfolio_store import upsert_position, upsert_symbol_alias


def test_backtest_materializes_three_strategy_metrics() -> None:
    data = make_sample_market_data(["NVDA", "AMD", "QQQ"], years=3)
    result = run_backtest(
        prices=data.prices,
        tickers=["NVDA", "AMD"],
        benchmark_ticker="QQQ",
        account=AccountConfig(nav=100_000),
        risk=RiskConfig(),
        config=BacktestConfig(initial_cash=100_000, max_positions=2),
    )
    assert {metric.strategy for metric in result.metrics} == {"trend", "trend_relative", "full_system"}
    assert not result.equity_curves.empty


def test_run_system_writes_html_report(tmp_path: Path) -> None:
    config = load_config("config/default.yaml")
    report_path = tmp_path / "report.html"
    result = run_system(config, report_path, offline_sample=True)
    html = report_path.read_text(encoding="utf-8")
    assert result.report_path == report_path
    assert "今日行动面板" in html
    assert "核心 1-2 个持仓候选" in html
    assert "GPT / Supervisor 最终审查" in html
    assert "真实仓位 vs LOTS" in html
    assert "利润保护与退出规则" in html
    assert "FMP 新闻面 / 研究线索" in html
    assert "完整观察池与 LOTS 仓位" in html
    assert "Public Equity 风险解释字段" in html
    assert len(result.signals) > 0


def test_open_positions_are_added_to_market_data_without_becoming_buy_candidates(tmp_path: Path) -> None:
    config = load_config("config/default.yaml")
    db = tmp_path / "portfolio.sqlite3"
    upsert_position(db, "XYZ", 10, 50, 45, "outside universe")
    config = replace(config, storage=replace(config.storage, db_path=str(db)))

    result = run_system(config, tmp_path / "report.html", offline_sample=True)

    assert "XYZ" in result.market_data.prices
    assert "XYZ" not in {signal.ticker for signal in result.signals}
    assert result.positions[0].ticker == "XYZ"


def test_symbol_alias_uses_data_symbol_but_keeps_broker_symbol_in_positions(tmp_path: Path) -> None:
    config = load_config("config/default.yaml")
    db = tmp_path / "portfolio.sqlite3"
    upsert_position(db, "SNXX", 10, 100, 90, "broker symbol")
    upsert_symbol_alias(db, "SNXX", "NVDA", "alias")
    config = replace(config, storage=replace(config.storage, db_path=str(db)))

    result = run_system(config, tmp_path / "report.html", offline_sample=True)

    assert "SNXX" in result.market_data.prices
    assert result.positions[0].ticker == "SNXX"
    assert "SNXX" not in {signal.ticker for signal in result.signals}
    assert result.exit_reviews[0].ticker == "SNXX"
    assert result.exit_reviews[0].close is not None


def test_cli_offline_run(tmp_path: Path) -> None:
    out = tmp_path / "cli_report.html"
    code = main(["run", "--config", "config/default.yaml", "--offline-sample", "--out", str(out)])
    assert code == 0
    assert out.exists()


def test_cli_data_check_missing_fmp_key(monkeypatch) -> None:
    monkeypatch.delenv("FMP_API_KEY", raising=False)
    code = main(["data-check", "--config", "config/default.yaml", "--provider", "fmp", "--tickers", "MSFT"])
    assert code == 1
