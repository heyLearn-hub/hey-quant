from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from quant_ai_system.config import AppConfig
from quant_ai_system.data import get_market_data
from quant_ai_system.indicators import build_indicators
from quant_ai_system.monitor import fetch_fmp_quote
from quant_ai_system.portfolio_store import get_data_symbol, list_positions
from quant_ai_system.research import build_news_briefs


@dataclass(frozen=True)
class AnalystResponse:
    command: str
    ticker: str
    conclusion: str
    sections: dict[str, list[str]]
    intended_alpha: str
    unwanted_risk: str
    retained_exposure: str
    binding_constraint: str
    liquidity_exit_posture: str
    supervisor: str


@dataclass(frozen=True)
class TradePlan:
    action: str
    ticker: str
    shares: float
    price: float
    stop_price: float | None = None


def format_analyst_response(response: AnalystResponse) -> str:
    lines = [f"Quant AI Analyst · {response.command}", f"{response.ticker}: {response.conclusion}", ""]
    for idx, (title, items) in enumerate(response.sections.items(), start=1):
        lines.append(f"{idx}. {title}")
        lines.extend(f"- {item}" for item in items)
    next_idx = len(response.sections) + 1
    lines.extend(
        [
            f"{next_idx}. Public Equity 风控",
            f"- intended alpha: {response.intended_alpha}",
            f"- unwanted risk: {response.unwanted_risk}",
            f"- retained exposure: {response.retained_exposure}",
            f"- binding constraint: {response.binding_constraint}",
            f"- liquidity/exit posture: {response.liquidity_exit_posture}",
            f"{next_idx + 1}. Supervisor",
            f"- {response.supervisor}",
        ]
    )
    return "\n".join(lines)


def _latest_price(config: AppConfig, ticker: str) -> tuple[float | None, str]:
    ticker = ticker.strip().upper()
    data_symbol = get_data_symbol(config.storage.db_path, ticker)
    quote, issue = fetch_fmp_quote(ticker, data_symbol, config)
    if quote is not None:
        return quote.price, f"fmp quote {quote.data_symbol}"
    data = get_market_data([data_symbol], config.data)
    frame = data.prices.get(data_symbol)
    if frame is None or frame.empty:
        return None, issue or "no usable quote or daily close"
    close = float(frame["close"].iloc[-1])
    return close, f"daily close fallback {data_symbol}"


def _technical_snapshot(config: AppConfig, ticker: str) -> list[str]:
    ticker = ticker.strip().upper()
    data_symbol = get_data_symbol(config.storage.db_path, ticker)
    benchmark = config.universe.primary_benchmark
    data = get_market_data(list(dict.fromkeys([data_symbol, benchmark])), config.data)
    frame = data.prices.get(data_symbol)
    if frame is None or frame.empty:
        return ["技术面无法计算：没有可用日线数据"]
    indicators = build_indicators(frame, data.prices.get(benchmark))
    usable = indicators.dropna(subset=["close"])
    if usable.empty:
        return ["技术面无法计算：日线数据不足"]
    latest = usable.iloc[-1]
    close = _safe_float(latest.get("close"))
    ma50 = _safe_float(latest.get("ma50"))
    ma200 = _safe_float(latest.get("ma200"))
    mom20 = _safe_float(latest.get("mom20"))
    mom60 = _safe_float(latest.get("mom60"))
    rsi14 = _safe_float(latest.get("rsi14"))
    atr_pct = _safe_float(latest.get("atr_pct"))
    lines = [f"收盘 {close:.2f}" if close is not None else "收盘无数据"]
    if close is not None and ma50 is not None:
        lines.append("价格高于50日线" if close > ma50 else "价格低于50日线")
    if close is not None and ma200 is not None:
        lines.append("价格高于200日线" if close > ma200 else "价格低于200日线")
    if mom20 is not None:
        lines.append(f"20日动量 {mom20 * 100:.1f}%")
    if mom60 is not None:
        lines.append(f"60日动量 {mom60 * 100:.1f}%")
    if rsi14 is not None:
        lines.append(f"RSI {rsi14:.1f}")
    if atr_pct is not None:
        lines.append(f"ATR {atr_pct * 100:.1f}%")
    return lines


