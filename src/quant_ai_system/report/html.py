from __future__ import annotations

from pathlib import Path

from jinja2 import Template

from quant_ai_system.action_summary import build_action_summary
from quant_ai_system.backtest import BacktestResult
from quant_ai_system.config import AppConfig
from quant_ai_system.exit_rules import PositionExitReview
from quant_ai_system.position_drift import PositionDriftReview
from quant_ai_system.report.templates import REPORT_TEMPLATE
from quant_ai_system.research import NewsBrief
from quant_ai_system.risk import PortfolioRiskState
from quant_ai_system.signals import SignalResult
from quant_ai_system.supervisor import SupervisorDecision
from quant_ai_system.portfolio_store import StoredPosition


def _css_for_action(action: str) -> str:
    if "退出" in action:
        return "exit"
    if "减仓" in action:
        return "trim"
    if "加仓" in action or "小仓" in action:
        return "buy"
    return "watch"


def _css_for_exit_action(action: str) -> str:
    if "退出" in action:
        return "exit"
    if "减仓" in action:
        return "trim"
    if "禁止加仓" in action:
        return "trim"
    return "watch"


def _css_for_drift_action(action: str) -> str:
    if "严重" in action:
        return "exit"
    if "超配" in action or "复核" in action or "禁止加仓" in action:
        return "trim"
    return "watch"


def render_report(
    config: AppConfig,
    signals: list[SignalResult],
    backtest: BacktestResult,
    portfolio_risk: PortfolioRiskState,
    issues: list[object],
    out_path: str | Path,
    as_of: object,
    supervisor_reviews: list[SupervisorDecision] | None = None,
    positions: list[StoredPosition] | None = None,
    exit_reviews: list[PositionExitReview] | None = None,
    drift_reviews: list[PositionDriftReview] | None = None,
    news_briefs: list[NewsBrief] | None = None,
) -> Path:
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    sorted_signals = sorted(signals, key=lambda s: (("退出" not in s.action and "减仓" not in s.action), s.score), reverse=True)
    signal_rows = [{"signal": signal, "css": _css_for_action(signal.action)} for signal in sorted_signals]
    supervisor_reviews = supervisor_reviews or []
    positions = positions or []
    exit_reviews = exit_reviews or []
    drift_reviews = drift_reviews or []
    news_briefs = news_briefs or []
    review_by_ticker = {review.ticker: review for review in supervisor_reviews}
    signal_by_ticker = {row["signal"].ticker: row["signal"] for row in signal_rows}
    exit_review_by_ticker = {review.ticker: review for review in exit_reviews}
    exit_review_rows = [{"review": review, "css": _css_for_exit_action(review.action)} for review in exit_reviews]
    drift_review_by_ticker = {review.ticker: review for review in drift_reviews}
    drift_review_rows = [{"review": review, "css": _css_for_drift_action(review.action)} for review in drift_reviews]
    action_summary = build_action_summary(
        signals,
        supervisor_reviews,
        exit_reviews,
        drift_reviews,
        news_briefs,
        set(config.universe.leveraged_tickers + config.universe.tactical_tickers),
        config.risk.max_positions,
    )
    core_tickers = {signal.ticker for signal in action_summary.stock_candidates}
    core_rows = [row for row in signal_rows if row["signal"].ticker in core_tickers]
    summary = {
        "ticker_count": len(signals),
        "buy_count": sum(1 for s in signals if "加仓" in s.action or "小仓" in s.action),
        "risk_count": sum(1 for s in signals if "减仓" in s.action or "退出" in s.action),
        "position_exit_count": sum(1 for r in exit_reviews if r.severity >= 50),
        "position_drift_count": sum(1 for r in drift_reviews if r.severity >= 50),
        "news_risk_count": sum(1 for brief in news_briefs if brief.risk_flags),
        "core_count": len(core_rows),
    }
    html = Template(REPORT_TEMPLATE).render(
        title=config.report.title,
        as_of=as_of,
        signals=signal_rows,
        core_signals=core_rows,
        supervisor_reviews=supervisor_reviews,
        review_by_ticker=review_by_ticker,
        positions=positions,
        signal_by_ticker=signal_by_ticker,
        exit_reviews=exit_review_rows,
        exit_review_by_ticker=exit_review_by_ticker,
        drift_reviews=drift_review_rows,
        drift_review_by_ticker=drift_review_by_ticker,
        news_briefs=news_briefs,
        metrics=backtest.metrics,
        portfolio_risk=portfolio_risk,
        issues=issues,
        summary=summary,
        action_summary=action_summary,
    )
    out.write_text(html, encoding="utf-8")
    return out
