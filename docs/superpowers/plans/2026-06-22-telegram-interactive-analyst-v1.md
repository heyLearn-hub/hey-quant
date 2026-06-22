# Telegram Interactive Analyst v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Telegram `/check`, `/position`, and `/plan` commands that return structured ticker, holding, and trade-plan analysis without placing trades or mutating SQLite.

**Architecture:** Create a focused `interactive_analyst.py` module that computes deterministic risk reviews from existing market data, indicators, data quality, portfolio store, and news helpers. Extend `TelegramCommandProcessor` only as a routing/parser layer so existing confirmed write commands remain unchanged.

**Tech Stack:** Python dataclasses, pandas, existing `quant_ai_system` modules, pytest, SQLite portfolio store, FMP/yfinance provider chain through existing abstractions.

---

## File Structure

- Create `src/quant_ai_system/interactive_analyst.py`
  - Owns `TradePlan`, `AnalystResponse`, `analyze_ticker`, `analyze_position`, `review_trade_plan`, and `format_analyst_response`.
  - Uses deterministic templates for Public Equity risk fields.
- Modify `src/quant_ai_system/telegram_commands.py`
  - Add routing for `/check`, `/position`, `/plan`.
  - Add parser for `/plan ACTION TICKER SHARES PRICE [stop STOP_PRICE]`.
  - Ensure analyst commands never create pending confirmations.
- Create `tests/test_interactive_analyst.py`
  - Unit tests for analyst logic and formatting.
- Modify `tests/test_telegram_commands.py`
  - Integration tests for command routing, authorization, malformed usage, and no-write behavior.
- Update `README.md` and `docs/milestones.md`
  - Document the new Telegram analyst commands after implementation.

## Task 1: Analyst Core Types And Formatting

**Files:**
- Create: `src/quant_ai_system/interactive_analyst.py`
- Test: `tests/test_interactive_analyst.py`

- [ ] **Step 1: Write failing tests for response formatting**

Add tests that expect a structured Telegram response with Public Equity fields:

```python
from quant_ai_system.interactive_analyst import AnalystResponse, format_analyst_response


def test_format_analyst_response_includes_public_equity_fields() -> None:
    response = AnalystResponse(
        command="CHECK",
        ticker="MRVL",
        conclusion="watch",
        sections={
            "技术/数据": ["趋势确认", "ATR 5.0%"],
            "新闻/事件": ["无高优先级风险"],
            "持仓/组合影响": ["非当前持仓"],
            "LOTS/风控": ["小仓观察"],
        },
        intended_alpha="AI/semi trend exposure",
        unwanted_risk="追高和主题拥挤",
        retained_exposure="未建仓则无保留暴露",
        binding_constraint="等待更好入场",
        liquidity_exit_posture="日线风控可管理",
        supervisor="local_rule: hold",
    )

    text = format_analyst_response(response)

    assert "Quant AI Analyst · CHECK" in text
    assert "MRVL: watch" in text
    assert "intended alpha" in text
    assert "unwanted risk" in text
    assert "retained exposure" in text
    assert "binding constraint" in text
    assert "liquidity/exit posture" in text
    assert "Supervisor" in text
```

- [ ] **Step 2: Run test to verify failure**

Run:

```bash
.venv/bin/python -m pytest tests/test_interactive_analyst.py::test_format_analyst_response_includes_public_equity_fields -q
```

Expected: fail because `quant_ai_system.interactive_analyst` does not exist.

- [ ] **Step 3: Implement minimal types and formatter**

Add:

```python
from __future__ import annotations

from dataclasses import dataclass


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
```

- [ ] **Step 4: Run test to verify pass**

Run:

```bash
.venv/bin/python -m pytest tests/test_interactive_analyst.py::test_format_analyst_response_includes_public_equity_fields -q
```

Expected: pass.

## Task 2: `/plan` Trade Plan Review

**Files:**
- Modify: `src/quant_ai_system/interactive_analyst.py`
- Test: `tests/test_interactive_analyst.py`

- [ ] **Step 1: Write failing tests for trade-plan review**

Add:

