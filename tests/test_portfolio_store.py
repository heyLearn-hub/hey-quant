from __future__ import annotations

from pathlib import Path

from quant_ai_system.portfolio_store import close_position, get_data_symbol, insert_supervisor_decision_logs, list_positions, list_supervisor_decision_logs, list_symbol_aliases, list_trades, record_trade, upsert_position, upsert_symbol_alias
from quant_ai_system.supervisor import SupervisorDecision


def test_portfolio_store_round_trip(tmp_path: Path) -> None:
    db = tmp_path / "portfolio.sqlite3"
    upsert_position(db, "msft", 3, 400.5, 370.0, "quality trend")
    record_trade(db, "msft", "buy", 3, 400.5, "initial")

    positions = list_positions(db)
    trades = list_trades(db)

    assert positions[0].ticker == "MSFT"
    assert positions[0].shares == 3
    assert positions[0].current_stop == 370.0
    assert trades[0].action == "buy"

    close_position(db, "MSFT", "risk exit")
    assert list_positions(db) == []
    assert list_positions(db, include_closed=True)[0].status == "closed"


def test_symbol_alias_round_trip(tmp_path: Path) -> None:
    db = tmp_path / "portfolio.sqlite3"

    upsert_symbol_alias(db, "snxx", "nvda", "broker alias")

    assert get_data_symbol(db, "SNXX") == "NVDA"
    assert get_data_symbol(db, "MSFT") == "MSFT"
    aliases = list_symbol_aliases(db)
    assert aliases[0].broker_symbol == "SNXX"
    assert aliases[0].data_symbol == "NVDA"


def test_supervisor_decision_log_round_trip(tmp_path: Path) -> None:
    db = tmp_path / "portfolio.sqlite3"
    decision = SupervisorDecision(
        ticker="msft",
        decision="approve_for_consideration",
        approval_score=82,
        final_action="可考虑执行",
        rationale="score and risk budget are acceptable",
        blockers=[],
        required_checks=["确认财报日期"],
        provider="local_rules",
    )

    run_id = insert_supervisor_decision_logs(db, [decision], "outputs/report.html")
    logs = list_supervisor_decision_logs(db)

    assert logs[0].run_id == run_id
    assert logs[0].ticker == "MSFT"
    assert logs[0].provider == "local_rules"
    assert logs[0].decision == "approve_for_consideration"
    assert logs[0].required_checks == ["确认财报日期"]
    assert logs[0].report_path == "outputs/report.html"
