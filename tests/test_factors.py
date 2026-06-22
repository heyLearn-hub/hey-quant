from __future__ import annotations

from pathlib import Path

from quant_ai_system.data.providers import make_sample_market_data
from quant_ai_system.factors import DEFAULT_FACTORS, FACTOR_REGISTRY, run_factor_experiment, write_factor_report


def test_factor_experiment_writes_report(tmp_path: Path) -> None:
    data = make_sample_market_data(["MSFT", "NVDA", "QQQ"], years=3)
    metrics, raw = run_factor_experiment(data.prices, ["MSFT", "NVDA"], "QQQ", forward_days=20)
    out = write_factor_report(metrics, tmp_path / "factor.html")
    html = out.read_text(encoding="utf-8")

    assert metrics
    assert not raw.empty
    assert out.exists()
    assert "因子实验报告" in html
    assert "因子注册表" in html
    assert "Momentum" in html
    assert "Volatility" in html
    assert "期权/情绪覆盖层暂缓" in html


def test_factor_registry_covers_default_factor_set() -> None:
    assert "mom120" in DEFAULT_FACTORS
    assert "risk_adjusted_mom60" in DEFAULT_FACTORS
    assert set(DEFAULT_FACTORS).issubset(FACTOR_REGISTRY)
    assert FACTOR_REGISTRY["mom120"].group == "Momentum"
    assert FACTOR_REGISTRY["realized_vol60"].production_use == "risk_control"
    assert "半导体" in FACTOR_REGISTRY["mom120"].sector_relevance


def test_factor_experiment_metrics_include_registry_metadata() -> None:
    data = make_sample_market_data(["MSFT", "NVDA", "QQQ"], years=3)
    metrics, raw = run_factor_experiment(data.prices, ["MSFT", "NVDA"], "QQQ", factors=["mom120", "realized_vol60"])

    assert {"mom120", "realized_vol60"}.issubset(raw.columns)
    by_factor = {metric.factor: metric for metric in metrics}
    assert by_factor["mom120"].group == "Momentum"
    assert by_factor["mom120"].production_use == "research_signal"
    assert by_factor["realized_vol60"].group == "Volatility"
    assert by_factor["realized_vol60"].production_use == "risk_control"
