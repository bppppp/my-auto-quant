# debug_mode: params / monitor
# strategy: trend_momentum_strategy_1
# version: v1 (baseline)
# purpose: 由 LLM 从 _original.md 翻译
# date: 2026-06-13
# mode: params (默认) | weight
# run:   single (默认) | --monitor
# --- monitor 监听目录 ---
#   params 模式 → strategiesParam/  下新增 *_v<n>.md          文件触发
#   weight 模式 → strategiesWeight/ 下新增 *_weight_v<n>.md  文件触发
#   debounce 5s, Ctrl+C 退出
# --- CONFIG 最高优先级 (覆盖 CLI / spec) ---
#   test_universe / start_date / end_date / limit
# command: python generated/strategy.py
# command: python generated/strategy.py params
# command: python generated/strategy.py weight
# command: python generated/strategy.py --monitor
# command: python generated/strategy.py weight --monitor
# command: python generated/strategy.py weight --weight-test trend_momentum_strategy_1
# command: python generated/strategy.py --start-date 2024-01-01 --end-date 2024-12-31

"""trend_momentum_strategy_1 策略. 由 LLM 从 _original.md 翻译.

按 subject_structure.md §4.6 模式手写. 包含 3 个方法:
- compute_factors(df, params) -> {factor_name: Series}
- entry_score(factors, params, weights) -> float
- should_exit(position, factors, params, weights) -> signal_name | None

权重从 weights 参数读 (不硬编码, 见 §4.9).
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

# 注意: 这里 *不* 调用 subject.factors 里的 ma/atr/rsi/volume_ratio 等公共函数,
# 而是直接用 pandas 实现. 原因: subject.factors._cache 里的预计算 cache 当前
# 会返回错位的数据 (取的是缓存的 *最后* length 行, 不是从起点到当前 bar 的切片),
# 导致 strategy.entry_score 看到的因子值退化为常数, 策略永远不触发交易.
# 绕过 cache 直接算因子, 牺牲少量性能换正确性. 公共 condition 原语 (check_*) 仍可调用.
from subject.conditions import (  # noqa: E402
    check_fixed_stop, check_trailing_stop, check_time_stop, check_rsi_above,
)


def _atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    """标准 ATR (Average True Range). 14 日."""
    prev_close = close.shift(1)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.rolling(window=period, min_periods=period).mean()


def _rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """标准 RSI (Relative Strength Index). 14 日."""
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    avg_gain = gain.rolling(window=period, min_periods=period).mean()
    avg_loss = loss.rolling(window=period, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0.0, pd.NA)
    return 100.0 - 100.0 / (1.0 + rs)


@dataclass
class StrategyConfig:
    test_universe: Optional[list[str]] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    limit: Optional[int] = None


CONFIG = StrategyConfig(
    test_universe=None,
    start_date="2016-01-01",
    end_date="2026-01-01",
    limit=None,
)


def _ema(series, span):
    return series.ewm(span=span, adjust=False).mean()


class Strategy:
    def compute_factors(self, df, params):
        # === 优先使用预计算因子 (data-by-stock-factor-bs) ===
        try:
            from subject.factors._cache import _factor_cache, _current_code, _current_date
            import pandas as _pd
            code = _current_code.get()
            date = _current_date.get()
            cached = _factor_cache.get(code)
            if cached is not None and code and date is not None:
                mask = cached["日期"] <= date
                if mask.any():
                    sub = cached[mask]
                    close_s = sub["close"].astype(float)
                    ema12 = close_s.ewm(span=12, adjust=False).mean()
                    ema26 = close_s.ewm(span=26, adjust=False).mean()
                    macd_l = ema12 - ema26
                    macd_s = macd_l.ewm(span=9, adjust=False).mean()
                    return {
                        "ma_5": sub["ma_5"].astype(float),
                        "ma_20": sub["ma_20"].astype(float),
                        "ma_60": sub["ma_60"].astype(float),
                        "atr_14": sub["atr_14"].astype(float),
                        "rsi_14": sub["rsi_14"].astype(float),
                        "macd_line": macd_l,
                        "macd_signal": macd_s,
                        "volume_ratio_20": sub["volume_ratio_20"].astype(float),
                        "close": close_s,
                    }
        except Exception:
            pass

        # === fallback: 实时计算 ===
        close = df["收盘价"]
        high = df["最高价"]
        low = df["最低价"]
        volume = df["成交量（股）"]
        ema_12 = _ema(close, 12)
        ema_26 = _ema(close, 26)
        macd_line = ema_12 - ema_26
        macd_signal = _ema(macd_line, 9)
        vol_ma_20 = volume.rolling(window=20, min_periods=20).mean()
        return {
            "ma_5": close.rolling(window=5, min_periods=5).mean(),
            "ma_20": close.rolling(window=20, min_periods=20).mean(),
            "ma_60": close.rolling(window=60, min_periods=60).mean(),
            "atr_14": _atr(high, low, close, 14),
            "rsi_14": _rsi(close, 14),
            "macd_line": macd_line,
            "macd_signal": macd_signal,
            "volume_ratio_20": volume / vol_ma_20,
            "close": close,
        }

    def entry_score(self, factors, params, weights):
        score = 0.0
        ew = weights["entry"]
        if (
            factors["ma_5"].iloc[-1] > factors["ma_20"].iloc[-1]
            and factors["ma_20"].iloc[-1] > factors["ma_60"].iloc[-1]
            and factors["macd_line"].iloc[-1] > factors["macd_signal"].iloc[-1]
            and factors["rsi_14"].iloc[-1] > params["rsi_low"]
            and factors["rsi_14"].iloc[-1] < params["rsi_high"]
            and factors["atr_14"].iloc[-1] / factors["close"].iloc[-1] > params["atr_min"]
            and factors["volume_ratio_20"].iloc[-1] > params["vol_min"]
        ):
            score += ew["trend_momentum_entry"]
        return score

    def get_triggered_signals(self, factors, params, weights):
        triggered = []
        if (
            factors["ma_5"].iloc[-1] > factors["ma_20"].iloc[-1]
            and factors["ma_20"].iloc[-1] > factors["ma_60"].iloc[-1]
            and factors["macd_line"].iloc[-1] > factors["macd_signal"].iloc[-1]
            and factors["rsi_14"].iloc[-1] > params["rsi_low"]
            and factors["rsi_14"].iloc[-1] < params["rsi_high"]
            and factors["atr_14"].iloc[-1] / factors["close"].iloc[-1] > params["atr_min"]
            and factors["volume_ratio_20"].iloc[-1] > params["vol_min"]
        ):
            triggered.append("trend_momentum_entry")
        return triggered

    def should_exit(self, position, factors, params, weights):
        ew = weights["exit"]
        for sig in sorted(ew, key=ew.get, reverse=True):
            if sig == "trend_reversal":
                if factors["ma_5"].iloc[-1] < factors["ma_20"].iloc[-1]:
                    return "trend_reversal"
            elif sig == "fixed_stop":
                if check_fixed_stop(
                    position["current_price"], position["entry_price"],
                    params["fixed_stop_pct"],
                ):
                    return "fixed_stop"
            elif sig == "trailing_stop":
                if check_trailing_stop(
                    position["current_price"], position["highest"],
                    params["trailing_stop_pct"],
                ):
                    return "trailing_stop"
            elif sig == "time_stop":
                if check_time_stop(position["holding_days"], params["max_holding_days"]):
                    return "time_stop"
            elif sig == "rsi_overbought_stop":
                if check_rsi_above(
                    factors["rsi_14"].iloc[-1], params["rsi_overbought"],
                ):
                    return "rsi_overbought_stop"
        return None


if __name__ == "__main__":
    import argparse
    import re
    import threading

    from watchdog.events import FileSystemEvent, FileSystemEventHandler
    from watchdog.observers import Observer

    os.chdir(_HERE.parents[2])

    parser = argparse.ArgumentParser(
        prog="strategy.py",
        description="trend_momentum_strategy_1 策略回测入口",
    )
    parser.add_argument("mode", nargs="?", default="params", choices=["params", "weight"])
    parser.add_argument("--monitor", action="store_true")
    parser.add_argument("--weight-test", default=None)
    parser.add_argument("--start-date", default=None)
    parser.add_argument("--end-date", default=None)
    parser.add_argument("--test-universe", default=None, help="逗号分隔股票代码, e.g. 000001.SZ,000002.SZ")
    parser.add_argument("--max-stocks", type=int, default=None, help="限制测试股票数")
    parser.add_argument("--capital", type=float, default=1_000_000)
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    def run_once():
        eff_test_universe = CONFIG.test_universe
        eff_start_date = CONFIG.start_date if CONFIG.start_date is not None else args.start_date
        eff_end_date = CONFIG.end_date if CONFIG.end_date is not None else args.end_date
        eff_limit = CONFIG.limit
        eff_weight_test = args.weight_test if args.weight_test else "trend_momentum_strategy_1"

        # CLI 参数 --test-universe / --max-stocks 覆盖 (用于 smoke test 等场景)
        if args.test_universe is not None:
            eff_test_universe = args.test_universe.split(",")
        if args.max_stocks is not None:
            eff_limit = args.max_stocks

        if eff_test_universe is not None or eff_limit is not None or CONFIG.start_date is not None or CONFIG.end_date is not None or args.weight_test:
            print(f"[CONFIG] test_universe={eff_test_universe} start={eff_start_date} end={eff_end_date} limit={eff_limit} weight_test={eff_weight_test}")

        from subject.cli.main import main
        cli_args = ["run", "--strategy", "trend_momentum_strategy_1", "--mode", args.mode]
        cli_args += ["--weight-test", eff_weight_test]
        if eff_test_universe is not None:
            cli_args += ["--test-universe", ",".join(eff_test_universe)]
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
        def _maybe_fire(self, path_str):
            if not path_str.endswith(".md"):
                return
            if watch_pattern.match(Path(path_str).name):
                trigger_event.set()

        def on_created(self, event):
            if not event.is_directory:
                self._maybe_fire(event.src_path)

        def on_modified(self, event):
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
