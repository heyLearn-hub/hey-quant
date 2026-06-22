# Telegram Interactive Analyst v1 Design

## Decision: Is This Worth Doing?

Yes. The current system already produces scheduled daily reports and passive monitor alerts, but the user also needs an active decision loop: ask about a ticker, current position, or proposed trade, then receive structured feedback before acting manually.

This is especially useful for a small, concentrated, high-volatility US tech/AI/semiconductor portfolio. The main user pain is not a lack of market information; it is deciding when to add, trim, protect profit, or avoid chasing a move. A Telegram analyst command layer can turn the existing market data, data-quality gate, positions database, LOTS logic, news checks, and Supervisor discipline into an on-demand risk review.

## Goals

- Add Telegram commands for all three requested active workflows:
  - `A`: `/plan` trade plan review.
  - `B`: `/position` current holding review.
  - `C`: `/check` single ticker quick analysis.
- Keep responses short enough for Telegram but structured enough to support decisions.
- Use deterministic Python calculations first, with AI/Supervisor as a final review layer where configured.
- Include Public Equity risk fields in every actionable response:
  - intended alpha
  - unwanted risk
  - retained exposure
  - binding constraint
  - liquidity/exit posture
- Respect the existing safety boundary: no broker API, no automatic order placement, no database write unless the user uses the existing confirmed write commands.

## Non-Goals

- No open-ended free-text chatbot in v1.
- No automatic trading or broker execution.
- No minute-level VWAP unless a reliable intraday data source is added later.
- No option wall, gamma exposure, IV rank, or options sentiment in v1.
- No guarantee that news alone can create a buy signal.
- No mutation of SQLite positions from `/plan`, `/check`, or `/position`.
- No replacement of the daily report or scheduled monitor.

## User Commands

### `/check TICKER`

Purpose: quick single-name analysis for a stock, ETF, or leveraged ETF.

Example:

```text
/check MRVL
```

Required output:

- conclusion: `watch`, `small_probe_candidate`, `do_not_chase`, `research_only`, or `data_fix_required`;
- technical state: trend, momentum, RSI, ATR percentage, and relative strength where available;
- news/events: FMP news risk and catalyst flags;
- data quality: tradable/research-only/blocked status;
- execution posture: whether the ticker can be considered for a live decision;
- Public Equity risk fields;
- Supervisor final decision.

### `/position TICKER`

Purpose: review an existing holding and answer whether the position needs action.

Example:

```text
/position SNXX
```

Required output:

- current position: shares, average cost, latest price, market value, unrealized P&L;
- position action: `hold`, `protect_profit`, `trim_candidate`, `exit_candidate`, or `data_fix_required`;
- manual stop and dynamic risk reference where available;
- profit giveback and loss severity review;
- LOTS drift context when calculable;
- news/risk flags;
- Public Equity risk fields;
- Supervisor final decision.

If the ticker is not an open position, the command must say so and suggest `/check TICKER` instead of inventing holding advice.

### `/plan ACTION TICKER SHARES PRICE [stop STOP_PRICE]`

Purpose: review a proposed manual trade before the user acts in the broker app.

Examples:

```text
/plan buy INTC 5 135 stop 128
/plan add SNXX 20 46 stop 41
/plan trim AAOX 30 42
/plan sell LNOK 79 70
```

Supported actions:

- `buy`
- `add`
- `trim`
- `sell`

Required output:

- parsed trade plan;
- notional amount and percentage of NAV;
- maximum loss if a stop is supplied;
- risk budget usage as percentage of NAV;
- whether the plan respects LOTS and concentration constraints;
- portfolio impact: theme exposure, leveraged ETF exposure, and open-position overlap;
- execution posture: `approve_small_probe`, `hold`, `reject`, or `manual_review`;
- Public Equity risk fields;
- Supervisor final decision.

`/plan` is review-only. It must not create a pending write confirmation and must not change positions or trades.

## Response Contract

Every response should use this compact Telegram structure:

```text
Quant AI Analyst · COMMAND
TICKER: conclusion

1. 技术/数据
2. 新闻/事件
3. 持仓/组合影响
4. LOTS/风控
5. Public Equity 风控
6. Supervisor
```

The message should stay concise. Long explanations belong in future HTML reports, not Telegram.

## Architecture

Add:

```text
src/quant_ai_system/interactive_analyst.py
```

Core dataclasses:

```text
AnalystRequest
AnalystResponse
TradePlan
PositionReview
TickerCheck
```

Core functions:

```text
analyze_ticker(config, ticker)
analyze_position(config, ticker)
review_trade_plan(config, plan)
format_analyst_response(response)
```

Telegram integration:

```text
src/quant_ai_system/telegram_commands.py
```

The existing `TelegramCommandProcessor` should route:

- `/check` to `analyze_ticker`
- `/position` to `analyze_position`
- `/plan` to `review_trade_plan`

Existing write commands stay unchanged:

- `/buy`
- `/add`
- `/trim`
- `/sell`
- `/stop`
- `/note`
- `/confirm`

## Data Flow

