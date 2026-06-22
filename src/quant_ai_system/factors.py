from __future__ import annotations

from dataclasses import dataclass
from html import escape
from pathlib import Path

import pandas as pd

from quant_ai_system.indicators import build_indicators


@dataclass(frozen=True)
class FactorDefinition:
    name: str
    group: str
    direction: str
    description: str
    production_use: str
    sector_relevance: str


FACTOR_REGISTRY: dict[str, FactorDefinition] = {
    "mom20": FactorDefinition("mom20", "Momentum", "higher_better", "20日价格动量，观察短中期资金延续性。", "research_signal", "适合半导体/AI趋势股，但容易受短线噪音影响。"),
    "mom60": FactorDefinition("mom60", "Momentum", "higher_better", "60日价格动量，衡量波段趋势是否延续。", "production_signal", "适合半导体/AI/内存股的波段趋势底座。"),
    "mom120": FactorDefinition("mom120", "Momentum", "higher_better", "120日价格动量，观察更长周期资金趋势。", "research_signal", "适合半导体/AI大波段，内存周期股需结合行业周期验证。"),
    "risk_adjusted_mom60": FactorDefinition("risk_adjusted_mom60", "Momentum", "higher_better", "60日动量除以60日实现波动率，观察单位波动下的趋势效率。", "research_signal", "适合比较高波动半导体股票的趋势质量。"),
    "trend_slope_50": FactorDefinition("trend_slope_50", "Trend", "higher_better", "50日均线20日斜率，确认中期趋势是否抬升。", "research_signal", "适合识别半导体/AI趋势是否仍在加速。"),
    "trend_slope_200": FactorDefinition("trend_slope_200", "Trend", "higher_better", "200日均线60日斜率，确认长期趋势是否改善。", "research_signal", "适合过滤周期下行中的假反弹。"),
    "dist_ma50": FactorDefinition("dist_ma50", "Trend", "context", "价格距离50日线百分比，衡量趋势强度或短期过热。", "research_only", "适合解释追高风险，不应简单越高越好。"),
    "dist_ma200": FactorDefinition("dist_ma200", "Trend", "context", "价格距离200日线百分比，衡量长期趋势位置和过度延伸。", "research_only", "适合判断AI/半导体强趋势是否过度拥挤。"),
    "rel20": FactorDefinition("rel20", "Relative strength", "higher_better", "20日相对基准强度，观察短期是否跑赢QQQ/SMH。", "research_signal", "适合板块内轮动确认。"),
    "rel60": FactorDefinition("rel60", "Relative strength", "higher_better", "60日相对基准强度，观察波段是否跑赢QQQ/SMH。", "production_signal", "非常适合半导体/AI股票池筛选。"),
    "realized_vol20": FactorDefinition("realized_vol20", "Volatility", "lower_better", "20日年化实现波动率，衡量近期风险强度。", "risk_control", "适合仓位控制，不适合直接否定高波动强趋势。"),
    "realized_vol60": FactorDefinition("realized_vol60", "Volatility", "lower_better", "60日年化实现波动率，衡量波段持仓风险。", "risk_control", "适合半导体/内存股风险预算和LOTS校准。"),
    "atr_pct": FactorDefinition("atr_pct", "Volatility", "lower_better", "ATR占收盘价比例，衡量日常波动和止损距离。", "risk_control", "适合集中持仓的仓位和止损风险控制。"),
    "drawdown60": FactorDefinition("drawdown60", "Drawdown", "higher_better", "当前价格相对60日高点的回撤，越接近0代表修复越好。", "risk_control", "适合判断半导体回撤是否破坏趋势。"),
    "drawdown120": FactorDefinition("drawdown120", "Drawdown", "higher_better", "当前价格相对120日高点的回撤，观察中期趋势损伤。", "risk_control", "适合内存/设备周期股趋势修复观察。"),
    "rsi14": FactorDefinition("rsi14", "Oscillator", "context", "14日RSI，辅助判断短期过热或动量衰减。", "research_only", "只适合作为追高/过热提示，不应作为核心买入因子。"),
}


