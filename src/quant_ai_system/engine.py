from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from quant_ai_system.backtest import BacktestResult, run_backtest
from quant_ai_system.config import AppConfig
from quant_ai_system.data import MarketDataSet, get_market_data, make_sample_market_data
from quant_ai_system.data.providers import DataIssue
from quant_ai_system.exit_rules import PositionExitReview, evaluate_positions_exit
from quant_ai_system.indicators import build_indicators
from quant_ai_system.position_drift import PositionDriftReview, evaluate_positions_drift
from quant_ai_system.quality import assess_quality
from quant_ai_system.report.html import render_report
from quant_ai_system.portfolio_store import StoredPosition, list_positions
from quant_ai_system.research import NewsBrief, build_news_briefs
from quant_ai_system.risk import PortfolioRiskState, evaluate_portfolio_drawdown
from quant_ai_system.signals import SignalResult, evaluate_signal
from quant_ai_system.supervisor import SupervisorDecision, run_supervisor_review


@dataclass
class RunResult:
    market_data: MarketDataSet
    signals: list[SignalResult]
    backtest: BacktestResult
    portfolio_risk: PortfolioRiskState
    supervisor_reviews: list[SupervisorDecision]
    positions: list[StoredPosition]
    exit_reviews: list[PositionExitReview]
    drift_reviews: list[PositionDriftReview]
    news_briefs: list[NewsBrief]
    report_path: Path


def run_system(config: AppConfig, out_path: str | Path, offline_sample: bool = False) -> RunResult:
    tradable_tickers = list(dict.fromkeys(config.universe.tickers + config.universe.leveraged_tickers))
    tickers = list(dict.fromkeys(tradable_tickers + config.universe.benchmarks))
    if offline_sample:
        market_data = make_sample_market_data(tickers, years=min(config.data.years, 5))
        market_data.issues.append(DataIssue("*", "sample", "offline sample mode; not live market data"))
    else:
        market_data = get_market_data(tickers, config.data)
    benchmark = market_data.prices.get(config.universe.primary_benchmark)

    signals: list[SignalResult] = []
    indicators_by_ticker = {}
    leveraged_set = set(config.universe.leveraged_tickers)
    for ticker in tradable_tickers:
        frame = market_data.prices.get(ticker)
        if frame is None or frame.empty:
            continue
        indicators = build_indicators(frame, benchmark)
        indicators_by_ticker[ticker] = indicators
        quality = assess_quality(ticker, config.quality, leveraged_set)
        signal = evaluate_signal(
            ticker,
            indicators,
            config.account,
            config.risk,
            quality,
            config.quality,
            ticker in leveraged_set,
        )
        if signal:
            signals.append(signal)

    backtest = run_backtest(
        prices=market_data.prices,
        tickers=tradable_tickers,
        benchmark_ticker=config.universe.primary_benchmark,
        account=config.account,
        risk=config.risk,
        config=config.backtest,
    )
    if backtest.equity_curves.empty:
        portfolio_risk = PortfolioRiskState(0.0, "unknown", True, ["回测净值曲线不足，暂不判断组合模式"])
    else:
        portfolio_risk = evaluate_portfolio_drawdown(backtest.equity_curves["full_system"], config.risk)
    positions = list_positions(config.storage.db_path)
    news_tickers = list(
        dict.fromkeys(
            [position.ticker for position in positions]
            + [signal.ticker for signal in sorted(signals, key=lambda item: item.score, reverse=True)]
        )
    )[: config.research.news_max_tickers]
    news_briefs = [] if offline_sample else build_news_briefs(news_tickers, config.research)
    supervisor_reviews = run_supervisor_review(signals, config.supervisor, market_data.issues, news_briefs)
    exit_reviews = evaluate_positions_exit(positions, indicators_by_ticker, config.risk, signals)
    drift_reviews = evaluate_positions_drift(positions, signals, exit_reviews, config.account, config.risk)
    report_path = render_report(
        config,
        signals,
        backtest,
        portfolio_risk,
        market_data.issues,
        out_path,
        market_data.as_of,
        supervisor_reviews=supervisor_reviews,
        positions=positions,
        exit_reviews=exit_reviews,
        drift_reviews=drift_reviews,
        news_briefs=news_briefs,
    )
    return RunResult(
        market_data,
        signals,
        backtest,
        portfolio_risk,
        supervisor_reviews,
        positions,
        exit_reviews,
        drift_reviews,
        news_briefs,
        report_path,
    )
