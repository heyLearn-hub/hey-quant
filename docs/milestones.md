# Quant AI System Milestones

This file is the project planning source of truth. Before starting a new feature, review this file and update it if scope, order, or acceptance criteria change.

Status legend:

- `Not started`: planned but no implementation work yet.
- `In progress`: active work exists but acceptance criteria are not fully met.
- `Done`: implemented, documented, and covered by tests or smoke checks.
- `Deferred`: intentionally postponed.

## Milestone 0: Project Governance And GitHub Foundation

Status: `Done`

Goal: make the project safe to develop over time and push to GitHub without leaking secrets or runtime data.

Deliverables:

- Initialize and clean the Git repository structure. `Done locally`
- Create or connect a GitHub repository. `Done`
- Keep `.env`, API keys, SQLite databases, reports, caches, logs, and virtualenvs out of Git. `Done`
- Document branch conventions. `Done`
  - `main`: stable versions.
  - `codex/*`: focused development branches from Codex.
  - `dev`: optional integration branch if the project later needs one.
- Add a basic PR checklist for tests, secrets, and docs. `Done`

Acceptance criteria:

- Project can be pushed to GitHub. `Done`
- `pytest` passes. `Done`
- No API keys, real holdings, local reports, or runtime databases are tracked. `Done locally`

## v1.0 Release Target

Status: `In progress`

Goal: ship a production-usable personal quant alert system for the Windows host, while Mac remains the development/PPE machine.

Definition of v1.0:

```text
Windows always-on service -> market/position/news checks -> action-first report -> Telegram alerts -> manual decision
```

v1.0 is not a promise that the strategy will make money. It is the first version that is stable enough to support disciplined manual trading decisions with auditable data quality, sizing, risk, and AI review.

In scope:

- Windows Docker production deployment with dashboard, scheduled daily report, Telegram command listener, and lightweight monitor.
- Real open positions treated as the highest-priority risk surface.
- FMP/yfinance/Stooq data quality checks, with FMP used for paid market data and news when configured.
- Action-first Telegram and HTML reports.
- LOTS sizing, current-position drift checks, profit protection, and exit candidates.
- Public Equity risk fields in every meaningful candidate or risk review:
  - intended alpha;
  - unwanted risk;
  - retained exposure;
  - binding constraint;
  - liquidity/exit posture;
  - monitoring triggers;
  - missing evidence.
- AI Supervisor review only for core candidates, held-position actions, and high-value news/risk events.
- Minimum credible backtest/factor tooling for trend, relative strength, and full-system variants.

Out of scope for v1.0:

- Broker API integration or automatic trading.
- Intraday high-frequency strategy.
- Enterprise-grade instrument master, data sourcing, mapping, and pricing platform.
- Complex machine learning strategy selection.
- Public internet exposure for the dashboard.

v1.0 acceptance criteria:

```bash
.venv/bin/python -m pytest -q
bin/quant-ai-local release-check --config config/default.yaml
bin/quant-ai-local run --config config/default.yaml --offline-sample --out outputs/sample_report.html
bin/quant-ai-local factor-test --config config/default.yaml --offline-sample --out outputs/factor_report.html
docker compose config
```

Windows target-host acceptance:

- `docker compose up -d quant-ai-web` serves `http://127.0.0.1:8765`.
- `/health` returns `ok: true` and no current fatal error.
- `monitor-status` shows recent price/news/data-health state.
- Daily scheduled report runs after the US close and sends Telegram.
- Telegram write commands require `/confirm <id>` before changing SQLite.
- Any missing held-position quote appears as data-fix priority, not as a buy/sell signal.
- No `.env`, API keys, SQLite database, cache, report, or log file is tracked by Git.

## Milestone 1: Local Core System Stable Version

Status: `Done`

Goal: keep the Mac development environment able to run the full offline research pipeline.

Deliverables:

- Free-first market data pipeline.
- Indicator and signal generation.
- LOTS sizing and risk checks.
- Local Supervisor rule review.
- HTML report generation.
- Local web service.
- Offline sample mode for deterministic smoke tests.

Acceptance criteria:

```bash
bin/quant-ai-local run --config config/default.yaml --offline-sample
bin/quant-ai-local factor-test --config config/default.yaml --offline-sample
.venv/bin/python -m pytest -q
```

All commands complete successfully.

## Milestone 2: Position Management V1

Status: `Done`

Goal: let the system know what the user actually holds, then compare holdings with current signals.

Deliverables:

- SQLite storage for positions and trade/action history.
- Web forms for adding and updating holdings.
- Web form for recording buy/add/trim/sell actions.
- Close-position flow.
- Report section for current holdings versus current system signals.

Acceptance criteria:

- A holding can be added from the local web page.
- A trade action can be recorded.
- The report shows the holding, cost, current signal, and stop reference.
- Runtime database files are ignored by Git.

## Milestone 3: Notification Alerts V1

Status: `Done`

Goal: send daily research summaries through Telegram first, with Outlook/SMTP kept as fallback.

Deliverables:

