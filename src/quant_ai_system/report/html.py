from __future__ import annotations

from pathlib import Path

from jinja2 import Template

from quant_ai_system.backtest import BacktestResult
from quant_ai_system.config import AppConfig
from quant_ai_system.report.templates import REPORT_TEMPLATE
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
) -> Path:
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    sorted_signals = sorted(signals, key=lambda s: (("退出" not in s.action and "减仓" not in s.action), s.score), reverse=True)
    signal_rows = [{"signal": signal, "css": _css_for_action(signal.action)} for signal in sorted_signals]
    supervisor_reviews = supervisor_reviews or []
    positions = positions or []
    review_by_ticker = {review.ticker: review for review in supervisor_reviews}
    signal_by_ticker = {row["signal"].ticker: row["signal"] for row in signal_rows}
    core_rows = [
        row for row in signal_rows
        if (
            row["signal"].score >= config.risk.min_core_score
            and ("加仓" in row["signal"].action or "小仓" in row["signal"].action)
            and review_by_ticker.get(row["signal"].ticker, None) is not None
            and review_by_ticker[row["signal"].ticker].decision == "approve_for_consideration"
        )
    ][: config.risk.max_positions]
    summary = {
        "ticker_count": len(signals),
        "buy_count": sum(1 for s in signals if "加仓" in s.action or "小仓" in s.action),
        "risk_count": sum(1 for s in signals if "减仓" in s.action or "退出" in s.action),
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
        metrics=backtest.metrics,
        portfolio_risk=portfolio_risk,
        issues=issues,
        summary=summary,
    )
    out.write_text(html, encoding="utf-8")
    return out
