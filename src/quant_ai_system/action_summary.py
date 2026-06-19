from __future__ import annotations

from dataclasses import dataclass

from quant_ai_system.exit_rules import PositionExitReview
from quant_ai_system.position_drift import PositionDriftReview
from quant_ai_system.research import NewsBrief
from quant_ai_system.signals import SignalResult
from quant_ai_system.supervisor import SupervisorDecision


@dataclass(frozen=True)
class ActionSummary:
    data_fix_positions: list[PositionDriftReview]
    position_exit_actions: list[PositionExitReview]
    position_size_actions: list[PositionDriftReview]
    stock_candidates: list[SignalResult]
    tactical_candidates: list[SignalResult]
    research_watch: list[SignalResult]
    news_risks: list[NewsBrief]
    news_catalysts: list[NewsBrief]
    no_action_message: str


def is_executable_candidate(signal: SignalResult, review_by_ticker: dict[str, SupervisorDecision]) -> bool:
    review = review_by_ticker.get(signal.ticker)
    return bool(
        review is not None
        and review.decision == "approve_for_consideration"
        and ("加仓" in signal.action or "小仓" in signal.action)
        and signal.close > 0
        and signal.position.stop_price > 0
        and signal.position.target_shares >= 1
    )


def build_action_summary(
    signals: list[SignalResult],
    supervisor_reviews: list[SupervisorDecision],
    exit_reviews: list[PositionExitReview],
    drift_reviews: list[PositionDriftReview],
    news_briefs: list[NewsBrief],
    tactical_tickers: set[str],
    max_core_positions: int,
) -> ActionSummary:
    review_by_ticker = {review.ticker: review for review in supervisor_reviews}
    approved = [signal for signal in sorted(signals, key=lambda item: item.score, reverse=True) if is_executable_candidate(signal, review_by_ticker)]
    stock_candidates = [signal for signal in approved if signal.ticker not in tactical_tickers][:max_core_positions]
    tactical_candidates = [signal for signal in approved if signal.ticker in tactical_tickers][:max_core_positions]
    actionable = {signal.ticker for signal in stock_candidates + tactical_candidates}
    research_watch = [
        signal
        for signal in sorted(signals, key=lambda item: item.score, reverse=True)
        if signal.ticker not in actionable and ("加仓" in signal.action or "小仓" in signal.action)
    ][:8]
    data_fix_positions = [review for review in drift_reviews if review.action == "数据修复优先"]
    position_exit_actions = [review for review in exit_reviews if review.severity >= 30 and review.ticker not in {item.ticker for item in data_fix_positions}]
    position_size_actions = [
        review
        for review in drift_reviews
        if review.severity >= 50 and review.action != "数据修复优先" and review.ticker not in {item.ticker for item in data_fix_positions}
    ]
    news_risks = [brief for brief in news_briefs if brief.risk_flags]
    news_catalysts = [brief for brief in news_briefs if brief.catalyst_flags]
    no_action_message = "今日无可执行买入；当前优先事项是数据修复/持仓监控"
    return ActionSummary(
        data_fix_positions=data_fix_positions,
        position_exit_actions=position_exit_actions,
        position_size_actions=position_size_actions,
        stock_candidates=stock_candidates,
        tactical_candidates=tactical_candidates,
        research_watch=research_watch,
        news_risks=news_risks,
        news_catalysts=news_catalysts,
        no_action_message=no_action_message,
    )
