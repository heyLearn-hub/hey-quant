from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from quant_ai_system.config import load_config
from quant_ai_system.emailer import build_email_body, send_summary_email
from quant_ai_system.engine import run_system


class _FakeSMTP:
    sent = False

    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def starttls(self):
        return None

    def login(self, username, password):
        assert username == "user@example.com"
        assert password == "pw"

    def send_message(self, msg):
        _FakeSMTP.sent = True
        assert "Quant AI" in msg["Subject"]


def test_email_body_contains_core_sections(tmp_path: Path) -> None:
    config = load_config("config/default.yaml")
    result = run_system(config, tmp_path / "report.html", offline_sample=True)
    body = build_email_body(result)
    assert "今日结论" in body
    assert "当前持仓检查" in body
    assert "Supervisor 审查" in body


def test_send_summary_email_uses_smtp_env(tmp_path: Path, monkeypatch) -> None:
    config = load_config("config/default.yaml")
    result = run_system(config, tmp_path / "report.html", offline_sample=True)
    monkeypatch.setenv("SMTP_USERNAME", "user@example.com")
    monkeypatch.setenv("SMTP_PASSWORD", "pw")
    monkeypatch.setenv("SMTP_FROM", "user@example.com")
    monkeypatch.setenv("SMTP_TO", "to@example.com")
    _FakeSMTP.sent = False
    with patch("quant_ai_system.emailer.smtplib.SMTP", _FakeSMTP):
        send_summary_email(config, result)
    assert _FakeSMTP.sent

