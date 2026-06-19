# Development Workflow

## Daily Development Loop

1. Read `docs/milestones.md`.
2. For v1.0 work, read `docs/v1_release_plan.md`.
3. Pick the smallest milestone task that can be finished and verified.
4. Make focused code changes.
5. Run tests.
6. Run a smoke command if behavior changed.
7. Update docs if the workflow changed.
8. Commit locally.

## Core Verification Commands

```bash
.venv/bin/python -m pytest -q
bin/quant-ai-local release-check --config config/default.yaml
bin/quant-ai-local run --config config/default.yaml --offline-sample --out outputs/sample_report.html
bin/quant-ai-local factor-test --config config/default.yaml --offline-sample --out outputs/factor_report.html
```

## Windows Verification Commands

On Windows:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\bin\quant-ai-local.ps1 run --config config\default.yaml --offline-sample --out outputs\sample_report.html
.\bin\quant-ai-local.ps1 serve --config config\default.yaml --out outputs\latest_report.html --open
```

## GitHub Status

Resolved. The repository is connected to GitHub and can be pushed from the configured local Git identity. Use focused `codex/*` branches for development work, then merge or PR into `main` when checks pass.

## Runtime Data

Runtime files are intentionally local:

- `data/*.sqlite3`
- `data/cache/`
- `outputs/`
- `logs/`
- `.env`

They should not be copied into GitHub. On Windows, recreate `.env` locally with SMTP/API credentials.
