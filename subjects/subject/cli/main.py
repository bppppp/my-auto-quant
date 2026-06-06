"""CLI 主入口. 见 subject_structure.md §6.4 / subject.md §5.1."""
from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

from ..backtest.runner import BacktestRunner


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="subject.cli", description="策略回测 CLI")
    sub = p.add_subparsers(dest="cmd", required=True)

    run = sub.add_parser("run", help="跑一次回测 / 启动 monitor")
    run.add_argument("--strategy", required=True, help="策略目录名 (e.g. ma_cross_atr_volume)")
    run.add_argument("--mode", required=True, choices=["params", "weight"], help="运行模式")
    run.add_argument("--weight-test", default=None,
                     help="weight 模式覆盖 test name (默认 = strategy_name, 即 strategiesWeight/<strategy_name>_weight_v<n>.md 的 test name. 仅在需覆盖文件前缀时传)")
    run.add_argument("--monitor", action="store_true", help="monitor 模式 (生成带日期戳的报告)")
    run.add_argument("--interval", default="1d", help="monitor 间隔 (e.g. 1d, 7d)")
    run.add_argument("--start-date", default=None, help="起始日期 YYYY-MM-DD (含)")
    run.add_argument("--end-date", default=None, help="结束日期 YYYY-MM-DD (含)")
    run.add_argument("--max-stocks", type=int, default=None,
                     help="最多测试的股票数 (None = 全跑 300 只, 性能慢; 调试建议 5-10)")
    run.add_argument("--test-universe", default=None,
                     help="自定义测试股票代码列表 (逗号分隔, 带后缀, 如 '000001.SZ,600000.SH'); "
                          "非空时覆盖 spec.test_universe, 然后再应用 --max-stocks")
    run.add_argument("--capital", type=float, default=300_000, help="初始资金")
    run.add_argument("--output", default=None, help="报告输出路径 (默认按 mode 规则)")
    return p


def _make_runner(args: argparse.Namespace) -> BacktestRunner:
    # 解析 --test-universe (逗号分隔 → list)
    test_universe_override: list[str] | None = None
    if args.test_universe:
        test_universe_override = [s.strip() for s in args.test_universe.split(",") if s.strip()]

    return BacktestRunner(
        strategy_name=args.strategy,
        mode=args.mode,
        weight_test=args.weight_test,
        start_date=args.start_date,
        end_date=args.end_date,
        initial_capital=args.capital,
        subjects_dir=".",
        max_stocks=args.max_stocks,
        test_universe_override=test_universe_override,
    )


def _output_path(args: argparse.Namespace, monitor_meta: dict | None, version: str = "v1") -> Path:
    """按 mode 决定输出路径. 见 subject.md §5.1.

    version: 实际跑的策略版本 (runner 已从 strategiesParam/strategiesWeight 选出的最新),
             透传到 report 文件名, 避免硬编码 v1 (v2 的回测不应再写 report_v1.md).
    """
    base = Path(args.strategy)
    if args.mode == "params":
        d = base / "reportParams"
        if args.monitor or monitor_meta is not None:
            today = datetime.now().strftime("%Y-%m-%d")
            return d / f"report_{version}_{today}.md"
        return d / f"report_{version}.md"
    else:
        d = base / "reportWeight"
        if args.monitor or monitor_meta is not None:
            today = datetime.now().strftime("%Y-%m-%d")
            return d / f"report_signals_{version}_{today}.md"
        return d / f"report_signals_{version}.md"


def _interval_seconds(s: str) -> int:
    """Parse '1d' / '7d' / '1h' → 秒."""
    m = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    if not s or not s[-1] in m:
        raise ValueError(f"invalid interval: {s!r} (use e.g. 1d, 7d, 1h)")
    try:
        n = int(s[:-1])
    except ValueError:
        raise ValueError(f"invalid interval: {s!r}")
    return n * m[s[-1]]


def cmd_run(args: argparse.Namespace) -> int:
    monitor_meta: dict | None = None
    if args.monitor:
        monitor_meta = {
            "start_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "end_date": "",
            "run_count": 0,
            "trigger_count": 0,
            "last_update": "",
        }

    while True:
        runner = _make_runner(args)
        results = runner.run()
        out_path = _output_path(args, monitor_meta, version=results.version)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        if monitor_meta is not None:
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            monitor_meta["end_date"] = now_str
            monitor_meta["run_count"] = monitor_meta.get("run_count", 0) + 1
            monitor_meta["last_update"] = now_str
            # 累计 trigger count
            n = 0
            if "events" in results.__dict__ and len(results.events) > 0:
                n = int((results.events["action"] == "triggered").sum())
            monitor_meta["trigger_count"] = monitor_meta.get("trigger_count", 0) + n
        runner.write_report(results, out_path, monitor_meta=monitor_meta)
        print(f"[OK] report written: {out_path}")

        if not args.monitor:
            break
        # monitor 模式: 循环
        interval_s = _interval_seconds(args.interval)
        time.sleep(interval_s)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.cmd == "run":
        return cmd_run(args)
    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
