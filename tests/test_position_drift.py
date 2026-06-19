from __future__ import annotations

from quant_ai_system.config import AccountConfig, RiskConfig
from quant_ai_system.position_drift import evaluate_position_drift
from quant_ai_system.portfolio import calculate_position_plan
from quant_ai_system.portfolio_store import StoredPosition
from quant_ai_system.quality import QualityAssessment
from quant_ai_system.risk import RiskState
from quant_ai_system.signals import SignalResult


def _signal() -> SignalResult:
    risk = RiskConfig(target_weight_min=0.20, target_weight_max=0.20, risk_budget_min=0.02, risk_budget_max=0.02)
    plan = calculate_position_plan(
        ticker="NVDA",
        action="小仓候选",
        price=100,
        stop_price=90,
        score=70,
        account=AccountConfig(nav=10_000),
        risk=risk,
    )
    return SignalResult(
        ticker="NVDA",
        as_of=None,  # type: ignore[arg-type]
        score=70,
        technical_score=70,
        quality=QualityAssessment("NVDA", 70, "test", "manual"),
        action="小仓候选",
        close=100,
        reasons=[],
        risk=RiskState("NVDA", 90, False, False, False, []),
        position=plan,
    )


def test_position_drift_flags_risk_budget_breach() -> None:
    position = StoredPosition("NVDA", 80, 80, "2026-01-01", None, "", "open")

    review = evaluate_position_drift(position, _signal(), None, AccountConfig(nav=10_000), RiskConfig())

    assert review.action == "严重超配/优先降风险"
    assert review.stop_loss_nav_pct == 0.08
    assert review.risk_budget_pct == 0.02
    assert any("风险预算" in note for note in review.notes)


def test_position_drift_handles_missing_signal() -> None:
    position = StoredPosition("XYZ", 10, 50, "2026-01-01", 45, "", "open")

    review = evaluate_position_drift(position, None, None, AccountConfig(nav=10_000), RiskConfig())

    assert review.action == "数据修复优先"
    assert review.lots_target_shares is None
    assert any("没有可用行情" in note for note in review.notes)
