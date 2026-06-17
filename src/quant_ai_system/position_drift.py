from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from quant_ai_system.config import AccountConfig, RiskConfig
from quant_ai_system.exit_rules import PositionExitReview
from quant_ai_system.portfolio_store import StoredPosition
from quant_ai_system.signals import SignalResult


@dataclass(frozen=True)
class PositionDriftReview:
    ticker: str
    actual_shares: float
    lots_target_shares: float | None
    lots_initial_shares: float | None
    actual_value: float | None
    actual_weight: float | None
    target_weight: float | None
    drift_shares: float | None
    drift_pct: float | None
    stop_loss_amount: float | None
    stop_loss_nav_pct: float | None
    risk_budget_pct: float | None
    action: str
    severity: int
    notes: list[str]


def _safe_float(value: object) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if isfinite(result) else None


def evaluate_position_drift(
    position: StoredPosition,
    signal: SignalResult | None,
    exit_review: PositionExitReview | None,
    account: AccountConfig,
    risk: RiskConfig,
) -> PositionDriftReview:
    close = signal.close if signal else exit_review.close if exit_review else None
    stop = None
    if exit_review and exit_review.dynamic_stop is not None:
        stop = exit_review.dynamic_stop
    elif signal:
        stop = signal.position.stop_price
    elif position.current_stop is not None:
        stop = position.current_stop

    actual_value = position.shares * close if close is not None else None
    actual_weight = actual_value / account.nav if actual_value is not None and account.nav > 0 else None
    lots_target = signal.position.target_shares if signal else None
    lots_initial = signal.position.initial_shares if signal else None
    target_weight = signal.position.target_weight if signal else None
    risk_budget = signal.position.risk_budget if signal else risk.risk_budget_max
    drift_shares = position.shares - lots_target if lots_target is not None else None
    drift_pct = drift_shares / lots_target if lots_target and lots_target > 0 else None

    stop_loss_amount = None
    stop_loss_nav_pct = None
    if close is not None and stop is not None and close > stop and account.nav > 0:
        stop_loss_amount = position.shares * (close - stop)
        stop_loss_nav_pct = stop_loss_amount / account.nav

    notes: list[str] = []
    severity = 0

    if signal is None:
        severity = max(severity, 50)
        notes.append("没有系统 LOTS 信号，先人工复核，不新增仓位")
    else:
        if drift_pct is not None:
            if drift_pct >= 1.0:
                severity = max(severity, 80)
                notes.append("实际股数超过 LOTS 目标 100% 以上")
            elif drift_pct >= 0.35:
                severity = max(severity, 60)
                notes.append("实际股数明显高于 LOTS 目标")
            elif drift_pct >= 0.10:
                severity = max(severity, 30)
                notes.append("实际股数略高于 LOTS 目标，禁止新增")
            elif drift_pct <= -0.5:
                notes.append("实际股数明显低于 LOTS 目标，但是否加仓仍取决于趋势和 Supervisor")
            else:
                notes.append("实际股数接近 LOTS 目标")

    if actual_weight is not None and target_weight is not None:
        if actual_weight >= target_weight * 1.5:
            severity = max(severity, 70)
            notes.append("实际仓位比例明显超过系统目标权重")
        elif actual_weight > target_weight:
            severity = max(severity, 40)
            notes.append("实际仓位比例高于系统目标权重")

    if stop_loss_nav_pct is not None:
        if stop_loss_nav_pct >= risk_budget * 2:
            severity = max(severity, 90)
            notes.append("跌到保护/止损线的亏损超过风险预算 2 倍")
        elif stop_loss_nav_pct > risk_budget:
            severity = max(severity, 70)
            notes.append("跌到保护/止损线的亏损超过系统风险预算")
        else:
            notes.append("止损风险在系统风险预算内")
    else:
        severity = max(severity, 40)
        notes.append("缺少价格或止损线，无法计算止损风险")

    if exit_review is not None and exit_review.severity >= 70:
        severity = max(severity, exit_review.severity)
        notes.append(f"利润保护/退出规则已触发：{exit_review.action}")

    if severity >= 90:
        action = "严重超配/优先降风险"
    elif severity >= 70:
        action = "超配/建议分批减仓"
    elif severity >= 50:
        action = "偏离 LOTS/人工复核"
    elif severity >= 30:
        action = "禁止加仓/等待消化"
    else:
        action = "接近 LOTS/可按信号管理"

    if not notes:
        notes.append("未发现明显 LOTS 偏离")

    return PositionDriftReview(
        ticker=position.ticker,
        actual_shares=position.shares,
        lots_target_shares=_safe_float(lots_target),
        lots_initial_shares=_safe_float(lots_initial),
        actual_value=_safe_float(actual_value),
        actual_weight=_safe_float(actual_weight),
        target_weight=_safe_float(target_weight),
        drift_shares=_safe_float(drift_shares),
        drift_pct=_safe_float(drift_pct),
        stop_loss_amount=_safe_float(stop_loss_amount),
        stop_loss_nav_pct=_safe_float(stop_loss_nav_pct),
        risk_budget_pct=_safe_float(risk_budget),
        action=action,
        severity=severity,
        notes=notes,
    )


def evaluate_positions_drift(
    positions: list[StoredPosition],
    signals: list[SignalResult],
    exit_reviews: list[PositionExitReview],
    account: AccountConfig,
    risk: RiskConfig,
) -> list[PositionDriftReview]:
    signal_by_ticker = {signal.ticker: signal for signal in signals}
    exit_by_ticker = {review.ticker: review for review in exit_reviews}
    reviews = [
        evaluate_position_drift(
            position=position,
            signal=signal_by_ticker.get(position.ticker),
            exit_review=exit_by_ticker.get(position.ticker),
            account=account,
            risk=risk,
        )
        for position in positions
    ]
    return sorted(reviews, key=lambda item: (item.severity, item.ticker), reverse=True)
