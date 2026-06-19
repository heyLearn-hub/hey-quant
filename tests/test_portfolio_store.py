from __future__ import annotations

from pathlib import Path

from quant_ai_system.portfolio_store import close_position, get_data_symbol, list_positions, list_symbol_aliases, list_trades, record_trade, upsert_position, upsert_symbol_alias


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
