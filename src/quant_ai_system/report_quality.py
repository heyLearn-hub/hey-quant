from __future__ import annotations


def validate_action_report_text(text: str) -> list[str]:
    problems: list[str] = []
    weak_tokens = text.count("无数据") + text.count("无信号")
    has_action_frame = any(
        marker in text
        for marker in [
            "数据修复优先",
            "当前持仓行动",
            "仓位 / LOTS 风险",
            "可执行股票候选",
            "战术 ETF",
            "今日无可执行买入",
        ]
    )
    if weak_tokens >= 3 and not has_action_frame:
        problems.append("日报包含多个无数据/无信号提示，但没有行动结论")
    if "观察池风控候选" in text:
        problems.append("Telegram 日报不应推送完整观察池风控候选列表")
    return problems
