from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from quant_ai_system.indicators import build_indicators


DEFAULT_FACTORS = ["mom20", "mom60", "rel20", "rel60", "rsi14"]


@dataclass(frozen=True)
class FactorMetric:
    factor: str
    observations: int
    top_quantile_forward_return: float
    bottom_quantile_forward_return: float
    spread: float
    hit_rate: float


def run_factor_experiment(
    prices: dict[str, pd.DataFrame],
    tickers: list[str],
    benchmark_ticker: str,
    factors: list[str] | None = None,
    forward_days: int = 20,
    quantile: float = 0.2,
) -> tuple[list[FactorMetric], pd.DataFrame]:
    factors = factors or DEFAULT_FACTORS
    benchmark = prices.get(benchmark_ticker)
    rows: list[dict[str, object]] = []
    for ticker in tickers:
        frame = prices.get(ticker)
        if frame is None or frame.empty:
            continue
        ind = build_indicators(frame, benchmark)
        ind["forward_return"] = ind["close"].shift(-forward_days) / ind["close"] - 1
        for date, row in ind.dropna(subset=["forward_return"]).iterrows():
            item = {"ticker": ticker, "date": date, "forward_return": float(row["forward_return"])}
            for factor in factors:
                item[factor] = row.get(factor)
            rows.append(item)
    raw = pd.DataFrame(rows).dropna(subset=factors + ["forward_return"])
    metrics: list[FactorMetric] = []
    if raw.empty:
        return metrics, raw
    for factor in factors:
        ranked = raw[[factor, "forward_return"]].dropna().sort_values(factor)
        if ranked.empty:
            continue
        n = max(int(len(ranked) * quantile), 1)
        bottom = ranked.head(n)["forward_return"]
        top = ranked.tail(n)["forward_return"]
        metrics.append(
            FactorMetric(
                factor=factor,
                observations=len(ranked),
                top_quantile_forward_return=float(top.mean()),
                bottom_quantile_forward_return=float(bottom.mean()),
                spread=float(top.mean() - bottom.mean()),
                hit_rate=float((top > 0).mean()),
            )
        )
    return metrics, raw


def write_factor_report(metrics: list[FactorMetric], out_path: str | Path) -> Path:
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    rows = "\n".join(
        f"<tr><td>{m.factor}</td><td>{m.observations}</td><td>{m.top_quantile_forward_return:.2%}</td>"
        f"<td>{m.bottom_quantile_forward_return:.2%}</td><td>{m.spread:.2%}</td><td>{m.hit_rate:.1%}</td></tr>"
        for m in metrics
    )
    html = f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>因子实验报告</title>
<style>body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:#f6f8fb;color:#17202a;margin:0;padding:28px}}table{{border-collapse:collapse;width:100%;background:#fff}}th,td{{padding:10px;border-bottom:1px solid #d9e0e8;text-align:left}}th{{background:#f8fafc}}</style>
</head><body><h1>因子实验报告</h1><p>解释：Top 分组未来收益高于 Bottom 分组，说明这个因子在该样本中有正向区分度。结果只用于研究，不构成交易建议。</p>
<table><thead><tr><th>因子</th><th>样本数</th><th>Top未来收益</th><th>Bottom未来收益</th><th>Spread</th><th>Top胜率</th></tr></thead><tbody>{rows}</tbody></table></body></html>"""
    out.write_text(html, encoding="utf-8")
    return out

