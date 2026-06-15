# debug_mode: params / monitor
# strategy: donchian_adx_volume_entry_1
# version: v1 (baseline)
# purpose: LLM translated from _original.md
# date: 2026-06-12
# mode: params (default) | weight
# run:   single (default) | --monitor
# --- monitor watch directory ---
#   params mode -> strategiesParam/  new *_v<n>.md triggers
#   weight mode -> strategiesWeight/ new *_weight_v<n>.md triggers
#   debounce 5s, Ctrl+C exit
# --- monitor cwd requirement ---
#   monitor mode: watch_dir uses absolute path
# --- CONFIG highest priority ---
#   test_universe / start_date / end_date / limit
# command: python generated/strategy.py
# command: python generated/strategy.py params
# command: python generated/strategy.py weight
# command: python generated/strategy.py --monitor
# command: python generated/strategy.py weight --monitor
# command: python generated/strategy.py weight --weight-test donchian_adx_volume_entry_1

"""donchian_adx_volume_entry_1 strategy. LLM translated from _original.md.

3 methods:
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

# sys.path setup for direct execution
_HERE = Path(__file__).resolve()
_SUBJECTS_DIR = _HERE.parents[2]  # subjects/<strategy>/generated/strategy.py -> parents[2] = subjects/
if str(_SUBJECTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SUBJECTS_DIR))

from subject.factors import (  # noqa: E402
    ma,
    donchian_high,
    donchian_low,
    volume_ratio,
)
from subject.conditions import (  # noqa: E402
    check_fixed_stop,
    check_trailing_stop,
    check_time_stop,
)

# ================================================================
# ADX (Average Directional Index) -- not in public library, manual implementation
# ================================================================
def _adx(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    """14-day Average Directional Index (ADX). Measures trend strength.

    Steps:
    1. True Range (TR) = max(high-low, |high-prev_close|, |low-prev_close|)
    2. Directional Movement: +DM / -DM
    3. Smooth +DM/-DM/TR (EMA, period times)
    4. +DI = +DMs / TRs * 100; -DI = -DMs / TRs * 100
    5. DX = |+DI - -DI| / (+DI + -DI) * 100
    6. ADX = EMA(DX, period)
    """
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    up_move = high.diff()
    down_move = -low.diff()

    plus_dm = pd.Series(0.0, index=high.index)
    minus_dm = pd.Series(0.0, index=high.index)
    plus_dm[(up_move > down_move) & (up_move > 0)] = up_move
    minus_dm[(down_move > up_move) & (down_move > 0)] = down_move

    # Wilders EMA (alpha = 1/period)
    alpha = 1.0 / period
    smooth_plus_dm = plus_dm.ewm(alpha=alpha, adjust=False).mean()
    smooth_minus_dm = minus_dm.ewm(alpha=alpha, adjust=False).mean()
    smooth_tr = tr.ewm(alpha=alpha, adjust=False).mean()

    plus_di = smooth_plus_dm / smooth_tr * 100
    minus_di = smooth_minus_dm / smooth_tr * 100

    dx = (plus_di - minus_di).abs() / (plus_di + minus_di) * 100
    adx = dx.ewm(alpha=alpha, adjust=False).mean()
    return adx

# ================================================================
# Strategy execution config (highest priority)
# ================================================================
@dataclass
class StrategyConfig:
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
            # data columns (referenced directly in triggers)
            "close": df["收盘价"],
            "high": df["最高价"],
            "low": df["最低价"],
            "volume": df["成交量（股）"],
            # spec factors
            "hh_20": donchian_high(df["最高价"], 20),
            "ll_10": donchian_low(df["最低价"], 10),
            "adx_14": _adx(df["最高价"], df["最低价"], df["收盘价"], 14),
            "ma_20": ma(df["收盘价"], 20),
            "ma_60": ma(df["收盘价"], 60),
            "volume_ratio_20": volume_ratio(df["成交量（股）"], 20),
        }

    def entry_score(self, factors: dict, params: dict, weights: dict) -> float:
        score = 0.0
        ew = weights["entry"]
        close = factors["close"].iloc[-1]
        threshold = params["entry_score_threshold"]

        # breakout: close > hh_20
        if close > factors["hh_20"].iloc[-1]:
            score += ew["breakout"]
        # trend_confirm: adx_14 > adx_threshold AND ma_20 > ma_60
        adx_ok = factors["adx_14"].iloc[-1] > params["adx_threshold"]
        ma_ok = factors["ma_20"].iloc[-1] > factors["ma_60"].iloc[-1]
        if adx_ok and ma_ok:
            score += ew["trend_confirm"]
        # volume_confirm: volume_ratio_20 > volume_threshold
        if factors["volume_ratio_20"].iloc[-1] > params["volume_threshold"]:
            score += ew["volume_confirm"]

        if score < threshold:
            return 0.0
        return score

    def should_exit(self, position: dict, factors: dict, params: dict, weights: dict) -> str | None:
        ew = weights["exit"]
        for sig in sorted(ew, key=ew.get, reverse=True):
            if sig == "fixed_stop":
                if check_fixed_stop(
                    position["current_price"],
                    position["entry_price"],
                    params["fixed_stop_pct"],
                ):
                    return "fixed_stop"
            elif sig == "trailing_stop":
                if check_trailing_stop(
                    position["current_price"],
                    position["highest"],
                    params["trailing_stop_pct"],
                ):
                    return "trailing_stop"
            elif sig == "trend_reversal":
                if factors["close"].iloc[-1] < factors["ll_10"].iloc[-1]:
                    return "trend_reversal"
            elif sig == "time_stop":
                if check_time_stop(position["holding_days"], params["max_holding_days"]):
                    return "time_stop"
        return None

    def get_triggered_signals(self, factors: dict, params: dict, weights: dict) -> list:
        triggered = []
        close = factors["close"].iloc[-1]
        if close > factors["hh_20"].iloc[-1]:
            triggered.append("breakout")
        adx_ok = factors["adx_14"].iloc[-1] > params["adx_threshold"]
        ma_ok = factors["ma_20"].iloc[-1] > factors["ma_60"].iloc[-1]
        if adx_ok and ma_ok:
            triggered.append("trend_confirm")
        if factors["volume_ratio_20"].iloc[-1] > params["volume_threshold"]:
            triggered.append("volume_confirm")
        return triggered


# ====================================================================
# Backtest entry point
# ====================================================================
if __name__ == "__main__":
    import argparse
    import re
    import threading
    import time

    from watchdog.events import FileSystemEvent, FileSystemEventHandler
    from watchdog.observers import Observer

    os.chdir(_HERE.parents[1])

    parser = argparse.ArgumentParser(
        prog="strategy.py",
        description="donchian_adx_volume_entry_1 strategy backtest entry",
    )
    parser.add_argument("mode", nargs="?", default="params", choices=["params", "weight"])
    parser.add_argument("--monitor", action="store_true")
    parser.add_argument("--weight-test", default=None)
    parser.add_argument("--start-date", default=None)
    parser.add_argument("--end-date", default=None)
    parser.add_argument("--capital", type=float, default=300_000)
    parser.add_argument("--output", default=None)
    parser.add_argument("--test-universe", default=None, help="comma-separated stock codes (e.g. 000001.SZ,600000.SH)")
    parser.add_argument("--max-stocks", type=int, default=None, help="limit number of stocks to test")
    parser.add_argument("--rounds", type=int, default=3, help="top300 mode: rounds (default 3)")
    parser.add_argument("--max-retries", type=int, default=3, help="top300 mode: max retries (default 3)")
    args = parser.parse_args()

    def run_once() -> int:
        # CLI args override CONFIG (CONFIG has highest priority when non-None)
        eff_test_universe = CONFIG.test_universe if CONFIG.test_universe is not None else args.test_universe
        if eff_test_universe is not None and isinstance(eff_test_universe, str):
            eff_test_universe = [x.strip() for x in eff_test_universe.split(",") if x.strip()]
        eff_start_date = CONFIG.start_date if CONFIG.start_date is not None else args.start_date
        eff_end_date = CONFIG.end_date if CONFIG.end_date is not None else args.end_date
        eff_limit = CONFIG.limit if CONFIG.limit is not None else args.max_stocks
        eff_weight_test = args.weight_test if args.weight_test else "donchian_adx_volume_entry_1"

        if eff_test_universe is not None or eff_limit is not None or CONFIG.start_date is not None or CONFIG.end_date is not None or args.weight_test:
            print(f"[CONFIG] test_universe={eff_test_universe} start={eff_start_date} end={eff_end_date} limit={eff_limit} weight_test={eff_weight_test}")

        from subject.cli.main import main
        cli_args = ["run", "--strategy", "donchian_adx_volume_entry_1", "--mode", args.mode]
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

    def run_top300() -> int:
        from subject.cli.top300 import run_top300_optimize
        eff_start_date = CONFIG.start_date if CONFIG.start_date is not None else args.start_date
        eff_end_date = CONFIG.end_date if CONFIG.end_date is not None else args.end_date
        eff_limit = CONFIG.limit if CONFIG.limit is not None else args.max_stocks
        result = run_top300_optimize(
            name="donchian_adx_volume_entry_1",
            rounds=args.rounds,
            max_retries=args.max_retries,
            start_date=eff_start_date,
            end_date=eff_end_date,
            limit=eff_limit,
        )
        if result is None:
            print("[ERROR] Top300 screening failed")
            return 1
        print(f"[OK] Top300 test set written: test_universe/top300.md")
        print(f"      Best round: Round {result.best_round}, avg annual return: {result.best_avg_return:+.2%}")
        return 0

    if not args.monitor:
        if args.mode == "top300":
            sys.exit(run_top300())
        sys.exit(run_once())

    if args.mode == "params":
        watch_dir = _HERE.parents[1] / "strategiesParam"
        watch_pattern = re.compile(r".+_v\d+\.md$")
    else:
        watch_dir = _HERE.parents[1] / "strategiesWeight"
        watch_pattern = re.compile(r".+_weight_v\d+\.md$")

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
    print(f"[monitor] debounce: {DEBOUNCE_SECONDS}s, Ctrl+C exit")

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
