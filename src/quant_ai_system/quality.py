from __future__ import annotations

from dataclasses import dataclass

from quant_ai_system.config import QualityConfig


@dataclass(frozen=True)
class QualityAssessment:
    ticker: str
    score: float
    note: str
    style: str


def assess_quality(ticker: str, config: QualityConfig, leveraged_tickers: set[str] | None = None) -> QualityAssessment:
    ticker = ticker.upper()
    leveraged_tickers = leveraged_tickers or set()
    overrides = config.score_overrides or {}
    override = overrides.get(ticker, {})
    if override:
        score = float(override.get("score", 50))
        note = str(override.get("note", "manual quality override"))
    elif ticker in leveraged_tickers:
        score = 30
        note = "leveraged ETF; tactical trend vehicle, not a quality compounder"
    else:
        score = 55
        note = "no fundamental override yet; treat as watchlist until financial quality is verified"
    style = "leveraged_tactical" if ticker in leveraged_tickers else "buffett_quality"
    return QualityAssessment(ticker=ticker, score=max(0, min(score, 100)), note=note, style=style)


def combined_score(technical_score: float, quality_score: float, config: QualityConfig) -> float:
    if not config.enabled:
        return technical_score
    total_weight = config.technical_weight + config.quality_weight
    if total_weight <= 0:
        return technical_score
    return (
        technical_score * config.technical_weight
        + quality_score * config.quality_weight
    ) / total_weight

