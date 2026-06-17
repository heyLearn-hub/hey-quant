from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from quant_ai_system.config import AccountConfig, BacktestConfig, RiskConfig
from quant_ai_system.indicators import build_indicators
from quant_ai_system.signals import score_latest


@dataclass(frozen=True)
class BacktestMetrics:
    strategy: str
    annual_return: float
    max_drawdown: float
    sharpe: float
    win_rate: float
    profit_factor: float
    turnover: float
    avg_holding_days: float
    max_consecutive_losses: int
    benchmark_excess_return: float


@dataclass
class BacktestResult:
    metrics: list[BacktestMetrics]
    equity_curves: pd.DataFrame
    trades: pd.DataFrame


def _max_drawdown(series: pd.Series) -> float:
    if series.empty:
        return 0.0
    return float((series / series.cummax() - 1).min())


def _metrics(strategy: str, equity: pd.Series, trades: pd.DataFrame, benchmark: pd.Series | None) -> BacktestMetrics:
    returns = equity.pct_change().dropna()
    annual_return = float((equity.iloc[-1] / equity.iloc[0]) ** (252 / max(len(equity), 1)) - 1) if len(equity) > 1 else 0.0
    sharpe = float(np.sqrt(252) * returns.mean() / returns.std()) if returns.std() and not np.isnan(returns.std()) else 0.0
    wins = trades[trades["pnl"] > 0] if not trades.empty else pd.DataFrame()
    losses = trades[trades["pnl"] < 0] if not trades.empty else pd.DataFrame()
    win_rate = float(len(wins) / len(trades)) if len(trades) else 0.0
    gross_profit = float(wins["pnl"].sum()) if not wins.empty else 0.0
    gross_loss = abs(float(losses["pnl"].sum())) if not losses.empty else 0.0
    profit_factor = gross_profit / gross_loss if gross_loss else 0.0
    turnover = float(trades["notional"].sum() / equity.mean()) if len(trades) and equity.mean() else 0.0
    avg_holding_days = float(trades["holding_days"].mean()) if len(trades) else 0.0
    max_losses = 0
    current = 0
    for pnl in trades["pnl"].tolist() if len(trades) else []:
        current = current + 1 if pnl < 0 else 0
        max_losses = max(max_losses, current)
    if benchmark is not None and len(benchmark) > 1:
        bench_ret = float(benchmark.iloc[-1] / benchmark.iloc[0] - 1)
        strat_ret = float(equity.iloc[-1] / equity.iloc[0] - 1)
        excess = strat_ret - bench_ret
    else:
        excess = 0.0
    return BacktestMetrics(strategy, annual_return, _max_drawdown(equity), sharpe, win_rate, profit_factor, turnover, avg_holding_days, max_losses, excess)


def _rebalance_dates(index: pd.DatetimeIndex, mode: str) -> set[pd.Timestamp]:
    if mode == "daily":
        return set(index)
    period_index = index.tz_convert(None).to_period("W") if index.tz is not None else index.to_period("W")
    grouped = pd.Series(index=index, data=index).groupby(period_index).last()
    return set(grouped.values)


def _score_history(frame: pd.DataFrame, benchmark: pd.DataFrame | None, strategy: str) -> pd.DataFrame:
    ind = build_indicators(frame, benchmark)
    scores = []
    for _, row in ind.iterrows():
        if pd.isna(row.get("ma200")):
            scores.append(np.nan)
            continue
        score, _ = score_latest(row)
        if strategy == "trend":
            score = 100 if row["close"] > row["ma50"] > row["ma200"] else 0
        elif strategy == "trend_relative":
            score = 100 if row["close"] > row["ma50"] > row["ma200"] and row.get("rel60", 0) > 0 else 0
        scores.append(score)
    ind["score"] = scores
    return ind


