from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

import pandas as pd

from quant_ai_system.config import RiskConfig
from quant_ai_system.portfolio_store import StoredPosition
from quant_ai_system.signals import SignalResult


@dataclass(frozen=True)
class PositionExitReview:
    ticker: str
    action: str
    severity: int
    close: float | None
    average_cost: float
    current_pnl_pct: float | None
    highest_close: float | None
    highest_pnl_pct: float | None
    profit_giveback_pct: float | None
    dynamic_stop: float | None
    profit_floor: float | None
    atr_trailing_stop: float | None
    notes: list[str]


def _clean_float(value: object) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if isfinite(result) else None


def _history_since_open(indicators: pd.DataFrame, opened_at: str) -> pd.DataFrame:
    if indicators.empty:
        return indicators
    try:
        opened = pd.Timestamp(opened_at)
    except ValueError:
        return indicators
    if opened.tzinfo is not None:
        opened = opened.tz_convert(None)
    index = pd.to_datetime(indicators.index)
    if getattr(index, "tz", None) is not None and opened.tzinfo is None:
        opened = opened.tz_localize(index.tz)
    elif getattr(index, "tz", None) is None and opened.tzinfo is not None:
        opened = opened.tz_convert(None)
    return indicators.loc[index >= opened] if (index >= opened).any() else indicators


def _action(severity: int) -> str:
    if severity >= 90:
        return "退出候选"
    if severity >= 70:
        return "减仓 1/2 候选"
    if severity >= 50:
        return "减仓 1/3 候选"
    if severity >= 30:
        return "禁止加仓/保护利润"
    if severity >= 10:
        return "继续持有/观察"
    return "继续持有"


def evaluate_position_exit(
    position: StoredPosition,
    indicators: pd.DataFrame | None,
    risk: RiskConfig,
    signal: SignalResult | None = None,
) -> PositionExitReview:
    if indicators is None or indicators.empty:
        return PositionExitReview(
            ticker=position.ticker,
            action="人工复核",
            severity=40,
            close=None,
            average_cost=position.average_cost,
            current_pnl_pct=None,
            highest_close=None,
            highest_pnl_pct=None,
            profit_giveback_pct=None,
            dynamic_stop=position.current_stop,
            profit_floor=None,
            atr_trailing_stop=None,
            notes=["没有可用行情数据，不能自动判断止盈/退出"],
        )

    usable = indicators.dropna(subset=["close"])
    if usable.empty:
        return PositionExitReview(
            ticker=position.ticker,
            action="人工复核",
            severity=40,
            close=None,
            average_cost=position.average_cost,
            current_pnl_pct=None,
            highest_close=None,
            highest_pnl_pct=None,
            profit_giveback_pct=None,
            dynamic_stop=position.current_stop,
            profit_floor=None,
            atr_trailing_stop=None,
            notes=["行情缺少收盘价，不能自动判断止盈/退出"],
        )

    latest = usable.iloc[-1]
    close = float(latest["close"])
    history = _history_since_open(usable, position.opened_at)
    highest_close = float(history["close"].max())
    current_pnl = close / position.average_cost - 1
    highest_pnl = highest_close / position.average_cost - 1
    profit_giveback = max((highest_pnl - current_pnl) / highest_pnl, 0.0) if highest_pnl > 0 else 0.0

    atr = _clean_float(latest.get("atr14"))
    ma50 = _clean_float(latest.get("ma50"))
    ma200 = _clean_float(latest.get("ma200"))
    rel20 = _clean_float(latest.get("rel20"))

    profit_floor = None
    atr_trailing_stop = None
    stop_candidates: list[float] = []
    notes: list[str] = []
    severity = 0

    if position.current_stop is not None:
        stop_candidates.append(position.current_stop)
        if close <= position.current_stop:
            severity = max(severity, 90)
            notes.append("跌破手动持仓止损价，退出候选")

    if signal is not None:
        stop_candidates.append(signal.position.stop_price)
        if "退出" in signal.action:
            severity = max(severity, 90)
            notes.append("系统趋势信号已给出退出候选")
        elif "减仓" in signal.action:
            severity = max(severity, 60)
            notes.append("系统趋势信号已给出减仓候选")

    if highest_pnl >= risk.profit_protection_min_gain:
        profit_floor = position.average_cost * (1 + highest_pnl * risk.profit_floor_keep_ratio)
        stop_candidates.append(profit_floor)
        notes.append(f"已进入利润保护区，最高浮盈 {highest_pnl * 100:.1f}%")
        if atr and atr > 0:
            atr_trailing_stop = highest_close - atr * risk.profit_trailing_atr_multiple
            stop_candidates.append(atr_trailing_stop)
        if profit_giveback >= risk.profit_giveback_exit:
            severity = max(severity, 90)
            notes.append("利润回吐超过退出阈值")
        elif profit_giveback >= risk.profit_giveback_trim:
            severity = max(severity, 70)
            notes.append("利润回吐超过减仓 1/2 阈值")
        elif profit_giveback >= risk.profit_giveback_watch:
            severity = max(severity, 50)
            notes.append("利润回吐超过减仓 1/3 观察阈值")
        elif profit_giveback > 0:
            severity = max(severity, 30)
            notes.append("利润开始回吐，禁止新增仓位")

    dynamic_stop = max(stop_candidates) if stop_candidates else None
    if dynamic_stop is not None and close <= dynamic_stop and highest_pnl >= risk.profit_protection_min_gain:
        severity = max(severity, 70)
        notes.append("价格触及动态利润保护线")

    if ma200 is not None and close < ma200:
        severity = max(severity, 90)
        notes.append("跌破200日线，长期趋势破坏")
    elif ma50 is not None and close < ma50:
        if rel20 is not None and rel20 < 0:
            severity = max(severity, 70)
            notes.append("跌破50日线且相对强度转弱")
        else:
            severity = max(severity, 50)
            notes.append("跌破50日线，先进入减仓观察")

    if current_pnl < 0 and dynamic_stop is not None and close <= dynamic_stop:
        severity = max(severity, 90)
        notes.append("持仓转亏并跌破止损参考")

    if not notes:
        notes.append("未触发利润保护或趋势退出规则")

    return PositionExitReview(
        ticker=position.ticker,
        action=_action(severity),
        severity=severity,
        close=close,
        average_cost=position.average_cost,
        current_pnl_pct=current_pnl,
        highest_close=highest_close,
        highest_pnl_pct=highest_pnl,
        profit_giveback_pct=profit_giveback if highest_pnl > 0 else None,
        dynamic_stop=dynamic_stop,
        profit_floor=profit_floor,
        atr_trailing_stop=atr_trailing_stop,
        notes=notes,
    )


def evaluate_positions_exit(
    positions: list[StoredPosition],
    indicators_by_ticker: dict[str, pd.DataFrame],
    risk: RiskConfig,
    signals: list[SignalResult],
) -> list[PositionExitReview]:
    signal_by_ticker = {signal.ticker: signal for signal in signals}
    reviews = [
        evaluate_position_exit(
            position=position,
            indicators=indicators_by_ticker.get(position.ticker),
            risk=risk,
            signal=signal_by_ticker.get(position.ticker),
        )
        for position in positions
    ]
    return sorted(reviews, key=lambda review: (review.severity, review.ticker), reverse=True)
