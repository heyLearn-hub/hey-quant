from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from html import escape
from pathlib import Path

import pandas as pd

from quant_ai_system.config import AppConfig
from quant_ai_system.data.providers import ProviderCheck, check_provider_data
from quant_ai_system.portfolio_store import list_positions, list_symbol_aliases


TRADABLE = "tradable"
RESEARCH_ONLY = "research_only"
DATA_FIX_REQUIRED = "data_fix_required"
BLOCKED = "blocked"

KNOWN_ETFS = {"QQQ", "SMH", "SPY", "SOXX"}
KNOWN_LEVERAGED_ETFS = {"TQQQ", "SOXL", "USD"}


@dataclass(frozen=True)
class DataQualityTarget:
    ticker: str
    data_symbol: str
    roles: tuple[str, ...]
    asset_class: str
    alias_status: str


@dataclass(frozen=True)
class DataQualityRecord:
    ticker: str
    data_symbol: str
    provider: str
    roles: tuple[str, ...]
    asset_class: str
    rows: int
    first_date: pd.Timestamp | None
    last_date: pd.Timestamp | None
    latest_close: float | None
    stale_days: int | None
    ok: bool
    status: str
    alias_status: str
    provider_message: str
    binding_constraint: str
    action: str
    intended_alpha: str
    unwanted_risk: str
    retained_exposure: str
    liquidity_exit_posture: str


@dataclass(frozen=True)
class DataQualityReport:
    provider: str
    generated_at: datetime
    records: tuple[DataQualityRecord, ...]

    @property
    def counts(self) -> Counter[str]:
        return Counter(record.status for record in self.records)


def _add_role(items: dict[str, set[str]], ticker: str, role: str) -> None:
    normalized = ticker.strip().upper()
    if normalized:
        items.setdefault(normalized, set()).add(role)


def _asset_class(ticker: str, roles: set[str]) -> str:
    if "benchmark" in roles:
        return "benchmark"
    if "leveraged_etf" in roles or ticker in KNOWN_LEVERAGED_ETFS:
        return "leveraged_etf"
    if "tactical" in roles or ticker in KNOWN_ETFS:
        return "etf"
    return "stock"


def collect_data_quality_universe(config: AppConfig) -> tuple[DataQualityTarget, ...]:
    roles_by_ticker: dict[str, set[str]] = {}
    for ticker in config.universe.tickers:
        _add_role(roles_by_ticker, ticker, "universe")
    for ticker in config.universe.benchmarks:
        _add_role(roles_by_ticker, ticker, "benchmark")
    for ticker in config.universe.leveraged_tickers:
        _add_role(roles_by_ticker, ticker, "leveraged_etf")
    for ticker in config.universe.tactical_tickers:
        _add_role(roles_by_ticker, ticker, "tactical")
    for position in list_positions(config.storage.db_path):
        _add_role(roles_by_ticker, position.ticker, "open_position")

    aliases = {alias.broker_symbol: alias.data_symbol for alias in list_symbol_aliases(config.storage.db_path)}
    targets: list[DataQualityTarget] = []
    role_priority = {"open_position": 0, "universe": 1, "leveraged_etf": 2, "tactical": 3, "benchmark": 4}
    for ticker in sorted(roles_by_ticker):
        roles = tuple(sorted(roles_by_ticker[ticker], key=lambda role: role_priority.get(role, 99)))
        data_symbol = aliases.get(ticker, ticker).upper()
        targets.append(
            DataQualityTarget(
                ticker=ticker,
                data_symbol=data_symbol,
                roles=roles,
                asset_class=_asset_class(ticker, roles_by_ticker[ticker]),
                alias_status="mapped" if data_symbol != ticker else "raw",
            )
        )
    return tuple(targets)


def _stale_days(last_date: pd.Timestamp | None, generated_at: datetime) -> int | None:
    if last_date is None:
        return None
    return (pd.Timestamp(generated_at).normalize() - pd.Timestamp(last_date).normalize()).days


def _status_for(check: ProviderCheck, roles: tuple[str, ...]) -> str:
    if check.ok:
        return TRADABLE
    if "open_position" in roles:
        return DATA_FIX_REQUIRED
    if check.rows >= 60 and check.latest_close is not None:
        return RESEARCH_ONLY
    return BLOCKED


def _binding_constraint(status: str, roles: tuple[str, ...], message: str) -> str:
    if status == TRADABLE:
        return "provider coverage ok; data can support signal evaluation"
    if status == RESEARCH_ONLY:
        return "limited or stale history; use for research only until coverage improves"
    if status == DATA_FIX_REQUIRED:
        return f"open position lacks usable provider data; add alias or verify coverage ({message})"
    role_text = ",".join(roles)
    return f"no usable provider data for {role_text}; {message or 'provider returned no data'}"


