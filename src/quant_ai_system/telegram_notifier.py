from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from quant_ai_system.config import AppConfig
from quant_ai_system.engine import RunResult


TELEGRAM_LIMIT = 4096


def _env(name: str) -> str:
    return os.environ.get(name, "").strip()


def _chunks(text: str, limit: int = 3800) -> list[str]:
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    for line in text.splitlines():
        line_len = len(line) + 1
        if current and current_len + line_len > limit:
            chunks.append("\n".join(current))
            current = []
            current_len = 0
        current.append(line)
        current_len += line_len
    if current:
        chunks.append("\n".join(current))
    return chunks


def _post_json(url: str, payload: dict[str, Any]) -> dict[str, Any]:
    data = urllib.parse.urlencode(payload).encode("utf-8")
    request = urllib.request.Request(url, data=data, method="POST")
    with urllib.request.urlopen(request, timeout=30) as response:
        raw = response.read().decode("utf-8")
    parsed = json.loads(raw)
    if not parsed.get("ok"):
        raise RuntimeError(f"Telegram API error: {parsed}")
    return parsed


def build_telegram_message(result: RunResult) -> str:
    approved = {review.ticker for review in result.supervisor_reviews if review.decision == "approve_for_consideration"}
    core = [
        signal
        for signal in sorted(result.signals, key=lambda item: item.score, reverse=True)
        if signal.ticker in approved and ("加仓" in signal.action or "小仓" in signal.action)
    ][:2]
    exit_items = [review for review in result.exit_reviews if review.severity >= 50]
    risk_signals = [signal for signal in result.signals if "减仓" in signal.action or "退出" in signal.action]

    lines = [
        "Quant AI 今日提醒",
        f"核心候选: {', '.join(signal.ticker for signal in core) if core else '无'}",
        f"持仓保护触发: {', '.join(review.ticker for review in exit_items) if exit_items else '无'}",
        f"观察池风控候选: {', '.join(signal.ticker for signal in risk_signals[:8]) if risk_signals else '无'}",
        f"组合模式: {result.portfolio_risk.mode}",
        f"数据质量问题: {len(result.market_data.issues)}",
    ]

    if exit_items:
        lines.extend(["", "利润保护 / 退出规则"])
        for review in exit_items[:5]:
            pnl = f"{review.current_pnl_pct * 100:.1f}%" if review.current_pnl_pct is not None else "无数据"
            giveback = f"{review.profit_giveback_pct * 100:.1f}%" if review.profit_giveback_pct is not None else "未进入保护"
            stop = f"{review.dynamic_stop:.2f}" if review.dynamic_stop is not None else "未设置"
            lines.append(f"- {review.ticker}: {review.action}, 当前浮盈 {pnl}, 回吐 {giveback}, 保护线 {stop}")
            lines.append(f"  {'; '.join(review.notes[:2])}")

    if core:
        lines.extend(["", "核心候选"])
        for signal in core:
            lines.append(f"- {signal.ticker}: {signal.action}, 综合分 {signal.score:.1f}, 止损参考 {signal.position.stop_price:.2f}")

    if result.positions and not exit_items:
        lines.extend(["", "当前持仓"])
        signal_by_ticker = {signal.ticker: signal for signal in result.signals}
        for position in result.positions[:5]:
            signal = signal_by_ticker.get(position.ticker)
            pnl = f"{(signal.close / position.average_cost - 1) * 100:.1f}%" if signal else "无数据"
            action = signal.action if signal else "无信号"
            lines.append(f"- {position.ticker}: 浮盈亏 {pnl}, 系统动作 {action}")

    if result.market_data.issues:
        lines.extend(["", "数据质量提示"])
        for issue in result.market_data.issues[:5]:
            lines.append(f"- {issue.ticker}/{issue.provider}: {issue.message}")

    lines.extend(["", f"完整报告: {Path(result.report_path).resolve()}"])
    return "\n".join(lines)


def send_telegram_message(config: AppConfig, result: RunResult) -> None:
    telegram = config.telegram
    token = _env(telegram.bot_token_env)
    chat_id = _env(telegram.chat_id_env)
    if not token or not chat_id:
        raise ValueError("Telegram env vars are incomplete: TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are required")

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    for chunk in _chunks(build_telegram_message(result), TELEGRAM_LIMIT - 200):
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "text": chunk,
            "disable_web_page_preview": "true" if telegram.disable_web_page_preview else "false",
        }
        if telegram.parse_mode:
            payload["parse_mode"] = telegram.parse_mode
        _post_json(url, payload)


def fetch_telegram_updates(config: AppConfig) -> list[dict[str, Any]]:
    token = _env(config.telegram.bot_token_env)
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN is required")
    url = f"https://api.telegram.org/bot{token}/getUpdates"
    request = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(request, timeout=30) as response:
        parsed = json.loads(response.read().decode("utf-8"))
    if not parsed.get("ok"):
        raise RuntimeError(f"Telegram API error: {parsed}")
    return list(parsed.get("result", []))
