from __future__ import annotations

import argparse
from pathlib import Path

from quant_ai_system.action_summary import build_action_summary
from quant_ai_system.config import load_config
from quant_ai_system.emailer import send_summary_email
from quant_ai_system.engine import run_system
from quant_ai_system.data import check_provider_data, get_market_data, make_sample_market_data
from quant_ai_system.factors import run_factor_experiment, write_factor_report
from quant_ai_system.research import build_news_briefs
from quant_ai_system.server import install_launch_agent, serve, service_status, uninstall_launch_agent
from quant_ai_system.telegram_notifier import fetch_telegram_updates, send_telegram_message


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="quant-ai", description="Local low-frequency US tech/AI quant alert system.")
    sub = parser.add_subparsers(dest="command", required=True)

    for name in ["run", "backtest"]:
        cmd = sub.add_parser(name)
        cmd.add_argument("--config", default="config/default.yaml")
        cmd.add_argument("--out", default="outputs/latest_report.html")
        cmd.add_argument("--offline-sample", action="store_true", help="Use deterministic sample data instead of remote market data.")
        cmd.add_argument("--send-email", action="store_true", help="Send summary email after generating the report.")
        cmd.add_argument("--send-telegram", action="store_true", help="Send summary Telegram message after generating the report.")

    email = sub.add_parser("send-email")
    email.add_argument("--config", default="config/default.yaml")
    email.add_argument("--out", default="outputs/latest_report.html")
    email.add_argument("--offline-sample", action="store_true")

    telegram = sub.add_parser("send-telegram")
    telegram.add_argument("--config", default="config/default.yaml")
    telegram.add_argument("--out", default="outputs/latest_report.html")
    telegram.add_argument("--offline-sample", action="store_true")

    telegram_chat = sub.add_parser("telegram-chat-id")
    telegram_chat.add_argument("--config", default="config/default.yaml")

    show = sub.add_parser("show-config")
    show.add_argument("--config", default="config/default.yaml")

    serve_cmd = sub.add_parser("serve")
    serve_cmd.add_argument("--config", default="config/default.yaml")
    serve_cmd.add_argument("--out", default="outputs/latest_report.html")
    serve_cmd.add_argument("--host", default="127.0.0.1")
    serve_cmd.add_argument("--port", type=int, default=8765)
    serve_cmd.add_argument("--offline-sample", action="store_true")
    serve_cmd.add_argument("--open", action="store_true", help="Open the local dashboard in the default browser.")

    install = sub.add_parser("install-service")
    install.add_argument("--config", default="config/default.yaml")
    install.add_argument("--out", default="outputs/latest_report.html")
    install.add_argument("--port", type=int, default=8765)
    install.add_argument("--offline-sample", action="store_true")

    uninstall = sub.add_parser("uninstall-service")
    uninstall.add_argument("--label", default="com.quant-ai-system.service")

    status = sub.add_parser("service-status")
    status.add_argument("--port", type=int, default=8765)

    factor = sub.add_parser("factor-test")
    factor.add_argument("--config", default="config/default.yaml")
    factor.add_argument("--out", default="outputs/factor_report.html")
    factor.add_argument("--offline-sample", action="store_true")
    factor.add_argument("--forward-days", type=int, default=20)

    data_check = sub.add_parser("data-check")
    data_check.add_argument("--config", default="config/default.yaml")
    data_check.add_argument("--provider", default="fmp", choices=["fmp", "yfinance", "stooq"])
    data_check.add_argument("--tickers", default="", help="Comma-separated ticker override. Defaults to configured universe plus benchmarks.")

    news_check = sub.add_parser("news-check")
    news_check.add_argument("--config", default="config/default.yaml")
    news_check.add_argument("--tickers", default="", help="Comma-separated ticker override. Defaults to configured universe.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command == "serve":
        serve(args.config, args.out, host=args.host, port=args.port, offline_sample=args.offline_sample, open_browser=args.open)
        return 0

    if args.command == "install-service":
        plist = install_launch_agent(args.config, args.out, args.port, offline_sample=args.offline_sample)
        print(f"Installed LaunchAgent: {plist}")
        print(f"Open: http://127.0.0.1:{args.port}")
        return 0

    if args.command == "uninstall-service":
        plist = uninstall_launch_agent(args.label)
        print(f"Uninstalled LaunchAgent: {plist}")
        return 0

    if args.command == "service-status":
        print(service_status(args.port))
        return 0

    config = load_config(args.config)

    if args.command == "factor-test":
        tickers = list(dict.fromkeys(config.universe.tickers + config.universe.leveraged_tickers + config.universe.benchmarks))
        data = make_sample_market_data(tickers, years=min(config.data.years, 5)) if args.offline_sample else get_market_data(tickers, config.data)
        metrics, _raw = run_factor_experiment(
            data.prices,
            config.universe.tickers + config.universe.leveraged_tickers,
            config.universe.primary_benchmark,
            forward_days=args.forward_days,
        )
        out = write_factor_report(metrics, args.out)
        print(f"Factor report: {out}")
        print(f"Factors: {len(metrics)}")
        if data.issues:
            print(f"Data issues: {len(data.issues)}")
        return 0

    if args.command == "data-check":
        if args.tickers.strip():
            tickers = [ticker.strip().upper() for ticker in args.tickers.split(",") if ticker.strip()]
        else:
            tickers = list(dict.fromkeys(config.universe.tickers + config.universe.leveraged_tickers + config.universe.benchmarks))
        checks = check_provider_data(tickers, args.provider, config.data)
        failures = [item for item in checks if not item.ok]
        print(f"Provider: {args.provider}")
        print(f"Tickers: {len(checks)}")
        print(f"OK: {len(checks) - len(failures)}")
        print(f"Failed/stale: {len(failures)}")
        for item in checks:
            first = item.first_date.date().isoformat() if item.first_date is not None else "-"
            last = item.last_date.date().isoformat() if item.last_date is not None else "-"
            close = f"{item.latest_close:.2f}" if item.latest_close is not None else "-"
            status = "OK" if item.ok else "CHECK"
            print(f"{status}\t{item.ticker}\trows={item.rows}\tfirst={first}\tlast={last}\tclose={close}\t{item.message}")
        return 1 if failures else 0

    if args.command == "news-check":
        if args.tickers.strip():
            tickers = [ticker.strip().upper() for ticker in args.tickers.split(",") if ticker.strip()]
        else:
            tickers = config.universe.tickers + config.universe.leveraged_tickers
        briefs = build_news_briefs(tickers, config.research)
        failures = [brief for brief in briefs if brief.data_issue]
        print(f"Provider: {config.research.news_provider}")
        print(f"Tickers: {len(briefs)}")
        print(f"With news: {sum(1 for brief in briefs if brief.article_count > 0)}")
        print(f"With risk flags: {sum(1 for brief in briefs if brief.risk_flags)}")
        for brief in briefs:
            risk = ",".join(brief.risk_flags) if brief.risk_flags else "-"
            catalyst = ",".join(brief.catalyst_flags) if brief.catalyst_flags else "-"
            headline = brief.headlines[0] if brief.headlines else brief.data_issue or "-"
            print(f"{brief.ticker}\tnews={brief.article_count}\tcatalyst={catalyst}\trisk={risk}\t{headline}")
        return 1 if failures and all(brief.article_count == 0 for brief in briefs) else 0

    if args.command == "show-config":
        print(f"NAV: {config.account.nav:,.0f} {config.account.currency}")
        print(f"Tickers: {', '.join(config.universe.tickers)}")
        print(f"Benchmarks: {', '.join(config.universe.benchmarks)}")
        print(f"Risk profile: {config.risk.profile}")
        return 0

    if args.command == "telegram-chat-id":
        updates = fetch_telegram_updates(config)
        seen: set[str] = set()
        for update in updates:
            message = update.get("message") or update.get("channel_post") or {}
            chat = message.get("chat") or {}
            chat_id = str(chat.get("id", "")).strip()
            if chat_id and chat_id not in seen:
                seen.add(chat_id)
                title = chat.get("title") or chat.get("username") or chat.get("first_name") or ""
                print(f"{chat_id}\t{title}")
        if not seen:
            print("No chat id found. Send /start to the bot in Telegram, then rerun this command.")
        return 0

    result = run_system(config, Path(args.out), offline_sample=args.offline_sample)
    if getattr(args, "send_email", False) or args.command == "send-email":
        send_summary_email(config, result)
        print("Email: sent")
    if getattr(args, "send_telegram", False) or args.command == "send-telegram":
        send_telegram_message(config, result)
        print("Telegram: sent")
    print(f"Report: {result.report_path}")
    print(f"Signals: {len(result.signals)}")
    action_summary = build_action_summary(
        result.signals,
        result.supervisor_reviews,
        result.exit_reviews,
        result.drift_reviews,
        result.news_briefs,
        set(result.tactical_tickers),
        config.risk.max_positions,
    )
    print(f"Stock candidates: {', '.join(signal.ticker for signal in action_summary.stock_candidates) if action_summary.stock_candidates else 'none'}")
    print(f"Tactical ETF candidates: {', '.join(signal.ticker for signal in action_summary.tactical_candidates) if action_summary.tactical_candidates else 'none'}")
    print(f"Data fix positions: {', '.join(review.ticker for review in action_summary.data_fix_positions) if action_summary.data_fix_positions else 'none'}")
    print(f"Supervisor reviews: {len(result.supervisor_reviews)}")
    print(f"Backtest strategies: {len(result.backtest.metrics)}")
    print(f"Portfolio mode: {result.portfolio_risk.mode}")
    if result.market_data.issues:
        print(f"Data issues: {len(result.market_data.issues)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
