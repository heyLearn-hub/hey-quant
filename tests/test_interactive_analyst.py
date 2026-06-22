from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from quant_ai_system.config import load_config
from quant_ai_system.interactive_analyst import (
    AnalystResponse,
    TradePlan,
    analyze_position,
    analyze_ticker,
    format_analyst_response,
    review_trade_plan,
)
from quant_ai_system.portfolio_store import list_positions, upsert_position


def _config(tmp_path: Path):
    config = load_config("config/default.yaml")
    return replace(config, storage=replace(config.storage, db_path=str(tmp_path / "portfolio.sqlite3")))


def test_format_analyst_response_includes_public_equity_fields() -> None:
    response = AnalystResponse(
        command="CHECK",
        ticker="MRVL",
        conclusion="watch",
        sections={
            "技术/数据": ["趋势确认", "ATR 5.0%"],
            "新闻/事件": ["无高优先级风险"],
            "持仓/组合影响": ["非当前持仓"],
            "LOTS/风控": ["小仓观察"],
        },
        intended_alpha="AI/semi trend exposure",
        unwanted_risk="追高和主题拥挤",
        retained_exposure="未建仓则无保留暴露",
        binding_constraint="等待更好入场",
        liquidity_exit_posture="日线风控可管理",
        supervisor="local_rule: hold",
    )

    text = format_analyst_response(response)

    assert "Quant AI Analyst · CHECK" in text
    assert "MRVL: watch" in text
    assert "intended alpha" in text
    assert "unwanted risk" in text
    assert "retained exposure" in text
    assert "binding constraint" in text
    assert "liquidity/exit posture" in text
    assert "Supervisor" in text


def test_review_trade_plan_calculates_notional_nav_and_max_loss(tmp_path: Path) -> None:
    config = _config(tmp_path)

    response = review_trade_plan(config, TradePlan("buy", "INTC", 5, 135, 128))
    text = format_analyst_response(response)

    assert response.command == "PLAN"
    assert response.ticker == "INTC"
    assert response.conclusion == "approve_small_probe"
    assert "金额 675.00" in text
    assert "最大亏损 35.00" in text
    assert list_positions(config.storage.db_path) == []


def test_review_trade_plan_rejects_buy_without_stop(tmp_path: Path) -> None:
    config = _config(tmp_path)

    response = review_trade_plan(config, TradePlan("buy", "INTC", 5, 135, None))

    assert response.conclusion == "reject"
    assert "stop" in response.binding_constraint.lower()


def test_analyze_position_protects_profitable_position(tmp_path: Path, monkeypatch) -> None:
    config = _config(tmp_path)
    upsert_position(config.storage.db_path, "SNXX", 10, 36, 32, "profitable")
    monkeypatch.setattr("quant_ai_system.interactive_analyst._latest_price", lambda config, ticker: (46.0, "fmp quote"))

    response = analyze_position(config, "SNXX")
    text = format_analyst_response(response)

    assert response.conclusion == "protect_profit"
    assert "浮盈亏 27.8%" in text
    assert "保护" in text


def test_analyze_position_not_held_suggests_check(tmp_path: Path) -> None:
    config = _config(tmp_path)

    response = analyze_position(config, "MRVL")
    text = format_analyst_response(response)

    assert response.conclusion == "not_held"
    assert "/check MRVL" in text


def test_analyze_ticker_returns_watch_or_candidate_with_risk_fields(monkeypatch) -> None:
    config = load_config("config/default.yaml")
    monkeypatch.setattr("quant_ai_system.interactive_analyst._latest_price", lambda config, ticker: (100.0, "fmp quote"))
    monkeypatch.setattr("quant_ai_system.interactive_analyst._technical_snapshot", lambda config, ticker: ["价格高于50日线", "ATR 4.0%"])
    monkeypatch.setattr("quant_ai_system.interactive_analyst._news_snapshot", lambda config, ticker: ["无高优先级新闻风险"])

    response = analyze_ticker(config, "MRVL")
    text = format_analyst_response(response)

    assert response.command == "CHECK"
    assert response.ticker == "MRVL"
    assert response.conclusion in {"watch", "small_probe_candidate", "do_not_chase"}
    assert "intended alpha" in text
    assert "MRVL" in text
