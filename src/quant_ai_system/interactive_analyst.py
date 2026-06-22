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
    lines.extend(
        [
            "5. Public Equity 风控",
            f"- intended alpha: {response.intended_alpha}",
            f"- unwanted risk: {response.unwanted_risk}",
            f"- retained exposure: {response.retained_exposure}",
            f"- binding constraint: {response.binding_constraint}",
            f"- liquidity/exit posture: {response.liquidity_exit_posture}",
            "6. Supervisor",
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
    technical = _technical_snapshot(config, ticker)
    news = _news_snapshot(config, ticker)
    if price is None:
        conclusion = "data_fix_required"
        binding = "no usable quote or daily close"
    elif any("ATR 1" in item or "ATR 2" in item for item in technical):
        conclusion = "do_not_chase"
        binding = "short-term volatility is elevated"
    else:
        conclusion = "watch"
        binding = "wait for a plan with explicit size and stop before action"
    return AnalystResponse(
        command="CHECK",
        ticker=ticker,
        conclusion=conclusion,
        sections={
            "技术/数据": [f"价格来源 {source}", f"当前价 {price:.2f}" if price is not None else "当前价不可用"] + technical,
            "新闻/事件": news,
            "持仓/组合影响": ["单票检查不改变当前持仓", "如要交易请继续用 /plan"],
            "LOTS/风控": ["未提供交易计划，不计算最终股数", "需要价格、股数、止损后才能审查风险预算"],
        },
        intended_alpha="AI/semi/tech swing-trend candidate after data and risk review",
        unwanted_risk="chasing, headline noise, factor crowding, and oversized single-name exposure",
        retained_exposure="no retained exposure unless opened manually",
        binding_constraint=binding,
        liquidity_exit_posture="watch-only until a specific manual trade plan is reviewed",
        supervisor=f"local_rule: {conclusion}",
    )


def _safe_float(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if isfinite(number) else None
