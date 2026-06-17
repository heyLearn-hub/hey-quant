from __future__ import annotations

import json
from datetime import UTC, datetime

from quant_ai_system.data import providers


class _FakeResponse:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self) -> bytes:
        rows = [
            {"symbol": "MSFT", "date": "2026-06-12", "open": 391.43, "high": 391.74, "low": 382.27, "close": 390.74, "volume": 34922036},
            {"symbol": "MSFT", "date": "2026-06-11", "open": 386.5, "high": 392.0, "low": 385.1, "close": 391.43, "volume": 31200000},
        ]
        return json.dumps(rows).encode("utf-8")


def test_download_fmp_normalizes_ohlcv(monkeypatch) -> None:
    monkeypatch.setenv("FMP_API_KEY", "test-key")
    monkeypatch.setattr(providers, "urlopen", lambda *args, **kwargs: _FakeResponse())

    prices, issues = providers._download_fmp(
        ["MSFT"],
        datetime(2026, 1, 1, tzinfo=UTC),
        datetime(2026, 6, 14, tzinfo=UTC),
    )

    assert not issues
    assert "MSFT" in prices
    frame = prices["MSFT"]
    assert list(frame.columns) == ["open", "high", "low", "close", "volume"]
    assert frame.index.is_monotonic_increasing
    assert frame.iloc[-1]["close"] == 390.74


def test_check_provider_data_reports_fmp_coverage(monkeypatch) -> None:
    monkeypatch.setenv("FMP_API_KEY", "test-key")
    monkeypatch.setattr(providers, "urlopen", lambda *args, **kwargs: _FakeResponse())

    checks = providers.check_provider_data(
        ["MSFT"],
        "fmp",
        providers.DataConfig(years=1),
    )

    assert checks[0].ticker == "MSFT"
    assert checks[0].provider == "fmp"
    assert checks[0].rows == 2
    assert checks[0].latest_close == 390.74


def test_check_provider_data_reports_missing_fmp_key(monkeypatch) -> None:
    monkeypatch.delenv("FMP_API_KEY", raising=False)

    checks = providers.check_provider_data(
        ["MSFT"],
        "fmp",
        providers.DataConfig(years=1),
    )

    assert checks[0].ok is False
    assert "FMP_API_KEY" in checks[0].message
