from __future__ import annotations

import pandas as pd

from quant_ai_system.config import AccountConfig, RiskConfig
from quant_ai_system.data.providers import make_sample_market_data
from quant_ai_system.indicators import build_indicators
from quant_ai_system.quality import QualityAssessment
from quant_ai_system.signals import evaluate_signal, score_latest


def test_indicator_frame_contains_core_columns() -> None:
    data = make_sample_market_data(["NVDA", "QQQ"], years=2)
    frame = build_indicators(data.prices["NVDA"], data.prices["QQQ"])
    latest = frame.dropna().iloc[-1]
    for column in [
        "ma50",
        "ma200",
        "mom20",
        "mom60",
        "mom120",
        "rsi14",
        "atr14",
        "atr_pct",
        "rel20",
        "rel60",
        "trend_slope_50",
        "trend_slope_200",
        "dist_ma50",
        "dist_ma200",
        "realized_vol20",
        "realized_vol60",
        "risk_adjusted_mom60",
        "drawdown60",
        "drawdown120",
    ]:
        assert column in frame.columns
        assert pd.notna(latest[column])
    assert latest["realized_vol20"] > 0
    assert latest["atr_pct"] > 0
    assert latest["drawdown60"] <= 0
    assert latest["drawdown120"] <= 0


def test_signal_evaluation_returns_position_and_risk_language() -> None:
    data = make_sample_market_data(["NVDA", "QQQ"], years=2)
    frame = build_indicators(data.prices["NVDA"], data.prices["QQQ"])
    quality = QualityAssessment("NVDA", 84, "AI accelerator leadership", "buffett_quality")
    from quant_ai_system.config import QualityConfig

    signal = evaluate_signal("NVDA", frame, AccountConfig(nav=100_000), RiskConfig(), quality, QualityConfig())

    assert signal is not None
    assert 0 <= signal.score <= 100
    assert signal.position.ticker == "NVDA"
    assert signal.position.initial_shares >= 0
    assert signal.position.intended_alpha
    assert signal.position.unwanted_risk
    assert signal.position.retained_exposure
    assert signal.position.liquidity_exit_posture
    assert signal.quality.score == 84


def test_score_latest_rewards_trend_momentum_and_relative_strength() -> None:
    row = pd.Series(
        {
            "close": 120,
            "ma50": 100,
            "ma200": 90,
            "mom20": 0.08,
            "mom60": 0.15,
            "rsi14": 60,
            "volume": 120,
            "volume_ma20": 100,
            "rel20": 0.03,
            "rel60": 0.06,
        }
    )
    score, reasons = score_latest(row)
    assert score == 100
    assert "价格高于50日线" in reasons
    assert "60日相对强度跑赢基准" in reasons
