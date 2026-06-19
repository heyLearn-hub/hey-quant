# Docker Deployment

Docker is the preferred deployment path for the Windows host. It keeps Python, packages, and runtime paths consistent between Mac development and Windows production.

## Runtime Shape

```text
quant-ai-web
  local web UI at http://127.0.0.1:8765

quant-ai-job
  one-shot job for scheduled report/Telegram generation
```

Persistent local folders:

```text
data/       SQLite holdings and market data cache
outputs/    HTML reports
logs/       service/job logs
config/     user-editable config
```

Secrets live in `.env`, never in the image.

For paid FMP market data, put this in `.env`:

```text
FMP_API_KEY=your_fmp_key
```

## First Setup

```bash
cp .env.example .env
docker compose build
docker compose up -d quant-ai-web
```

If `docker compose build` cannot connect to the Docker daemon, start Docker Desktop first and rerun the command.

Open:

```text
http://127.0.0.1:8765
```

By default the web service binds to `127.0.0.1` on the host. Keep this setting for local use. For remote access, prefer Tailscale or another private network instead of exposing the port directly to the public internet.

## Offline Smoke Test

```bash
docker compose --profile job run --rm quant-ai-job run --config config/default.yaml --offline-sample --out outputs/docker_sample_report.html
docker compose --profile job run --rm quant-ai-job factor-test --config config/default.yaml --offline-sample --out outputs/docker_factor_report.html
```

## Market Data Check

Validate FMP coverage before relying on live signals:

```bash
docker compose --profile job run --rm quant-ai-job data-check --config config/default.yaml --provider fmp
```

The command exits with code `0` only when all checked tickers have enough recent rows. Missing or stale tickers should be fixed before treating signals as live.

Validate FMP news coverage for candidate or held tickers:

```bash
docker compose --profile job run --rm quant-ai-job news-check --config config/default.yaml --tickers NVDA,MSFT,TSLA
```

News checks are research context only. A headline can add a catalyst or risk flag, but it does not override trend, LOTS sizing, stop rules, or data-quality checks.

## Daily Report Job

Without email:

```bash
docker compose --profile job run --rm quant-ai-job run --config config/default.yaml --out outputs/latest_report.html
```

With Telegram:

```bash
docker compose --profile job run --rm quant-ai-job run --config config/default.yaml --out outputs/latest_report.html --send-telegram
```

To discover the Telegram chat id, first send `/start` to the bot, set `TELEGRAM_BOT_TOKEN` in `.env`, then run:

```bash
docker compose --profile job run --rm quant-ai-job telegram-chat-id --config config/default.yaml
```

## Telegram Remote Position Commands

Telegram write commands are handled by the long-running web service, not the one-shot job:

```bash
docker compose up -d --build quant-ai-web
```

When `.env` contains `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`, the service polls Telegram and accepts commands only from that configured chat id.

Supported commands:

```text
/pos
/buy TICKER SHARES PRICE note
/add TICKER SHARES PRICE note
/trim TICKER SHARES PRICE note
/sell TICKER SHARES PRICE note
/stop TICKER PRICE
/note TICKER text
/confirm <id>
```

Write commands first create a pending action. The SQLite portfolio changes only after `/confirm <id>`. This records manual trades and stops; it does not connect to a broker or place orders.

## Lightweight Monitor And Aliases

The long-running web service also starts a lightweight monitor when `monitor.enabled` is true. This is not an institutional data platform. It only keeps enough local state for personal alerts:

```text
symbol aliases
latest pricing snapshots
data health checks
deduped news events
deduped monitor alerts
```

Useful commands:

```bash
docker compose --profile job run --rm quant-ai-job alias-list --config config/default.yaml
docker compose --profile job run --rm quant-ai-job alias-set SNXX NVDA --config config/default.yaml --note "broker symbol mapping"
docker compose --profile job run --rm quant-ai-job monitor-once --config config/default.yaml
docker compose --profile job run --rm quant-ai-job monitor-status --config config/default.yaml
```

If a broker symbol has no vendor coverage, add an alias rather than editing the original position ticker. Reports keep the broker symbol visible while data pulls use the mapped symbol.

Production state rule:

```text
GitHub syncs code only.
Windows data/portfolio.sqlite3 is the source of truth for real positions.
Do not copy SQLite bidirectionally between Mac/PPE and Windows/prod.
```

## Updating From GitHub

Normal release flow:

```text
Mac development -> git push GitHub -> Windows host pulls -> Docker rebuilds -> service restarts
```

On the Mac development machine:

```bash
git status
git push origin main
```

On the Windows host, run:

```powershell
.\scripts\windows_docker_update.ps1 -ProjectRoot "C:\path\to\hey-quant"
```

The update script does this:

```text
check Docker is running
check Git working tree is clean
git fetch origin main
git checkout main
git pull --ff-only origin main
docker compose build
docker compose up -d quant-ai-web
offline sample report smoke test
HTTP check at http://127.0.0.1:8765
```

Useful options:

```powershell
.\scripts\windows_docker_update.ps1 -ProjectRoot "C:\path\to\hey-quant" -Branch main
.\scripts\windows_docker_update.ps1 -ProjectRoot "C:\path\to\hey-quant" -OnlyWhenRemoteChanged
.\scripts\windows_docker_update.ps1 -ProjectRoot "C:\path\to\hey-quant" -SkipPull
.\scripts\windows_docker_update.ps1 -ProjectRoot "C:\path\to\hey-quant" -SkipSmokeTest
```

## Auto Update After Push

The Windows host can poll GitHub and redeploy automatically after every Mac-side push. This avoids exposing a public webhook endpoint from the home Windows machine.

Import this Task Scheduler template:

```text
scripts/windows_docker_auto_update_task.xml
```

Before importing, replace `__PROJECT_ROOT__` with the absolute Windows project path.

The task runs every 10 minutes and calls:

```powershell
.\scripts\windows_docker_update.ps1 -ProjectRoot "C:\path\to\hey-quant" -OnlyWhenRemoteChanged
```

Behavior:

```text
fetch origin/main
if remote commit equals local commit: stop
if remote commit is new: pull, rebuild Docker, restart web service, run smoke test
```

The update script uses a lock file under `logs/` so overlapping scheduled runs do not deploy at the same time.

For remote operation, prefer one of these:

- Tailscale SSH or another private VPN command session.
- Windows Remote Desktop.
- Sunlogin/向日葵 for manual maintenance.

Do not expose the Docker web port directly to the public internet.

## Windows Task Scheduler

Use this helper:

```powershell
.\scripts\windows_docker_daily_job.ps1 -ProjectRoot "C:\path\to\hey-quant" -SendTelegram
```

Or import:

```text
scripts/windows_docker_daily_telegram_task.xml
```

Before importing, replace `__PROJECT_ROOT__` with the absolute project path on the Windows host.

## Useful Commands

```bash
docker compose ps
docker compose logs -f quant-ai-web
docker compose restart quant-ai-web
docker compose down
```

## Notes

- The Docker image does not contain `.env`, reports, cache, logs, or holdings.
- If market data providers fail, the report should show data-quality issues rather than silently approving signals.
- Scheduler-based daily runs are intentional for the current low-frequency trend strategy.