- Telegram Bot API notification sender. `Done`
- Telegram chat id helper command. `Done`
- SMTP config via environment variables.
- Daily summary email body.
- Risk/high-action candidates highlighted in subject/body.
- HTML report attachment.
- Data quality warning included in email body.

Acceptance criteria:

- Telegram sending can be tested with mocked HTTP in tests.
- Email sending can be tested with mocked SMTP in tests.
- A real Windows host can set `.env` variables and run:

```powershell
.\bin\quant-ai-local.ps1 run --config config\default.yaml --out outputs\latest_report.html --send-telegram
```

## Milestone 4: Dockerized Windows Deployment V1

Status: `In progress`

Goal: run the system on a Windows host through Docker while using the Mac as the development and planning machine.

Deliverables:

- Dockerfile. `Done`
- Docker Compose services for web and scheduled jobs. `Done`
- `.env.example` for local secrets. `Done`
- Windows Docker daily job PowerShell helper. `Done`
- Windows Task Scheduler Docker XML template. `Done`
- Docker deployment documentation. `Done`
- Windows Docker update/redeploy helper. `Done on Mac`
- Windows auto-update Task Scheduler template. `Done on Mac`
- Docker Compose config validation. `Done on Mac`
- Release readiness check command. `Done on Mac`
- Local web service available through Docker. `Done on Mac, pending target Windows verification`
- Daily scheduled report command through Docker. `Done on Mac, pending target Windows verification`

Acceptance criteria:

- `docker compose build` succeeds.
- `docker compose up -d quant-ai-web` serves `http://127.0.0.1:8765`.
- `docker compose --profile job run --rm quant-ai-job run --config config/default.yaml --offline-sample --out outputs/docker_sample_report.html` succeeds.
- `bin/quant-ai-local release-check --config config/default.yaml` identifies missing production env/config issues before deployment.
- Windows Task Scheduler can run `scripts/windows_docker_daily_job.ps1` with `-SendTelegram`.
- Windows host can pull from GitHub and redeploy with `scripts/windows_docker_update.ps1`.
- Windows host can poll GitHub and redeploy only when `origin/main` changes.
- `data/`, `outputs/`, and `logs/` persist outside the container.
- `.env` is loaded at runtime and never baked into the image.

Verification notes:

- Mac Docker smoke test passed after Docker Desktop was started: image build succeeded, web service responded on `http://127.0.0.1:8765`, and offline sample report was generated at `outputs/docker_sample_report.html`.
- Windows Task Scheduler and Telegram delivery still need final verification on the target Windows host.

## Milestone 5: Strategy And Factor Experiments V1

Status: `Done`

Goal: support learning and research with simple factor tests before adding more complex strategies.

Deliverables:

- `factor-test` command.
- Basic factors:
  - `mom20`
  - `mom60`
  - `rel20`
  - `rel60`
  - `rsi14`
- Factor report with top/bottom forward returns, spread, and hit rate.

Acceptance criteria:

- Offline factor report can be generated.
- Report explains that factor results are research tools, not direct trading signals.

## Milestone 5A: Profit Protection And Exit Rules V1

Status: `Done`

Goal: reduce the user's pain from large unrealized gains giving back too much before there is an explicit sell decision.

Deliverables:

- Position-level highest close and highest unrealized profit tracking. `Done`
- Profit giveback calculation. `Done`
- Dynamic protection line using manual stop, system stop, profit floor, and ATR trailing stop. `Done`
- Action labels for hold, no-add, trim, and exit candidates. `Done`
- Report section for profit protection and exit rules. `Done`
- Telegram/email summary includes protection triggers. `Done`

Acceptance criteria:

- Given an open position and price history, the system reports current PnL, highest PnL, giveback percentage, dynamic protection line, and protection action.
- Triggered protection actions appear before the generic observation list in the HTML report.
- Unit tests cover profit giveback and missing market-data manual review.

## Milestone 5B: Actual Position vs LOTS Drift Check

Status: `Done`

Goal: compare imported real holdings against current LOTS sizing so old positions do not have to be blindly forced into today's target.

Deliverables:

- Actual shares versus LOTS initial and target shares. `Done`
- Actual position weight versus target weight. `Done`
- Stop-loss risk as percent of NAV. `Done`
- Risk-budget breach detection. `Done`
- HTML report section and Telegram/email summary. `Done`
- Strategy and report explanation document. `Done`

Acceptance criteria:

- Imported positions show whether they are close to LOTS, overallocated, severely overallocated, or need manual review.
- Report explains stop-loss risk versus risk budget.
- The system does not automatically tell the user to immediately rebalance legacy positions; it suggests risk actions.

## Milestone 5C: Actionable Daily Report And Remote Position Commands

Status: `Done`

Goal: make daily alerts decision-useful and allow safe Telegram-based manual position updates on the Windows prod host.

Deliverables:

- Open positions are automatically included in market-data downloads. `Done`
- Missing held-position market data is marked as data-fix priority instead of generic LOTS drift. `Done`
- Telegram report is ordered by action priority. `Done`
- Stock candidates and tactical ETF candidates are separated. `Done`
- HTML report includes a front-page action panel. `Done`
- Telegram write commands require `/confirm <id>` before SQLite mutation. `Done`
- Unauthorized chat ids are rejected. `Done`

