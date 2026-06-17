from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import json
import os
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen

import numpy as np
import pandas as pd

from quant_ai_system.config import DataConfig


REQUIRED_COLUMNS = ["open", "high", "low", "close", "volume"]


@dataclass(frozen=True)
class DataIssue:
    ticker: str
    provider: str
    message: str


@dataclass
class MarketDataSet:
    prices: dict[str, pd.DataFrame]
    issues: list[DataIssue]
    as_of: pd.Timestamp | None


def normalize_ohlcv(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=REQUIRED_COLUMNS)
    df = frame.copy()
    df.columns = [str(col).strip().lower().replace(" ", "_") for col in df.columns]
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], utc=True, errors="coerce")
        df = df.set_index("date")
    df.index = pd.to_datetime(df.index, utc=True, errors="coerce")
    df = df[~df.index.isna()].sort_index()
    if "adj_close" in df.columns and "close" in df.columns:
        factor = (df["adj_close"] / df["close"]).replace([np.inf, -np.inf], np.nan).ffill()
        for col in ["open", "high", "low", "close"]:
            if col in df.columns:
                df[col] = df[col] * factor
    keep = [col for col in REQUIRED_COLUMNS if col in df.columns]
    df = df[keep].rename_axis("date")
    for col in REQUIRED_COLUMNS:
        if col not in df.columns:
            df[col] = np.nan
    df = df[REQUIRED_COLUMNS].apply(pd.to_numeric, errors="coerce")
    return df.dropna(subset=["close"])


def _cache_path(cache_dir: Path, ticker: str) -> Path:
    return cache_dir / f"{ticker.upper()}.csv"


def _read_cache(cache_dir: Path, ticker: str) -> pd.DataFrame:
    path = _cache_path(cache_dir, ticker)
    if not path.exists():
        return pd.DataFrame(columns=REQUIRED_COLUMNS)
    return normalize_ohlcv(pd.read_csv(path))


def _write_cache(cache_dir: Path, ticker: str, frame: pd.DataFrame) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    out = frame.reset_index()
    out.to_csv(_cache_path(cache_dir, ticker), index=False)


def _download_yfinance(tickers: list[str], start: datetime, end: datetime) -> tuple[dict[str, pd.DataFrame], list[DataIssue]]:
    issues: list[DataIssue] = []
    try:
        import yfinance as yf
    except ImportError as exc:
        return {}, [DataIssue("*", "yfinance", f"yfinance is not installed: {exc}")]

    try:
        raw = yf.download(
            tickers=" ".join(tickers),
            start=start.date().isoformat(),
            end=end.date().isoformat(),
            group_by="ticker",
            auto_adjust=False,
            progress=False,
            threads=True,
        )
    except Exception as exc:  # pragma: no cover - depends on remote service
        return {}, [DataIssue("*", "yfinance", f"download failed: {exc}")]

    prices: dict[str, pd.DataFrame] = {}
    if raw.empty:
        return prices, [DataIssue("*", "yfinance", "download returned no rows")]

    for ticker in tickers:
        try:
            if isinstance(raw.columns, pd.MultiIndex):
                frame = raw[ticker].dropna(how="all")
            else:
                frame = raw.dropna(how="all")
            norm = normalize_ohlcv(frame)
            if norm.empty:
                issues.append(DataIssue(ticker, "yfinance", "empty normalized frame"))
            else:
                prices[ticker] = norm
        except Exception as exc:  # pragma: no cover - defensive around yfinance shapes
            issues.append(DataIssue(ticker, "yfinance", str(exc)))
    return prices, issues


def _download_fmp(tickers: list[str], start: datetime, end: datetime) -> tuple[dict[str, pd.DataFrame], list[DataIssue]]:
    api_key = os.environ.get("FMP_API_KEY", "").strip()
    if not api_key:
        return {}, [DataIssue("*", "fmp", "FMP_API_KEY is not configured")]

    prices: dict[str, pd.DataFrame] = {}
    issues: list[DataIssue] = []
    for ticker in tickers:
        params = urlencode(
            {
                "symbol": ticker,
                "from": start.date().isoformat(),
                "to": end.date().isoformat(),
                "apikey": api_key,
            }
        )
        url = f"https://financialmodelingprep.com/stable/historical-price-eod/full?{params}"
        try:
            with urlopen(url, timeout=25) as response:
                data = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:  # pragma: no cover - remote service
            issues.append(DataIssue(ticker, "fmp", str(exc)))
            continue
        if isinstance(data, dict) and data.get("Error Message"):
            issues.append(DataIssue(ticker, "fmp", str(data.get("Error Message"))))
            continue
        if not isinstance(data, list) or not data:
            issues.append(DataIssue(ticker, "fmp", "download returned no usable rows"))
            continue
        norm = normalize_ohlcv(pd.DataFrame(data))
        if norm.empty:
            issues.append(DataIssue(ticker, "fmp", "empty normalized frame"))
            continue
        prices[ticker] = norm
    return prices, issues