def _ticker_action_context(config: AppConfig, ticker: str, price: float) -> dict[str, object]:
    ticker = ticker.strip().upper()
    data_symbol = get_data_symbol(config.storage.db_path, ticker)
    benchmark = config.universe.primary_benchmark
    data = get_market_data(list(dict.fromkeys([data_symbol, benchmark])), config.data)
    frame = data.prices.get(data_symbol)
    if frame is None or frame.empty:
        return {
            "conclusion": "data_fix_required",
            "binding": "没有可用日线数据，不能生成行动价位",
            "technical": ["技术面无法计算：没有可用日线数据"],
            "levels": ["数据修复前不做交易计划"],
            "sizing": ["数据阻断，不建议开仓"],
            "risks": ["缺少价格历史会造成错误止损和仓位判断"],
            "triggers": ["先修复 ticker/provider/alias，再重新 /check"],
        }
    indicators = build_indicators(frame, data.prices.get(benchmark))
    usable = indicators.dropna(subset=["close", "atr14"])
    if usable.empty:
        return {
            "conclusion": "research_only",
            "binding": "日线历史不足，不能计算 ATR 行动价位",
            "technical": ["技术面不足：ATR/均线数据不完整"],
            "levels": ["只观察，不生成入场区"],
            "sizing": ["不建议开仓"],
            "risks": ["样本不足会低估波动"],
            "triggers": ["等待更多历史数据或改用可靠数据源"],
        }
    latest = usable.iloc[-1]
    close = _safe_float(latest.get("close")) or price
    atr14 = _safe_float(latest.get("atr14"))
    atr_pct = _safe_float(latest.get("atr_pct"))
    mom20 = _safe_float(latest.get("mom20"))
    mom60 = _safe_float(latest.get("mom60"))
    rsi14 = _safe_float(latest.get("rsi14"))
    ma50 = _safe_float(latest.get("ma50"))
    ma200 = _safe_float(latest.get("ma200"))
    rel20 = _safe_float(latest.get("rel20"))
    rel60 = _safe_float(latest.get("rel60"))
    atr = atr14 or max(close * 0.05, 0.01)
    pullback = max(price - atr, 0.01)
    invalidation = max(price - 2 * atr, 0.01)
    deeper_invalidation = max(price - 2.5 * atr, 0.01)
    trend_ok = close > (ma50 or 0) and close > (ma200 or 0)
    overextended = (mom60 is not None and mom60 > 0.8) or (atr_pct is not None and atr_pct > 0.07) or (rsi14 is not None and rsi14 > 72)
    if overextended:
        conclusion = "do_not_chase"
        binding = "短线涨幅或波动过高，等待回踩确认"
        max_weight = "2%-3% NAV"
    elif trend_ok and mom20 is not None and mom20 > 0:
        conclusion = "wait_for_pullback"
        binding = "趋势有效，但需要更清晰入场和止损"
        max_weight = "3%-5% NAV"
    else:
        conclusion = "watch"
        binding = "趋势或动量确认不足，先观察"
        max_weight = "0%-2% NAV"
    technical = [
        "趋势强：高于50/200日线" if trend_ok else "趋势未完全确认",
        f"20日动量 {mom20 * 100:.1f}%" if mom20 is not None else "20日动量无数据",
        f"60日动量 {mom60 * 100:.1f}%" if mom60 is not None else "60日动量无数据",
        f"RSI {rsi14:.1f}" if rsi14 is not None else "RSI无数据",
        f"ATR {atr_pct * 100:.1f}%" if atr_pct is not None else f"ATR {atr:.2f}",
    ]
    if rel20 is not None or rel60 is not None:
        technical.append(
            "相对强度 "
            + ", ".join(
                item
                for item in [
                    f"20日 {rel20 * 100:.1f}%" if rel20 is not None else "",
                    f"60日 {rel60 * 100:.1f}%" if rel60 is not None else "",
                ]
                if item
            )
        )
    levels = [
        "当前不追，先等触发条件",
        f"第一观察区 {pullback:.2f}（约1 ATR回踩）",
        f"失效线 {invalidation:.2f}（约2 ATR）",
        f"深度风控线 {deeper_invalidation:.2f}（约2.5 ATR）",
    ]
    sizing = [
        f"最大建议仓位 {max_weight}",
        "没有明确 stop 不允许买入/加仓",
        "如要执行，请用 /plan 带股数、价格和 stop 复核",
    ]
    risks = []
    if overextended:
        risks.append("短线过热或波动偏高，追高容易被回撤洗出")
    if atr_pct is not None and atr_pct > 0.06:
        risks.append("ATR较高，同样金额对应更高止损风险")
    if mom60 is not None and mom60 > 0.8:
        risks.append("60日涨幅过大，容易出现叙事退潮或获利回吐")
    risks.append("新闻和主题催化不能替代价格/止损纪律")
    triggers = [
        f"回踩 {pullback:.2f} 附近后重新站稳：再用 /plan 审查小仓",
        f"跌破 {invalidation:.2f}：当前趋势交易想法作废",
        "大盘/SMH 转弱：降低仓位或放弃追入",
    ]
    return {
        "conclusion": conclusion,
        "binding": binding,
        "technical": technical,
        "levels": levels,
        "sizing": sizing,
        "risks": risks,
        "triggers": triggers,
    }


