# Docker Deployment

Docker is the preferred deployment path for the Windows host. It keeps Python, packages, and runtime paths consistent between Mac development and Windows production.

## Runtime Shape

```text
quant-ai-web
  local web UI at http://127.0.0.1:8765

quant-ai-job
  one-shot job for scheduled report/email generation
```

Persistent local folders:

```text
data/       SQLite holdings and market data cache
outputs/    HTML reports
logs/       service/job logs
config/     user-editable config
```

Secrets live in `.env`, never in the image.

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

## Offline Smoke Test

```bash
docker compose --profile job run --rm quant-ai-job run --config config/default.yaml --offline-sample --out outputs/docker_sample_report.html
docker compose --profile job run --rm quant-ai-job factor-test --config config/default.yaml --offline-sample --out outputs/docker_factor_report.html
```

## Daily Report Job

Without email:

```bash
docker compose --profile job run --rm quant-ai-job run --config config/default.yaml --out outputs/latest_report.html
```

With email:

```bash
docker compose --profile job run --rm quant-ai-job run --config config/default.yaml --out outputs/latest_report.html --send-email
```

## Windows Task Scheduler

Use this helper:

```powershell
.\scripts\windows_docker_daily_job.ps1 -ProjectRoot "C:\path\to\hey-quant" -SendEmail
```

Or import:

```text
scripts/windows_docker_daily_email_task.xml
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