DEFAULT_FACTORS = [
    "mom20",
    "mom60",
    "mom120",
    "risk_adjusted_mom60",
    "trend_slope_50",
    "trend_slope_200",
    "dist_ma50",
    "dist_ma200",
    "rel20",
    "rel60",
    "realized_vol20",
    "realized_vol60",
    "atr_pct",
    "drawdown60",
    "drawdown120",
    "rsi14",
]


@dataclass(frozen=True)
class FactorMetric:
    factor: str
    group: str
    direction: str
    description: str
    production_use: str
    sector_relevance: str
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
        definition = FACTOR_REGISTRY.get(
            factor,
            FactorDefinition(factor, "Custom", "unknown", "custom factor", "research_only", "需要人工确认适用范围。"),
        )
        metrics.append(
            FactorMetric(
                factor=factor,
                group=definition.group,
                direction=definition.direction,
                description=definition.description,
                production_use=definition.production_use,
                sector_relevance=definition.sector_relevance,
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
    registry_rows = "\n".join(
        f"<tr><td><code>{escape(item.name)}</code></td><td>{escape(item.group)}</td><td>{escape(item.direction)}</td>"
        f"<td>{escape(item.production_use)}</td><td>{escape(item.description)}</td><td>{escape(item.sector_relevance)}</td></tr>"
        for item in FACTOR_REGISTRY.values()
    )
    groups = sorted({metric.group for metric in metrics})
    grouped_sections = []
    for group in groups:
        rows = "\n".join(
            f"<tr><td><code>{escape(m.factor)}</code></td><td>{escape(m.production_use)}</td><td>{escape(m.direction)}</td>"
            f"<td>{m.observations}</td><td>{m.top_quantile_forward_return:.2%}</td>"
            f"<td>{m.bottom_quantile_forward_return:.2%}</td><td>{m.spread:.2%}</td><td>{m.hit_rate:.1%}</td>"
            f"<td>{escape(m.description)}</td><td>{escape(m.sector_relevance)}</td></tr>"
            for m in metrics
            if m.group == group
        )
        grouped_sections.append(
            f"<h2>{escape(group)}</h2><table><thead><tr><th>因子</th><th>用途</th><th>方向</th><th>样本数</th><th>高分组未来收益</th>"
            f"<th>低分组未来收益</th><th>Spread</th><th>高分组胜率</th><th>经济含义</th><th>半导体/AI适用性</th></tr></thead><tbody>{rows}</tbody></table>"
        )
    grouped_html = "\n".join(grouped_sections) or "<p>暂无可用因子结果。</p>"
    html = f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>因子实验报告</title>
<style>body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:#f6f8fb;color:#17202a;margin:0;padding:28px}}table{{border-collapse:collapse;width:100%;background:#fff;margin:12px 0 28px}}th,td{{padding:10px;border-bottom:1px solid #d9e0e8;text-align:left;vertical-align:top}}th{{background:#f8fafc}}code{{background:#eef2f7;padding:2px 5px;border-radius:4px}}.note{{background:#fff7ed;border:1px solid #fed7aa;border-radius:8px;padding:14px;margin:16px 0}}</style>
</head><body><h1>因子实验报告</h1>
<p>解释：高分组未来收益高于低分组，说明这个因子在该样本中有正向区分度。结果只用于研究，不构成交易建议，也不会自动改变生产买卖信号。</p>
<div class="note"><b>期权/情绪覆盖层暂缓。</b> 先验证这些可回测的日线因子是否真的改善决策，再判断 put/call、IV、option wall 或新闻情绪是否值得接入。</div>
<h2>因子注册表</h2>
<table><thead><tr><th>因子</th><th>分组</th><th>方向</th><th>用途</th><th>经济含义</th><th>半导体/AI适用性</th></tr></thead><tbody>{registry_rows}</tbody></table>
{grouped_html}
</body></html>"""
    out.write_text(html, encoding="utf-8")
    return out