```python
from quant_ai_system.config import load_config
from quant_ai_system.interactive_analyst import TradePlan, review_trade_plan
from quant_ai_system.portfolio_store import list_positions


def test_review_trade_plan_calculates_notional_nav_and_max_loss(tmp_path):
    config = load_config("config/default.yaml")
    config = replace(config, storage=replace(config.storage, db_path=str(tmp_path / "portfolio.sqlite3")))

    response = review_trade_plan(config, TradePlan("buy", "INTC", 5, 135, 128))
    text = format_analyst_response(response)

    assert response.command == "PLAN"
    assert response.ticker == "INTC"
    assert "金额" in text
    assert "675.00" in text
    assert "最大亏损 35.00" in text
    assert list_positions(config.storage.db_path) == []


def test_review_trade_plan_rejects_buy_without_stop(tmp_path):
    config = load_config("config/default.yaml")
    config = replace(config, storage=replace(config.storage, db_path=str(tmp_path / "portfolio.sqlite3")))

    response = review_trade_plan(config, TradePlan("buy", "INTC", 5, 135, None))

    assert response.conclusion == "reject"
    assert "stop" in response.binding_constraint.lower()
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
.venv/bin/python -m pytest tests/test_interactive_analyst.py::test_review_trade_plan_calculates_notional_nav_and_max_loss tests/test_interactive_analyst.py::test_review_trade_plan_rejects_buy_without_stop -q
```

Expected: fail because `TradePlan` and `review_trade_plan` do not exist.

- [ ] **Step 3: Implement `TradePlan` and `review_trade_plan`**

Implement:

```python
@dataclass(frozen=True)
class TradePlan:
    action: str
    ticker: str
    shares: float
    price: float
    stop_price: float | None = None


def review_trade_plan(config: AppConfig, plan: TradePlan) -> AnalystResponse:
    action = plan.action.lower()
    ticker = plan.ticker.upper()
    notional = plan.shares * plan.price
    nav_pct = notional / config.account.nav if config.account.nav > 0 else 0
    max_loss = max((plan.price - plan.stop_price) * plan.shares, 0) if plan.stop_price else None
    risk_pct = max_loss / config.account.nav if max_loss is not None and config.account.nav > 0 else None
    if action in {"buy", "add"} and plan.stop_price is None:
        conclusion = "reject"
        binding = "buy/add plan requires a stop to bound downside risk"
    elif action in {"buy", "add"} and risk_pct is not None and risk_pct > config.risk.risk_budget_max:
        conclusion = "manual_review"
        binding = "risk budget usage exceeds default max"
    elif action in {"buy", "add"}:
        conclusion = "approve_small_probe"
        binding = "position size and stop are mechanically reviewable"
    elif action in {"trim", "sell"}:
        conclusion = "manual_review"
        binding = "sell-side action should confirm current holding and execution price"
    else:
        conclusion = "reject"
        binding = "unsupported action"
    sections = {
        "技术/数据": [f"计划价格 {plan.price:.2f}", "交易前审查不替代实时盘口"],
        "新闻/事件": ["新闻不单独生成买入结论"],
        "持仓/组合影响": [f"计划金额 {notional:.2f}", f"占 NAV {nav_pct * 100:.2f}%"],
        "LOTS/风控": [
            f"最大亏损 {max_loss:.2f}" if max_loss is not None else "最大亏损无法计算",
            f"风险预算 {risk_pct * 100:.2f}% NAV" if risk_pct is not None else "风险预算无法计算",
        ],
    }
    return AnalystResponse("PLAN", ticker, conclusion, sections, "manual trade plan alpha under review", "oversizing, chasing, and unbounded downside", "existing portfolio exposure plus proposed trade", binding, "manual execution only; stop required for add/buy review", f"local_rule: {conclusion}")
```

- [ ] **Step 4: Run tests to verify pass**

Run:

```bash
.venv/bin/python -m pytest tests/test_interactive_analyst.py -q
```

Expected: pass for current tests.

## Task 3: `/position` Holding Review

**Files:**
- Modify: `src/quant_ai_system/interactive_analyst.py`
- Test: `tests/test_interactive_analyst.py`

- [ ] **Step 1: Write failing tests for position review**

Add:

