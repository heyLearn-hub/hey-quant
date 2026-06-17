from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

from quant_ai_system.config import SupervisorConfig
from quant_ai_system.signals import SignalResult


@dataclass(frozen=True)
class SupervisorDecision:
    ticker: str
    decision: str
    approval_score: float
    final_action: str
    rationale: str
    blockers: list[str]
    required_checks: list[str]
    provider: str


REVIEW_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "reviews": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "ticker": {"type": "string"},
                    "decision": {"type": "string", "enum": ["approve_for_consideration", "hold", "reject", "manual_review"]},
                    "approval_score": {"type": "number", "minimum": 0, "maximum": 100},
                    "final_action": {"type": "string"},
                    "rationale": {"type": "string"},
                    "blockers": {"type": "array", "items": {"type": "string"}},
                    "required_checks": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["ticker", "decision", "approval_score", "final_action", "rationale", "blockers", "required_checks"],
            },
        }
    },
    "required": ["reviews"],
}


def _signal_payload(signals: list[SignalResult], data_quality_issues: list[object]) -> list[dict[str, Any]]:
    issue_count = len(data_quality_issues)
    payload = []
    for signal in signals:
        payload.append(
            {
                "ticker": signal.ticker,
                "action": signal.action,
                "combined_score": round(signal.score, 2),
                "technical_score": round(signal.technical_score, 2),
                "quality_score": round(signal.quality.score, 2),
                "quality_note": signal.quality.note,
                "style": signal.quality.style,
                "price": round(signal.close, 2),
                "initial_shares": signal.position.initial_shares,
                "target_shares": signal.position.target_shares,
                "target_weight": round(signal.position.target_weight, 4),
                "initial_weight": round(signal.position.initial_weight, 4),
                "stop_price": round(signal.position.stop_price, 2),
                "binding_constraint": signal.position.binding_constraint,
                "risk_notes": signal.risk.notes,
                "data_quality_issue_count": issue_count,
            }
        )
    return payload


def local_supervisor_review(
    signals: list[SignalResult],
    config: SupervisorConfig,
    data_quality_issues: list[object],
) -> list[SupervisorDecision]:
    decisions: list[SupervisorDecision] = []
    data_blocked = any(getattr(issue, "provider", "") == "sample" for issue in data_quality_issues)
    ranked = sorted(signals, key=lambda item: item.score, reverse=True)
    approvals = 0
    for signal in ranked:
        blockers: list[str] = []
        checks = ["确认行情数据不是样本/过期数据", "确认财报日期和重大新闻", "确认止损价和可接受亏损金额"]
        if data_blocked:
            blockers.append("当前报告使用样本或非实时数据，不能作为执行依据")
        if signal.score < config.min_approval_score:
            blockers.append("综合分低于主管审批门槛")
        if signal.position.target_shares <= 0:
            blockers.append("LOTS 目标股数为0")
        if "退出" in signal.action or "减仓" in signal.action:
            decision = "reject"
            final_action = signal.action
            blockers.append("量化层已触发减仓/退出")
        elif blockers:
            decision = "manual_review" if data_blocked else "hold"
            final_action = "暂缓"
        elif approvals < config.max_core_approvals and ("加仓" in signal.action or "小仓" in signal.action):
            decision = "approve_for_consideration"
            final_action = "可考虑执行"
            approvals += 1
        else:
            decision = "hold"
            final_action = "观察"
        rationale = (
            f"综合分 {signal.score:.1f}，技术分 {signal.technical_score:.1f}，质量分 {signal.quality.score:.1f}；"
            f"仓位约束为 {signal.position.binding_constraint}。"
        )
        decisions.append(
            SupervisorDecision(
                ticker=signal.ticker,
                decision=decision,
                approval_score=0 if blockers else min(signal.score, 95),
                final_action=final_action,
                rationale=rationale,
                blockers=blockers,
                required_checks=checks,
                provider="local_rules",
            )
        )
    return decisions


def _parse_reviews(raw_text: str, provider: str) -> list[SupervisorDecision]:
    data = json.loads(raw_text)
    return [
        SupervisorDecision(
            ticker=str(item["ticker"]).upper(),
            decision=str(item["decision"]),
            approval_score=float(item["approval_score"]),
            final_action=str(item["final_action"]),
            rationale=str(item["rationale"]),
            blockers=list(item.get("blockers", [])),
            required_checks=list(item.get("required_checks", [])),
            provider=provider,
        )
        for item in data.get("reviews", [])
    ]


def openai_supervisor_review(
    signals: list[SignalResult],
    config: SupervisorConfig,
    data_quality_issues: list[object],
) -> list[SupervisorDecision]:
    from openai import OpenAI

    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    payload = _signal_payload(signals, data_quality_issues)
    prompt = {
        "role": "user",
        "content": (
            "Act as a public-equity investment committee supervisor. Review these quant signals for a small, "
            "concentrated US tech/AI portfolio. Do not give personalized financial advice or automatic execution. "
            "Approve only signals that pass data quality, trend, quality, sizing, stop-loss, and concentration checks. "
            f"Policy: {config.policy or []}. Signals: {json.dumps(payload, ensure_ascii=False)}"
        ),
    }
    response = client.responses.create(
        model=config.model,
        input=[prompt],
        text={
            "format": {
                "type": "json_schema",
                "name": "supervisor_reviews",
                "strict": True,
                "schema": REVIEW_SCHEMA,
            }
        },
    )
    return _parse_reviews(response.output_text, "openai")


def run_supervisor_review(
    signals: list[SignalResult],
    config: SupervisorConfig,
    data_quality_issues: list[object],
) -> list[SupervisorDecision]:
    if not config.enabled:
        return []
    if config.provider == "openai" and os.environ.get("OPENAI_API_KEY"):
        try:
            return openai_supervisor_review(signals, config, data_quality_issues)
        except Exception as exc:
            fallback = local_supervisor_review(signals, config, data_quality_issues)
            return [
                SupervisorDecision(
                    ticker=item.ticker,
                    decision="manual_review" if item.decision == "approve_for_consideration" else item.decision,
                    approval_score=min(item.approval_score, 50),
                    final_action="GPT审查失败，人工复核",
                    rationale=f"OpenAI review failed: {exc}. Local fallback applied.",
                    blockers=item.blockers + ["OpenAI supervisor review failed"],
                    required_checks=item.required_checks,
                    provider="local_rules_after_openai_failure",
                )
                for item in fallback
            ]
    if config.require_api:
        return [
            SupervisorDecision(
                ticker=signal.ticker,
                decision="manual_review",
                approval_score=0,
                final_action="缺少OPENAI_API_KEY，人工复核",
                rationale="Supervisor requires OpenAI API but no key is configured.",
                blockers=["OPENAI_API_KEY is missing"],
                required_checks=["配置OPENAI_API_KEY后重新运行"],
                provider="missing_openai_key",
            )
            for signal in signals
        ]
    return local_supervisor_review(signals, config, data_quality_issues)

