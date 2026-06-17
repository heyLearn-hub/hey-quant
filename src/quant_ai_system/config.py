from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


DEFAULT_TICKERS = [
    "NVDA",
    "AMD",
    "AVGO",
    "TSM",
    "ASML",
    "AMAT",
    "LRCX",
    "KLAC",
    "MU",
    "ARM",
    "MRVL",
    "SMCI",
    "MSFT",
    "GOOGL",
    "META",
    "AMZN",
    "TSLA",
    "PLTR",
    "ORCL",
    "ANET",
    "VRT",
]


@dataclass(frozen=True)
class AccountConfig:
    nav: float = 100_000
    currency: str = "USD"
    source_capital_hkd: float | None = None
    hkd_usd_rate: float | None = None
    fractional_shares: bool = False


@dataclass(frozen=True)
class UniverseConfig:
    tickers: list[str]
    leveraged_tickers: list[str]
    benchmarks: list[str]
    primary_benchmark: str = "QQQ"
    theme_benchmark: str = "SMH"


@dataclass(frozen=True)
class DataConfig:
    years: int = 10
    cache_dir: str = "data/cache"
    prefer_cache: bool = True
    sample_on_remote_failure: bool = True
    stop_after_paid_provider: bool = True
    provider_priority: list[str] | None = None


@dataclass(frozen=True)
class StorageConfig:
    db_path: str = "data/portfolio.sqlite3"


@dataclass(frozen=True)
class EmailConfig:
    enabled: bool = False
    smtp_host: str = "smtp.office365.com"
    smtp_port: int = 587
    use_tls: bool = True
    username_env: str = "SMTP_USERNAME"
    password_env: str = "SMTP_PASSWORD"
    from_addr_env: str = "SMTP_FROM"
    to_addrs_env: str = "SMTP_TO"
    subject_prefix: str = "[Quant AI]"


@dataclass(frozen=True)
class TelegramConfig:
    enabled: bool = False
    bot_token_env: str = "TELEGRAM_BOT_TOKEN"
    chat_id_env: str = "TELEGRAM_CHAT_ID"
    parse_mode: str = ""
    disable_web_page_preview: bool = True


@dataclass(frozen=True)
class RiskConfig:
    profile: str = "aggressive"
    holding_style: str = "concentrated_position"
    max_positions: int = 2
    min_core_score: float = 70
    initial_weight_min: float = 0.04
    initial_weight_max: float = 0.06
    target_weight_min: float = 0.08
    target_weight_max: float = 0.12
    leveraged_initial_weight_max: float = 0.10
    leveraged_target_weight_max: float = 0.20
    risk_budget_min: float = 0.015
    risk_budget_max: float = 0.02
    theme_exposure_limit: float = 0.65
    atr_stop_multiple: float = 2.8
    portfolio_drawdown_reduce: float = 0.08
    portfolio_drawdown_defensive: float = 0.12
    portfolio_drawdown_stop_new: float = 0.15
    earnings_profit_cushion: float = 0.08
    profit_protection_min_gain: float = 0.12
    profit_giveback_watch: float = 0.25
    profit_giveback_trim: float = 0.35
    profit_giveback_exit: float = 0.55
    profit_floor_keep_ratio: float = 0.50
    profit_trailing_atr_multiple: float = 2.5


@dataclass(frozen=True)
class BacktestConfig:
    years: int = 10
    initial_cash: float = 100_000
    slippage_bps: float = 15
    rebalance: str = "weekly"
    max_positions: int = 12


@dataclass(frozen=True)
class ReportConfig:
    title: str = "美股科技/半导体/AI 低频量化提醒系统"
    locale: str = "zh-CN"


@dataclass(frozen=True)
class QualityConfig:
    enabled: bool = True
    technical_weight: float = 0.65
    quality_weight: float = 0.35
    buffett_style_notes: list[str] | None = None
    score_overrides: dict[str, dict[str, Any]] | None = None


@dataclass(frozen=True)
class SupervisorConfig:
    enabled: bool = True
    provider: str = "openai"
    model: str = "gpt-5"
    require_api: bool = False
    min_approval_score: float = 70
    max_core_approvals: int = 2
    review_style: str = "investment_committee"
    policy: list[str] | None = None


@dataclass(frozen=True)
class AppConfig:
    account: AccountConfig
    universe: UniverseConfig
    data: DataConfig
    storage: StorageConfig
    email: EmailConfig
    telegram: TelegramConfig
    risk: RiskConfig
    backtest: BacktestConfig
    report: ReportConfig
    quality: QualityConfig
    supervisor: SupervisorConfig


def _upper_list(values: list[Any]) -> list[str]:
    return [str(value).strip().upper() for value in values if str(value).strip()]


def load_config(path: str | Path) -> AppConfig:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    account = AccountConfig(**raw.get("account", {}))
    universe_raw = raw.get("universe", {})
    universe = UniverseConfig(
        tickers=_upper_list(universe_raw.get("tickers", DEFAULT_TICKERS)),
        leveraged_tickers=_upper_list(universe_raw.get("leveraged_tickers", [])),
        benchmarks=_upper_list(universe_raw.get("benchmarks", ["QQQ", "SMH", "SPY"])),
        primary_benchmark=str(universe_raw.get("primary_benchmark", "QQQ")).upper(),
        theme_benchmark=str(universe_raw.get("theme_benchmark", "SMH")).upper(),
    )
    return AppConfig(
        account=account,
        universe=universe,
        data=DataConfig(**raw.get("data", {})),
        storage=StorageConfig(**raw.get("storage", {})),
        email=EmailConfig(**raw.get("email", {})),
        telegram=TelegramConfig(**raw.get("telegram", {})),
        risk=RiskConfig(**raw.get("risk", {})),
        backtest=BacktestConfig(**raw.get("backtest", {})),
        report=ReportConfig(**raw.get("report", {})),
        quality=QualityConfig(**raw.get("quality", {})),
        supervisor=SupervisorConfig(**raw.get("supervisor", {})),
    )
