# Windows Codex Handoff

This document is the handoff checklist for moving day-to-day operation from the Mac development machine to the Windows host.

For normal code updates, use `scripts/windows_docker_update.ps1`; do not repeat this handoff checklist. This file is mainly for first setup or for a new Windows Codex thread that needs project context.

## Target Shape

```text
Mac
  development, commits, planning

GitHub
  source of truth: heyLearn-hub/hey-quant

Windows
  Docker runtime, scheduled Telegram alerts, local dashboard
```

The Windows host should not edit strategy code directly unless we intentionally switch development there. It should normally pull from GitHub and redeploy.

## One-Time Windows Setup

Install:

- Git for Windows
- Docker Desktop
- Codex
- Tailscale or your preferred private remote access tool

Clone the repository:

```powershell
cd C:\Users\<you>\Documents
git clone https://github.com/heyLearn-hub/hey-quant.git
cd hey-quant
```

If GitHub asks for login, use the GitHub account that owns or can write to `heyLearn-hub/hey-quant`.

Create local runtime config:

```powershell
copy .env.example .env
```

Edit `.env` locally. Do not commit it.

Required for Telegram:

```text
TELEGRAM_BOT_TOKEN=your_rotated_bot_token
TELEGRAM_CHAT_ID=your_chat_id
```

Optional for AI Supervisor:

```text
DEEPSEEK_API_KEY=your_deepseek_key
# or
OPENAI_API_KEY=your_openai_key
```

The default AI provider is DeepSeek. If no AI key is configured, the system falls back to local supervisor rules unless `supervisor.require_api` is set to `true`.

Important: if a Telegram bot token was ever pasted into chat, rotate it in BotFather before using it for production.

Find chat id:

1. Send `/start` to the Telegram bot.
2. Put `TELEGRAM_BOT_TOKEN` in `.env`.
3. Run:

```powershell
docker compose --profile job run --rm quant-ai-job telegram-chat-id --config config/default.yaml
```

## First Docker Run

```powershell
docker compose build
docker compose up -d quant-ai-web
```

Open:

```text
http://127.0.0.1:8765
```

Smoke test:

```powershell
docker compose --profile job run --rm quant-ai-job run --config config/default.yaml --offline-sample --out outputs/windows_smoke_report.html
```

Telegram test:

```powershell
docker compose --profile job run --rm quant-ai-job run --config config/default.yaml --offline-sample --out outputs/windows_telegram_test.html --send-telegram
```

## Daily Operation

Run the daily Telegram report manually:

```powershell
.\scripts\windows_docker_daily_job.ps1 -ProjectRoot "C:\Users\<you>\Documents\hey-quant" -SendTelegram
```

For Task Scheduler, import:

```text
scripts/windows_docker_daily_telegram_task.xml
```

Before importing, replace `__PROJECT_ROOT__` with the real Windows path.

## Pull Updates From Mac/GitHub

After the Mac side pushes changes to GitHub, run on Windows:

```powershell
.\scripts\windows_docker_update.ps1 -ProjectRoot "C:\Users\<you>\Documents\hey-quant"
```

The script performs:

```text
git pull --ff-only
docker compose build
docker compose up -d quant-ai-web
offline sample smoke test
HTTP check
```

If it refuses to pull because the working tree is dirty, do not force reset immediately. Ask Mac-side Codex to inspect the Windows changes first.

## Windows Codex Startup Prompt

When starting a new Codex thread on Windows, use this prompt:

```text
We are continuing the hey-quant project on the Windows host.
Please read:
- docs/milestones.md
- docs/windows_handoff.md
- docs/docker_deployment.md

This machine is the runtime host. Do not commit secrets or .env.
Use Docker for running the app.
First check:
- git status
- docker compose ps
- whether http://127.0.0.1:8765 is reachable

Then help me continue from the latest milestone.
```

## Runtime Data Policy

These files stay local on Windows and must not be committed:

```text
.env
data/
outputs/
logs/
```

Tracked strategy code and docs should come from GitHub.

## Useful Commands

```powershell
git status
git pull --ff-only
docker compose ps
docker compose logs -f quant-ai-web
docker compose restart quant-ai-web
docker compose down
```
