"""CLI 入口——一条命令做 MVP 主要事情。

用法：
  hindcast backtest [--only LABEL_SUBSTRING]
  hindcast predict YYYY-MM-DD              （单时点跑常态预测）
"""

from __future__ import annotations

import argparse
import json
import sys

from hindcast.backtest import run_backtest
from hindcast.data import SNAPSHOTS, ALL_SNAPSHOTS
from hindcast.predict import predict


def cmd_backtest(args: argparse.Namespace) -> None:
    snaps = ALL_SNAPSHOTS
    if args.only:
        snaps = [s for s in snaps if args.only.lower() in s.label.lower()]
        if not snaps:
            print(f"ERROR: no snapshot matches --only={args.only}")
            sys.exit(1)

    # Phase 1: target=fed-funds 走 policy rate backtest
    if args.target == "fed-funds":
        from hindcast.policy_rate import run_policy_rate_backtest
        snaps_with_macro = [s for s in snaps if s.macro is not None]
        print(f"回测时点 (Fed funds rate): {[s.label for s in snaps_with_macro]}")
        run_policy_rate_backtest(snaps_with_macro)
        return

    # Phase 2: target=us-2y / us-10y 走 yield backtest
    if args.target in ("us-2y", "us-10y"):
        from hindcast.treasury_yield import run_yield_backtest
        yield_target = "US_2Y" if args.target == "us-2y" else "US_10Y"
        snaps_with_macro = [s for s in snaps if s.macro is not None]
        print(f"回测时点 ({yield_target}): {[s.label for s in snaps_with_macro]}")
        run_yield_backtest(yield_target, snaps_with_macro)  # type: ignore[arg-type]
        return

    # Phase 3: FX
    if args.target in ("fx-cnh", "fx-jpy", "fx-eur"):
        from hindcast.fx import run_fx_backtest
        fx_target = {"fx-cnh": "USD/CNH", "fx-jpy": "USD/JPY", "fx-eur": "EUR/USD"}[args.target]
        snaps_with_macro = [s for s in snaps if s.macro is not None]
        print(f"回测时点 ({fx_target}): {[s.label for s in snaps_with_macro]}")
        run_fx_backtest(fx_target, snaps_with_macro)  # type: ignore[arg-type]
        return

    # Phase 4a: 派生 target (2s10s 利差) — 无新 prompt, 复用 2Y/10Y
    if args.target == "2s10s":
        from hindcast.derived import run_2s10s_backtest
        snaps_with_macro = [s for s in snaps if s.macro is not None]
        print(f"回测时点 (US 2s10s 利差): {[s.label for s in snaps_with_macro]}")
        run_2s10s_backtest(snaps_with_macro)
        return

    # Phase 2.5: 桥梁变量 (TIPS / BEI / DXY) — XAU 集成预测必备
    if args.target in ("tips", "bei", "dxy"):
        from hindcast.bridge import run_bridge_backtest
        bridge_target = {"tips": "US_10Y_TIPS", "bei": "US_10Y_BEI", "dxy": "DXY"}[args.target]
        snaps_with_macro = [s for s in snaps if s.macro is not None]
        print(f"回测时点 ({bridge_target}): {[s.label for s in snaps_with_macro]}")
        run_bridge_backtest(bridge_target, snaps_with_macro)  # type: ignore[arg-type]
        return

    # Phase 3: 商品
    if args.target in ("copper", "oil", "crude-oil"):
        from hindcast.commodity import run_commodity_backtest
        comm_target = "CRUDE_OIL" if args.target in ("oil", "crude-oil") else "COPPER"
        snaps_with_macro = [s for s in snaps if s.macro is not None]
        print(f"回测时点 ({comm_target}): {[s.label for s in snaps_with_macro]}")
        run_commodity_backtest(comm_target, snaps_with_macro)  # type: ignore[arg-type]
        return

    # 默认: XAU/USD
    print(f"回测时点 (XAU/USD): {[s.label for s in snaps]}")
    report = run_backtest(snaps)
    print("\n\n========== W3 HARD GATE 回测结果 ==========")
    print(report.pretty())