def _news_snapshot(config: AppConfig, ticker: str) -> list[str]:
    brief = build_news_briefs([ticker.strip().upper()], config.research)[0]
    if brief.data_issue:
        return [f"新闻数据问题: {brief.data_issue}"]
    flags = []
    if brief.risk_flags:
        flags.append(f"风险: {', '.join(brief.risk_flags[:3])}")
    if brief.catalyst_flags:
        flags.append(f"催化: {', '.join(brief.catalyst_flags[:3])}")
    if brief.headlines:
        flags.append(f"最新: {brief.headlines[0]}")
    return flags or ["无高优先级新闻风险"]


def review_trade_plan(config: AppConfig, plan: TradePlan) -> AnalystResponse:
    action = plan.action.strip().lower()
    ticker = plan.ticker.strip().upper()
    notional = plan.shares * plan.price
    nav_pct = notional / config.account.nav if config.account.nav > 0 else 0.0
    max_loss = max((plan.price - plan.stop_price) * plan.shares, 0.0) if plan.stop_price is not None else None
    risk_pct = max_loss / config.account.nav if max_loss is not None and config.account.nav > 0 else None
    if action in {"buy", "add"} and plan.stop_price is None:
        conclusion = "reject"
        binding = "buy/add plan requires a stop to bound downside risk"
    elif action not in {"buy", "add", "trim", "sell"}:
        conclusion = "reject"
        binding = "unsupported action"
    elif action in {"buy", "add"} and risk_pct is not None and risk_pct > config.risk.risk_budget_max:
        conclusion = "manual_review"
        binding = "risk budget usage exceeds default max"
    elif action in {"buy", "add"}:
        conclusion = "approve_small_probe"
        binding = "position size and stop are mechanically reviewable"
    else:
        conclusion = "manual_review"
        binding = "sell-side action should confirm current holding and execution price"
    sections = {
        "技术/数据": [f"计划动作 {action.upper()} {ticker}", f"计划价格 {plan.price:.2f}"],
        "新闻/事件": ["新闻不单独生成买入结论"],
        "持仓/组合影响": [f"金额 {notional:.2f}", f"占 NAV {nav_pct * 100:.2f}%"],
        "LOTS/风控": [
            f"最大亏损 {max_loss:.2f}" if max_loss is not None else "最大亏损无法计算",
            f"风险预算 {risk_pct * 100:.2f}% NAV" if risk_pct is not None else "风险预算无法计算",
        ],
    }
    return AnalystResponse(
        command="PLAN",
        ticker=ticker,
        conclusion=conclusion,
        sections=sections,
        intended_alpha="manual trade plan alpha under review",
        unwanted_risk="oversizing, chasing, and unbounded downside",
        retained_exposure="existing portfolio exposure plus proposed trade",
        binding_constraint=binding,
        liquidity_exit_posture="manual execution only; stop required for add/buy review",
        supervisor=f"local_rule: {conclusion}",
    )


