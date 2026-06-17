# Quant AI System Milestones

This file is the project planning source of truth. Before starting a new feature, review this file and update it if scope, order, or acceptance criteria change.

Status legend:

- `Not started`: planned but no implementation work yet.
- `In progress`: active work exists but acceptance criteria are not fully met.
- `Done`: implemented, documented, and covered by tests or smoke checks.
- `Deferred`: intentionally postponed.

## Milestone 0: Project Governance And GitHub Foundation

Status: `Not started`

Goal: make the project safe to develop over time and push to GitHub without leaking secrets or runtime data.

Deliverables:

- Initialize and clean the Git repository structure.
- Create or connect a GitHub repository.
- Keep `.env`, API keys, SQLite databases, reports, caches, logs, and virtualenvs out of Git.
- Document branch conventions:
  - `main`: stable versions.
  - `dev`: integration branch.
  - `feature/*`: focused feature branches.
- Add a basic PR checklist for tests, secrets, and docs.

Acceptance criteria:

- Project can be pushed to GitHub.
- `pytest` passes.
- No API keys, real holdings, local reports, or runtime databases are tracked.

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

## Milestone 3: Email Alerts V1

Status: `Done`

Goal: send daily research summaries through Outlook/SMTP.

Deliverables:

- SMTP config via environment variables.
- Daily summary email body.
- Risk/high-action candidates highlighted in subject/body.
- HTML report attachment.
- Data quality warning included in email body.

Acceptance criteria:

- Email sending can be tested with mocked SMTP in tests.
- A real Windows host can set `.env` variables and run:

```powershell
.\bin\quant-ai-local.ps1 run --config config\default.yaml --out outputs\latest_report.html --send-email
```

## Milestone 4: Windows Deployment V1

Status: `In progress`

Goal: run the system on a Windows host while using the Mac as the development and planning machine.

Deliverables:

- PowerShell launcher.
- Batch launcher.
- Windows Task Scheduler XML template.
- Windows setup instructions.
- Local web service available on Windows.
- Daily scheduled report and email command.

Acceptance criteria:

- Windows host can run the local web service at `http://127.0.0.1:8765`.
- Windows Task Scheduler can run the daily report command.
- Logs and outputs are inspectable.
- The service survives a Windows reboot or can be restarted predictably.

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

Status: `Not started`

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

