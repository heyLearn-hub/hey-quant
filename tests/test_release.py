from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from quant_ai_system.cli import main
from quant_ai_system.config import load_config
from quant_ai_system.release import format_release_checks, release_check_exit_code, run_release_checks


def test_release_checks_pass_with_required_runtime_env(tmp_path: Path) -> None:
    for name in ["Dockerfile", "docker-compose.yml"]:
        (tmp_path / name).write_text("ok\n", encoding="utf-8")
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    for name in ["windows_docker_daily_job.ps1", "windows_docker_update.ps1", "windows_docker_auto_update_task.xml"]:
        (scripts / name).write_text("ok\n", encoding="utf-8")
    (tmp_path / ".gitignore").write_text(".env\ndata/*.sqlite3\ndata/cache/\noutputs/\nlogs/\n", encoding="utf-8")
    data = tmp_path / "data"
    data.mkdir()
    db = data / "portfolio.sqlite3"
    db.write_text("", encoding="utf-8")

    config = load_config("config/default.yaml")
    config = replace(config, storage=replace(config.storage, db_path=str(db)))

    checks = run_release_checks(
        config,
        project_root=tmp_path,
        env={
            "FMP_API_KEY": "configured",
            "TELEGRAM_BOT_TOKEN": "configured",
            "TELEGRAM_CHAT_ID": "configured",
            "DEEPSEEK_API_KEY": "configured",
        },
    )

    assert release_check_exit_code(checks) == 0
    assert "FAIL=0" in format_release_checks(checks)
    assert {item.name for item in checks if item.level == "PASS"} >= {"telegram", "fmp", "ai-supervisor", "windows-docker"}


def test_cli_release_check_fails_when_telegram_env_missing(monkeypatch) -> None:
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)

    assert main(["release-check", "--config", "config/default.yaml"]) == 1
