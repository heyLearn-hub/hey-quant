from __future__ import annotations

from pathlib import Path

from quant_ai_system.backtest import run_backtest
from quant_ai_system.cli import main
from quant_ai_system.config import AccountConfig, BacktestConfig, RiskConfig, load_config
from quant_ai_system.data.providers import make_sample_market_data
from quant_ai_system.engine import run_system


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
    assert "核心 1-2 个持仓候选" in html
    assert "GPT / Supervisor 最终审查" in html
    assert "利润保护与退出规则" in html
    assert "完整观察池与 LOTS 仓位" in html
    assert "Public Equity 风险解释字段" in html
    assert len(result.signals) > 0


def test_cli_offline_run(tmp_path: Path) -> None:
    out = tmp_path / "cli_report.html"
    code = main(["run", "--config", "config/default.yaml", "--offline-sample", "--out", str(out)])
    assert code == 0
    assert out.exists()


def test_cli_data_check_missing_fmp_key(monkeypatch) -> None:
    monkeypatch.delenv("FMP_API_KEY", raising=False)
    code = main(["data-check", "--config", "config/default.yaml", "--provider", "fmp", "--tickers", "MSFT"])
    assert code == 1
