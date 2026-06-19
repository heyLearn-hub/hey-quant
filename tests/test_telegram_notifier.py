from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from quant_ai_system.config import load_config
from quant_ai_system.engine import run_system
from quant_ai_system.telegram_notifier import build_telegram_message, send_telegram_message


class _FakeResponse:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self) -> bytes:
        return json.dumps({"ok": True, "result": {"message_id": 1}}).encode("utf-8")


def test_telegram_message_contains_action_sections(tmp_path: Path) -> None:
    config = load_config("config/default.yaml")
    result = run_system(config, tmp_path / "report.html", offline_sample=True)

    message = build_telegram_message(result)

    assert "Quant AI 今日提醒" in message
    assert "股票候选" in message
    assert "观察池风控候选" not in message
    assert "完整报告" in message


def test_send_telegram_uses_env_token_and_chat_id(tmp_path: Path, monkeypatch) -> None:
    config = load_config("config/default.yaml")
    result = run_system(config, tmp_path / "report.html", offline_sample=True)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "123")

    calls = []

    def fake_urlopen(request, timeout=30):
        calls.append((request.full_url, request.data.decode("utf-8"), timeout))
        return _FakeResponse()

    with patch("quant_ai_system.telegram_notifier.urllib.request.urlopen", fake_urlopen):
        send_telegram_message(config, result)

    assert calls
    assert "bottest-token/sendMessage" in calls[0][0]
    assert "chat_id=123" in calls[0][1]
