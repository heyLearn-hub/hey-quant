from __future__ import annotations

from datetime import UTC, datetime
import json
from unittest.mock import patch

from quant_ai_system.config import ResearchConfig
from quant_ai_system.research import build_news_briefs, fetch_fmp_stock_news


class _FakeResponse:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self) -> bytes:
        today = datetime.now(tz=UTC).date().isoformat()
        return json.dumps(
            [
                {
                    "symbol": "NVDA",
                    "publishedDate": f"{today}T12:00:00Z",
                    "title": "Nvidia AI data center demand beats expectations after cloud order",
                    "site": "Example",
                    "url": "https://example.com/nvda",
                    "text": "Analysts upgrade shares after record revenue.",
                },
                {
                    "symbol": "TSLA",
                    "publishedDate": f"{today}T12:00:00Z",
                    "title": "Tesla faces probe and margin pressure after delay",
                    "site": "Example",
                    "url": "https://example.com/tsla",
                },
            ]
        ).encode("utf-8")


def test_fetch_fmp_stock_news_normalizes_payload(monkeypatch) -> None:
    monkeypatch.setenv("FMP_API_KEY", "test-key")

    with patch("quant_ai_system.research.urlopen", return_value=_FakeResponse()):
        items, issue = fetch_fmp_stock_news(["NVDA"], ResearchConfig(news_limit_per_ticker=2))

    assert issue == ""
    assert items[0].ticker == "NVDA"
    assert "AI data center" in items[0].title


def test_build_news_briefs_flags_catalysts_and_risks(monkeypatch) -> None:
    monkeypatch.setenv("FMP_API_KEY", "test-key")

    with patch("quant_ai_system.research.urlopen", return_value=_FakeResponse()):
        briefs = build_news_briefs(["NVDA", "TSLA"], ResearchConfig(news_limit_per_ticker=2))

    by_ticker = {brief.ticker: brief for brief in briefs}
    assert {"AI", "data center", "earnings beat"} <= set(by_ticker["NVDA"].catalyst_flags)
    assert {"investigation", "margin pressure", "delay"} <= set(by_ticker["TSLA"].risk_flags)


def test_build_news_briefs_requires_api_key(monkeypatch) -> None:
    monkeypatch.delenv("FMP_API_KEY", raising=False)

    briefs = build_news_briefs(["NVDA"], ResearchConfig())

    assert briefs[0].article_count == 0
    assert "FMP_API_KEY" in briefs[0].data_issue
