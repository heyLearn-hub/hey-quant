from __future__ import annotations

import json
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


@dataclass(frozen=True)
class SymbolAlias:
    broker_symbol: str
    data_symbol: str
    note: str
    updated_at: str


@dataclass(frozen=True)
class DataHealthRecord:
    ticker: str
    check_type: str
    provider: str
    ok: bool
    message: str
    checked_at: str


@dataclass(frozen=True)
class PricingSnapshot:
    ticker: str
    data_symbol: str
    provider: str
    price: float
    change_pct: float | None
    session: str
    checked_at: str


@dataclass(frozen=True)
class NewsEventRecord:
    event_key: str
    ticker: str
    title: str
    url: str
    published_at: str
    priority: str
    pushed: bool
    created_at: str


@dataclass(frozen=True)
class MonitorAlertRecord:
    alert_key: str
    ticker: str
    category: str
    priority: str
    message: str
    created_at: str


@dataclass(frozen=True)
class SupervisorDecisionLogRecord:
    id: int
    run_id: str
    ticker: str
    provider: str
    decision: str
    approval_score: float
    final_action: str
    rationale: str
    blockers: list[str]
    required_checks: list[str]
    report_path: str
    created_at: str


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
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS symbol_aliases (
                broker_symbol TEXT PRIMARY KEY,
                data_symbol TEXT NOT NULL,
                note TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS data_health (
                ticker TEXT NOT NULL,
                check_type TEXT NOT NULL,
                provider TEXT NOT NULL,
                ok INTEGER NOT NULL,
                message TEXT NOT NULL,
                checked_at TEXT NOT NULL,
                PRIMARY KEY (ticker, check_type, provider)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS pricing_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker TEXT NOT NULL,
                data_symbol TEXT NOT NULL,
                provider TEXT NOT NULL,
                price REAL NOT NULL,
                change_pct REAL,
                session TEXT NOT NULL,
                checked_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS news_events (
                event_key TEXT PRIMARY KEY,
                ticker TEXT NOT NULL,
                title TEXT NOT NULL,
                url TEXT NOT NULL,
                published_at TEXT NOT NULL,
                priority TEXT NOT NULL,
                pushed INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS monitor_alerts (
                alert_key TEXT PRIMARY KEY,
                ticker TEXT NOT NULL,
                category TEXT NOT NULL,
                priority TEXT NOT NULL,
                message TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS supervisor_decision_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                ticker TEXT NOT NULL,
                provider TEXT NOT NULL,
                decision TEXT NOT NULL,
                approval_score REAL NOT NULL,
                final_action TEXT NOT NULL,
                rationale TEXT NOT NULL,
                blockers_json TEXT NOT NULL,
                required_checks_json TEXT NOT NULL,
                report_path TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
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


def upsert_symbol_alias(db_path: str | Path, broker_symbol: str, data_symbol: str, note: str = "") -> None:
    init_db(db_path)
    now = datetime.now(tz=UTC).isoformat(timespec="seconds")
    with _connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO symbol_aliases (broker_symbol, data_symbol, note, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(broker_symbol) DO UPDATE SET
                data_symbol = excluded.data_symbol,
                note = excluded.note,
                updated_at = excluded.updated_at
            """,
            (broker_symbol.strip().upper(), data_symbol.strip().upper(), note, now),
        )


def list_symbol_aliases(db_path: str | Path) -> list[SymbolAlias]:
    init_db(db_path)
    with _connect(db_path) as conn:
        rows = conn.execute("SELECT * FROM symbol_aliases ORDER BY broker_symbol").fetchall()
    return [SymbolAlias(row["broker_symbol"], row["data_symbol"], row["note"], row["updated_at"]) for row in rows]


def get_data_symbol(db_path: str | Path, broker_symbol: str) -> str:
    init_db(db_path)
    ticker = broker_symbol.strip().upper()
    with _connect(db_path) as conn:
        row = conn.execute("SELECT data_symbol FROM symbol_aliases WHERE broker_symbol = ?", (ticker,)).fetchone()
    return str(row["data_symbol"]).upper() if row else ticker


def upsert_data_health(db_path: str | Path, ticker: str, check_type: str, provider: str, ok: bool, message: str) -> None:
    init_db(db_path)
    now = datetime.now(tz=UTC).isoformat(timespec="seconds")
    with _connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO data_health (ticker, check_type, provider, ok, message, checked_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(ticker, check_type, provider) DO UPDATE SET
                ok = excluded.ok,
                message = excluded.message,
                checked_at = excluded.checked_at
            """,
            (ticker.strip().upper(), check_type, provider, 1 if ok else 0, message, now),
        )


def list_data_health(db_path: str | Path, limit: int = 50) -> list[DataHealthRecord]:
    init_db(db_path)
    with _connect(db_path) as conn:
        rows = conn.execute("SELECT * FROM data_health ORDER BY checked_at DESC LIMIT ?", (limit,)).fetchall()
    return [
        DataHealthRecord(row["ticker"], row["check_type"], row["provider"], bool(row["ok"]), row["message"], row["checked_at"])
        for row in rows
    ]


def insert_pricing_snapshot(db_path: str | Path, ticker: str, data_symbol: str, provider: str, price: float, change_pct: float | None, session: str) -> None:
    init_db(db_path)
    now = datetime.now(tz=UTC).isoformat(timespec="seconds")
    with _connect(db_path) as conn:
        conn.execute(
            "INSERT INTO pricing_snapshots (ticker, data_symbol, provider, price, change_pct, session, checked_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (ticker.strip().upper(), data_symbol.strip().upper(), provider, price, change_pct, session, now),
        )


def list_pricing_snapshots(db_path: str | Path, limit: int = 50) -> list[PricingSnapshot]:
    init_db(db_path)
    with _connect(db_path) as conn:
        rows = conn.execute("SELECT * FROM pricing_snapshots ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    return [
        PricingSnapshot(row["ticker"], row["data_symbol"], row["provider"], float(row["price"]), float(row["change_pct"]) if row["change_pct"] is not None else None, row["session"], row["checked_at"])
        for row in rows
    ]


def insert_news_event(db_path: str | Path, event_key: str, ticker: str, title: str, url: str, published_at: str, priority: str, pushed: bool = False) -> bool:
    init_db(db_path)
    now = datetime.now(tz=UTC).isoformat(timespec="seconds")
    with _connect(db_path) as conn:
        cur = conn.execute(
            "INSERT OR IGNORE INTO news_events (event_key, ticker, title, url, published_at, priority, pushed, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (event_key, ticker.strip().upper(), title, url, published_at, priority, 1 if pushed else 0, now),
        )
    return cur.rowcount > 0


def mark_news_event_pushed(db_path: str | Path, event_key: str) -> None:
    init_db(db_path)
    with _connect(db_path) as conn:
        conn.execute("UPDATE news_events SET pushed = 1 WHERE event_key = ?", (event_key,))


def list_news_events(db_path: str | Path, limit: int = 50) -> list[NewsEventRecord]:
    init_db(db_path)
    with _connect(db_path) as conn:
        rows = conn.execute("SELECT * FROM news_events ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
    return [
        NewsEventRecord(row["event_key"], row["ticker"], row["title"], row["url"], row["published_at"], row["priority"], bool(row["pushed"]), row["created_at"])
        for row in rows
    ]


def insert_monitor_alert(db_path: str | Path, alert_key: str, ticker: str, category: str, priority: str, message: str) -> bool:
    init_db(db_path)
    now = datetime.now(tz=UTC).isoformat(timespec="seconds")
    with _connect(db_path) as conn:
        cur = conn.execute(
            "INSERT OR IGNORE INTO monitor_alerts (alert_key, ticker, category, priority, message, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (alert_key, ticker.strip().upper(), category, priority, message, now),
        )
    return cur.rowcount > 0


def list_monitor_alerts(db_path: str | Path, limit: int = 50) -> list[MonitorAlertRecord]:
    init_db(db_path)
    with _connect(db_path) as conn:
        rows = conn.execute("SELECT * FROM monitor_alerts ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
    return [
        MonitorAlertRecord(row["alert_key"], row["ticker"], row["category"], row["priority"], row["message"], row["created_at"])
        for row in rows
    ]


def insert_supervisor_decision_logs(db_path: str | Path, decisions: list[object], report_path: str | Path = "") -> str:
    init_db(db_path)
    run_id = datetime.now(tz=UTC).isoformat(timespec="seconds")
    rows = [
        (
            run_id,
            str(getattr(decision, "ticker")).strip().upper(),
            str(getattr(decision, "provider")),
            str(getattr(decision, "decision")),
            float(getattr(decision, "approval_score")),
            str(getattr(decision, "final_action")),
            str(getattr(decision, "rationale")),
            json.dumps(list(getattr(decision, "blockers", [])), ensure_ascii=False),
            json.dumps(list(getattr(decision, "required_checks", [])), ensure_ascii=False),
            str(report_path),
            run_id,
        )
        for decision in decisions
    ]
    if not rows:
        return run_id
    with _connect(db_path) as conn:
        conn.executemany(
            """
            INSERT INTO supervisor_decision_log
                (run_id, ticker, provider, decision, approval_score, final_action, rationale, blockers_json, required_checks_json, report_path, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
    return run_id


def list_supervisor_decision_logs(db_path: str | Path, limit: int = 50) -> list[SupervisorDecisionLogRecord]:
    init_db(db_path)
    with _connect(db_path) as conn:
        rows = conn.execute("SELECT * FROM supervisor_decision_log ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    return [
        SupervisorDecisionLogRecord(
            id=int(row["id"]),
            run_id=row["run_id"],
            ticker=row["ticker"],
            provider=row["provider"],
            decision=row["decision"],
            approval_score=float(row["approval_score"]),
            final_action=row["final_action"],
            rationale=row["rationale"],
            blockers=list(json.loads(row["blockers_json"] or "[]")),
            required_checks=list(json.loads(row["required_checks_json"] or "[]")),
            report_path=row["report_path"],
            created_at=row["created_at"],
        )
        for row in rows
    ]