```python
from quant_ai_system.portfolio_store import upsert_position


def test_analyze_position_protects_profitable_position(tmp_path, monkeypatch):
    config = load_config("config/default.yaml")
    db = tmp_path / "portfolio.sqlite3"
    config = replace(config, storage=replace(config.storage, db_path=str(db)))
    upsert_position(db, "SNXX", 10, 36, 32, "profitable")
    monkeypatch.setattr("quant_ai_system.interactive_analyst._latest_price", lambda config, ticker: (46.0, "fmp quote"))

    response = analyze_position(config, "SNXX")
    text = format_analyst_response(response)

    assert response.conclusion == "protect_profit"
    assert "浮盈亏 27.8%" in text
    assert "保护" in text


def test_analyze_position_not_held_suggests_check(tmp_path):
    config = load_config("config/default.yaml")
    config = replace(config, storage=replace(config.storage, db_path=str(tmp_path / "portfolio.sqlite3")))

    response = analyze_position(config, "MRVL")

    assert response.conclusion == "not_held"
    assert "/check MRVL" in format_analyst_response(response)
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
.venv/bin/python -m pytest tests/test_interactive_analyst.py::test_analyze_position_protects_profitable_position tests/test_interactive_analyst.py::test_analyze_position_not_held_suggests_check -q
```

Expected: fail because `analyze_position` and `_latest_price` do not exist.

- [ ] **Step 3: Implement `analyze_position`**

Implementation should:

- find open position by ticker;
- return `not_held` if not found;
- fetch latest price through `_latest_price`;
- calculate P&L percentage and market value;
- return `exit_candidate` if below manual stop;
- return `protect_profit` if P&L is above `risk.profit_protection_min_gain`;
- return `hold` otherwise.

- [ ] **Step 4: Run tests to verify pass**

Run:

```bash
.venv/bin/python -m pytest tests/test_interactive_analyst.py -q
```

Expected: pass.

## Task 4: `/check` Ticker Quick Analysis

**Files:**
- Modify: `src/quant_ai_system/interactive_analyst.py`
- Test: `tests/test_interactive_analyst.py`

- [ ] **Step 1: Write failing tests for ticker check**

Add:

```python
def test_analyze_ticker_returns_watch_or_candidate_with_risk_fields(monkeypatch):
    config = load_config("config/default.yaml")
    monkeypatch.setattr("quant_ai_system.interactive_analyst._latest_price", lambda config, ticker: (100.0, "fmp quote"))
    monkeypatch.setattr("quant_ai_system.interactive_analyst._technical_snapshot", lambda config, ticker: ["价格高于50日线", "ATR 4.0%"])
    monkeypatch.setattr("quant_ai_system.interactive_analyst._news_snapshot", lambda config, ticker: ["无高优先级新闻风险"])

    response = analyze_ticker(config, "MRVL")
    text = format_analyst_response(response)

    assert response.command == "CHECK"
    assert response.ticker == "MRVL"
    assert response.conclusion in {"watch", "small_probe_candidate", "do_not_chase"}
    assert "intended alpha" in text
    assert "MRVL" in text
```

- [ ] **Step 2: Run test to verify failure**

Run:

```bash
.venv/bin/python -m pytest tests/test_interactive_analyst.py::test_analyze_ticker_returns_watch_or_candidate_with_risk_fields -q
```

Expected: fail because `analyze_ticker` does not exist.

- [ ] **Step 3: Implement `analyze_ticker` and helpers**

Implement helper functions:

- `_latest_price(config, ticker)` uses `monitor.fetch_fmp_quote` with aliases first; falls back to latest daily close from `get_market_data`.
- `_technical_snapshot(config, ticker)` returns compact daily indicator text.
- `_news_snapshot(config, ticker)` returns compact news flags from `build_news_briefs`.

Decision:

- no price -> `data_fix_required`;
- high ATR/overextension text -> `do_not_chase`;
- otherwise -> `watch` for v1.

- [ ] **Step 4: Run tests to verify pass**

Run:

```bash
.venv/bin/python -m pytest tests/test_interactive_analyst.py -q
```

Expected: pass.

## Task 5: Telegram Routing

