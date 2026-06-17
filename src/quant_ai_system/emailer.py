from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage
from pathlib import Path

from quant_ai_system.config import AppConfig
from quant_ai_system.engine import RunResult


def _env(name: str) -> str:
    return os.environ.get(name, "").strip()


def build_email_body(result: RunResult) -> str:
    approved = {review.ticker for review in result.supervisor_reviews if review.decision == "approve_for_consideration"}
    core = [
        signal
        for signal in sorted(result.signals, key=lambda item: item.score, reverse=True)
        if signal.ticker in approved and ("加仓" in signal.action or "小仓" in signal.action)
    ]
    risk_items = [signal for signal in result.signals if "减仓" in signal.action or "退出" in signal.action]
    exit_items = [review for review in result.exit_reviews if review.severity >= 50]
    drift_items = [review for review in result.drift_reviews if review.severity >= 50]
    lines = [
        "今日结论",
        f"- 核心候选: {', '.join(signal.ticker for signal in core[:2]) if core else '无'}",
        f"- 风控候选: {', '.join(signal.ticker for signal in risk_items) if risk_items else '无'}",
        f"- 持仓保护触发: {', '.join(review.ticker for review in exit_items) if exit_items else '无'}",
        f"- LOTS 偏离: {', '.join(review.ticker for review in drift_items) if drift_items else '无'}",
        f"- 数据质量问题: {len(result.market_data.issues)}",
        "",
        "核心候选",
    ]
    for signal in core[:2]:
        lines.append(
            f"- {signal.ticker}: {signal.action}, 综合分 {signal.score:.1f}, "
            f"初始股数 {signal.position.initial_shares:.0f}, 目标股数 {signal.position.target_shares:.0f}, "
            f"止损参考 {signal.position.stop_price:.2f}"
        )
    lines.extend(["", "当前持仓检查"])
    if result.positions:
        signal_by_ticker = {signal.ticker: signal for signal in result.signals}
        exit_by_ticker = {review.ticker: review for review in result.exit_reviews}
        drift_by_ticker = {review.ticker: review for review in result.drift_reviews}
        for position in result.positions:
            signal = signal_by_ticker.get(position.ticker)
            exit_review = exit_by_ticker.get(position.ticker)
            drift_review = drift_by_ticker.get(position.ticker)
            action = signal.action if signal else "无信号"
            protection = drift_review.action if drift_review else exit_review.action if exit_review else "未生成"
            pnl = f"{(signal.close / position.average_cost - 1) * 100:.1f}%" if signal else "无数据"
            lines.append(f"- {position.ticker}: {position.shares:.2f} 股, 成本 {position.average_cost:.2f}, 浮盈亏 {pnl}, 系统动作 {action}, 保护动作 {protection}")
    else:
        lines.append("- 暂无录入持仓")
    lines.extend(["", "Supervisor 审查"])
    for review in result.supervisor_reviews[:8]:
        lines.append(f"- {review.ticker}: {review.decision} / {review.final_action} / {review.rationale}")
    if result.market_data.issues:
        lines.extend(["", "数据质量提示"])
        for issue in result.market_data.issues[:12]:
            lines.append(f"- {issue.ticker} / {issue.provider}: {issue.message}")
    lines.extend(["", f"完整报告: {Path(result.report_path).resolve()}"])
    return "\n".join(lines)


def send_summary_email(config: AppConfig, result: RunResult) -> None:
    email_config = config.email
    username = _env(email_config.username_env)
    password = _env(email_config.password_env)
    from_addr = _env(email_config.from_addr_env) or username
    to_addrs = [addr.strip() for addr in _env(email_config.to_addrs_env).split(",") if addr.strip()]
    if not username or not password or not from_addr or not to_addrs:
        raise ValueError("SMTP env vars are incomplete: username/password/from/to are required")

    risk_count = sum(1 for signal in result.signals if "减仓" in signal.action or "退出" in signal.action)
    risk_count += sum(1 for review in result.exit_reviews if review.severity >= 50)
    risk_count += sum(1 for review in result.drift_reviews if review.severity >= 50)
    subject_type = "风控提醒" if risk_count else "每日摘要"
    msg = EmailMessage()
    msg["Subject"] = f"{email_config.subject_prefix} {subject_type}"
    msg["From"] = from_addr
    msg["To"] = ", ".join(to_addrs)
    msg.set_content(build_email_body(result))
    if Path(result.report_path).exists():
        msg.add_attachment(Path(result.report_path).read_bytes(), maintype="text", subtype="html", filename=Path(result.report_path).name)

    with smtplib.SMTP(email_config.smtp_host, email_config.smtp_port, timeout=30) as smtp:
        if email_config.use_tls:
            smtp.starttls()
        smtp.login(username, password)
        smtp.send_message(msg)
