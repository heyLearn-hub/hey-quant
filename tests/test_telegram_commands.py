from __future__ import annotations

from pathlib import Path

from quant_ai_system.config import load_config
from quant_ai_system.portfolio_store import list_positions
from quant_ai_system.interactive_analyst import AnalystResponse
from quant_ai_system.telegram_commands import TelegramCommandProcessor


def _processor(tmp_path: Path, monkeypatch, refresh_calls: list[str]) -> TelegramCommandProcessor:
    config = load_config("config/default.yaml")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "123")
    return TelegramCommandProcessor(config, tmp_path / "portfolio.sqlite3", refresh_callback=lambda: refresh_calls.append("refresh"))


def test_telegram_command_rejects_unauthorized_chat(tmp_path: Path, monkeypatch) -> None:
    processor = _processor(tmp_path, monkeypatch, [])

    reply = processor.handle_update({"update_id": 1, "message": {"chat": {"id": 999}, "text": "/buy MSFT 1 400"}})

    assert reply == "未授权 chat，已拒绝。"
    assert list_positions(tmp_path / "portfolio.sqlite3") == []


def test_buy_command_requires_confirmation_before_writing(tmp_path: Path, monkeypatch) -> None:
    refresh_calls: list[str] = []
    processor = _processor(tmp_path, monkeypatch, refresh_calls)
    db = tmp_path / "portfolio.sqlite3"

    reply = processor.handle_text("123", "/buy MSFT 2 400 initial")

    assert "待确认" in reply
    assert list_positions(db) == []
    pending_id = next(iter(processor.pending))

    confirm = processor.handle_text("123", f"/confirm {pending_id}")

    positions = list_positions(db)
    assert "已记录" in confirm
    assert refresh_calls == ["refresh"]
    assert positions[0].ticker == "MSFT"
    assert positions[0].shares == 2
    assert positions[0].average_cost == 400


def test_malformed_trade_command_does_not_write(tmp_path: Path, monkeypatch) -> None:
    processor = _processor(tmp_path, monkeypatch, [])
    db = tmp_path / "portfolio.sqlite3"

    reply = processor.handle_text("123", "/buy MSFT wrong")

    assert "用法" in reply
    assert list_positions(db) == []


def _fake_response(command: str, ticker: str, conclusion: str) -> AnalystResponse:
    return AnalystResponse(
        command=command,
        ticker=ticker,
        conclusion=conclusion,
        sections={"技术/数据": ["ok"], "新闻/事件": ["ok"], "持仓/组合影响": ["ok"], "LOTS/风控": ["ok"]},
        intended_alpha="alpha",
        unwanted_risk="risk",
        retained_exposure="exposure",
        binding_constraint="constraint",
        liquidity_exit_posture="exit",
        supervisor="local_rule",
    )


def test_check_command_routes_to_interactive_analyst(tmp_path: Path, monkeypatch) -> None:
    processor = _processor(tmp_path, monkeypatch, [])
    monkeypatch.setattr("quant_ai_system.telegram_commands.analyze_ticker", lambda config, ticker: _fake_response("CHECK", ticker, "watch"))
    monkeypatch.setattr("quant_ai_system.telegram_commands.format_analyst_response", lambda response: f"{response.command}:{response.ticker}:{response.conclusion}")

    assert processor.handle_text("123", "/check MRVL") == "CHECK:MRVL:watch"


def test_position_command_routes_to_interactive_analyst(tmp_path: Path, monkeypatch) -> None:
    processor = _processor(tmp_path, monkeypatch, [])
    monkeypatch.setattr("quant_ai_system.telegram_commands.analyze_position", lambda config, ticker: _fake_response("POSITION", ticker, "protect_profit"))
    monkeypatch.setattr("quant_ai_system.telegram_commands.format_analyst_response", lambda response: f"{response.command}:{response.ticker}:{response.conclusion}")

    assert processor.handle_text("123", "/position SNXX") == "POSITION:SNXX:protect_profit"


def test_plan_command_does_not_create_pending_confirmation(tmp_path: Path, monkeypatch) -> None:
    processor = _processor(tmp_path, monkeypatch, [])
    monkeypatch.setattr("quant_ai_system.telegram_commands.review_trade_plan", lambda config, plan: _fake_response("PLAN", plan.ticker, "approve_small_probe"))
    monkeypatch.setattr("quant_ai_system.telegram_commands.format_analyst_response", lambda response: f"{response.command}:{response.ticker}:{response.conclusion}")

    reply = processor.handle_text("123", "/plan buy INTC 5 135 stop 128")

    assert reply == "PLAN:INTC:approve_small_probe"
    assert processor.pending == {}


def test_malformed_plan_command_returns_usage(tmp_path: Path, monkeypatch) -> None:
    processor = _processor(tmp_path, monkeypatch, [])

    reply = processor.handle_text("123", "/plan buy INTC")

    assert "用法" in reply
    assert processor.pending == {}