**Files:**
- Modify: `src/quant_ai_system/telegram_commands.py`
- Modify: `tests/test_telegram_commands.py`

- [ ] **Step 1: Write failing Telegram routing tests**

Add tests:

```python
def test_check_command_routes_to_interactive_analyst(tmp_path, monkeypatch):
    processor = _processor(tmp_path, monkeypatch, [])
    monkeypatch.setattr("quant_ai_system.telegram_commands.analyze_ticker", lambda config, ticker: _fake_response("CHECK", ticker, "watch"))
    monkeypatch.setattr("quant_ai_system.telegram_commands.format_analyst_response", lambda response: f"{response.command}:{response.ticker}:{response.conclusion}")

    assert processor.handle_text("123", "/check MRVL") == "CHECK:MRVL:watch"


def test_plan_command_does_not_create_pending_confirmation(tmp_path, monkeypatch):
    processor = _processor(tmp_path, monkeypatch, [])
    monkeypatch.setattr("quant_ai_system.telegram_commands.review_trade_plan", lambda config, plan: _fake_response("PLAN", plan.ticker, "approve_small_probe"))
    monkeypatch.setattr("quant_ai_system.telegram_commands.format_analyst_response", lambda response: f"{response.command}:{response.ticker}:{response.conclusion}")

    reply = processor.handle_text("123", "/plan buy INTC 5 135 stop 128")

    assert reply == "PLAN:INTC:approve_small_probe"
    assert processor.pending == {}
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
.venv/bin/python -m pytest tests/test_telegram_commands.py::test_check_command_routes_to_interactive_analyst tests/test_telegram_commands.py::test_plan_command_does_not_create_pending_confirmation -q
```

Expected: fail because routing is not implemented.

- [ ] **Step 3: Implement Telegram routing and parser**

Modify `TelegramCommandProcessor.handle_text`:

- `/check TICKER` calls `analyze_ticker`;
- `/position TICKER` calls `analyze_position`;
- `/plan ACTION TICKER SHARES PRICE [stop STOP]` parses a `TradePlan`;
- malformed commands return usage text.

- [ ] **Step 4: Run Telegram tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_telegram_commands.py -q
```

Expected: pass.

## Task 6: Documentation And Final Verification

**Files:**
- Modify: `README.md`
- Modify: `docs/milestones.md`

- [ ] **Step 1: Document commands**

Add Telegram analyst usage examples:

```text
/check MRVL
/position SNXX
/plan buy INTC 5 135 stop 128
```

State that analyst commands are read-only and do not create pending confirmations.

- [ ] **Step 2: Run target and full tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_interactive_analyst.py tests/test_telegram_commands.py -q
.venv/bin/python -m pytest -q
```

Expected: all tests pass.

- [ ] **Step 3: Run production checks**

Run:

```bash
TELEGRAM_BOT_TOKEN=configured TELEGRAM_CHAT_ID=configured FMP_API_KEY=configured DEEPSEEK_API_KEY=configured bin/quant-ai-local release-check --config config/default.yaml
rg -n "REAL_SECRET_PREFIX_1|REAL_SECRET_PREFIX_2|REAL_BOT_TOKEN_PREFIX" README.md bin docs src tests config scripts Dockerfile docker-compose.yml pyproject.toml requirements.txt -S
```

Expected:

- release-check: `FAIL=0`;
- secret scan: no matches.

- [ ] **Step 4: Commit and push**

Run:

```bash
git add README.md docs/milestones.md src/quant_ai_system/interactive_analyst.py src/quant_ai_system/telegram_commands.py tests/test_interactive_analyst.py tests/test_telegram_commands.py
git commit -m "Add Telegram interactive analyst commands"
git push origin codex/telegram-interactive-analyst-v1
```

Expected: branch is pushed.

## Self-Review

- Spec coverage: `/check`, `/position`, `/plan`, Public Equity fields, no automatic trading, no SQLite mutation for analyst commands, malformed command handling, and Telegram authorization are covered.
- Completion-marker scan: no unfinished marker text or deferred implementation markers are used as requirements.
- Type consistency: `AnalystResponse`, `TradePlan`, and formatting names are consistent across tasks.
