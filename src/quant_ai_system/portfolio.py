from __future__ import annotations

from dataclasses import dataclass
from math import floor

from quant_ai_system.config import AccountConfig, RiskConfig


@dataclass(frozen=True)
class PositionPlan:
    ticker: str
    action: str
    price: float
    stop_price: float
    score: float
    target_weight: float
    initial_weight: float
    risk_budget: float
    target_shares: float
    initial_shares: float
    max_risk_shares: float
    binding_constraint: str
    intended_alpha: str
    unwanted_risk: str
    retained_exposure: str
    liquidity_exit_posture: str


def _scale(score: float, low: float, high: float, score_low: float = 60, score_high: float = 90) -> float:
    clipped = min(max(score, score_low), score_high)
    return low + (high - low) * ((clipped - score_low) / (score_high - score_low))


def calculate_position_plan(
    ticker: str,
    action: str,
    price: float,
    stop_price: float,
    score: float,
    account: AccountConfig,
    risk: RiskConfig,
    is_leveraged: bool = False,
) -> PositionPlan:
    target_weight = _scale(score, risk.target_weight_min, risk.target_weight_max)
    initial_weight = _scale(score, risk.initial_weight_min, risk.initial_weight_max)
    if is_leveraged:
        target_weight = min(target_weight, risk.leveraged_target_weight_max)
        initial_weight = min(initial_weight, risk.leveraged_initial_weight_max)
    risk_budget = _scale(score, risk.risk_budget_min, risk.risk_budget_max)
    stop_distance = max(price - stop_price, 0)
    target_weight_shares = account.nav * target_weight / price if price > 0 else 0
    initial_weight_shares = account.nav * initial_weight / price if price > 0 else 0
    max_risk_shares = account.nav * risk_budget / stop_distance if stop_distance > 0 else target_weight_shares
    target_shares = min(target_weight_shares, max_risk_shares)
    initial_shares = min(initial_weight_shares, max_risk_shares)
    if not account.fractional_shares:
        target_shares = floor(target_shares)
        initial_shares = floor(initial_shares)
        max_risk_shares = floor(max_risk_shares)
    binding_constraint = "risk_budget" if max_risk_shares < target_weight_shares else "target_weight"
    if "退出" in action or "减仓" in action:
        initial_shares = 0
    return PositionPlan(
        ticker=ticker,
        action=action,
        price=float(price),
        stop_price=float(stop_price),
        score=float(score),
        target_weight=float(target_weight),
        initial_weight=float(initial_weight),
        risk_budget=float(risk_budget),
        target_shares=float(target_shares),
        initial_shares=float(initial_shares),
        max_risk_shares=float(max_risk_shares),
        binding_constraint=binding_constraint,
        intended_alpha="低频趋势、相对强度和AI/半导体主题暴露",
        unwanted_risk="单票跳空、主题拥挤、估值回撤、财报前波动",
        retained_exposure="保留股票本身的趋势/行业 beta 与基本面验证弹性",
        liquidity_exit_posture="以日线信号分批处理；跌破风控线时优先减仓或退出候选",
    )
