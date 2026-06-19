from __future__ import annotations

from quant_ai_system.config import SupervisorConfig
import numpy as np
import pandas as pd

from quant_ai_system.data.providers import DataIssue
from quant_ai_system.indicators import build_indicators
from quant_ai_system.quality import QualityAssessment
from quant_ai_system.research import NewsBrief
from quant_ai_system.signals import evaluate_signal
from quant_ai_system.config import AccountConfig, QualityConfig, RiskConfig
from quant_ai_system.supervisor import deepseek_supervisor_review, local_supervisor_review, run_supervisor_review


def _uptrend_frame() -> tuple[pd.DataFrame, pd.DataFrame]:
    dates = pd.bdate_range(end=pd.Timestamp("2026-06-12", tz="UTC"), periods=320)
    close = np.linspace(100, 210, len(dates))
    volume = np.full(len(dates), 2_000_000)
    volume[-1] = 3_000_000
    stock = pd.DataFrame(
        {
            "open": close * 0.995,
            "high": close * 1.01,
            "low": close * 0.99,
            "close": close,
            "volume": volume,
        },
        index=dates,
    )
    benchmark_close = np.linspace(100, 150, len(dates))
    benchmark = pd.DataFrame(
        {
            "open": benchmark_close,
            "high": benchmark_close * 1.005,
            "low": benchmark_close * 0.995,
            "close": benchmark_close,
            "volume": volume,
        },
        index=dates,
    )
    return stock, benchmark


def test_local_supervisor_blocks_sample_data_execution() -> None:
    stock, benchmark = _uptrend_frame()
    frame = build_indicators(stock, benchmark)
    signal = evaluate_signal(
        "MSFT",
        frame,
        AccountConfig(nav=17_870),
        RiskConfig(),
        QualityAssessment("MSFT", 92, "quality compounder", "buffett_quality"),
        QualityConfig(),
    )
    assert signal is not None

    reviews = local_supervisor_review(
        [signal],
        SupervisorConfig(min_approval_score=50),
        [DataIssue("*", "sample", "sample data")],
    )

    assert reviews[0].decision == "manual_review"
    assert "样本" in reviews[0].blockers[0]


def test_local_supervisor_can_approve_clean_high_score_signal() -> None:
    stock, benchmark = _uptrend_frame()
    frame = build_indicators(stock, benchmark)
    signal = evaluate_signal(
        "MSFT",
        frame,
        AccountConfig(nav=17_870),
        RiskConfig(),
        QualityAssessment("MSFT", 95, "quality compounder", "buffett_quality"),
        QualityConfig(technical_weight=0.0, quality_weight=1.0),
    )
    assert signal is not None

    reviews = local_supervisor_review([signal], SupervisorConfig(min_approval_score=70), [])

    assert reviews[0].decision in {"approve_for_consideration", "hold"}
    assert reviews[0].provider == "local_rules"


def test_local_supervisor_sends_news_risk_to_manual_review() -> None:
    stock, benchmark = _uptrend_frame()
    frame = build_indicators(stock, benchmark)
    signal = evaluate_signal(
        "MSFT",
        frame,
        AccountConfig(nav=17_870),
        RiskConfig(),
        QualityAssessment("MSFT", 95, "quality compounder", "buffett_quality"),
        QualityConfig(technical_weight=0.0, quality_weight=1.0),
    )
    assert signal is not None

    reviews = local_supervisor_review(
        [signal],
        SupervisorConfig(min_approval_score=70),
        [],
        [
            NewsBrief(
                ticker="MSFT",
                article_count=1,
                latest_at="2026-06-18T00:00:00Z",
                headlines=["Microsoft faces antitrust investigation"],
                catalyst_flags=[],
                risk_flags=["antitrust", "investigation"],
                summary="1 article; risk: antitrust, investigation",
            )
        ],
    )

    assert reviews[0].decision == "manual_review"
    assert "新闻风险" in reviews[0].blockers[0]


def test_deepseek_provider_falls_back_without_key(monkeypatch) -> None:
    stock, benchmark = _uptrend_frame()
    frame = build_indicators(stock, benchmark)
    signal = evaluate_signal(
        "MSFT",
        frame,
        AccountConfig(nav=17_870),
        RiskConfig(),
        QualityAssessment("MSFT", 95, "quality compounder", "buffett_quality"),
        QualityConfig(technical_weight=0.0, quality_weight=1.0),
    )
    assert signal is not None
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

    reviews = run_supervisor_review([signal], SupervisorConfig(provider="deepseek", require_api=False), [])

    assert reviews[0].provider == "local_rules"


def test_deepseek_provider_requires_key_when_configured(monkeypatch) -> None:
    stock, benchmark = _uptrend_frame()
    frame = build_indicators(stock, benchmark)
    signal = evaluate_signal(
        "MSFT",
        frame,
        AccountConfig(nav=17_870),
        RiskConfig(),
        QualityAssessment("MSFT", 95, "quality compounder", "buffett_quality"),
        QualityConfig(technical_weight=0.0, quality_weight=1.0),
    )
    assert signal is not None
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

    reviews = run_supervisor_review([signal], SupervisorConfig(provider="deepseek", require_api=True), [])

    assert reviews[0].decision == "manual_review"
    assert reviews[0].provider == "missing_deepseek_key"


def test_deepseek_review_parses_json_response(monkeypatch) -> None:
    stock, benchmark = _uptrend_frame()
    frame = build_indicators(stock, benchmark)
    signal = evaluate_signal(
        "MSFT",
        frame,
        AccountConfig(nav=17_870),
        RiskConfig(),
        QualityAssessment("MSFT", 95, "quality compounder", "buffett_quality"),
        QualityConfig(technical_weight=0.0, quality_weight=1.0),
    )
    assert signal is not None
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")

    class _FakeMessage:
        content = (
            '{"reviews":[{"ticker":"MSFT","decision":"hold","approval_score":72,'
            '"final_action":"观察","rationale":"test","blockers":[],"required_checks":["check"]}]}'
        )

    class _FakeChoice:
        message = _FakeMessage()

    class _FakeCompletions:
        def create(self, **kwargs):
            assert kwargs["model"] == "deepseek-v4-pro"
            assert kwargs["response_format"] == {"type": "json_object"}
            return type("Resp", (), {"choices": [_FakeChoice()]})()

    class _FakeClient:
        def __init__(self, api_key=None, base_url=None):
            assert api_key == "test-key"
            assert base_url == "https://api.deepseek.com"
            self.chat = type("Chat", (), {"completions": _FakeCompletions()})()

    monkeypatch.setattr("openai.OpenAI", _FakeClient)

    reviews = deepseek_supervisor_review([signal], SupervisorConfig(provider="deepseek"), [])

    assert reviews[0].ticker == "MSFT"
    assert reviews[0].provider == "deepseek"
