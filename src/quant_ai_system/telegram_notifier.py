from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from quant_ai_system.action_summary import build_action_summary
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
    summary = build_action_summary(
        result.signals,
        result.supervisor_reviews,
        result.exit_reviews,
        result.drift_reviews,
        result.news_briefs,
        set(result.tactical_tickers),
        2,
    )

    lines = [
        "Quant AI 今日提醒",
        f"数据阻断: {', '.join(review.ticker for review in summary.data_fix_positions) if summary.data_fix_positions else '无'}",
        f"持仓行动: {', '.join(review.ticker for review in summary.position_exit_actions[:5]) if summary.position_exit_actions else '无'}",
        f"仓位风险: {', '.join(review.ticker for review in summary.position_size_actions[:5]) if summary.position_size_actions else '无'}",
        f"股票候选: {', '.join(signal.ticker for signal in summary.stock_candidates) if summary.stock_candidates else '无'}",
        f"战术ETF候选: {', '.join(signal.ticker for signal in summary.tactical_candidates) if summary.tactical_candidates else '无'}",
        f"新闻风险: {', '.join(brief.ticker for brief in summary.news_risks[:5]) if summary.news_risks else '无'}",
        f"组合模式: {result.portfolio_risk.mode}",
        f"数据质量问题: {len(result.market_data.issues)}",
    ]

    if not (summary.data_fix_positions or summary.position_exit_actions or summary.position_size_actions or summary.stock_candidates or summary.tactical_candidates):
        lines.extend(["", summary.no_action_message])

    if summary.data_fix_positions:
        lines.extend(["", "数据修复优先"])
        for review in summary.data_fix_positions[:6]:
            lines.append(f"- {review.ticker}: 无法计算盈亏/止损/仓位风险")
            lines.append(f"  {'; '.join(review.notes[:2])}")

    if summary.position_exit_actions:
        lines.extend(["", "当前持仓行动"])
        for review in summary.position_exit_actions[:5]:
            pnl = f"{review.current_pnl_pct * 100:.1f}%" if review.current_pnl_pct is not None else "无数据"
            giveback = f"{review.profit_giveback_pct * 100:.1f}%" if review.profit_giveback_pct is not None else "未进入保护"
            stop = f"{review.dynamic_stop:.2f}" if review.dynamic_stop is not None else "未设置"
            lines.append(f"- {review.ticker}: {review.action}, 当前浮盈 {pnl}, 回吐 {giveback}, 保护线 {stop}")
            lines.append(f"  {'; '.join(review.notes[:2])}")

    if summary.position_size_actions:
        lines.extend(["", "仓位 / LOTS 风险"])
        for review in summary.position_size_actions[:5]:
            actual_weight = f"{review.actual_weight * 100:.1f}%" if review.actual_weight is not None else "无数据"
            risk_pct = f"{review.stop_loss_nav_pct * 100:.1f}%" if review.stop_loss_nav_pct is not None else "无法计算"
            budget = f"{review.risk_budget_pct * 100:.1f}%" if review.risk_budget_pct is not None else "无信号"
            lines.append(f"- {review.ticker}: {review.action}, 实际仓位 {actual_weight}, 止损风险 {risk_pct}, 预算 {budget}")
            lines.append(f"  {'; '.join(review.notes[:2])}")

    if summary.stock_candidates:
        lines.extend(["", "可执行股票候选"])
        for signal in summary.stock_candidates:
            lines.append(f"- {signal.ticker}: {signal.action}, 综合分 {signal.score:.1f}, 止损参考 {signal.position.stop_price:.2f}")

    if summary.tactical_candidates:
        lines.extend(["", "战术 ETF / 杠杆候选"])
        for signal in summary.tactical_candidates:
            lines.append(f"- {signal.ticker}: {signal.action}, 综合分 {signal.score:.1f}, 目标股数 {signal.position.target_shares:.0f}, 止损 {signal.position.stop_price:.2f}")
            lines.append(f"  {signal.position.unwanted_risk}; {signal.position.liquidity_exit_posture}")

    if summary.research_watch:
        lines.extend(["", "研究观察"])
        for signal in summary.research_watch[:5]:
            lines.append(f"- {signal.ticker}: {signal.action}, 综合分 {signal.score:.1f}，未进入可执行候选")

    if summary.news_risks or summary.news_catalysts:
        lines.extend(["", "FMP 新闻面"])
        for brief in (summary.news_risks + [item for item in summary.news_catalysts if item.ticker not in {risk.ticker for risk in summary.news_risks}])[:5]:
            risk = ", ".join(brief.risk_flags[:3]) if brief.risk_flags else "无"
            catalyst = ", ".join(brief.catalyst_flags[:3]) if brief.catalyst_flags else "无"
            lines.append(f"- {brief.ticker}: 新闻 {brief.article_count} 条, 催化 {catalyst}, 风险 {risk}")
            if brief.headlines:
                lines.append(f"  {brief.headlines[0]}")

    if result.positions and not summary.position_exit_actions and not summary.data_fix_positions:
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

    send_telegram_text(config, build_telegram_message(result))


def send_telegram_text(config: AppConfig, text: str) -> None:
    telegram = config.telegram
    token = _env(telegram.bot_token_env)
    chat_id = _env(telegram.chat_id_env)
    if not token or not chat_id:
        raise ValueError("Telegram env vars are incomplete: TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are required")

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    for chunk in _chunks(text, TELEGRAM_LIMIT - 200):
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "text": chunk,
            "disable_web_page_preview": "true" if telegram.disable_web_page_preview else "false",
        }
        if telegram.parse_mode:
            payload["parse_mode"] = telegram.parse_mode
        _post_json(url, payload)


def fetch_telegram_updates(config: AppConfig, offset: int | None = None, timeout: int = 0) -> list[dict[str, Any]]:
    token = _env(config.telegram.bot_token_env)
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN is required")
    params: dict[str, Any] = {}
    if offset is not None:
        params["offset"] = offset
    if timeout:
        params["timeout"] = timeout
    suffix = f"?{urllib.parse.urlencode(params)}" if params else ""
    url = f"https://api.telegram.org/bot{token}/getUpdates{suffix}"
    request = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(request, timeout=30) as response:
        parsed = json.loads(response.read().decode("utf-8"))
    if not parsed.get("ok"):
        raise RuntimeError(f"Telegram API error: {parsed}")
    return list(parsed.get("result", []))
