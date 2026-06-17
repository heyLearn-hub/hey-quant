from __future__ import annotations

import pandas as pd

from quant_ai_system.config import AccountConfig, RiskConfig
from quant_ai_system.portfolio import calculate_position_plan
from quant_ai_system.risk import evaluate_portfolio_drawdown, evaluate_security_risk


def test_lots_uses_tighter_risk_budget_constraint() -> None:
    plan = calculate_position_plan(
        ticker="NVDA",
        action="小仓候选",
        price=100,
        stop_price=70,
        score=70,
        account=AccountConfig(nav=100_000, fractional_shares=False),
        risk=RiskConfig(),
    )
    assert plan.max_risk_shares == 55
    assert plan.target_shares == 55
    assert plan.binding_constraint == "risk_budget"


def test_exit_trigger_when_price_breaks_200dma() -> None:
    latest = pd.Series({"close": 80, "ma50": 90, "ma200": 100, "atr14": 4, "rel20": -0.04})
    state = evaluate_security_risk("AMD", latest, RiskConfig(), score=35)
    assert state.exit_trigger is True
    assert state.trim_trigger is True
    assert state.signal_decay is True
    assert state.stop_price < 80


def test_portfolio_drawdown_modes() -> None:
    equity = pd.Series([100, 110, 105, 96.5])
    state = evaluate_portfolio_drawdown(equity, RiskConfig())
    assert state.mode == "defensive"
    assert state.new_positions_allowed is False