def run_backtest(
    prices: dict[str, pd.DataFrame],
    tickers: list[str],
    benchmark_ticker: str,
    account: AccountConfig,
    risk: RiskConfig,
    config: BacktestConfig,
) -> BacktestResult:
    benchmark = prices.get(benchmark_ticker)
    usable_tickers = [ticker for ticker in tickers if ticker in prices and len(prices[ticker]) > 260]
    if not usable_tickers:
        return BacktestResult(metrics=[], equity_curves=pd.DataFrame(), trades=pd.DataFrame())

    common_index = sorted(set.intersection(*(set(prices[ticker].index) for ticker in usable_tickers)))
    common_index = pd.DatetimeIndex(common_index)
    if len(common_index) < 260:
        return BacktestResult(metrics=[], equity_curves=pd.DataFrame(), trades=pd.DataFrame())

    strategies = ["trend", "trend_relative", "full_system"]
    curves: dict[str, pd.Series] = {}
    all_trades: list[dict[str, object]] = []
    metrics: list[BacktestMetrics] = []
    slippage = config.slippage_bps / 10_000
    rebal_dates = _rebalance_dates(common_index, config.rebalance)

    scored = {
        strategy: {ticker: _score_history(prices[ticker].loc[common_index], benchmark, strategy) for ticker in usable_tickers}
        for strategy in strategies
    }

    for strategy in strategies:
        cash = config.initial_cash
        holdings: dict[str, float] = {}
        entry_dates: dict[str, pd.Timestamp] = {}
        entry_prices: dict[str, float] = {}
        equity_values: list[float] = []
        equity_index: list[pd.Timestamp] = []
        for i, date in enumerate(common_index[:-1]):
            next_date = common_index[i + 1]
            market_value = sum(holdings.get(t, 0) * float(prices[t].loc[date, "close"]) for t in holdings)
            equity = cash + market_value
            equity_values.append(equity)
            equity_index.append(date)
            if date not in rebal_dates:
                continue

            candidates: list[tuple[str, float]] = []
            exits: list[str] = []
            for ticker in usable_tickers:
                row = scored[strategy][ticker].loc[date]
                score = float(row["score"]) if not pd.isna(row["score"]) else 0
                close = float(row["close"])
                if ticker in holdings and (score < 45 or close < float(row["ma200"])):
                    exits.append(ticker)
                if score >= 65:
                    candidates.append((ticker, score))

            for ticker in exits:
                shares = holdings.pop(ticker, 0)
                if shares:
                    sell_price = float(prices[ticker].loc[next_date, "open"]) * (1 - slippage)
                    cash += shares * sell_price
                    pnl = shares * (sell_price - entry_prices.pop(ticker, sell_price))
                    all_trades.append({
                        "strategy": strategy,
                        "ticker": ticker,
                        "entry_date": entry_dates.pop(ticker, date),
                        "exit_date": next_date,
                        "pnl": pnl,
                        "notional": shares * sell_price,
                        "holding_days": max((next_date - date).days, 1),
                    })

            candidates = sorted(candidates, key=lambda item: item[1], reverse=True)[: config.max_positions]
            target_weight = min(risk.target_weight_min, 1 / max(config.max_positions, 1))
            for ticker, _score in candidates:
                if ticker in holdings:
                    continue
                buy_price = float(prices[ticker].loc[next_date, "open"]) * (1 + slippage)
                alloc = (cash + sum(holdings.get(t, 0) * float(prices[t].loc[date, "close"]) for t in holdings)) * target_weight
                shares = int(alloc / buy_price)
                if shares <= 0 or cash < shares * buy_price:
                    continue
                cash -= shares * buy_price
                holdings[ticker] = shares
                entry_dates[ticker] = next_date
                entry_prices[ticker] = buy_price

        final_date = common_index[-1]
        final_equity = cash + sum(holdings.get(t, 0) * float(prices[t].loc[final_date, "close"]) for t in holdings)
        equity_values.append(final_equity)
        equity_index.append(final_date)
        curve = pd.Series(equity_values, index=pd.DatetimeIndex(equity_index), name=strategy)
        curves[strategy] = curve
        trades_df = pd.DataFrame([row for row in all_trades if row["strategy"] == strategy])
        bench_curve = benchmark.loc[curve.index, "close"] if benchmark is not None and not benchmark.empty else None
        metrics.append(_metrics(strategy, curve, trades_df, bench_curve))

    return BacktestResult(metrics=metrics, equity_curves=pd.DataFrame(curves), trades=pd.DataFrame(all_trades))
