from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SerenityAlphaHypothesis:
    ticker: str
    observed_demand_change: str
    financial_transmission: str
    validation_metrics: list[str] = field(default_factory=list)
    falsification_condition: str = ""


def blank_research_hypothesis(ticker: str) -> SerenityAlphaHypothesis:
    return SerenityAlphaHypothesis(
        ticker=ticker,
        observed_demand_change="待输入新闻、财报电话会或供应链证据；无证据时仅保留观察。",
        financial_transmission="待映射到收入、毛利、经营杠杆或现金流项目。",
        validation_metrics=["收入增速/指引", "毛利率或产品组合", "订单/库存/产能利用率", "管理层主动提及需求驱动"],
        falsification_condition="若未来1-4个季度没有财务验证，降级为观察或移出股票池。",
    )

