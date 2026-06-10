# debug_mode: params / monitor
# strategy: trend_momo_vol_filter_1
# version: v1 (baseline)
# purpose: 由 LLM 从 _original.md 翻译
# date: 2026-06-10
# mode: params (默认) | weight
# run:   single (默认) | --monitor
# --- monitor 监听目录 ---
#   params 模式 → strategiesParam/  下新增 *_v<n>.md          文件触发
#   weight 模式 → strategiesWeight/ 下新增 *_weight_v<n>.md  文件触发
#   debounce 5s, Ctrl+C 退出
# --- monitor cwd 要求 ---
#   monitor 模式下 watch_dir 改用绝对路径
# --- CONFIG 最高优先级 ---
#   test_universe / start_date / end_date / limit
# command: python generated/strategy.py
# command: python generated/strategy.py params
# command: python generated/strategy.py weight
# command: python generated/strategy.py --monitor
# command: python generated/strategy.py weight --monitor
# command: python generated/strategy.py weight --weight-test trend_momo_vol_filter_1

"""trend_momo_vol_filter_1 策略. 由 LLM 从 _original.md 翻译.

按 subject_structure.md §4.6 模式手写. 包含 4 个方法:
- compute_factors(df, params) -> {factor_name: Series}
- entry_score(factors, params, weights) -> float
- get_triggered_signals(factors, params, weights) -> list[str]
- should_exit(position, factors, params, weights) -> signal_name | None
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pandas as pd

_HERE = Path(__file__).resolve()
_SUBJECTS_DIR = _HERE.parents[2]
if str(_SUBJECTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SUBJECTS_DIR))

from subject.factors import (  # noqa: E402
    ma,
    atr,
    volume_ratio,
)
from subject.conditions import (  # noqa: E402
    check_fixed_stop,
    check_trailing_stop,
    check_time_stop,
)


# ====================================================================
# 策略执行配置 (最高优先级, 覆盖 CLI / spec 默认值)
# ====================================================================
@dataclass
class StrategyConfig:
    """策略执行配置. 任何字段非 None 时, 覆盖对应 CLI 参数和 spec 默认值."""
    test_universe: Optional[list[str]] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    limit: Optional[int] = None


CONFIG = StrategyConfig(
    test_universe=None,
    start_date=None,
    end_date=None,
    limit=None,
)


class Strategy:
    def compute_factors(self, df: pd.DataFrame, params: dict) -> dict:
        return {
            "close": df["收盘价"],
            "ma_10": ma(df["收盘价"], 10),
            "ma_30": ma(df["收盘价"], 30),
            "macd_diff": df["收盘价"].ewm(span=12, adjust=False).mean()
                           - df["收盘价"].ewm(span=26, adjust=False).mean(),
            "volume_ratio_20": volume_ratio(df["成交量（股）"], 20),
            "atr_14": atr(df["最高价"], df["最低价"], df["收盘价"], 14),
        }

    def entry_score(self, factors: dict, params: dict, weights: dict) -> float:
        score = 0.0
        ew = weights["entry"]

        if (factors["ma_10"] > factors["ma_30"]).iloc[-1]:
            score += ew["ma_golden_cross"]

        if (factors["macd_diff"] > 0).iloc[-1]:
            score += ew["macd_positive"]

        if (factors["volume_ratio_20"] > params["vol_break_ratio"]).iloc[-1]:
            score += ew["volume_surge"]

        atr_ratio = factors["atr_14"].iloc[-1] / factors["close"].iloc[-1]
        if atr_ratio > params["atr_low_limit"] and atr_ratio < params["atr_up_limit"]:
            score += ew["atr_normal_range"]

        return score

    def get_triggered_signals(self, factors: dict, params: dict, weights: dict) -> list[str]:
        triggered = []

        if (factors["ma_10"] > factors["ma_30"]).iloc[-1]:
            triggered.append("ma_golden_cross")

        if (factors["macd_diff"] > 0).iloc[-1]:
            triggered.append("macd_positive")

        if (factors["volume_ratio_20"] > params["vol_break_ratio"]).iloc[-1]:
            triggered.append("volume_surge")

        atr_ratio = factors["atr_14"].iloc[-1] / factors["close"].iloc[-1]
        if atr_ratio > params["atr_low_limit"] and atr_ratio < params["atr_up_limit"]:
            triggered.append("atr_normal_range")

        return triggered

    def should_exit(self, position: dict, factors: dict, params: dict, weights: dict) -> Optional[str]:
        ew = weights["exit"]
        for sig in sorted(ew, key=ew.get, reverse=True):
            if sig == "fixed_stop_loss":
                if check_fixed_stop(position["current_price"], position["entry_price"], params["stop_loss_pct"]):
                    return "fixed_stop_loss"
            elif sig == "trailing_stop":
                if check_trailing_stop(position["current_price"], position["highest"], params["trailing_stop_pct"]):
                    return "trailing_stop"
            elif sig == "time_stop":
                if check_time_stop(position["holding_days"], params["max_holding_days"]):
                    return "time_stop"
        return None


# ====================================================================
# 策略回测执行入口
# ====================================================================
if __name__ == "__main__":
    import argparse
    import re
    import threading
    import time

    from watchdog.events import FileSystemEvent, FileSystemEventHandler
    from watchdog.observers import Observer

    os.chdir(_HERE.parents[2])

    parser = argparse.ArgumentParser(
        prog="strategy.py",
        description="trend_momo_vol_filter_1 策略回测入口",
    )
    parser.add_argument("mode", nargs="?", default="params", choices=["params", "weight"])
    parser.add_argument("--monitor", action="store_true")
    parser.add_argument("--weight-test", default=None)
    parser.add_argument("--start-date", default=None)
    parser.add_argument("--end-date", default=None)
    parser.add_argument("--test-universe", default=None, help="自定义股票代码 (逗号分隔)")
    parser.add_argument("--max-stocks", type=int, default=None, help="限制测试股票数")
    parser.add_argument("--capital", type=float, default=300_000)
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    def run_once() -> int:
        eff_test_universe = CONFIG.test_universe
        if eff_test_universe is None and args.test_universe is not None:
            eff_test_universe = [s.strip() for s in args.test_universe.split(",") if s.strip()]
        eff_start_date = CONFIG.start_date if CONFIG.start_date is not None else args.start_date
        eff_end_date = CONFIG.end_date if CONFIG.end_date is not None else args.end_date
        eff_limit = CONFIG.limit if CONFIG.limit is not None else args.max_stocks
        eff_weight_test = args.weight_test if args.weight_test else "trend_momo_vol_filter_1"

        if eff_test_universe is not None or eff_limit is not None or CONFIG.start_date is not None or CONFIG.end_date is not None or args.weight_test:
            print(f"[CONFIG] test_universe={eff_test_universe} start={eff_start_date} end={eff_end_date} limit={eff_limit} weight_test={eff_weight_test}")

        from subject.cli.main import main
        cli_args = ["run", "--strategy", "trend_momo_vol_filter_1", "--mode", args.mode]
        cli_args += ["--weight-test", eff_weight_test]
        if eff_test_universe is not None:
            cli_args += ["--test-universe", ",".join(eff_test_universe)]
        if eff_limit is not None:
            cli_args += ["--max-stocks", str(eff_limit)]
        if eff_start_date:
            cli_args += ["--start-date", eff_start_date]
        if eff_end_date:
            cli_args += ["--end-date", eff_end_date]
        if args.capital != 300_000:
            cli_args += ["--capital", str(args.capital)]
        if args.output:
            cli_args += ["--output", args.output]
        return main(cli_args)

    if not args.monitor:
        sys.exit(run_once())

    if args.mode == "params":
        watch_dir = _HERE.parents[1] / "strategiesParam"
        watch_pattern = re.compile(r".+_v\d+\.md$")
    else:
        watch_dir = _HERE.parents[1] / "strategiesWeight"
        watch_pattern = re.compile(r".+_weight_v\d+\.md$")

    if not watch_dir.exists():
        print(f"ERROR: monitor 模式需要 {watch_dir}/ 目录, 不存在", file=sys.stderr)
        sys.exit(1)

    trigger_event = threading.Event()
    stop_event = threading.Event()

    class _WatchHandler(FileSystemEventHandler):
        def _maybe_fire(self, path_str: str) -> None:
            if not path_str.endswith(".md"):
                return
            if watch_pattern.match(Path(path_str).name):
                trigger_event.set()

        def on_created(self, event: FileSystemEvent) -> None:
            if not event.is_directory:
                self._maybe_fire(event.src_path)

        def on_modified(self, event: FileSystemEvent) -> None:
            if not event.is_directory:
                self._maybe_fire(event.src_path)

    handler = _WatchHandler()
    observer = Observer()
    observer.schedule(handler, str(watch_dir.resolve()), recursive=False)
    observer.start()

    import signal as _signal
    def _handle_sigint(signum, frame):
        stop_event.set()
    try:
        _signal.signal(_signal.SIGINT, _handle_sigint)
    except (ValueError, OSError):
        pass

    DEBOUNCE_SECONDS = 5.0
    print(f"[monitor] watching: {watch_dir.resolve()}/")
    print(f"[monitor] pattern:  {watch_pattern.pattern}")
    print(f"[monitor] debounce: {DEBOUNCE_SECONDS}s, Ctrl+C 退出")

    try:
        while not stop_event.is_set():
            if not trigger_event.wait(timeout=1.0):
                continue
            trigger_event.clear()
            while not stop_event.is_set():
                fired_again = trigger_event.wait(timeout=DEBOUNCE_SECONDS)
                if fired_again:
                    trigger_event.clear()
                else:
                    break
            if stop_event.is_set():
                break
            print(f"[trigger] new version file in {watch_dir.name}/, running backtest...")
            rc = run_once()
            print(f"[trigger] backtest exit code: {rc}")
    except KeyboardInterrupt:
        stop_event.set()
        print("\n[monitor] stopped (KeyboardInterrupt)")
    finally:
        observer.stop()
        observer.join(timeout=3.0)
        if observer.is_alive():
            print("[monitor] warning: watchdog observer 未在 3s 内退出, 强制丢弃")
