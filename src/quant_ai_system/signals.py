from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from quant_ai_system.config import AccountConfig, QualityConfig, RiskConfig
from quant_ai_system.portfolio import PositionPlan, calculate_position_plan
from quant_ai_system.quality import QualityAssessment, combined_score
from quant_ai_system.risk import RiskState, evaluate_security_risk


@dataclass(frozen=True)
class SignalResult:
    ticker: str
    as_of: pd.Timestamp
    score: float
    technical_score: float
    quality: QualityAssessment
    action: str
    close: float
    reasons: list[str]
    risk: RiskState
    position: PositionPlan


def score_latest(latest: pd.Series) -> tuple[float, list[str]]:
    score = 0.0
    reasons: list[str] = []

    def add(condition: bool, points: float, reason: str) -> None:
        nonlocal score
        if condition:
            score += points
            reasons.append(reason)

    close = float(latest["close"])
    ma50 = float(latest.get("ma50", 0) or 0)
    ma200 = float(latest.get("ma200", 0) or 0)
    mom20 = float(latest.get("mom20", 0) or 0)
    mom60 = float(latest.get("mom60", 0) or 0)
    rsi14 = float(latest.get("rsi14", 50) or 50)
    volume = float(latest.get("volume", 0) or 0)
    volume_ma20 = float(latest.get("volume_ma20", 0) or 0)
    rel20 = float(latest.get("rel20", 0) or 0)
    rel60 = float(latest.get("rel60", 0) or 0)

    add(close > ma50 > 0, 15, "价格高于50日线")
    add(close > ma200 > 0, 15, "价格高于200日线")
    add(ma50 > ma200 > 0, 15, "50日线高于200日线")
    add(mom20 > 0, 10, "20日动量为正")
    add(mom60 > 0, 10, "60日动量为正")
    add(45 <= rsi14 <= 72, 10, "RSI处于趋势可接受区间")
    add(volume_ma20 > 0 and volume > volume_ma20 * 1.05, 10, "成交量高于20日均量")
    add(rel20 > 0, 7.5, "20日相对强度跑赢基准")
    add(rel60 > 0, 7.5, "60日相对强度跑赢基准")
    return min(score, 100.0), reasons


def action_from_score(score: float, risk_state: RiskState) -> str:
    if risk_state.exit_trigger:
        return "退出候选"
    if risk_state.trim_trigger:
        return "减仓候选"
    if risk_state.signal_decay:
        return "信号衰减/观察"
    if score >= 80:
        return "加仓候选"
    if score >= 65:
        return "小仓候选"
    if score >= 50:
        return "观察"
    return "弱信号/观察"


def evaluate_signal(
    ticker: str,
    indicators: pd.DataFrame,
    account: AccountConfig,
    risk: RiskConfig,
    quality: QualityAssessment,
    quality_config: QualityConfig,
    is_leveraged: bool = False,
) -> SignalResult | None:
    usable = indicators.dropna(subset=["close", "ma50", "ma200", "atr14"])
    if usable.empty:
        return None
    latest = usable.iloc[-1]
    technical_score, reasons = score_latest(latest)
    score = combined_score(technical_score, quality.score, quality_config)
    risk_state = evaluate_security_risk(ticker, latest, risk, score)
    action = action_from_score(score, risk_state)
    position = calculate_position_plan(
        ticker=ticker,
        action=action,
        price=float(latest["close"]),
        stop_price=risk_state.stop_price,
        score=score,
        account=account,
        risk=risk,
        is_leveraged=is_leveraged,
    )
    return SignalResult(
        ticker=ticker,
        as_of=usable.index[-1],
        score=score,
        technical_score=technical_score,
        quality=quality,
        action=action,
        close=float(latest["close"]),
        reasons=reasons,
        risk=risk_state,
        position=position,
    )