Acceptance criteria:

- A report with multiple no-data holdings must state a data-fix action before any candidate list.
- Non-universe holdings can be monitored for exit/protection but do not become buy candidates.
- Telegram command tests prove no write occurs before confirmation.

## Milestone 5D: Lightweight Monitor Foundation

Status: `Done`

Goal: use the Windows always-on service for low-noise position and news monitoring without building an institutional data platform.

Deliverables:

- Symbol alias table for broker symbol to data symbol mapping. `Done`
- Data health table for price/news checks. `Done`
- Pricing snapshots for latest monitored quotes. `Done`
- News event dedupe table. `Done`
- Monitor alert dedupe table. `Done`
- `monitor-once`, `monitor-status`, `alias-list`, and `alias-set` commands. `Done`
- Dashboard alias entry and data-health view. `Done`
- Background monitor listener in `quant-ai-web`. `Done`

Acceptance criteria:

- Alias mapping allows a broker symbol to use a vendor symbol while preserving the broker symbol in reports.
- Missing quote data creates a data-fix alert instead of a trading signal.
- Repeated price/data/news events are deduped.
- Monitor failures do not block the dashboard or Telegram command listener.

## Milestone 6: Backtest System Enhancement

Status: `In progress`

Goal: make strategy results more credible before relying on them.

Deliverables:

- Factor Research Pack v1 registry and grouped report. `Done`
- Additional OHLCV factors for trend, momentum, volatility, drawdown, and risk-adjusted momentum. `Done`
- Factor report states that results are research tools and do not automatically change production buy/sell rules. `Done`
- Options and market sentiment are explicitly deferred until the base factor report proves the need. `Done`
- In-sample and out-of-sample split.
- Parameter grid tests, such as 20/60/120-day momentum.
- Market regime slices.
- Benchmark comparison against `QQQ`, `SMH`, and `SPY`.
- Clear transaction cost and slippage assumptions.
- Drawdown analysis.

Acceptance criteria:

- Any proposed strategy variation can produce a backtest report with:
  - annualized return;
  - max drawdown;
  - Sharpe;
  - win rate;
  - profit factor;
  - turnover;
  - average holding days;
  - benchmark-relative return.

## Milestone 7: AI Supervisor V2

Status: `In progress`

Goal: make AI review more useful while keeping Python as the deterministic calculation layer.

Deliverables:

- AI reviews only core candidates and current holdings requiring action.
- AI reviews earnings/calendar risk when available.
- AI can summarize relevant news or thesis changes when explicitly supplied or connected later.
- AI decisions are logged for later review. `Done`
- AI output remains structured:
  - `approve_for_consideration`
  - `hold`
  - `reject`
  - `manual_review`

Acceptance criteria:

- AI never approves when data quality is blocked.
- AI output references system-calculated data.
- Reports and emails can display AI review results.
- Dashboard and `supervisor-log` can show recent AI/local-rule decision history.
- Python rules remain available as fallback.

## Milestone 7A: AI Provider Adapter V1

Status: `Done`

Goal: support low-cost AI supervisor review while keeping local rules as a fallback.

Deliverables:

- DeepSeek provider through OpenAI-compatible chat completions. `Done`
- OpenAI provider through chat completions. `Done`
- Provider config for model, env var names, and DeepSeek base URL. `Done`
- Missing-key behavior with local fallback unless `require_api` is true. `Done`
- Unit tests for fallback, missing-key blocking, and DeepSeek JSON parsing. `Done`

Acceptance criteria:

- `.env` can provide `DEEPSEEK_API_KEY` without committing secrets.
- The default config uses `provider: deepseek` and `model: deepseek-v4-pro`.
- If AI review fails, the report still completes with local rule fallback and marks the review as manual.

## Milestone 8: Paid Market Data Integration

Status: `In progress`

Goal: use FMP Starter as the primary paid market-data provider while retaining free-source fallback.

Candidate providers:

- FMP
- EODHD
- Tiingo
- Polygon/Massive

Deliverables:

- FMP Starter selected as paid provider. `Done`
- Credentials loaded through `.env` / `FMP_API_KEY`. `Done`
- Coverage test command for every configured ticker. `Done`
- FMP stock news research check command. `Done`
- HTML/Telegram/email news risk summary. `Done`
- Adjusted price validation. `Pending`
- ETF availability validation. `Pending`
- Historical depth validation.
- Press release / earnings calendar integration. `Pending`
- Provider comparison report.
- Free data source fallback retained. `Done`

Acceptance criteria:

- Target universe coverage is close to complete.
- Missing data appears clearly in report and email.
- Paid source failure does not generate false buy signals.
- Provider credentials are loaded from `.env` or environment variables only.

## Update Rules

- Update this file when the project direction changes.
- Keep milestones small enough to finish and verify.
- Mark a milestone `Done` only after implementation, documentation, and tests/smoke checks are complete.
- Do not store credentials, real holdings, or local runtime state in this document.
