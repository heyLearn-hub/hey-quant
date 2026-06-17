from __future__ import annotations

import pandas as pd
import pytest

from quant_ai_system.config import RiskConfig
from quant_ai_system.exit_rules import evaluate_position_exit
from quant_ai_system.portfolio_store import StoredPosition


def test_profit_giveback_triggers_trim_candidate() -> None:
    dates = pd.date_range("2026-01-01", periods=6, freq="D")
    indicators = pd.DataFrame(
        {
            "close": [100, 120, 140, 132, 126, 123],
            "atr14": [4, 4, 4, 4, 4, 4],
            "ma50": [95, 100, 105, 110, 115, 118],
            "ma200": [80, 82, 84, 86, 88, 90],
            "rel20": [0.1, 0.1, 0.1, 0.04, -0.01, -0.02],
        },
        index=dates,
    )
    position = StoredPosition("NVDA", 10, 100, "2026-01-01", None, "", "open")

    review = evaluate_position_exit(position, indicators, RiskConfig())

    assert review.highest_pnl_pct == pytest.approx(0.4)
    assert review.profit_giveback_pct is not None
    assert review.profit_giveback_pct > RiskConfig().profit_giveback_trim
    assert "减仓" in review.action
    assert review.dynamic_stop is not None


def test_missing_market_data_requires_manual_review() -> None:
    position = StoredPosition("MSFT", 3, 400, "2026-01-01", 370, "", "open")

    review = evaluate_position_exit(position, None, RiskConfig())

    assert review.action == "人工复核"
    assert review.dynamic_stop == 370
    assert review.close is None
