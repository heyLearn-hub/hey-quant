from __future__ import annotations

from quant_ai_system.action_summary import build_action_summary
from quant_ai_system.config import AccountConfig, RiskConfig
from quant_ai_system.portfolio import calculate_position_plan
from quant_ai_system.quality import QualityAssessment
from quant_ai_system.risk import RiskState
from quant_ai_system.signals import SignalResult
from quant_ai_system.supervisor import SupervisorDecision


def _signal(ticker: str) -> SignalResult:
    plan = calculate_position_plan(
        ticker=ticker,
        action="加仓候选",
        price=100,
        stop_price=90,
        score=85,
        account=AccountConfig(nav=20_000),
        risk=RiskConfig(target_weight_min=0.2, target_weight_max=0.2, risk_budget_min=0.02, risk_budget_max=0.02),
    )
    return SignalResult(
        ticker=ticker,
        as_of=None,  # type: ignore[arg-type]
        score=85,
        technical_score=85,
        quality=QualityAssessment(ticker, 85, "test", "manual"),
        action="加仓候选",
        close=100,
        reasons=[],
        risk=RiskState(ticker, 90, False, False, False, []),
        position=plan,
    )


def _review(ticker: str) -> SupervisorDecision:
    return SupervisorDecision(ticker, "approve_for_consideration", 85, "可考虑执行", "test", [], [], "local_rules")


def test_action_summary_splits_stocks_and_tactical_etfs() -> None:
    stock = _signal("MSFT")
    tactical = _signal("TQQQ")

    summary = build_action_summary(
        [stock, tactical],
        [_review("MSFT"), _review("TQQQ")],
        [],
        [],
        [],
        {"TQQQ"},
        max_core_positions=2,
    )

    assert [signal.ticker for signal in summary.stock_candidates] == ["MSFT"]
    assert [signal.ticker for signal in summary.tactical_candidates] == ["TQQQ"]
