# Quant AI System Milestones

This file is the project planning source of truth. Before starting a new feature, review this file and update it if scope, order, or acceptance criteria change.

Status legend:

- `Not started`: planned but no implementation work yet.
- `In progress`: active work exists but acceptance criteria are not fully met.
- `Done`: implemented, documented, and covered by tests or smoke checks.
- `Deferred`: intentionally postponed.

## Milestone 0: Project Governance And GitHub Foundation

Status: `In progress`

Goal: make the project safe to develop over time and push to GitHub without leaking secrets or runtime data.

Deliverables:

- Initialize and clean the Git repository structure. `Done locally`
- Create or connect a GitHub repository. `Remote configured; push blocked by permission`
- Keep `.env`, API keys, SQLite databases, reports, caches, logs, and virtualenvs out of Git. `Done`
- Document branch conventions. `Done`
  - `main`: stable versions.
  - `dev`: integration branch.
  - `feature/*`: focused feature branches.
- Add a basic PR checklist for tests, secrets, and docs. `Done`

Acceptance criteria:

- Project can be pushed to GitHub. `Blocked: current GitHub credential lacks write access`
- `pytest` passes. `Done`
- No API keys, real holdings, local reports, or runtime databases are tracked. `Done locally`

Blocker:

- `git push -u origin main` currently fails with GitHub `403` because the authenticated user does not have write permission to `heyLearn-hub/hey-quant`.

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
- Docker Compose config validation. `Done on Mac`
- Local web service available through Docker. `Done on Mac, pending target Windows verification`
- Daily scheduled report command through Docker. `Done on Mac, pending target Windows verification`

Acceptance criteria:

- `docker compose build` succeeds.
- `docker compose up -d quant-ai-web` serves `http://127.0.0.1:8765`.
- `docker compose --profile job run --rm quant-ai-job run --config config/default.yaml --offline-sample --out outputs/docker_sample_report.html` succeeds.
- Windows Task Scheduler can run `scripts/windows_docker_daily_job.ps1` with `-SendTelegram`.
- Windows host can pull from GitHub and redeploy with `scripts/windows_docker_update.ps1`.
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

## Milestone 6: Backtest System Enhancement

Status: `Not started`

Goal: make strategy results more credible before relying on them.

Deliverables:

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
- AI decisions are logged for later review.
- AI output remains structured:
  - `approve_for_consideration`
  - `hold`
  - `reject`
  - `manual_review`

Acceptance criteria:

- AI never approves when data quality is blocked.
- AI output references system-calculated data.
- Reports and emails can display AI review results.
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
- The default config uses `provider: deepseek` and `model: deepseek-v4-flash`.
- If AI review fails, the report still completes with local rule fallback and marks the review as manual.

## Milestone 8: Paid Market Data Integration

Status: `Deferred`

Goal: add a paid provider only when free sources become a practical blocker.

Candidate providers:

- FMP
- EODHD
- Tiingo
- Polygon/Massive

Deliverables:

- Coverage test for every configured ticker.
- Adjusted price validation.
- ETF availability validation.
- Historical depth validation.
- Provider comparison report.
- Free data source fallback retained.

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
