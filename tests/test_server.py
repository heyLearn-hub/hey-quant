from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from quant_ai_system.server import ServerState, install_launch_agent, service_status


def test_server_state_paths_are_stored(tmp_path: Path) -> None:
    state = ServerState(tmp_path / "config.yaml", tmp_path / "report.html", offline_sample=True)
    assert state.config_path.name == "config.yaml"
    assert state.report_path.name == "report.html"
    assert state.offline_sample is True


def test_install_launch_agent_writes_plist(tmp_path: Path, monkeypatch) -> None:
    fake_home = tmp_path / "home"
    project = tmp_path / "project"
    launcher = project / "bin" / "quant-ai-local"
    launcher.parent.mkdir(parents=True)
    launcher.write_text("#!/bin/sh\n", encoding="utf-8")
    (project / "src" / "quant_ai_system").mkdir(parents=True)
    (project / "config.yaml").write_text("account: {}\n", encoding="utf-8")
    (project / "config").mkdir()
    (project / "config" / "default.yaml").write_text("account: {}\n", encoding="utf-8")
    (project / "pyproject.toml").write_text("[project]\nname='x'\nversion='0.0.1'\n", encoding="utf-8")
    (project / "README.md").write_text("readme\n", encoding="utf-8")
    monkeypatch.setattr(Path, "home", lambda: fake_home)
    monkeypatch.chdir(project)

    with patch("quant_ai_system.server.subprocess.run") as run:
        path = install_launch_agent("config.yaml", "outputs/latest.html", 8765)

    assert path.exists()
    text = path.read_text(encoding="utf-8")
    assert "com.quant-ai-system.service" in text
    assert "quant-ai-local" in text
    assert "8765" in text
    assert "Application Support" in text
    assert run.call_count == 4


def test_service_status_mentions_local_url() -> None:
    status = service_status(8765)
    assert "http://127.0.0.1:8765" in status
