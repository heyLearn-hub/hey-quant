from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from quant_ai_system.config import RiskConfig


@dataclass(frozen=True)
class RiskState:
    ticker: str
    stop_price: float
    trim_trigger: bool
    exit_trigger: bool
    signal_decay: bool
    notes: list[str]


@dataclass(frozen=True)
class PortfolioRiskState:
    drawdown: float
    mode: str
    new_positions_allowed: bool
    notes: list[str]


def evaluate_security_risk(ticker: str, latest: pd.Series, risk: RiskConfig, score: float) -> RiskState:
    close = float(latest["close"])
    atr_stop = close - float(latest.get("atr14", 0) or 0) * risk.atr_stop_multiple
    ma200 = float(latest.get("ma200", close) or close)
    stop_price = min(close * 0.92, atr_stop) if atr_stop > 0 else close * 0.92
    trim_trigger = bool(close < float(latest.get("ma50", close)) and float(latest.get("rel20", 0) or 0) < 0)
    exit_trigger = bool(close < ma200)
    signal_decay = bool(score < 40)
    notes: list[str] = []
    if trim_trigger:
        notes.append("跌破50日线且相对强度转弱，减仓候选")
    if exit_trigger:
        notes.append("跌破200日线，退出候选")
    if signal_decay:
        notes.append("综合信号衰减，降级观察")
    if not notes:
        notes.append("未触发硬性退出条件")
    return RiskState(ticker=ticker, stop_price=float(stop_price), trim_trigger=trim_trigger, exit_trigger=exit_trigger, signal_decay=signal_decay, notes=notes)


def evaluate_portfolio_drawdown(equity_curve: pd.Series, risk: RiskConfig) -> PortfolioRiskState:
    if equity_curve.empty:
        return PortfolioRiskState(0.0, "normal", True, ["暂无组合净值曲线"])
    peak = equity_curve.cummax()
    drawdown = float((equity_curve / peak - 1).min())
    abs_dd = abs(drawdown)
    if abs_dd >= risk.portfolio_drawdown_stop_new:
        return PortfolioRiskState(drawdown, "stop_new_positions", False, ["组合回撤超过15%，暂停新开仓"])
    if abs_dd >= risk.portfolio_drawdown_defensive:
        return PortfolioRiskState(drawdown, "defensive", False, ["组合回撤超过12%，只允许减仓/换仓"])
    if abs_dd >= risk.portfolio_drawdown_reduce:
        return PortfolioRiskState(drawdown, "reduce_risk", True, ["组合回撤超过8%，降低新开仓强度"])
    return PortfolioRiskState(drawdown, "normal", True, ["组合回撤在默认阈值内"])

