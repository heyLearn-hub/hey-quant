from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

from quant_ai_system.config import SupervisorConfig
from quant_ai_system.research import NewsBrief
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


def _signal_payload(
    signals: list[SignalResult],
    data_quality_issues: list[object],
    news_briefs: list[NewsBrief] | None = None,
) -> list[dict[str, Any]]:
    issue_count = len(data_quality_issues)
    news_by_ticker = {brief.ticker: brief for brief in news_briefs or []}
    payload = []
    for signal in signals:
        news = news_by_ticker.get(signal.ticker)
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
                "news": {
                    "article_count": news.article_count,
                    "latest_at": news.latest_at,
                    "catalyst_flags": news.catalyst_flags,
                    "risk_flags": news.risk_flags,
                    "headline": news.headlines[0] if news.headlines else "",
                    "data_issue": news.data_issue,
                }
                if news
                else {},
            }
        )
    return payload


def local_supervisor_review(
    signals: list[SignalResult],
    config: SupervisorConfig,
    data_quality_issues: list[object],
    news_briefs: list[NewsBrief] | None = None,
) -> list[SupervisorDecision]:
    decisions: list[SupervisorDecision] = []
    data_blocked = any(getattr(issue, "provider", "") == "sample" for issue in data_quality_issues)
    news_by_ticker = {brief.ticker: brief for brief in news_briefs or []}
    ranked = sorted(signals, key=lambda item: item.score, reverse=True)
    approvals = 0
    for signal in ranked:
        blockers: list[str] = []
        checks = ["确认行情数据不是样本/过期数据", "确认财报日期和重大新闻", "确认止损价和可接受亏损金额"]
        news = news_by_ticker.get(signal.ticker)
        if news and news.risk_flags:
            checks.append(f"复核FMP新闻风险: {', '.join(news.risk_flags[:3])}")
            if "加仓" in signal.action or "小仓" in signal.action:
                blockers.append("候选股存在FMP新闻风险标记，执行前需要人工确认")
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
            decision = "manual_review" if data_blocked or (news and news.risk_flags) else "hold"
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


def _supervisor_prompt(
    config: SupervisorConfig,
    signals: list[SignalResult],
    data_quality_issues: list[object],
    news_briefs: list[NewsBrief] | None = None,
) -> str:
    payload = _signal_payload(signals, data_quality_issues, news_briefs)
    return (
        "Act as a public-equity investment committee supervisor for a small, concentrated US tech/AI portfolio. "
        "This is research support, not personalized financial advice or automatic execution. "
        "Approve only signals that pass data quality, trend, quality, sizing, stop-loss, liquidity, news-risk, and concentration checks. "
        "Return JSON only with this exact shape: "
        '{"reviews":[{"ticker":"MSFT","decision":"approve_for_consideration|hold|reject|manual_review",'
        '"approval_score":0,"final_action":"string","rationale":"string","blockers":[],"required_checks":[]}]}. '
        f"Policy: {config.policy or []}. Signals: {json.dumps(payload, ensure_ascii=False)}"
    )


def _chat_completion_supervisor_review(
    signals: list[SignalResult],
    config: SupervisorConfig,
    data_quality_issues: list[object],
    news_briefs: list[NewsBrief] | None = None,
    *,
    provider: str,
    api_key: str,
    base_url: str | None = None,
) -> list[SupervisorDecision]:
    from openai import OpenAI

    client = OpenAI(api_key=api_key, base_url=base_url) if base_url else OpenAI(api_key=api_key)
    response = client.chat.completions.create(
        model=config.model,
        messages=[
            {"role": "system", "content": "You are a strict investment risk supervisor. Return valid JSON only."},
            {"role": "user", "content": _supervisor_prompt(config, signals, data_quality_issues, news_briefs)},
        ],
        response_format={"type": "json_object"},
        temperature=0.2,
    )
    content = response.choices[0].message.content or '{"reviews":[]}'
    return _parse_reviews(content, provider)