def cmd_predict(args: argparse.Namespace) -> None:
    snap = SNAPSHOTS.get(args.date)
    if not snap:
        print(f"ERROR: no snapshot for {args.date}. Available: {list(SNAPSHOTS.keys())}")
        sys.exit(1)
    forecast = predict(snap)
    print(f"\n========== {forecast.label} ({forecast.as_of}) ==========")
    for v in forecast.verdicts:
        if v._failed:
            print(f"  {v.school:<25} FAILED — {v._error}")
        else:
            t5 = v.verdict.get("T+5")
            t20 = v.verdict.get("T+20")
            print(f"  {v.school:<25} T+5: {t5.dir:<5} {t5.range_pct}  T+20: {t20.dir:<5} {t20.range_pct}")
            print(f"    Top signals: {v.top_signals}")
            print(f"    Reasoning: {v.reasoning[:120]}")

    print(f"\n整合预测（多数投票）:")
    for h, hf in forecast.horizons.items():
        print(f"  {h}: {hf.dir}  votes={hf.vote_counts}")
    print(f"\n是否一致: {forecast.is_unanimous}, 是否分裂: {forecast.is_split}")


def cmd_web(args: argparse.Namespace) -> None:
    """启动 FastAPI Web 服务。"""
    from hindcast.web import main as web_main
    sys.argv = ["hindcast web"]
    if args.host:
        sys.argv += ["--host", args.host]
    if args.port:
        sys.argv += ["--port", str(args.port)]
    web_main()


def cmd_continuous(args: argparse.Namespace) -> None:
    from hindcast.continuous import run_continuous_backtest
    run_continuous_backtest(target=args.target, start_ym=args.start, end_ym=args.end)


def cmd_school_ledger(args: argparse.Namespace) -> None:
    from hindcast.school_ledger import build_ledger
    build_ledger(logs=args.logs.split(","))


def cmd_compass_eval(args: argparse.Namespace) -> None:
    from hindcast.continuous import compass_eval, compass_eval_event
    if args.catalyst:
        compass_eval_event(logs=args.logs.split(","), target=args.target)
    else:
        compass_eval(logs=args.logs.split(","), target=args.target)


def cmd_kaofa_f(args: argparse.Namespace) -> None:
    from hindcast.kaofa_f import run_kaofa_f
    run_kaofa_f(which=args.predictor)


def main():
    parser = argparse.ArgumentParser(prog="hindcast")
    sub = parser.add_subparsers(dest="cmd", required=True)

    bp = sub.add_parser("backtest", help="W3 hard gate 历史回测")
    bp.add_argument("--only", help="substring 匹配时点 label")
    bp.add_argument("--target", choices=[
        "xau", "fed-funds", "us-2y", "us-10y",
        "fx-cnh", "fx-jpy", "fx-eur", "copper", "oil", "crude-oil",
        "tips", "bei", "dxy", "2s10s",
    ], default="xau", help="预测目标 (default: xau)")
    bp.set_defaults(func=cmd_backtest)

    pp = sub.add_parser("predict", help="单时点常态预测")
    pp.add_argument("date", help="ISO 日期，如 2022-02-23（必须在 snapshots 内）")
    pp.set_defaults(func=cmd_predict)

    wp = sub.add_parser("web", help="启动 FastAPI Web 服务")
    wp.add_argument("--host", default="127.0.0.1")
    wp.add_argument("--port", type=int, default=8000)
    wp.set_defaults(func=cmd_web)

    cp = sub.add_parser("continuous", help="平稳期月度滚动回测 (factual_rag 喂数据)")
    cp.add_argument("--target", default="USD/JPY",
                    choices=["USD/JPY", "EUR/USD", "USD/CNH", "XAU/USD"])
    cp.add_argument("--start", default="2016-06", help="起始 YYYY-MM")
    cp.add_argument("--end", default="2018-01", help="结束 YYYY-MM")
    cp.set_defaults(func=cmd_continuous)

    sl = sub.add_parser("school-ledger", help="学派命中率+缺陷洞察账本(17-ADR首个产出,零LLM)")
    sl.add_argument("--logs", required=True, help="逗号分隔的事件回测 log 路径")
    sl.set_defaults(func=cmd_school_ledger)

    ce = sub.add_parser("compass-eval", help="考法D 罗盘有效性(复用已有log+诚实基线)")
    ce.add_argument("--logs", required=True, help="逗号分隔的连续回测 log 路径")
    ce.add_argument("--target", default="USD/JPY",
                    choices=["USD/JPY", "EUR/USD", "USD/CNH", "XAU/USD"])
    ce.add_argument("--catalyst", action="store_true",
                    help="考法E 事件触发型(事前催化剂探测)")
    ce.set_defaults(func=cmd_compass_eval)

    kf = sub.add_parser("kaofa-f", help="考法F 脆弱性预警校准(structural_prudential考场,零LLM)")
    kf.add_argument("--predictor", default="all",
                    choices=["all", "never", "always", "proxy", "rag"],
                    help="预测端: 笨基线/已证伪代理/RAG脆弱性合成(即插即测)")
    kf.set_defaults(func=cmd_kaofa_f)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
