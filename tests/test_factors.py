from __future__ import annotations

from pathlib import Path

from quant_ai_system.data.providers import make_sample_market_data
from quant_ai_system.factors import run_factor_experiment, write_factor_report


def test_factor_experiment_writes_report(tmp_path: Path) -> None:
    data = make_sample_market_data(["MSFT", "NVDA", "QQQ"], years=3)
    metrics, raw = run_factor_experiment(data.prices, ["MSFT", "NVDA"], "QQQ", forward_days=20)
    out = write_factor_report(metrics, tmp_path / "factor.html")

    assert metrics
    assert not raw.empty
    assert out.exists()
    assert "因子实验报告" in out.read_text(encoding="utf-8")