def _action_for(status: str) -> str:
    if status == TRADABLE:
        return "allow research and signal evaluation"
    if status == RESEARCH_ONLY:
        return "do not use for buy/add until data improves"
    if status == DATA_FIX_REQUIRED:
        return "repair alias/provider coverage before relying on hold/trim/exit signal"
    return "block buy/add signal"


def _intended_alpha(target: DataQualityTarget) -> str:
    if target.asset_class == "benchmark":
        return "benchmark context and relative-strength baseline"
    if target.asset_class == "leveraged_etf":
        return "tactical leveraged exposure only; not a long-term core thesis"
    if "open_position" in target.roles:
        return "monitor retained exposure and exit risk for an existing manual position"
    return "AI/semi/tech swing-trend candidate after data coverage passes"


def _unwanted_risk(status: str, target: DataQualityTarget) -> str:
    if status in {DATA_FIX_REQUIRED, BLOCKED}:
        return "false confidence from missing or unmapped market data"
    if target.asset_class == "leveraged_etf":
        return "leverage decay, gap risk, and oversized tactical exposure"
    if target.asset_class == "benchmark":
        return "benchmark drift only; not an actionable position risk"
    return "trend failure, earnings gap, liquidity surprise, or factor crowding"


def _retained_exposure(target: DataQualityTarget) -> str:
    if "open_position" in target.roles:
        return "existing manual position remains until the user records a trade or close"
    if target.asset_class == "benchmark":
        return "reference exposure only; no portfolio allocation implied"
    return "no retained exposure unless opened manually"


def _liquidity_exit_posture(status: str) -> str:
    if status == TRADABLE:
        return "daily data supports hold/add/trim/exit review"
    if status == RESEARCH_ONLY:
        return "manual review only; do not promote to executable action"
    if status == DATA_FIX_REQUIRED:
        return "cannot calculate reliable exit posture until data mapping is repaired"
    return "no implementation-ready exit posture"


def evaluate_data_quality(config: AppConfig, provider: str = "fmp") -> DataQualityReport:
    generated_at = datetime.now(tz=UTC)
    targets = collect_data_quality_universe(config)
    symbols = list(dict.fromkeys(target.data_symbol for target in targets))
    checks = {check.ticker.upper(): check for check in check_provider_data(symbols, provider, config.data)}
    records: list[DataQualityRecord] = []

    for target in targets:
        check = checks.get(
            target.data_symbol,
            ProviderCheck(target.data_symbol, provider, 0, None, None, None, False, "provider did not return a coverage row"),
        )
        status = _status_for(check, target.roles)
        stale_days = _stale_days(check.last_date, generated_at)
        records.append(
            DataQualityRecord(
                ticker=target.ticker,
                data_symbol=target.data_symbol,
                provider=provider,
                roles=target.roles,
                asset_class=target.asset_class,
                rows=check.rows,
                first_date=check.first_date,
                last_date=check.last_date,
                latest_close=check.latest_close,
                stale_days=stale_days,
                ok=check.ok,
                status=status,
                alias_status=target.alias_status,
                provider_message=check.message,
                binding_constraint=_binding_constraint(status, target.roles, check.message),
                action=_action_for(status),
                intended_alpha=_intended_alpha(target),
                unwanted_risk=_unwanted_risk(status, target),
                retained_exposure=_retained_exposure(target),
                liquidity_exit_posture=_liquidity_exit_posture(status),
            )
        )

    status_order = {DATA_FIX_REQUIRED: 0, BLOCKED: 1, RESEARCH_ONLY: 2, TRADABLE: 3}
    records.sort(key=lambda record: (status_order.get(record.status, 99), "open_position" not in record.roles, record.ticker))
    return DataQualityReport(provider=provider, generated_at=generated_at, records=tuple(records))


def data_quality_exit_code(report: DataQualityReport) -> int:
    for record in report.records:
        if record.status == BLOCKED:
            return 1
        if record.status == DATA_FIX_REQUIRED and "open_position" in record.roles:
            return 1
    return 0


def _fmt_date(value: pd.Timestamp | None) -> str:
    return value.date().isoformat() if value is not None else "-"


def _fmt_close(value: float | None) -> str:
    return f"{value:.2f}" if value is not None else "-"


def format_data_quality_summary(report: DataQualityReport) -> str:
    counts = report.counts
    lines = [
        f"Provider: {report.provider}",
        f"Tickers: {len(report.records)}",
        "Status: "
        + ", ".join(
            f"{status}={counts.get(status, 0)}"
            for status in [TRADABLE, RESEARCH_ONLY, DATA_FIX_REQUIRED, BLOCKED]
        ),
    ]
    blockers = [record for record in report.records if record.status in {DATA_FIX_REQUIRED, BLOCKED}]
    if blockers:
        lines.append("Blockers:")
        for record in blockers[:30]:
            lines.append(
                f"{record.status}\t{record.ticker}\tdata={record.data_symbol}\troles={','.join(record.roles)}\t"
                f"rows={record.rows}\tlast={_fmt_date(record.last_date)}\t{record.binding_constraint}"
            )
    else:
        lines.append("Blockers: none")
    return "\n".join(lines)


