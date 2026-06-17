from __future__ import annotations

from quant_ai_system.config import SupervisorConfig
import numpy as np
import pandas as pd

from quant_ai_system.data.providers import DataIssue
from quant_ai_system.indicators import build_indicators
from quant_ai_system.quality import QualityAssessment
from quant_ai_system.signals import evaluate_signal
from quant_ai_system.config import AccountConfig, QualityConfig, RiskConfig
from quant_ai_system.supervisor import local_supervisor_review


def _uptrend_frame() -> tuple[pd.DataFrame, pd.DataFrame]:
    dates = pd.bdate_range(end=pd.Timestamp("2026-06-12", tz="UTC"), periods=320)
    close = np.linspace(100, 210, len(dates))
    volume = np.full(len(dates), 2_000_000)
    volume[-1] = 3_000_000
    stock = pd.DataFrame(
        {
            "open": close * 0.995,
            "high": close * 1.01,
            "low": close * 0.99,
            "close": close,
            "volume": volume,
        },
        index=dates,
    )
    benchmark_close = np.linspace(100, 150, len(dates))
    benchmark = pd.DataFrame(
        {
            "open": benchmark_close,
            "high": benchmark_close * 1.005,
            "low": benchmark_close * 0.995,
            "close": benchmark_close,
            "volume": volume,
        },
        index=dates,
    )
    return stock, benchmark


def test_local_supervisor_blocks_sample_data_execution() -> None:
    stock, benchmark = _uptrend_frame()
    frame = build_indicators(stock, benchmark)
    signal = evaluate_signal(
        "MSFT",
        frame,
        AccountConfig(nav=17_870),
        RiskConfig(),
        QualityAssessment("MSFT", 92, "quality compounder", "buffett_quality"),
        QualityConfig(),
    )
    assert signal is not None

    reviews = local_supervisor_review(
        [signal],
        SupervisorConfig(min_approval_score=50),
        [DataIssue("*", "sample", "sample data")],
    )

    assert reviews[0].decision == "manual_review"
    assert "样本" in reviews[0].blockers[0]


def test_local_supervisor_can_approve_clean_high_score_signal() -> None:
    stock, benchmark = _uptrend_frame()
    frame = build_indicators(stock, benchmark)
    signal = evaluate_signal(
        "MSFT",
        frame,
        AccountConfig(nav=17_870),
        RiskConfig(),
        QualityAssessment("MSFT", 95, "quality compounder", "buffett_quality"),
        QualityConfig(technical_weight=0.0, quality_weight=1.0),
    )
    assert signal is not None

    reviews = local_supervisor_review([signal], SupervisorConfig(min_approval_score=70), [])

    assert reviews[0].decision in {"approve_for_consideration", "hold"}
    assert reviews[0].provider == "local_rules"
