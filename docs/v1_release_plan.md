# Quant AI v1.0 Release Plan

This file defines what must be true before the project is treated as v1.0. It is intentionally narrower than the long-term product vision.

## Current Progress

| Area | Status | Current capability | v1.0 gap |
| --- | --- | --- | --- |
| Local quant core | Done | Data pipeline, indicators, signals, LOTS, risk, HTML report | Keep stable and documented |
| Position management | Done | SQLite positions/trades, dashboard edits, close-position flow | Verify with Windows production data |
| Telegram alerts | Done | Action-first daily summary and confirmed remote position writes | Tune real-world noise level |
| Docker Windows deployment | In progress | Dockerfile, compose, daily job, update scripts, auto-update template | Windows target-host verification |
| FMP market/news data | In progress | FMP price provider, data-check, news-check, news summary, monitor quotes | Adjusted-price, ETF, press release, earnings calendar validation |
| Action-first reports | Done | Data blockers, position actions, stock/ETF split, report quality checks | Continue improving report language from real examples |
| Lightweight monitor | Done | alias, data_health, pricing snapshots, news dedupe, monitor alerts | Validate long-running Windows behavior |
| AI Supervisor | In progress | DeepSeek/OpenAI adapter, local fallback, structured decisions, SQLite decision log | Add high-value news review discipline |
| Backtest/factor research | In progress | Factor registry, grouped factor report, expanded OHLCV factors, and three strategy backtest variants | Add in/out-of-sample and clearer regime/parameter reporting |

## v1.0 Product Goal

v1.0 is a personal swing-trading decision support system:

```text
Windows production service
  -> market data and position monitor
  -> deterministic Python signal/risk engine
  -> AI Supervisor review for high-value decisions
  -> HTML dashboard and Telegram alerts
  -> user makes the final manual trade decision
```

The product is not an automatic trading system and does not connect to a broker.

## v1.0 Release Stages

### Stage 1: Release Readiness Baseline

Goal: make the current system measurable and stop relying on memory.

Deliverables:

- `release-check` CLI command.
- Updated milestone and development workflow docs.
- Stable v1.0 scope, exclusions, and acceptance criteria.
- Stale GitHub/auth/model-status documentation removed.

Exit criteria:

```bash
bin/quant-ai-local release-check --config config/default.yaml
.venv/bin/python -m pytest -q
```

### Stage 2: Windows Production Verification

Goal: prove the Windows host can run the system continuously.

Deliverables:

- `quant-ai-web` running through Docker on Windows.
- `/health` reachable locally.
- Telegram command listener active.
- Monitor loop active.
- Daily scheduled report verified.
- Auto-update task verified after a GitHub push.

Exit criteria:

- Windows service runs for at least 48 hours without manual restart.
- One scheduled daily report is sent after the US close.
- One `/pos` command and one confirmed write command work from Telegram.
- `monitor-status` shows recent data-health checks.

### Stage 3: Data Coverage And Symbol Repair

Goal: make real positions and watchlist symbols reliable before trusting signals.

Deliverables:

- FMP coverage report for configured universe, leveraged ETFs, benchmarks, and open positions.
- `data-quality` CLI gate that combines provider coverage, open positions, symbol aliases, asset class, and Public Equity risk fields.
- Alias repair queue for broker symbols that are not covered by FMP/yfinance/Stooq.
- ETF and leveraged ETF coverage validation.
- Adjusted daily-price validation for split/dividend handling.

Exit criteria:

- No open position is silently ignored.
- Missing data produces `data_fix_required`, not a trading signal.
- Any alias mapping preserves the broker symbol in reports while using the mapped data symbol for pricing.
- CLI exits non-zero when a blocked ticker or open-position data repair issue would make live signals unsafe.

### Stage 4: Action Quality And Public Equity Risk Discipline

Goal: ensure every actionable idea has a real risk decision frame.

Every actionable candidate, held-position action, and high-priority news item must include:

- intended alpha;
- unwanted risk;
- retained exposure;
- binding constraint;
- liquidity/exit posture;
- hedge or size-down tradeoff where relevant;
- monitoring triggers;
- implementation-readiness gaps.

Exit criteria:

- Telegram does not send generic observation-pool noise.
- Core candidates without price, stop, LOTS shares, or Supervisor approval are downgraded to research observation.
- Tactical ETF ideas are separate from ordinary stock candidates.
- AI cannot approve data-blocked candidates.

### Stage 5: AI Supervisor V2

Goal: use AI only where it adds judgment.

Deliverables:

- AI review decision log. `Done`
- High-value news review path.
- Clear fallback when AI API fails.
- Cost/noise control: no AI review of the full universe every cycle.

Exit criteria:

- AI reviews only core candidates, current holdings requiring action, and high-value news/risk events.
- AI output is structured as `approve_for_consideration`, `hold`, `reject`, or `manual_review`.
- Reports show whether a decision came from AI, local fallback, or manual-review status.
- `supervisor-log` shows recent decisions with provider, final action, approval score, and blockers.

### Stage 6: Minimum Credible Backtest

Goal: make the strategy research good enough to challenge, not just display.

Deliverables:

- Factor registry and grouped factor research report. `Done`
- Expanded OHLCV factor set for trend, momentum, volatility, drawdown, and risk-adjusted momentum. `Done`
- In-sample and out-of-sample split.
- Parameter grid for momentum windows such as 20/60/120.
- Benchmark-relative results versus `QQQ`, `SMH`, and `SPY`.
- Transaction cost and slippage assumptions shown in the report.

Exit criteria:

- The report includes annualized return, max drawdown, Sharpe, win rate, profit factor, turnover, average holding days, and benchmark-relative return.
- Backtest trades do not occur before signal dates.
- A weak factor can be rejected instead of promoted into production.

## v1.0 Acceptance Checklist

Local/PPE:

```bash
.venv/bin/python -m pytest -q
bin/quant-ai-local release-check --config config/default.yaml
bin/quant-ai-local run --config config/default.yaml --offline-sample --out outputs/sample_report.html
bin/quant-ai-local factor-test --config config/default.yaml --offline-sample --out outputs/factor_report.html
docker compose config
```

Windows/prod:

- Docker web service starts and serves `http://127.0.0.1:8765`.
- `/health` returns a healthy JSON response.
- Daily scheduled Telegram report works.
- Telegram remote write commands require confirmation.
- Monitor sends at most useful, deduped risk/news alerts.
- Missing data is visible as a blocker.
- Runtime secrets and databases remain local and untracked.

## Out Of Scope Before v1.0

- Broker API and automatic execution.
- Intraday high-frequency trading.
- Machine-learning strategy selection.
- Public internet exposure.
- Enterprise data platform capabilities beyond aliases, data health, pricing snapshots, and news dedupe.
