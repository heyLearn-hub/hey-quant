# Contributing

This repository is a local research and alerting system for low-frequency equity trend strategies. It does not place trades and must not store secrets or real account data in Git.

## Branches

- `main`: stable branch only.
- `dev`: integration branch for tested work.
- `feature/<short-name>`: focused feature branches.

For local work with Codex, prefer one small feature per branch or commit.

## Before Committing

Run:

```bash
.venv/bin/python -m pytest -q
```

For UI/report changes, also run at least one smoke command:

```bash
bin/quant-ai-local run --config config/default.yaml --offline-sample --out outputs/sample_report.html
```

For factor work:

```bash
bin/quant-ai-local factor-test --config config/default.yaml --offline-sample --out outputs/factor_report.html
```

## Do Not Commit

Never commit:

- `.env`
- API keys
- SMTP passwords
- real holdings
- SQLite runtime databases
- generated reports
- market data cache
- local logs
- virtual environments

The `.gitignore` is configured for these files, but always check `git status --ignored` if unsure.

## Strategy Changes

Any strategy, risk, sizing, or factor change should update the relevant docs when behavior changes:

- `docs/milestones.md`
- `docs/architecture_and_learning_plan.md`
- `README.md`

When adding a factor or signal rule, include a short note explaining:

- why the factor exists;
- where it is calculated;
- how it should be tested;
- what could make it fail.

## Safety Boundary

The system is a decision-support tool. It must not:

- connect to a broker for live trading;
- auto-submit orders;
- hide data-quality failures;
- let AI override deterministic risk rules.

