from __future__ import annotations

import argparse
from pathlib import Path

from quant_ai_system.config import load_config
from quant_ai_system.emailer import send_summary_email
from quant_ai_system.engine import run_system
from quant_ai_system.data import get_market_data, make_sample_market_data
from quant_ai_system.factors import run_factor_experiment, write_factor_report
from quant_ai_system.server import install_launch_agent, serve, service_status, uninstall_launch_agent


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="quant-ai", description="Local low-frequency US tech/AI quant alert system.")
    sub = parser.add_subparsers(dest="command", required=True)

    for name in ["run", "backtest"]:
        cmd = sub.add_parser(name)
        cmd.add_argument("--config", default="config/default.yaml")
        cmd.add_argument("--out", default="outputs/latest_report.html")
        cmd.add_argument("--offline-sample", action="store_true", help="Use deterministic sample data instead of remote market data.")
        cmd.add_argument("--send-email", action="store_true", help="Send summary email after generating the report.")

    email = sub.add_parser("send-email")
    email.add_argument("--config", default="config/default.yaml")
    email.add_argument("--out", default="outputs/latest_report.html")
    email.add_argument("--offline-sample", action="store_true")

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

    if args.command == "show-config":
        print(f"NAV: {config.account.nav:,.0f} {config.account.currency}")
        print(f"Tickers: {', '.join(config.universe.tickers)}")
        print(f"Benchmarks: {', '.join(config.universe.benchmarks)}")
        print(f"Risk profile: {config.risk.profile}")
        return 0

    result = run_system(config, Path(args.out), offline_sample=args.offline_sample)
    if getattr(args, "send_email", False) or args.command == "send-email":
        send_summary_email(config, result)
        print("Email: sent")
    print(f"Report: {result.report_path}")
    print(f"Signals: {len(result.signals)}")
    approved = {review.ticker for review in result.supervisor_reviews if review.decision == "approve_for_consideration"}
    core = [
        signal for signal in sorted(result.signals, key=lambda item: item.score, reverse=True)
        if (
            signal.ticker in approved
            and signal.score >= config.risk.min_core_score
            and ("加仓" in signal.action or "小仓" in signal.action)
        )
    ][: config.risk.max_positions]
    print(f"Core candidates: {', '.join(signal.ticker for signal in core) if core else 'none'}")
    print(f"Supervisor reviews: {len(result.supervisor_reviews)}")
    print(f"Backtest strategies: {len(result.backtest.metrics)}")
    print(f"Portfolio mode: {result.portfolio_risk.mode}")
    if result.market_data.issues:
        print(f"Data issues: {len(result.market_data.issues)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
