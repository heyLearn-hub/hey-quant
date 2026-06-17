from __future__ import annotations

import numpy as np
import pandas as pd


def sma(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window=window, min_periods=window).mean()


def rsi(series: pd.Series, window: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / window, adjust=False, min_periods=window).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / window, adjust=False, min_periods=window).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def atr(frame: pd.DataFrame, window: int = 14) -> pd.Series:
    high_low = frame["high"] - frame["low"]
    high_close = (frame["high"] - frame["close"].shift()).abs()
    low_close = (frame["low"] - frame["close"].shift()).abs()
    true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    return true_range.ewm(alpha=1 / window, adjust=False, min_periods=window).mean()


def build_indicators(frame: pd.DataFrame, benchmark: pd.DataFrame | None = None) -> pd.DataFrame:
    out = frame.copy()
    close = out["close"]
    out["ma50"] = sma(close, 50)
    out["ma200"] = sma(close, 200)
    out["mom20"] = close.pct_change(20)
    out["mom60"] = close.pct_change(60)
    out["rsi14"] = rsi(close, 14)
    out["atr14"] = atr(out, 14)
    out["volume_ma20"] = out["volume"].rolling(20, min_periods=20).mean()
    if benchmark is not None and not benchmark.empty:
        aligned = pd.concat([close, benchmark["close"].rename("benchmark_close")], axis=1).ffill()
        rel = aligned["close"] / aligned["benchmark_close"]
        out["rel20"] = rel.pct_change(20)
        out["rel60"] = rel.pct_change(60)
    else:
        out["rel20"] = np.nan
        out["rel60"] = np.nan
    out["daily_return"] = close.pct_change()
    return out