def _download_stooq(ticker: str, start: datetime, end: datetime) -> tuple[pd.DataFrame, DataIssue | None]:
    d1 = start.strftime("%Y%m%d")
    d2 = end.strftime("%Y%m%d")
    symbol = ticker.lower()
    url = f"https://stooq.com/q/d/l/?s={symbol}.us&d1={d1}&d2={d2}&i=d"
    try:
        frame = pd.read_csv(url)
    except (URLError, OSError, ValueError) as exc:  # pragma: no cover - remote service
        return pd.DataFrame(columns=REQUIRED_COLUMNS), DataIssue(ticker, "stooq", str(exc))
    norm = normalize_ohlcv(frame)
    if norm.empty:
        return norm, DataIssue(ticker, "stooq", "download returned no usable rows")
    return norm, None


def get_market_data(tickers: list[str], config: DataConfig) -> MarketDataSet:
    tickers = list(dict.fromkeys(ticker.upper() for ticker in tickers))
    end = datetime.now(tz=UTC)
    start = end - timedelta(days=int(config.years * 365.25) + 30)
    cache_dir = Path(config.cache_dir)
    prices: dict[str, pd.DataFrame] = {}
    issues: list[DataIssue] = []

    if config.prefer_cache:
        for ticker in tickers:
            cached = _read_cache(cache_dir, ticker)
            if not cached.empty and cached.index.max() >= pd.Timestamp(end - timedelta(days=5)):
                prices[ticker] = cached

    provider_priority = config.provider_priority or ["fmp", "yfinance", "stooq"]
    for provider in provider_priority:
        missing = [ticker for ticker in tickers if ticker not in prices]
        if not missing:
            break
        if provider == "fmp":
            fmp_prices, fmp_issues = _download_fmp(missing, start, end)
            prices.update(fmp_prices)
            issues.extend(fmp_issues)
            for ticker, frame in fmp_prices.items():
                _write_cache(cache_dir, ticker, frame)
            if config.stop_after_paid_provider and os.environ.get("FMP_API_KEY", "").strip():
                break
        elif provider == "yfinance":
            yf_prices, yf_issues = _download_yfinance(missing, start, end)
            prices.update(yf_prices)
            issues.extend(yf_issues)
            for ticker, frame in yf_prices.items():
                _write_cache(cache_dir, ticker, frame)
        elif provider == "stooq":
            for ticker in missing:
                stooq_frame, issue = _download_stooq(ticker, start, end)
                if not stooq_frame.empty:
                    prices[ticker] = stooq_frame
                    _write_cache(cache_dir, ticker, stooq_frame)
                if issue:
                    issues.append(issue)

    for ticker in tickers:
        if ticker in prices and not prices[ticker].empty:
            _write_cache(cache_dir, ticker, prices[ticker])
            continue

    if not prices and config.sample_on_remote_failure:
        sample = make_sample_market_data(tickers, years=min(config.years, 5))
        sample.issues = issues + [
            DataIssue(
                "*",
                "sample",
                "all remote market data providers failed; report uses deterministic sample data and is not live market data",
            )
        ]
        return sample

    as_of = max((frame.index.max() for frame in prices.values() if not frame.empty), default=None)
    return MarketDataSet(prices=prices, issues=issues, as_of=as_of)


def make_sample_market_data(tickers: list[str], years: int = 5, seed: int = 7) -> MarketDataSet:
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range(end=pd.Timestamp.now(tz=UTC).normalize(), periods=252 * years)
    prices: dict[str, pd.DataFrame] = {}
    for idx, ticker in enumerate(dict.fromkeys(tickers)):
        drift = 0.00025 + idx * 0.00001
        vol = 0.018 + (idx % 5) * 0.002
        returns = rng.normal(drift, vol, len(dates))
        close = 80 * np.exp(np.cumsum(returns)) * (1 + idx * 0.02)
        open_ = close * (1 + rng.normal(0, 0.003, len(dates)))
        high = np.maximum(open_, close) * (1 + np.abs(rng.normal(0.004, 0.003, len(dates))))
        low = np.minimum(open_, close) * (1 - np.abs(rng.normal(0.004, 0.003, len(dates))))
        volume = rng.integers(2_000_000, 80_000_000, len(dates))
        prices[ticker] = pd.DataFrame(
            {"open": open_, "high": high, "low": low, "close": close, "volume": volume},
            index=dates,
        ).rename_axis("date")
    return MarketDataSet(prices=prices, issues=[], as_of=dates[-1])
