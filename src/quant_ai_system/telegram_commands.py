from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import threading
import time
from pathlib import Path
from typing import Callable
from uuid import uuid4

from quant_ai_system.config import AppConfig
from quant_ai_system.portfolio_store import StoredPosition, close_position, list_positions, record_trade, upsert_position
from quant_ai_system.telegram_notifier import fetch_telegram_updates, send_telegram_text


@dataclass(frozen=True)
class PendingTelegramCommand:
    id: str
    chat_id: str
    action: str
    ticker: str
    shares: float
    price: float
    note: str
    created_at: str


class TelegramCommandProcessor:
    def __init__(
        self,
        config: AppConfig,
        db_path: str | Path,
        refresh_callback: Callable[[], None] | None = None,
    ) -> None:
        self.config = config
        self.db_path = Path(db_path)
        self.refresh_callback = refresh_callback
        self.pending: dict[str, PendingTelegramCommand] = {}

    @property
    def authorized_chat_id(self) -> str:
        import os

        return os.environ.get(self.config.telegram.chat_id_env, "").strip()

    def handle_update(self, update: dict) -> str | None:
        message = update.get("message") or update.get("channel_post") or {}
        chat = message.get("chat") or {}
        chat_id = str(chat.get("id", "")).strip()
        text = str(message.get("text") or "").strip()
        if not text:
            return None
        if not self.authorized_chat_id or chat_id != self.authorized_chat_id:
            return "未授权 chat，已拒绝。"
        return self.handle_text(chat_id, text)

    def handle_text(self, chat_id: str, text: str) -> str:
        parts = text.strip().split(maxsplit=4)
        command = parts[0].lower().split("@", 1)[0]
        if command == "/pos":
            return self._format_positions()
        if command == "/confirm":
            if len(parts) < 2:
                return "用法: /confirm <id>"
            return self._confirm(parts[1])
        if command in {"/buy", "/add", "/trim", "/sell"}:
            return self._prepare_trade(chat_id, command[1:], parts)
        if command == "/stop":
            return self._prepare_stop(chat_id, parts)
        if command == "/note":
            return self._prepare_note(chat_id, parts)
        return "未知命令。可用: /pos, /buy, /add, /trim, /sell, /stop, /note, /confirm"

    def _format_positions(self) -> str:
        positions = list_positions(self.db_path)
        if not positions:
            return "当前无 open positions。"
        lines = ["当前持仓"]
        for position in positions:
            stop = f"{position.current_stop:.2f}" if position.current_stop is not None else "未设置"
            lines.append(f"- {position.ticker}: {position.shares:g} 股, 成本 {position.average_cost:.2f}, 止损 {stop}")
        return "\n".join(lines)

    def _prepare_trade(self, chat_id: str, action: str, parts: list[str]) -> str:
        if len(parts) < 4:
            return f"用法: /{action} TICKER SHARES PRICE note"
        try:
            ticker = parts[1].upper()
            shares = float(parts[2])
            price = float(parts[3])
        except ValueError:
            return f"用法: /{action} TICKER SHARES PRICE note"
        if shares <= 0 or price <= 0:
            return "股数和价格必须大于 0。"
        note = parts[4] if len(parts) >= 5 else ""
        return self._add_pending(chat_id, action, ticker, shares, price, note)

    def _prepare_stop(self, chat_id: str, parts: list[str]) -> str:
        if len(parts) < 3:
            return "用法: /stop TICKER PRICE"
        try:
            ticker = parts[1].upper()
            price = float(parts[2])
        except ValueError:
            return "用法: /stop TICKER PRICE"
        if price <= 0:
            return "止损价必须大于 0。"
        return self._add_pending(chat_id, "stop", ticker, 0.0, price, "")

    def _prepare_note(self, chat_id: str, parts: list[str]) -> str:
        if len(parts) < 3:
            return "用法: /note TICKER text"
        ticker = parts[1].upper()
        note = parts[2] if len(parts) == 3 else " ".join(parts[2:])
        return self._add_pending(chat_id, "note", ticker, 0.0, 0.0, note)

    def _add_pending(self, chat_id: str, action: str, ticker: str, shares: float, price: float, note: str) -> str:
        pending_id = uuid4().hex[:6]
        command = PendingTelegramCommand(
            id=pending_id,
            chat_id=chat_id,
            action=action,
            ticker=ticker,
            shares=shares,
            price=price,
            note=note,
            created_at=datetime.now(tz=UTC).isoformat(timespec="seconds"),
        )
        self.pending[pending_id] = command
        return f"待确认 {pending_id}: {self._describe(command)}\n确认执行请输入 /confirm {pending_id}"

    def _confirm(self, pending_id: str) -> str:
        command = self.pending.pop(pending_id, None)
        if command is None:
            return "确认 id 不存在或已过期。"
        self._apply(command)
        if self.refresh_callback:
            self.refresh_callback()
        return f"已记录: {self._describe(command)}\n报告刷新已触发。"

    def _apply(self, command: PendingTelegramCommand) -> None:
        positions = {position.ticker: position for position in list_positions(self.db_path)}
        current = positions.get(command.ticker)
        if command.action in {"buy", "add"}:
            new_shares, new_cost = self._add_position(current, command.shares, command.price)
            upsert_position(self.db_path, command.ticker, new_shares, new_cost, current.current_stop if current else None, command.note or (current.thesis_note if current else ""))
            record_trade(self.db_path, command.ticker, command.action, command.shares, command.price, command.note)
            return
        if command.action in {"trim", "sell"}:
            if current is None:
                raise ValueError(f"{command.ticker} 当前没有 open position")
            record_trade(self.db_path, command.ticker, command.action, command.shares, command.price, command.note)
            remaining = current.shares - command.shares
            if command.action == "sell" or remaining <= 0:
                close_position(self.db_path, command.ticker, command.note or command.action)
            else:
                upsert_position(self.db_path, command.ticker, remaining, current.average_cost, current.current_stop, current.thesis_note)
            return
        if command.action == "stop":
            if current is None:
                raise ValueError(f"{command.ticker} 当前没有 open position")
            upsert_position(self.db_path, command.ticker, current.shares, current.average_cost, command.price, current.thesis_note)
            record_trade(self.db_path, command.ticker, "stop", 0.0, command.price, "update stop")
            return
        if command.action == "note":
            if current is None:
                raise ValueError(f"{command.ticker} 当前没有 open position")
            upsert_position(self.db_path, command.ticker, current.shares, current.average_cost, current.current_stop, command.note)
            record_trade(self.db_path, command.ticker, "note", 0.0, 0.0, command.note)
            return
        raise ValueError(f"Unsupported command: {command.action}")

    @staticmethod
    def _add_position(current: StoredPosition | None, shares: float, price: float) -> tuple[float, float]:
        if current is None:
            return shares, price
        total_shares = current.shares + shares
        average_cost = ((current.shares * current.average_cost) + (shares * price)) / total_shares
        return total_shares, average_cost

    @staticmethod
    def _describe(command: PendingTelegramCommand) -> str:
        if command.action in {"buy", "add", "trim", "sell"}:
            return f"{command.action.upper()} {command.ticker} {command.shares:g} @ {command.price:.2f} {command.note}".strip()
        if command.action == "stop":
            return f"STOP {command.ticker} -> {command.price:.2f}"
        if command.action == "note":
            return f"NOTE {command.ticker}: {command.note}"
        return f"{command.action} {command.ticker}"


class TelegramCommandListener:
    def __init__(self, processor: TelegramCommandProcessor, poll_interval: float = 5.0) -> None:
        self.processor = processor
        self.poll_interval = poll_interval
        self.offset: int | None = None
        self._stop = threading.Event()
        self.thread = threading.Thread(target=self._run, name="telegram-command-listener", daemon=True)

    def start(self) -> None:
        self._bootstrap_offset()
        self.thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _bootstrap_offset(self) -> None:
        try:
            updates = fetch_telegram_updates(self.processor.config)
        except Exception:
            return
        if updates:
            self.offset = max(int(update.get("update_id", 0)) for update in updates) + 1

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                updates = fetch_telegram_updates(self.processor.config, offset=self.offset, timeout=0)
                for update in updates:
                    self.offset = int(update.get("update_id", 0)) + 1
                    reply = self.processor.handle_update(update)
                    if reply:
                        send_telegram_text(self.processor.config, reply)
            except Exception:
                pass
            self._stop.wait(self.poll_interval)
