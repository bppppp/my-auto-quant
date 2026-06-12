# debug_mode: params / monitor
# strategy: trend_atr_volume_strategy_1
# version: v1 (baseline)
# purpose: translated from _original.md by LLM
# date: 2026-06-11
# mode: params (default) | weight
# run:   single (default) | --monitor
# --- monitor watch dir ---
#   params mode -> strategiesParam/  for *_v<n>.md  trigger
#   weight mode -> strategiesWeight/ for *_weight_v<n>.md trigger
#   debounce 5s, Ctrl+C to exit
# --- monitor cwd requirement ---
#   monitor mode: watch_dir must be absolute path
# --- CONFIG highest priority ---
#   test_universe / start_date / end_date / limit
# command: python generated/strategy.py
# command: python generated/strategy.py params
# command: python generated/strategy.py weight
# command: python generated/strategy.py --monitor
# command: python generated/strategy.py weight --monitor
# command: python generated/strategy.py weight --weight-test trend_atr_volume_strategy_1

"""trend_atr_volume_strategy_1 strategy. Translated from _original.md by LLM.

Contains 3 methods:
- compute_factors(df, params) -> {factor_name: Series}
- entry_score(factors, params, weights) -> float
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


@dataclass
class StrategyConfig:
    test_universe: Optional[list[str]] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    limit: Optional[int] = None
    top300_start_date: Optional[str] = None
    top300_end_date: Optional[str] = None
    top300_limit: Optional[int] = None


CONFIG = StrategyConfig(
    test_universe=None,
    start_date=None,
    end_date=None,
    limit=None,
    top300_start_date=None,
    top300_end_date=None,
    top300_limit=None,
)


class Strategy:
    def compute_factors(self, df: pd.DataFrame, params: dict) -> dict:
        close = df["收盘价"]
        return {
            "close": close,
            "ma_10": ma(close, 10),
            "ma_30": ma(close, 30),
            "atr_14": atr(df["最高价"], df["最低价"], close, 14),
            "volume_ratio_20": volume_ratio(df["成交量（股）"], 20),
            "highest_close_20": close.rolling(20).max(),
        }

    def entry_score(self, factors: dict, params: dict, weights: dict) -> float:
        score = 0.0
        ew = weights["entry"]
        if factors["ma_10"].iloc[-1] > factors["ma_30"].iloc[-1]:
            score += ew["ma_trend_up"]
        if (factors["atr_14"] / factors["close"]).iloc[-1] > params["atr_min_threshold"]:
            score += ew["volatility_expand"]
        if factors["volume_ratio_20"].iloc[-1] > params["volume_breakout_ratio"]:
            score += ew["volume_confirm"]
        return score

    def should_exit(self, position: dict, factors: dict, params: dict, weights: dict) -> str | None:
        ew = weights["exit"]
        for sig in sorted(ew, key=ew.get, reverse=True):
            if sig == "fixed_stop_loss":
                if check_fixed_stop(position["current_price"], position["entry_price"], params["fixed_stop_pct"]):
                    return "fixed_stop_loss"
            elif sig == "trailing_stop":
                highest_close = factors["highest_close_20"].iloc[-1]
                if check_trailing_stop(position["current_price"], highest_close, params["trailing_stop_pct"]):
                    return "trailing_stop"
            elif sig == "time_stop":
                if check_time_stop(position["holding_days"], params["max_holding_days"]):
                    return "time_stop"
        return None

    def get_triggered_signals(self, factors: dict, params: dict, weights: dict) -> list[str]:
        triggered = []
        if factors["ma_10"].iloc[-1] > factors["ma_30"].iloc[-1]:
            triggered.append("ma_trend_up")
        if (factors["atr_14"] / factors["close"]).iloc[-1] > params["atr_min_threshold"]:
            triggered.append("volatility_expand")
        if factors["volume_ratio_20"].iloc[-1] > params["volume_breakout_ratio"]:
            triggered.append("volume_confirm")
        return triggered


if __name__ == "__main__":
    import argparse, re, threading
    from watchdog.events import FileSystemEvent, FileSystemEventHandler
    from watchdog.observers import Observer

    os.chdir(_HERE.parents[1])

    parser = argparse.ArgumentParser(prog="strategy.py", description="trend_atr_volume_strategy_1 backtest entry")
    parser.add_argument("mode", nargs="?", default="params", choices=["params", "weight", "top300"])
    parser.add_argument("--monitor", action="store_true")
    parser.add_argument("--weight-test", default=None)
    parser.add_argument("--start-date", default=None)
    parser.add_argument("--end-date", default=None)
    parser.add_argument("--capital", type=float, default=1_000_000)
    parser.add_argument("--output", default=None)
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--max-retries", type=int, default=3)
    parser.add_argument("--test-universe", default=None)
    parser.add_argument("--max-stocks", type=int, default=None)
    args = parser.parse_args()

    def run_once() -> int:
        eff_test_universe = CONFIG.test_universe if CONFIG.test_universe is not None else args.test_universe
        eff_start_date = CONFIG.start_date if CONFIG.start_date is not None else args.start_date
        eff_end_date = CONFIG.end_date if CONFIG.end_date is not None else args.end_date
        eff_limit = CONFIG.limit if CONFIG.limit is not None else args.max_stocks
        eff_weight_test = args.weight_test if args.weight_test else "trend_atr_volume_strategy_1"
        if eff_test_universe is not None or eff_limit is not None or CONFIG.start_date is not None or CONFIG.end_date is not None or args.weight_test:
            print(f"[CONFIG] test_universe={eff_test_universe} start={eff_start_date} end={eff_end_date} limit={eff_limit} weight_test={eff_weight_test}")
        from subject.cli.main import main
        cli_args = ["run", "--strategy", "trend_atr_volume_strategy_1", "--mode", args.mode, "--weight-test", eff_weight_test]
        if eff_test_universe is not None:
            # args.test_universe is comma-separated string; CLI expects same format
            cli_args += ["--test-universe", str(eff_test_universe)]
        if eff_limit is not None:
            cli_args += ["--max-stocks", str(eff_limit)]
        if eff_start_date:
            cli_args += ["--start-date", eff_start_date]
        if eff_end_date:
            cli_args += ["--end-date", eff_end_date]
        if args.capital != 1_000_000:
            cli_args += ["--capital", str(args.capital)]
        if args.output:
            cli_args += ["--output", args.output]
        return main(cli_args)

    def run_top300() -> int:
        from subject.cli.top300 import run_top300_optimize
        eff_start_date = CONFIG.top300_start_date if CONFIG.top300_start_date is not None else args.start_date
        eff_end_date = CONFIG.top300_end_date if CONFIG.top300_end_date is not None else args.end_date
        eff_limit = CONFIG.top300_limit
        result = run_top300_optimize(name="trend_atr_volume_strategy_1", rounds=args.rounds, max_retries=args.max_retries, start_date=eff_start_date, end_date=eff_end_date, limit=eff_limit)
        if result is None:
            print("[ERROR] Top300 failed")
            return 1
        print(f"[OK] Top300 test set written: test_universe/top300.md")
        print(f"      Best round: {result.best_round}, avg annual return: {result.best_avg_return:+.2%}")
        return 0

    if not args.monitor:
        if args.mode == "top300":
            sys.exit(run_top300())
        sys.exit(run_once())

    if args.mode == "params":
        watch_dir = _HERE.parents[1] / "strategiesParam"
        watch_pattern = re.compile(r".+_v\d+\.md$")
    elif args.mode == "weight":
        watch_dir = _HERE.parents[1] / "strategiesWeight"
        watch_pattern = re.compile(r".+_weight_v\d+\.md$")
    else:
        print("ERROR: top300 mode does not support --monitor", file=sys.stderr)
        sys.exit(1)

    if not watch_dir.exists():
        print(f"ERROR: monitor mode requires {watch_dir}/ directory, not found", file=sys.stderr)
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

    observer = Observer()
    observer.schedule(_WatchHandler(), str(watch_dir.resolve()), recursive=False)
    observer.start()

    import signal as _signal
    def _handle_sigint(s, f):
        stop_event.set()
    try:
        _signal.signal(_signal.SIGINT, _handle_sigint)
    except (ValueError, OSError):
        pass

    DEBOUNCE_SECONDS = 5.0
    print(f"[monitor] watching: {watch_dir.resolve()}/")
    print(f"[monitor] pattern:  {watch_pattern.pattern}")
    print(f"[monitor] debounce: {DEBOUNCE_SECONDS}s, Ctrl+C to exit")

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
        observer.join(timeout=2.0)
        print("[monitor] observer stopped")
