from __future__ import annotations

import html
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import webbrowser
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from quant_ai_system.config import load_config
from quant_ai_system.engine import RunResult, run_system
from quant_ai_system.monitor import MonitorListener
from quant_ai_system.portfolio_store import close_position, list_data_health, list_positions, list_supervisor_decision_logs, list_symbol_aliases, list_trades, record_trade, upsert_position, upsert_symbol_alias
from quant_ai_system.telegram_commands import TelegramCommandListener, TelegramCommandProcessor
from quant_ai_system.telegram_notifier import send_telegram_text


@dataclass
class ServerState:
    config_path: Path
    report_path: Path
    offline_sample: bool
    last_result: RunResult | None = None
    last_error: str | None = None
    last_run_at: float | None = None
    is_refreshing: bool = False


def _approved_core(result: RunResult) -> list[str]:
    approved = {review.ticker for review in result.supervisor_reviews if review.decision == "approve_for_consideration"}
    tactical = set(result.tactical_tickers)
    return [
        signal.ticker
        for signal in sorted(result.signals, key=lambda item: item.score, reverse=True)
        if (
            signal.ticker in approved
            and signal.ticker not in tactical
            and ("加仓" in signal.action or "小仓" in signal.action)
            and signal.position.target_shares >= 1
        )
    ]


def refresh_report(state: ServerState) -> None:
    state.is_refreshing = True
    config = load_config(state.config_path)
    try:
        state.last_result = run_system(config, state.report_path, offline_sample=state.offline_sample)
        state.last_error = None
        state.last_run_at = time.time()
    finally:
        state.is_refreshing = False


def _db_path(state: ServerState) -> str:
    return load_config(state.config_path).storage.db_path


def refresh_report_background(state: ServerState) -> None:
    if state.is_refreshing:
        return

    def worker() -> None:
        try:
            refresh_report(state)
        except Exception as exc:  # pragma: no cover - background error path
            state.last_error = str(exc)
            state.last_run_at = time.time()
            state.is_refreshing = False

    threading.Thread(target=worker, daemon=True).start()


def _shell_quote(value: str) -> str:
    return "'" + value.replace("'", "'\\''") + "'"


def install_launch_agent(
    config_path: str | Path,
    report_path: str | Path,
    port: int,
    offline_sample: bool = False,
    label: str = "com.quant-ai-system.service",
) -> Path:
    source_root = Path.cwd().resolve()
    deploy_root = Path.home() / "Library" / "Application Support" / "QuantAISystem" / "app"
    if deploy_root.exists():
        shutil.rmtree(deploy_root)
    deploy_root.mkdir(parents=True, exist_ok=True)
    for name in ["src", "config", "bin", "pyproject.toml", "README.md"]:
        src = source_root / name
        dst = deploy_root / name
        if src.is_dir():
            shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__", "*.egg-info", ".pytest_cache"))
        elif src.exists():
            shutil.copy2(src, dst)
    env_src = source_root / ".env"
    if env_src.exists():
        env_dst = deploy_root / ".env"
        shutil.copy2(env_src, env_dst)
        env_dst.chmod(0o600)

    config_src = Path(config_path)
    if config_src.exists():
        service_config = deploy_root / "config" / "service.yaml"
        service_config.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(config_src, service_config)
    else:
        service_config = deploy_root / "config" / "default.yaml"

    launcher = deploy_root / "bin" / "quant-ai-local"
    if not launcher.exists():
        raise FileNotFoundError(f"Missing launcher after deploy: {launcher}")
    launcher.chmod(0o755)

    venv_python = deploy_root / ".venv" / "bin" / "python"
    subprocess.run(["python3", "-m", "venv", str(deploy_root / ".venv")], check=True)
    subprocess.run([str(venv_python), "-m", "pip", "install", "-e", "."], cwd=deploy_root, check=True)

    log_dir = deploy_root / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    service_report_path = deploy_root / "outputs" / Path(report_path).name
    args = [
        str(launcher),
        "serve",
        "--config",
        str(service_config),
        "--out",
        str(service_report_path),
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
    ]
    if offline_sample:
        args.append("--offline-sample")

    program_arguments = "\n".join(f"    <string>{html.escape(arg)}</string>" for arg in args)
    plist = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>{label}</string>
  <key>ProgramArguments</key>
  <array>
{program_arguments}
  </array>
  <key>WorkingDirectory</key>
  <string>{html.escape(str(deploy_root))}</string>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>{html.escape(str(log_dir / "service.out.log"))}</string>
  <key>StandardErrorPath</key>
  <string>{html.escape(str(log_dir / "service.err.log"))}</string>