def write_data_quality_report(report: DataQualityReport, out_path: str | Path) -> Path:
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    counts = report.counts
    blockers = [record for record in report.records if record.status in {DATA_FIX_REQUIRED, BLOCKED}]
    open_position_blockers = [record for record in blockers if "open_position" in record.roles]
    other_blockers = [record for record in blockers if "open_position" not in record.roles]
    rows = []
    for record in report.records:
        rows.append(
            "<tr>"
            f"<td>{escape(record.status)}</td>"
            f"<td>{escape(record.ticker)}</td>"
            f"<td>{escape(record.data_symbol)}</td>"
            f"<td>{escape(', '.join(record.roles))}</td>"
            f"<td>{escape(record.asset_class)}</td>"
            f"<td>{record.rows}</td>"
            f"<td>{escape(_fmt_date(record.last_date))}</td>"
            f"<td>{escape(_fmt_close(record.latest_close))}</td>"
            f"<td>{escape(record.alias_status)}</td>"
            f"<td>{escape(record.binding_constraint)}</td>"
            f"<td>{escape(record.intended_alpha)}</td>"
            f"<td>{escape(record.unwanted_risk)}</td>"
            f"<td>{escape(record.retained_exposure)}</td>"
            f"<td>{escape(record.liquidity_exit_posture)}</td>"
            "</tr>"
        )
    open_position_items = "\n".join(
        f"<li><strong>{escape(record.ticker)}</strong> ({escape(record.status)}): {escape(record.binding_constraint)}</li>"
        for record in open_position_blockers
    )
    if not open_position_items:
        open_position_items = "<li>No open-position data blockers.</li>"
    other_blocker_items = "\n".join(
        f"<li><strong>{escape(record.ticker)}</strong> ({escape(record.status)}): {escape(record.binding_constraint)}</li>" for record in other_blockers[:30]
    )
    if not other_blocker_items:
        other_blocker_items = "<li>No other data blockers.</li>"
    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Data Quality Report</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 32px; color: #1f2937; }}
    h1, h2 {{ margin-bottom: 8px; }}
    .cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px; margin: 20px 0; }}
    .card {{ border: 1px solid #d1d5db; border-radius: 8px; padding: 12px; background: #f9fafb; }}
    .num {{ font-size: 24px; font-weight: 700; }}
    .warning {{ border-left: 4px solid #b91c1c; padding: 12px 16px; background: #fef2f2; margin: 18px 0; }}
    table {{ border-collapse: collapse; width: 100%; font-size: 13px; }}
    th, td {{ border: 1px solid #d1d5db; padding: 8px; vertical-align: top; }}
    th {{ background: #f3f4f6; text-align: left; }}
  </style>
</head>
<body>
  <h1>Data Quality Report</h1>
  <p>Provider: {escape(report.provider)} | Generated: {escape(report.generated_at.isoformat(timespec="seconds"))}</p>
  <div class="warning">Blocked tickers cannot support buy/add signals. Open-position data blockers require alias or provider coverage repair before relying on hold/trim/exit signals.</div>
  <section class="cards">
    <div class="card"><div>tradable</div><div class="num">{counts.get(TRADABLE, 0)}</div></div>
    <div class="card"><div>research_only</div><div class="num">{counts.get(RESEARCH_ONLY, 0)}</div></div>
    <div class="card"><div>data_fix_required</div><div class="num">{counts.get(DATA_FIX_REQUIRED, 0)}</div></div>
    <div class="card"><div>blocked</div><div class="num">{counts.get(BLOCKED, 0)}</div></div>
  </section>
  <h2>Open-Position Blockers And Alias Guidance</h2>
  <p>If broker symbols such as SNXX/MUU/LNOK/AAOX do not exist in FMP/yfinance/Stooq, add an alias that maps the broker symbol to the data provider symbol.</p>
  <ul>{open_position_items}</ul>
  <h2>Other Blockers</h2>
  <ul>{other_blocker_items}</ul>
  <h2>All Records</h2>
  <table>
    <thead>
      <tr>
        <th>Status</th><th>Ticker</th><th>Data Symbol</th><th>Roles</th><th>Asset Class</th><th>Rows</th><th>Last Date</th><th>Close</th><th>Alias</th><th>Binding Constraint</th><th>Intended Alpha</th><th>Unwanted Risk</th><th>Retained Exposure</th><th>Liquidity/Exit Posture</th>
      </tr>
    </thead>
    <tbody>{''.join(rows)}</tbody>
  </table>
</body>
</html>
"""
    out.write_text(html, encoding="utf-8")
    return out