def openai_supervisor_review(
    signals: list[SignalResult],
    config: SupervisorConfig,
    data_quality_issues: list[object],
    news_briefs: list[NewsBrief] | None = None,
) -> list[SupervisorDecision]:
    api_key = os.environ.get(config.openai_api_key_env, "").strip()
    if not api_key:
        raise ValueError(f"{config.openai_api_key_env} is missing")
    return _chat_completion_supervisor_review(signals, config, data_quality_issues, news_briefs, provider="openai", api_key=api_key)


def deepseek_supervisor_review(
    signals: list[SignalResult],
    config: SupervisorConfig,
    data_quality_issues: list[object],
    news_briefs: list[NewsBrief] | None = None,
) -> list[SupervisorDecision]:
    api_key = os.environ.get(config.deepseek_api_key_env, "").strip()
    if not api_key:
        raise ValueError(f"{config.deepseek_api_key_env} is missing")
    return _chat_completion_supervisor_review(
        signals,
        config,
        data_quality_issues,
        news_briefs,
        provider="deepseek",
        api_key=api_key,
        base_url=config.deepseek_base_url,
    )


def _missing_api_reviews(signals: list[SignalResult], provider: str, env_name: str) -> list[SupervisorDecision]:
    return [
        SupervisorDecision(
            ticker=signal.ticker,
            decision="manual_review",
            approval_score=0,
            final_action=f"缺少{env_name}，人工复核",
            rationale=f"Supervisor requires {provider} API but {env_name} is not configured.",
            blockers=[f"{env_name} is missing"],
            required_checks=[f"配置{env_name}后重新运行"],
            provider=f"missing_{provider}_key",
        )
        for signal in signals
    ]


def _fallback_after_api_failure(
    signals: list[SignalResult],
    config: SupervisorConfig,
    data_quality_issues: list[object],
    news_briefs: list[NewsBrief] | None,
    provider: str,
    exc: Exception,
) -> list[SupervisorDecision]:
    fallback = local_supervisor_review(signals, config, data_quality_issues, news_briefs)
    return [
        SupervisorDecision(
            ticker=item.ticker,
            decision="manual_review" if item.decision == "approve_for_consideration" else item.decision,
            approval_score=min(item.approval_score, 50),
            final_action=f"{provider}审查失败，人工复核",
            rationale=f"{provider} review failed: {exc}. Local fallback applied.",
            blockers=item.blockers + [f"{provider} supervisor review failed"],
            required_checks=item.required_checks,
            provider=f"local_rules_after_{provider}_failure",
        )
        for item in fallback
    ]


def run_supervisor_review(
    signals: list[SignalResult],
    config: SupervisorConfig,
    data_quality_issues: list[object],
    news_briefs: list[NewsBrief] | None = None,
) -> list[SupervisorDecision]:
    if not config.enabled:
        return []
    provider = config.provider.lower().strip()
    if provider == "openai":
        if not os.environ.get(config.openai_api_key_env):
            return _missing_api_reviews(signals, "openai", config.openai_api_key_env) if config.require_api else local_supervisor_review(signals, config, data_quality_issues, news_briefs)
        try:
            return openai_supervisor_review(signals, config, data_quality_issues, news_briefs)
        except Exception as exc:
            return _fallback_after_api_failure(signals, config, data_quality_issues, news_briefs, "openai", exc)
    if provider == "deepseek":
        if not os.environ.get(config.deepseek_api_key_env):
            return _missing_api_reviews(signals, "deepseek", config.deepseek_api_key_env) if config.require_api else local_supervisor_review(signals, config, data_quality_issues, news_briefs)
        try:
            return deepseek_supervisor_review(signals, config, data_quality_issues, news_briefs)
        except Exception as exc:
            return _fallback_after_api_failure(signals, config, data_quality_issues, news_briefs, "deepseek", exc)
    if config.require_api:
        return _missing_api_reviews(signals, provider or "unknown", "SUPERVISOR_API_KEY")
    return local_supervisor_review(signals, config, data_quality_issues, news_briefs)
