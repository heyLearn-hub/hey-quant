from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from quant_ai_system.config import AppConfig


@dataclass(frozen=True)
class ReleaseCheck:
    level: str
    name: str
    message: str


def _has_env(env: Mapping[str, str], name: str) -> bool:
    return bool(env.get(name, "").strip())


def _root_path(project_root: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else project_root / path


def run_release_checks(
    config: AppConfig,
    *,
    project_root: str | Path = ".",
    env: Mapping[str, str] | None = None,
) -> list[ReleaseCheck]:
    root = Path(project_root).resolve()
    runtime_env = os.environ if env is None else env
    checks: list[ReleaseCheck] = []

    checks.append(ReleaseCheck("PASS", "config", "配置文件已加载"))

    gitignore = root / ".gitignore"
    required_ignored = [".env", "data/*.sqlite3", "data/cache/", "outputs/", "logs/"]
    if gitignore.exists():
        text = gitignore.read_text(encoding="utf-8")
        missing = [item for item in required_ignored if item not in text]
        if missing:
            checks.append(ReleaseCheck("FAIL", "gitignore", f"运行时文件未完整忽略: {', '.join(missing)}"))
        else:
            checks.append(ReleaseCheck("PASS", "gitignore", "密钥、数据库、缓存、报告和日志已从 Git 排除"))
    else:
        checks.append(ReleaseCheck("FAIL", "gitignore", "缺少 .gitignore"))

    storage_path = _root_path(root, config.storage.db_path)
    if storage_path.parent.exists():
        checks.append(ReleaseCheck("PASS", "storage", f"数据库目录存在: {storage_path.parent}"))
    else:
        checks.append(ReleaseCheck("WARN", "storage", f"数据库目录尚未创建: {storage_path.parent}"))
    if storage_path.exists():
        checks.append(ReleaseCheck("PASS", "positions-db", f"持仓数据库存在: {storage_path}"))
    else:
        checks.append(ReleaseCheck("WARN", "positions-db", "持仓数据库尚未创建；首次录入持仓或运行服务后会生成"))

    providers = [item.lower() for item in (config.data.provider_priority or [])]
    if providers:
        checks.append(ReleaseCheck("PASS", "data-priority", f"数据源优先级: {' -> '.join(providers)}"))
    else:
        checks.append(ReleaseCheck("WARN", "data-priority", "未显式配置 provider_priority，将使用程序默认值"))

    needs_fmp = "fmp" in providers or config.research.news_provider.lower() == "fmp"
    if needs_fmp and _has_env(runtime_env, "FMP_API_KEY"):
        checks.append(ReleaseCheck("PASS", "fmp", "FMP_API_KEY 已配置"))
    elif needs_fmp:
        checks.append(ReleaseCheck("WARN", "fmp", "FMP_API_KEY 未配置；会退回免费行情源，新闻/monitor 能力受限"))

    if config.telegram.enabled:
        missing = [name for name in [config.telegram.bot_token_env, config.telegram.chat_id_env] if not _has_env(runtime_env, name)]
        if missing:
            checks.append(ReleaseCheck("FAIL", "telegram", f"Telegram 已启用但缺少环境变量: {', '.join(missing)}"))
        else:
            checks.append(ReleaseCheck("PASS", "telegram", "Telegram token/chat id 已配置"))
    else:
        checks.append(ReleaseCheck("WARN", "telegram", "Telegram 未启用；v1.0 生产提醒能力不可用"))

    ai_key_env = config.supervisor.deepseek_api_key_env if config.supervisor.provider.lower() == "deepseek" else config.supervisor.openai_api_key_env
    if _has_env(runtime_env, ai_key_env):
        checks.append(ReleaseCheck("PASS", "ai-supervisor", f"{config.supervisor.provider} key 已配置"))
    elif config.supervisor.require_api:
        checks.append(ReleaseCheck("FAIL", "ai-supervisor", f"Supervisor 要求 API，但缺少 {ai_key_env}"))
    else:
        checks.append(ReleaseCheck("WARN", "ai-supervisor", f"缺少 {ai_key_env}；会使用本地规则 fallback"))

    if config.monitor.enabled:
        checks.append(ReleaseCheck("PASS", "monitor", "轻量 price/news monitor 已启用"))
    else:
        checks.append(ReleaseCheck("WARN", "monitor", "monitor 未启用；Windows 常驻服务空闲监控不可用"))

    if config.risk.max_positions <= 2:
        checks.append(ReleaseCheck("PASS", "concentration", f"集中持仓上限: {config.risk.max_positions}"))
    else:
        checks.append(ReleaseCheck("WARN", "concentration", f"当前 max_positions={config.risk.max_positions}，不符合 v1.0 小资金集中持仓目标"))

    required_windows_files = [
        "Dockerfile",
        "docker-compose.yml",
        "scripts/windows_docker_daily_job.ps1",
        "scripts/windows_docker_update.ps1",
        "scripts/windows_docker_auto_update_task.xml",
    ]
    missing_files = [name for name in required_windows_files if not (root / name).exists()]
    if missing_files:
        checks.append(ReleaseCheck("FAIL", "windows-docker", f"缺少 Windows/Docker 部署文件: {', '.join(missing_files)}"))
    else:
        checks.append(ReleaseCheck("PASS", "windows-docker", "Windows Docker 部署与自动更新脚本齐全"))

    return checks


def release_check_exit_code(checks: list[ReleaseCheck]) -> int:
    return 1 if any(check.level == "FAIL" for check in checks) else 0


def format_release_checks(checks: list[ReleaseCheck]) -> str:
    counts = {level: sum(1 for item in checks if item.level == level) for level in ["PASS", "WARN", "FAIL"]}
    lines = [
        "Quant AI v1.0 release readiness",
        f"PASS={counts['PASS']} WARN={counts['WARN']} FAIL={counts['FAIL']}",
    ]
    lines.extend(f"{item.level}\t{item.name}\t{item.message}" for item in checks)
    return "\n".join(lines)