def analyze_position(config: AppConfig, ticker: str) -> AnalystResponse:
    ticker = ticker.strip().upper()
    positions = {position.ticker: position for position in list_positions(config.storage.db_path)}
    position = positions.get(ticker)
    if position is None:
        return AnalystResponse(
            command="POSITION",
            ticker=ticker,
            conclusion="not_held",
            sections={
                "技术/数据": [f"{ticker} 不是当前 open position"],
                "新闻/事件": ["未做持仓新闻审查"],
                "持仓/组合影响": [f"如需单票研究请用 /check {ticker}"],
                "LOTS/风控": ["未持仓，无需持仓止损动作"],
            },
            intended_alpha="not applicable because this is not an open position",
            unwanted_risk="inventing holding advice for a non-held ticker",
            retained_exposure="no retained position exposure",
            binding_constraint="ticker is not in open positions",
            liquidity_exit_posture="use /check before considering a new manual trade",
            supervisor="local_rule: not_held",
        )
    price, source = _latest_price(config, ticker)
    if price is None:
        conclusion = "data_fix_required"
        pnl_pct = None
        market_value = None
    else:
        pnl_pct = price / position.average_cost - 1 if position.average_cost > 0 else None
        market_value = price * position.shares
        if position.current_stop is not None and price <= position.current_stop:
            conclusion = "exit_candidate"
        elif pnl_pct is not None and pnl_pct >= config.risk.profit_protection_min_gain:
            conclusion = "protect_profit"
        elif pnl_pct is not None and pnl_pct <= -config.risk.risk_budget_max * 4:
            conclusion = "trim_candidate"
        else:
            conclusion = "hold"
    pnl_text = f"浮盈亏 {pnl_pct * 100:.1f}%" if pnl_pct is not None else "浮盈亏无法计算"
    value_text = f"市值 {market_value:.2f}" if market_value is not None else "市值无法计算"
    stop_text = f"手动止损 {position.current_stop:.2f}" if position.current_stop is not None else "未设置手动止损"
    protection = "保护利润：考虑上移止损或部分减仓" if conclusion == "protect_profit" else "未触发利润保护"
    return AnalystResponse(
        command="POSITION",
        ticker=ticker,
        conclusion=conclusion,
        sections={
            "技术/数据": [f"价格来源 {source}", f"当前价 {price:.2f}" if price is not None else "当前价不可用"],
            "新闻/事件": _news_snapshot(config, ticker),
            "持仓/组合影响": [f"{position.shares:g} 股", f"成本 {position.average_cost:.2f}", value_text, pnl_text],
            "LOTS/风控": [stop_text, protection],
        },
        intended_alpha="retain intended swing exposure while monitoring exit risk",
        unwanted_risk="profit giveback, loss escalation, and stale price data",
        retained_exposure="existing manual position remains until user records a trim or sell",
        binding_constraint="open position review depends on current price and configured stop",
        liquidity_exit_posture="manual hold/trim/exit review; no automatic order is placed",
        supervisor=f"local_rule: {conclusion}",
    )


def analyze_ticker(config: AppConfig, ticker: str) -> AnalystResponse:
    ticker = ticker.strip().upper()
    price, source = _latest_price(config, ticker)
    news = _news_snapshot(config, ticker)
    if price is None:
        conclusion = "data_fix_required"
        binding = "no usable quote or daily close"
        context = {
            "technical": ["当前价不可用，不能生成行动卡片"],
            "levels": ["数据修复前不做交易计划"],
            "sizing": ["数据阻断，不建议开仓"],
            "risks": ["缺少价格会导致止损和仓位错误"],
            "triggers": ["修复 FMP/provider/alias 后重新 /check"],
        }
    else:
        context = _ticker_action_context(config, ticker, price)
        conclusion = str(context["conclusion"])
        binding = str(context["binding"])
    return AnalystResponse(
        command="CHECK",
        ticker=ticker,
        conclusion=conclusion,
        sections={
            "今日结论": [f"当前价 {price:.2f}" if price is not None else "当前价不可用", f"价格来源 {source}"] + list(context["technical"]),
            "可执行价位": list(context["levels"]),
            "仓位建议": list(context["sizing"]),
            "风险原因": list(context["risks"]) + news,
            "改变结论": list(context["triggers"]),
        },
        intended_alpha="AI/semi/tech swing-trend candidate after data and risk review",
        unwanted_risk="chasing, headline noise, factor crowding, and oversized single-name exposure",
        retained_exposure="no retained exposure unless opened manually",
        binding_constraint=binding,
        liquidity_exit_posture="action-card only; use /plan with size and stop before any manual trade",
        supervisor=f"local_rule: {conclusion}",
    )


def _safe_float(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if isfinite(number) else None