</dict>
</plist>
"""
    agents_dir = Path.home() / "Library" / "LaunchAgents"
    agents_dir.mkdir(parents=True, exist_ok=True)
    plist_path = agents_dir / f"{label}.plist"
    plist_path.write_text(plist, encoding="utf-8")

    subprocess.run(["launchctl", "unload", str(plist_path)], check=False, capture_output=True)
    subprocess.run(["launchctl", "load", str(plist_path)], check=True)
    return plist_path


def uninstall_launch_agent(label: str = "com.quant-ai-system.service") -> Path:
    plist_path = Path.home() / "Library" / "LaunchAgents" / f"{label}.plist"
    subprocess.run(["launchctl", "unload", str(plist_path)], check=False, capture_output=True)
    if plist_path.exists():
        plist_path.unlink()
    return plist_path


def service_status(port: int = 8765) -> str:
    plist_path = Path.home() / "Library" / "LaunchAgents" / "com.quant-ai-system.service.plist"
    deploy_root = Path.home() / "Library" / "Application Support" / "QuantAISystem" / "app"
    lines = [
        f"LaunchAgent: {'installed' if plist_path.exists() else 'not installed'}",
        f"URL: http://127.0.0.1:{port}",
        f"Deploy path: {deploy_root}",
        f"Logs: {deploy_root / 'logs' / 'service.out.log'} and {deploy_root / 'logs' / 'service.err.log'}",
    ]
    return "\n".join(lines)


def make_handler(state: ServerState) -> type[BaseHTTPRequestHandler]:
    class QuantHandler(BaseHTTPRequestHandler):
        server_version = "QuantAISystem/0.1"

        def _send(self, body: str | bytes, content_type: str = "text/html; charset=utf-8", status: int = 200) -> None:
            payload = body.encode("utf-8") if isinstance(body, str) else body
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path == "/health":
                self._send(json.dumps({"ok": True, "refreshing": state.is_refreshing, "last_error": state.last_error}), "application/json")
                return
            if parsed.path == "/report":
                if not state.report_path.exists():
                    self._render_home(message="报告还没有生成，请点击刷新。")
                    return
                self._send(state.report_path.read_bytes(), "text/html; charset=utf-8")
                return
            if parsed.path == "/refresh":
                query = parse_qs(parsed.query)
                if query.get("offline", ["0"])[0] == "1":
                    state.offline_sample = True
                elif query.get("offline", ["0"])[0] == "0":
                    state.offline_sample = False
                try:
                    refresh_report_background(state)
                    self._redirect("/")
                except Exception as exc:  # pragma: no cover - HTTP error path
                    state.last_error = str(exc)
                    state.last_run_at = time.time()
                    self._render_home(message=f"刷新失败：{html.escape(str(exc))}", status=500)
                return
            self._render_home()

        def do_POST(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length).decode("utf-8")
            form = parse_qs(body)
            try:
                if parsed.path == "/positions/upsert":
                    ticker = form.get("ticker", [""])[0]
                    shares = float(form.get("shares", ["0"])[0])
                    average_cost = float(form.get("average_cost", ["0"])[0])
                    current_stop_raw = form.get("current_stop", [""])[0].strip()
                    current_stop = float(current_stop_raw) if current_stop_raw else None
                    note = form.get("thesis_note", [""])[0]
                    upsert_position(_db_path(state), ticker, shares, average_cost, current_stop, note)
                    self._redirect("/")
                    return
                if parsed.path == "/trades/record":
                    record_trade(
                        _db_path(state),
                        form.get("ticker", [""])[0],
                        form.get("action", ["buy"])[0],
                        float(form.get("shares", ["0"])[0]),
                        float(form.get("price", ["0"])[0]),
                        form.get("note", [""])[0],
                    )
                    self._redirect("/")
                    return
                if parsed.path == "/positions/close":
                    close_position(_db_path(state), form.get("ticker", [""])[0], form.get("note", [""])[0])
                    self._redirect("/")
                    return
                if parsed.path == "/aliases/upsert":
                    upsert_symbol_alias(
                        _db_path(state),
                        form.get("broker_symbol", [""])[0],
                        form.get("data_symbol", [""])[0],
                        form.get("note", [""])[0],
                    )
                    self._redirect("/")
                    return
            except Exception as exc:
                self._render_home(message=f"保存失败：{html.escape(str(exc))}", status=400)
                return
            self._send("Not found", status=HTTPStatus.NOT_FOUND)

        def _redirect(self, location: str) -> None:
            self.send_response(302)
            self.send_header("Location", location)
            self.end_headers()

        def _render_home(self, message: str = "", status: int = 200) -> None:
            result = state.last_result
            core = _approved_core(result) if result else []
            last_run = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(state.last_run_at)) if state.last_run_at else "尚未运行"
            issue_count = len(result.market_data.issues) if result else 0
            signal_count = len(result.signals) if result else 0
            refresh_label = "刷新中" if state.is_refreshing else "空闲"
            try:
                positions = list_positions(_db_path(state))
                trades = list_trades(_db_path(state), limit=10)
                aliases = list_symbol_aliases(_db_path(state))
                health = list_data_health(_db_path(state), limit=8)
                supervisor_logs = list_supervisor_decision_logs(_db_path(state), limit=8)
            except Exception:
                positions = []
                trades = []
                aliases = []
                health = []
                supervisor_logs = []
            position_rows = "".join(
                f"<tr><td><b>{html.escape(p.ticker)}</b></td><td>{p.shares:.2f}</td><td>{p.average_cost:.2f}</td><td>{p.current_stop if p.current_stop is not None else ''}</td><td>{html.escape(p.thesis_note)}</td>"
                f"<td><form method='post' action='/positions/close'><input type='hidden' name='ticker' value='{html.escape(p.ticker)}'><input name='note' placeholder='清仓备注'><button type='submit'>清仓</button></form></td></tr>"
                for p in positions
            ) or "<tr><td colspan='6' class='muted'>暂无持仓</td></tr>"
            trade_rows = "".join(
                f"<tr><td>{html.escape(t.executed_at[:19])}</td><td><b>{html.escape(t.ticker)}</b></td><td>{html.escape(t.action)}</td><td>{t.shares:.2f}</td><td>{t.price:.2f}</td><td>{html.escape(t.note)}</td></tr>"
                for t in trades
            ) or "<tr><td colspan='6' class='muted'>暂无交易记录</td></tr>"
            alias_rows = "".join(
                f"<tr><td><b>{html.escape(a.broker_symbol)}</b></td><td>{html.escape(a.data_symbol)}</td><td>{html.escape(a.note)}</td><td>{html.escape(a.updated_at[:19])}</td></tr>"
                for a in aliases
            ) or "<tr><td colspan='4' class='muted'>暂无 alias。若券商符号无行情，在这里映射到数据源 symbol。</td></tr>"
            health_rows = "".join(
                f"<tr><td><b>{html.escape(h.ticker)}</b></td><td>{html.escape(h.check_type)}</td><td>{html.escape(h.provider)}</td><td>{'OK' if h.ok else 'CHECK'}</td><td>{html.escape(h.message)}</td><td>{html.escape(h.checked_at[:19])}</td></tr>"
                for h in health
            ) or "<tr><td colspan='6' class='muted'>暂无 monitor 检查记录</td></tr>"
            supervisor_log_rows = "".join(
                f"<tr><td>{html.escape(item.created_at[:19])}</td><td><b>{html.escape(item.ticker)}</b></td><td>{html.escape(item.provider)}</td><td>{html.escape(item.decision)}</td><td>{item.approval_score:.1f}</td><td>{html.escape(item.final_action)}</td><td>{html.escape('; '.join(item.blockers[:2]) if item.blockers else '-')}</td></tr>"
                for item in supervisor_logs
            ) or "<tr><td colspan='7' class='muted'>暂无 Supervisor 决策日志。刷新报告后会自动记录。</td></tr>"
            body = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Quant AI 本地服务</title>
  <style>
    body {{ margin:0; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; background:#f6f8fb; color:#17202a; }}
    main {{ max-width:960px; margin:0 auto; padding:36px 24px; }}
    h1 {{ margin:0 0 10px; font-size:28px; }}
    .panel {{ background:#fff; border:1px solid #d9e0e8; border-radius:8px; padding:18px; margin:16px 0; }}
    .grid {{ display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:12px; }}
    .tile {{ background:#fff; border:1px solid #d9e0e8; border-radius:8px; padding:14px; }}
    .tile b {{ display:block; font-size:22px; margin-top:6px; }}
    a.button {{ display:inline-block; margin-right:10px; padding:10px 14px; border-radius:7px; background:#0f766e; color:#fff; text-decoration:none; font-weight:650; }}
    a.secondary {{ background:#334155; }}
    input, select, textarea {{ width:100%; box-sizing:border-box; padding:8px; border:1px solid #cbd5e1; border-radius:6px; }}
    button {{ padding:8px 12px; border:0; border-radius:6px; background:#0f766e; color:#fff; font-weight:650; cursor:pointer; }}
    table {{ width:100%; border-collapse:collapse; font-size:14px; }}
    th, td {{ padding:8px; border-bottom:1px solid #e2e8f0; text-align:left; vertical-align:top; }}
    .formgrid {{ display:grid; grid-template-columns:repeat(5,minmax(0,1fr)); gap:10px; align-items:end; }}
    .muted {{ color:#64748b; }}
    .warn {{ color:#b45309; }}
    @media (max-width:760px) {{ .grid {{ grid-template-columns:repeat(2,minmax(0,1fr)); }} }}
  </style>
</head>
<body>
<main>
  <h1>Quant AI 本地服务</h1>
  <p class="muted">本地运行，不自动交易。Supervisor 只做审查和提醒，最终决策仍由你确认。</p>
  <div class="grid">
    <div class="tile">最后运行 <b>{html.escape(last_run)}</b></div>
    <div class="tile">信号数 <b>{signal_count}</b></div>
    <div class="tile">核心候选 <b>{html.escape(', '.join(core) if core else 'none')}</b></div>
    <div class="tile">状态 <b>{refresh_label}</b></div>
  </div>
  <div class="panel">
    <a class="button" href="/refresh">刷新真实行情</a>
    <a class="button secondary" href="/report">打开完整报告</a>
    <a class="button secondary" href="/refresh?offline=1">样本模式测试</a>
  </div>
  <div class="panel">
    <h2>新增/更新持仓</h2>
    <form method="post" action="/positions/upsert" class="formgrid">
      <label>Ticker<input name="ticker" required placeholder="MSFT"></label>
      <label>股数<input name="shares" type="number" step="0.0001" required></label>
      <label>平均成本<input name="average_cost" type="number" step="0.01" required></label>
      <label>止损价<input name="current_stop" type="number" step="0.01"></label>
      <label>备注<input name="thesis_note" placeholder="买入理由/计划"></label>
      <button type="submit">保存持仓</button>
    </form>
  </div>
  <div class="panel">
    <h2>记录操作</h2>
    <form method="post" action="/trades/record" class="formgrid">
      <label>Ticker<input name="ticker" required placeholder="MSFT"></label>
      <label>动作<select name="action"><option value="buy">买入</option><option value="add">加仓</option><option value="trim">减仓</option><option value="sell">卖出</option></select></label>
      <label>股数<input name="shares" type="number" step="0.0001" required></label>
      <label>价格<input name="price" type="number" step="0.01" required></label>
      <label>备注<input name="note" placeholder="执行原因"></label>
      <button type="submit">记录操作</button>
    </form>
  </div>
  <div class="panel">
    <h2>当前持仓</h2>
    <table><thead><tr><th>Ticker</th><th>股数</th><th>平均成本</th><th>止损价</th><th>备注</th><th>操作</th></tr></thead><tbody>{position_rows}</tbody></table>
  </div>
  <div class="panel">
    <h2>最近操作</h2>
    <table><thead><tr><th>时间</th><th>Ticker</th><th>动作</th><th>股数</th><th>价格</th><th>备注</th></tr></thead><tbody>{trade_rows}</tbody></table>
  </div>
  <div class="panel">
    <h2>Symbol Alias</h2>
    <form method="post" action="/aliases/upsert" class="formgrid">
      <label>券商符号<input name="broker_symbol" required placeholder="SNXX"></label>
      <label>数据源符号<input name="data_symbol" required placeholder="NVDA"></label>
      <label>备注<input name="note" placeholder="为什么映射"></label>
      <button type="submit">保存 Alias</button>
    </form>
    <table><thead><tr><th>券商符号</th><th>数据源符号</th><th>备注</th><th>更新时间</th></tr></thead><tbody>{alias_rows}</tbody></table>
  </div>
  <div class="panel">
    <h2>Monitor / Data Health</h2>
    <table><thead><tr><th>Ticker</th><th>检查</th><th>来源</th><th>状态</th><th>说明</th><th>时间</th></tr></thead><tbody>{health_rows}</tbody></table>
  </div>
  <div class="panel">
    <h2>Supervisor 决策日志</h2>
    <table><thead><tr><th>时间</th><th>Ticker</th><th>来源</th><th>决策</th><th>分数</th><th>动作</th><th>阻断原因</th></tr></thead><tbody>{supervisor_log_rows}</tbody></table>
  </div>
  <div class="panel">
    <b>状态</b>
    <p class="{'warn' if message or state.last_error else 'muted'}">{message or state.last_error or f'服务正常。数据问题：{issue_count}。真实行情源如果限流，报告会显示数据质量提示。'}</p>
    <p class="muted">配置：{html.escape(str(state.config_path))}<br>报告：{html.escape(str(state.report_path))}</p>
  </div>
</main>
</body>
</html>"""
            self._send(body, status=status)

        def log_message(self, format: str, *args: object) -> None:
            sys.stderr.write("%s - - [%s] %s\n" % (self.address_string(), self.log_date_time_string(), format % args))

    return QuantHandler


