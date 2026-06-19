from __future__ import annotations

from quant_ai_system.report_quality import validate_action_report_text


def test_report_quality_rejects_weak_no_data_dump() -> None:
    text = "A 无数据\nB 无信号\nC 无数据\n观察池风控候选: NVDA, MSFT"

    problems = validate_action_report_text(text)

    assert problems


def test_report_quality_accepts_action_framed_no_data_report() -> None:
    text = "数据修复优先\n- SNXX: 无数据\n- MUU: 无信号\n今日无可执行买入"

    assert validate_action_report_text(text) == []
