"""CLI 主入口. 见 subject_structure.md §6.4 / subject.md §5.1."""
from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

from ..backtest.runner import BacktestRunner
from .top300 import run_top300_optimize


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
                          "非空时覆盖默认测试集; 默认从 test_universe/top300.md 读取(存在时),否则用 HS300")
    run.add_argument("--capital", type=float, default=300_000, help="初始资金")
    run.add_argument("--output", default=None, help="报告输出路径 (默认按 mode 规则)")

    # run-top300 子命令
    top300 = sub.add_parser("run-top300", help="Top300 测试集筛选（三轮全量回测 + params 调优）")
    top300.add_argument("--strategy", required=True, help="策略目录名 (e.g. trend_breakout_atr_rsi)")
    top300.add_argument("--rounds", type=int, default=3, help="调优轮数（默认 3）")
    top300.add_argument("--max-retries", type=int, default=3, help="LLM 重试上限（默认 3）")
    top300.add_argument("--start-date", default=None, help="top300 模式起始日期 YYYY-MM-DD (默认5 年)")
    top300.add_argument("--end-date", default=None, help="top300 模式结束日期 YYYY-MM-DD (默认数据末日)")
    top300.add_argument("--limit", type=int, default=None, help="top300 模式每轮回测的 limit (None = 不限)")

    return p


def _make_runner(args: argparse.Namespace) -> BacktestRunner:
    # 解析 --test-universe (逗号分隔 → list)
    test_universe_override: list[str] | None = None
    if args.test_universe:
        # 用户显式指定
        test_universe_override = [s.strip() for s in args.test_universe.split(",") if s.strip()]
    else:
        # 默认从 test_universe/top300.md 读取，存在时使用，否则 fallback 到 HS300
        from .top300 import get_test_universe
        test_universe_override = get_test_universe(args.strategy)

    # subjects_dir 使用项目根目录 (subjects/ 的父目录)
    # 兼容 CLI 从 subjects/ 目录运行: subjects_dir="."
    # 也兼容从项目根运行: subjects_dir=Path(__file__).parent.parent.parent
    import sys
    from pathlib import Path
    _cli_dir = Path(__file__).resolve().parent  # cli/ 目录
    _subject_dir = _cli_dir.parent.parent  # subjects/ 的父目录 (项目根)
    # 如果当前目录有 subjects/ 子目录，说明是从项目根运行的
    if (Path.cwd() / "subjects").exists():
        _subjects_dir = Path.cwd()
    # 如果当前目录本身就是 subjects/ 目录 (cwd/subject存在, cwd/backtest 不存在)
    elif (Path.cwd() / "subject").exists() and not (Path.cwd() / "backtest").exists():
        _subjects_dir = Path.cwd()
    else:
        _subjects_dir = _subject_dir

    return BacktestRunner(
        strategy_name=args.strategy,
        mode=args.mode,
        weight_test=args.weight_test,
        start_date=args.start_date,
        end_date=args.end_date,
        initial_capital=args.capital,
        subjects_dir=_subjects_dir,
        max_stocks=args.max_stocks,
        test_universe_override=test_universe_override,
    )


def _output_path(args: argparse.Namespace, monitor_meta: dict | None, version: str = "v1") -> Path:
    """按 mode 决定输出路径. 见 subject.md §5.1.

    version: 实际跑的策略版本 (runner 已从 strategiesParam/strategiesWeight 选出的最新),
             透传到 report 文件名, 避免硬编码 v1 (v2 的回测不应再写 report_v1.md).
    """
    # 使用与 _make_runner 相同的逻辑确定 subjects_dir，确保绝对路径
    _cli_dir = Path(__file__).resolve().parent
    _subject_dir = _cli_dir.parent.parent
    if (Path.cwd() / "subjects").exists():
        _subjects_dir = Path.cwd()
    elif (Path.cwd() / "subject").exists() and not (Path.cwd() / "backtest").exists():
        _subjects_dir = Path.cwd()
    else:
        _subjects_dir = _subject_dir

    # 构建绝对路径: subjects_dir / strategy_name / reportParams|reportWeight / ...
    base = _subjects_dir / args.strategy
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


def cmd_top300(args: argparse.Namespace) -> int:
    """Top300 测试集筛选."""
    result = run_top300_optimize(
        name=args.strategy,
        rounds=args.rounds,
        max_retries=args.max_retries,
        start_date=args.start_date,
        end_date=args.end_date,
        limit=args.limit,
    )
    if result is None:
        print(f"[ERROR] Top300 筛选失败")
        return 1
    print(f"[OK] Top300 测试集已写入: subjects/{args.strategy}/test_universe/top300.md")
    print(f"      最优轮: Round {result.best_round}, 平均年化收益率: {result.best_avg_return:+.2%}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.cmd == "run":
        return cmd_run(args)
    if args.cmd == "run-top300":
        return cmd_top300(args)
    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