def serve(
    config_path: str | Path,
    report_path: str | Path,
    host: str = "127.0.0.1",
    port: int = 8765,
    offline_sample: bool = False,
    open_browser: bool = False,
) -> None:
    state = ServerState(Path(config_path).resolve(), Path(report_path).resolve(), offline_sample)
    server = ThreadingHTTPServer((host, port), make_handler(state))
    url = f"http://{host}:{port}"
    print(f"Quant AI service running at {url}")
    print(f"Report path: {state.report_path}")
    if open_browser:
        webbrowser.open(url)
    refresh_report_background(state)
    config = load_config(state.config_path)
    listener = None
    if (
        config.telegram.command_polling_enabled
        and os.environ.get(config.telegram.bot_token_env, "").strip()
        and os.environ.get(config.telegram.chat_id_env, "").strip()
    ):
        processor = TelegramCommandProcessor(config, _db_path(state), refresh_callback=lambda: refresh_report_background(state))
        listener = TelegramCommandListener(processor, poll_interval=config.telegram.command_poll_interval_seconds)
        listener.start()
        print("Telegram command listener: enabled")
    else:
        print("Telegram command listener: disabled")
    monitor_listener = None
    if config.monitor.enabled:
        send_text = None
        if os.environ.get(config.telegram.bot_token_env, "").strip() and os.environ.get(config.telegram.chat_id_env, "").strip():
            send_text = lambda text: send_telegram_text(config, text)
        monitor_listener = MonitorListener(config, send_text=send_text)
        monitor_listener.start()
        print("Monitor listener: enabled")
    else:
        print("Monitor listener: disabled")
    server.serve_forever()