```text
Telegram command
  -> authorized TELEGRAM_CHAT_ID check
  -> command parser
  -> SQLite positions and aliases
  -> market data / quote / daily OHLCV
  -> data-quality gate
  -> indicators, LOTS, risk, news
  -> local or AI Supervisor review
  -> compact Telegram response
```

## Data Sources

v1 should reuse existing project capabilities:

- FMP quote and stock news where configured;
- daily OHLCV through current market data provider chain;
- SQLite positions and aliases;
- `data-quality` status for tradable/research-only/blocked;
- current indicator functions for MA, momentum, RSI, ATR, and relative strength;
- current LOTS/risk defaults;
- local Supervisor fallback when AI provider fails.

If FMP quote fails but daily data is available, the response may use the latest daily close and mark the quote freshness limitation. If both quote and daily data fail, the response must be `data_fix_required` or `blocked`.

## Public Equity Risk Discipline

Every actionable response must state:

- `intended_alpha`: why this ticker or trade could make money if it works.
- `unwanted_risk`: what exposure or bad behavior the system is trying to avoid.
- `retained_exposure`: what exposure remains after the action or current holding state.
- `binding_constraint`: the strongest reason limiting size or blocking action.
- `liquidity_exit_posture`: whether the user can reasonably hold, add, trim, exit, or must repair data first.

For v1 these fields can be deterministic templates enriched with computed values. The Codex plugin is not called from the running service; the project implements the risk discipline in Python.

## Decision Rules

### `/check`

- `data_fix_required`: no usable quote or daily data.
- `research_only`: limited/stale data or missing risk inputs.
- `do_not_chase`: strong trend but overextended, high ATR, or high gap/news risk.
- `small_probe_candidate`: tradable data, trend confirmed, risk budget allows only small initial size.
- `watch`: tradable but no clear entry or risk/reward edge.

### `/position`

- `data_fix_required`: open position cannot be priced.
- `exit_candidate`: below manual stop, severe loss, or major trend failure.
- `trim_candidate`: near stop, risk budget too high, or position materially exceeds LOTS.
- `protect_profit`: unrealized gain is meaningful and giveback risk requires a protection line.
- `hold`: no action trigger.

### `/plan`

- `reject`: missing/invalid stop for buy/add when risk cannot be bounded, data blocked, or size violates hard constraints.
- `manual_review`: news/data/portfolio risk is conflicted.
- `hold`: trade is not currently justified even if mechanically possible.
- `approve_small_probe`: size and risk budget are acceptable for a small manual trade.

These are review labels, not order instructions.

## Error Handling

- Unauthorized chat IDs are rejected exactly like existing Telegram commands.
- Malformed commands return usage examples.
- Missing ticker, invalid shares, invalid prices, or negative values return a validation message.
- Missing FMP key or provider failures must not crash the listener.
- Data blocks must appear in the response before any trading interpretation.
- AI/Supervisor API failure must fall back to local rules and mark the review as local/fallback.
- `/position` for a non-held ticker must not create a synthetic position review.
- `/plan` must not write to SQLite or create pending confirmation.

## Testing Plan

Use TDD before implementation.

Unit tests:

- `/check TICKER` routes to analyst logic and returns the Public Equity risk fields.
- `/position TICKER` returns holding advice for an open position.
- `/position TICKER` returns a clear not-held message when ticker is not open.
- `/plan buy INTC 5 135 stop 128` calculates notional, NAV percentage, and max loss.
- `/plan` does not mutate positions or trades.
- blocked data produces `data_fix_required` and does not produce buy/add approval.
- profit position produces `protect_profit` when gain/giveback conditions are met.
- leveraged ETF responses identify tactical exposure and lower sizing posture.
- unauthorized chat IDs cannot access analyst commands.
- malformed commands return usage text without crashing.

Integration tests:

- Telegram command processor can serve `/pos`, write commands, and new analyst commands together.
- Analyst commands work when FMP/news calls are mocked.
- AI/Supervisor failure falls back to local rule review.
- Existing daily report, monitor, and confirmed write commands keep passing.

## Acceptance Criteria

```bash
.venv/bin/python -m pytest tests/test_interactive_analyst.py tests/test_telegram_commands.py -q
.venv/bin/python -m pytest -q
```

Manual command examples should produce useful Telegram text:

```text
/check MRVL
/position SNXX
/plan buy INTC 5 135 stop 128
```

The output must answer:

- Is the ticker actionable, research-only, or blocked?
- If it is a holding, should the user hold, protect profit, trim, or exit?
- If it is a proposed trade, does the plan fit NAV, LOTS, stop, and concentration limits?
- What is the intended alpha?
- What risk is unwanted?
- What exposure remains?
- What is the binding constraint?
- What is the liquidity/exit posture?
- What did the Supervisor conclude?

## Follow-Up Scope

After v1 is stable, consider:

- natural language aliases that translate "帮我看看 MRVL" into `/check MRVL`;
- optional intraday VWAP if a minute-data source is selected;
- option sentiment and option wall analysis;
- an HTML detail link for longer analyst reports;
- saving analyst reviews into SQLite for later trade journaling.
