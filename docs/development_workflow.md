# Development Workflow

## Daily Development Loop

1. Read `docs/milestones.md`.
2. Pick the smallest milestone task that can be finished and verified.
3. Make focused code changes.
4. Run tests.
5. Run a smoke command if behavior changed.
6. Update docs if the workflow changed.
7. Commit locally.

## Core Verification Commands

```bash
.venv/bin/python -m pytest -q
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

## GitHub Push Blocker

The first local commit exists, but push to `https://github.com/heyLearn-hub/hey-quant.git` is currently blocked by GitHub permissions for the authenticated account.

Resolution options:

- grant the current authenticated GitHub account write access to `heyLearn-hub/hey-quant`;
- clear the GitHub HTTPS credential and authenticate as the repo owner;
- switch the remote to SSH after SSH keys are configured.

## Runtime Data

Runtime files are intentionally local:

- `data/*.sqlite3`
- `data/cache/`
- `outputs/`
- `logs/`
- `.env`

They should not be copied into GitHub. On Windows, recreate `.env` locally with SMTP/API credentials.

