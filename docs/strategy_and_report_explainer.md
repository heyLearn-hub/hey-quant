# Strategy And Report Explainer

This document explains how the current report is calculated. The system is a low-frequency research and alert tool, not an automatic trading system.

## Pipeline

```text
market data
  -> indicators
  -> technical score
  -> quality score
  -> combined signal
  -> LOTS sizing
  -> real position drift check
  -> profit protection / exit rules
  -> AI/local supervisor review
  -> HTML report + Telegram alert
```

## Data

Default provider order:

```text
FMP -> yfinance -> Stooq
```

The system expects daily OHLCV:

```text
open / high / low / close / volume
```

If paid data fails, the system can fall back to free providers. If all live providers fail, sample data is clearly marked as non-tradable.

## Technical Indicators

For every ticker, the system calculates:

```text
MA50
MA200
20-day momentum
60-day momentum
RSI14
ATR14
20-day volume average
20-day relative strength versus benchmark
60-day relative strength versus benchmark
```

Primary benchmark is `QQQ`.

## Technical Score

The technical score is out of 100:

```text
price > MA50                         15 points
price > MA200                        15 points
MA50 > MA200                         15 points
20-day momentum > 0                  10 points
60-day momentum > 0                  10 points
45 <= RSI14 <= 72                    10 points
volume > 1.05 * 20-day volume avg    10 points
20-day relative strength > 0          7.5 points
60-day relative strength > 0          7.5 points
```

This makes the strategy trend-following and momentum-oriented. It is not a mean-reversion or intraday strategy.

## Quality Score

Quality score is manually configured for selected companies. It reflects:

```text
durable moat
cash generation
return on capital / margin quality
balance sheet risk
valuation discipline versus growth
```

Leveraged ETFs have low quality scores because they are tactical tools, not long-term compounders.

## Combined Score

Default formula:

```text
combined score = technical score * 65% + quality score * 35%
```

This is why a high-quality company still needs trend confirmation, and a strong chart with weak quality does not automatically become a core holding.

## Signal Action

The signal action is determined after risk checks:

```text
exit candidate
  if price breaks MA200

trim candidate
  if price breaks MA50 and relative strength weakens

signal decay / watch
  if combined score < 40

add candidate
  if score >= 80 and risk checks pass

small position candidate
  if score >= 65 and risk checks pass

watch
  if score >= 50

weak signal / watch
  otherwise
```

The system does not output "must buy" or "must sell"; it outputs decision-support categories.

## LOTS Sizing

LOTS answers:

```text
Given account NAV, price, stop price, and risk budget, how many shares are allowed?
```

Formula:

```text
target_weight_shares = NAV * target_weight / price
risk_budget_shares = NAV * risk_budget / (price - stop_price)
target_shares = min(target_weight_shares, risk_budget_shares)
```

If fractional shares are disabled, shares are rounded down.

For concentrated small-account mode, target weights are intentionally higher than a diversified system, but risk budget still caps share count.

## Real Position vs LOTS

This is used when your real imported position does not match the system's current LOTS sizing.

The system compares:

```text
actual shares
LOTS initial shares
LOTS target shares
actual market value
actual weight in NAV
target weight
share drift
loss if price falls to protection / stop line
stop-loss risk as % of NAV
risk budget
```

Important interpretation:

```text
LOTS does not force you to immediately rebalance old positions.
It tells you whether the current position is oversized, undersized, or close to the current system plan.
```

Example:

```text
actual shares: 80
LOTS target: 35
stop-loss risk: 4.9% NAV
risk budget: 2.0% NAV
action: overallocated / reduce risk in batches
```

## Profit Protection / Exit Rules

For existing positions, the system tracks:

```text
current PnL
highest close since opened_at
highest unrealized PnL
profit giveback
manual stop
system stop
profit floor
ATR trailing stop
dynamic protection line
```

Profit protection starts after the position has reached the configured minimum gain.

Default logic:

```text
profit floor = average cost * (1 + highest PnL * keep ratio)
ATR trailing stop = highest close - ATR14 * trailing ATR multiple
dynamic protection line = max(manual stop, system stop, profit floor, ATR trailing stop)
```

Actions:

```text
profit starts giving back
  -> no add / protect profit

giveback reaches watch threshold
  -> trim 1/3 candidate

giveback reaches trim threshold
  -> trim 1/2 candidate

giveback reaches exit threshold or long-term trend breaks
  -> exit candidate
```

## AI Supervisor

Python does the calculations. AI only reviews selected outputs.

AI checks:

```text
data quality
technical score
quality score
position size
stop / exit posture
concentration risk
leveraged ETF risk
```

Possible AI decisions:

```text
approve_for_consideration
hold
reject
manual_review
```

If no AI key is configured, local rules are used as fallback.

## Report Sections

The report sections mean:

```text
Core 1-2 candidates
  strongest approved candidates after scoring and supervisor review

Supervisor review
  AI or local-rule investment committee review

Real position vs LOTS
  whether your actual imported position is oversized or within risk budget

Profit protection and exit rules
  whether existing positions should be held, protected, trimmed, or marked as exit candidates

Current holdings
  imported positions compared with today's system signal

Full watchlist and LOTS
  all scanned tickers with score, action, shares, stop, and risk notes

Backtest summary
  current basic historical strategy statistics

Data quality
  provider failures, sample data warnings, missing data
```

## Current Limitations

The current strategy is still in validation mode:

```text
not optimized for every market regime
not yet fully parameter-grid tested
basic backtest only
fundamental data is mostly manually scored
earnings calendar risk is not fully automated
```

Use it first for observation, small-lot decisions, and risk discipline before trusting it with larger size.

