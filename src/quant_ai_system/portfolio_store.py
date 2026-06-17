from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


@dataclass(frozen=True)
class StoredPosition:
    ticker: str
    shares: float
    average_cost: float
    opened_at: str
    current_stop: float | None
    thesis_note: str
    status: str


@dataclass(frozen=True)
class StoredTrade:
    id: int
    ticker: str
    action: str
    shares: float
    price: float
    executed_at: str
    note: str


def _connect(db_path: str | Path) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: str | Path) -> None:
    with _connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS positions (
                ticker TEXT PRIMARY KEY,
                shares REAL NOT NULL,
                average_cost REAL NOT NULL,
                opened_at TEXT NOT NULL,
                current_stop REAL,
                thesis_note TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'open'
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker TEXT NOT NULL,
                action TEXT NOT NULL,
                shares REAL NOT NULL,
                price REAL NOT NULL,
                executed_at TEXT NOT NULL,
                note TEXT NOT NULL DEFAULT ''
            )
            """
        )


def list_positions(db_path: str | Path, include_closed: bool = False) -> list[StoredPosition]:
    init_db(db_path)
    sql = "SELECT * FROM positions"
    params: tuple[object, ...] = ()
    if not include_closed:
        sql += " WHERE status = ?"
        params = ("open",)
    sql += " ORDER BY ticker"
    with _connect(db_path) as conn:
        rows = conn.execute(sql, params).fetchall()
    return [
        StoredPosition(
            ticker=row["ticker"],
            shares=float(row["shares"]),
            average_cost=float(row["average_cost"]),
            opened_at=row["opened_at"],
            current_stop=float(row["current_stop"]) if row["current_stop"] is not None else None,
            thesis_note=row["thesis_note"],
            status=row["status"],
        )
        for row in rows
    ]


def list_trades(db_path: str | Path, limit: int = 50) -> list[StoredTrade]:
    init_db(db_path)
    with _connect(db_path) as conn:
        rows = conn.execute("SELECT * FROM trades ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    return [
        StoredTrade(
            id=int(row["id"]),
            ticker=row["ticker"],
            action=row["action"],
            shares=float(row["shares"]),
            price=float(row["price"]),
            executed_at=row["executed_at"],
            note=row["note"],
        )
        for row in rows
    ]


def upsert_position(
    db_path: str | Path,
    ticker: str,
    shares: float,
    average_cost: float,
    current_stop: float | None,
    thesis_note: str,
    opened_at: str | None = None,
    status: str = "open",
) -> None:
    init_db(db_path)
    ticker = ticker.strip().upper()
    opened_at = opened_at or datetime.now(tz=UTC).date().isoformat()
    with _connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO positions (ticker, shares, average_cost, opened_at, current_stop, thesis_note, status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(ticker) DO UPDATE SET
                shares = excluded.shares,
                average_cost = excluded.average_cost,
                current_stop = excluded.current_stop,
                thesis_note = excluded.thesis_note,
                status = excluded.status
            """,
            (ticker, shares, average_cost, opened_at, current_stop, thesis_note, status),
        )


def record_trade(
    db_path: str | Path,
    ticker: str,
    action: str,
    shares: float,
    price: float,
    note: str,
    executed_at: str | None = None,
) -> None:
    init_db(db_path)
    executed_at = executed_at or datetime.now(tz=UTC).isoformat(timespec="seconds")
    with _connect(db_path) as conn:
        conn.execute(
            "INSERT INTO trades (ticker, action, shares, price, executed_at, note) VALUES (?, ?, ?, ?, ?, ?)",
            (ticker.strip().upper(), action, shares, price, executed_at, note),
        )


def close_position(db_path: str | Path, ticker: str, note: str = "") -> None:
    init_db(db_path)
    ticker = ticker.strip().upper()
    with _connect(db_path) as conn:
        conn.execute("UPDATE positions SET status = 'closed', thesis_note = thesis_note || ? WHERE ticker = ?", (f"\n{note}" if note else "", ticker))

