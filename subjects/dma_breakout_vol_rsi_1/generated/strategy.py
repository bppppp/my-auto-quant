# debug_mode: params / single
# strategy: dma_breakout_vol_rsi_1
# version: v1 (baseline)
# purpose: 由 LLM 从 _original.md 翻译
# date: 2026-06-17
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
# command: python generated/strategy.py weight --weight-test dma_breakout_vol_rsi_1

"""dma_breakout_vol_rsi_1 策略. 由 LLM 从 _original.md 翻译.

策略业务逻辑:
- 入场: 5 个 entry signal 全部触发才入场 (AND 关系, 总分=1.0)
  - ma_trend_bull:     ma_5 > ma_20 AND close > ma_20
  - price_breakout:    close > high_20 (20 日最高收盘价)
  - volume_surge:      vol_ratio > {vol_breakout_ratio}
  - rsi_healthy:       {rsi_min} < rsi_14 < {rsi_max}
  - volatility_active: atr_14 / close > {min_atr_ratio}
- 出场优先级 (按 weight 降序): ma_trend_bear -> fixed_stop -> trailing_stop -> time_stop
  - ma_trend_bear:     ma_5 < ma_20
  - fixed_stop:        current_price < entry_price * (1 - {fixed_stop_pct})
  - trailing_stop:     current_price < high_20 * (1 - {trail_stop_pct})
  - time_stop:         holding_days >= {max_hold_days}
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

from subject.factors import ma, atr, rsi, donchian_high, volume_ratio  # noqa: E402
from subject.conditions import (  # noqa: E402
    check_fixed_stop,
    check_time_stop,
    check_rsi_in_range,
    check_volume_ratio_above,
)


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


class Strategy:
    def compute_factors(self, df: pd.DataFrame, params: dict) -> dict:
        """计算 spec 中声明的 factors.

        - ma_5 / ma_20:  简单移动平均
        - high_20:       20 日最高**收盘价** (donchian_high 接 close 而非 high)
        - rsi_14:        14 日 RSI
        - vol_ratio:     20 日量比
        - atr_14:        14 日 ATR
        - close:         trigger 中需要 (e.g. close > high_20)
        """
        return {
            "ma_5": ma(df["收盘价"], 5),
            "ma_20": ma(df["收盘价"], 20),
            "high_20": donchian_high(df["收盘价"], 20),
            "rsi_14": rsi(df["收盘价"], 14),
            "vol_ratio": volume_ratio(df["成交量（股）"], 20),
            "atr_14": atr(df["最高价"], df["最低价"], df["收盘价"], 14),
            # A 类数据列 (trigger 中需要)
            "close": df["收盘价"],
            "high": df["最高价"],
            "low": df["最低价"],
            "open": df["开盘价"],
            "volume": df["成交量（股）"],
        }

    def entry_score(self, factors: dict, params: dict, weights: dict) -> float:
        """入场评分: 5 个 entry signal 全部触发才入场 (narrative 描述总分=1.0).

        - ma_trend_bull (0.30):     ma_5 > ma_20 AND close > ma_20
        - price_breakout (0.25):    close > high_20
        - volume_surge (0.15):      vol_ratio > {vol_breakout_ratio}
        - rsi_healthy (0.15):       rsi_14 in ({rsi_min}, {rsi_max})
        - volatility_active (0.15): atr_14 / close > {min_atr_ratio}

        注: narrative 明确 "总分达到1.0 即全部满足" 才入场. runner 的入场阈值为
        ``score > 0`` (任何正分都入场), 所以这里在 5 个条件未全触发时返回 0,
        避免 "任一条件触发即入场" 的过度交易.
        """
        ew = weights["entry"]

        # 取最近一根 K 线的 scalar
        ma_5_v = factors["ma_5"].iloc[-1]
        ma_20_v = factors["ma_20"].iloc[-1]
        close_v = factors["close"].iloc[-1]
        high_20_v = factors["high_20"].iloc[-1]
        rsi_14_v = factors["rsi_14"].iloc[-1]
        vol_ratio_v = factors["vol_ratio"].iloc[-1]
        atr_14_v = factors["atr_14"].iloc[-1]

        # 5 个 bool 标记 (分别记录各条件是否触发)
        cond_ma = (
            (not pd.isna(ma_5_v))
            and (not pd.isna(ma_20_v))
            and (not pd.isna(close_v))
            and (ma_5_v > ma_20_v)
            and (close_v > ma_20_v)
        )
        cond_breakout = (
            (not pd.isna(close_v)) and (not pd.isna(high_20_v)) and (close_v > high_20_v)
        )
        cond_vol = (not pd.isna(vol_ratio_v)) and check_volume_ratio_above(
            vol_ratio_v, params["vol_breakout_ratio"]
        )
        cond_rsi = (not pd.isna(rsi_14_v)) and check_rsi_in_range(
            rsi_14_v, params["rsi_min"], params["rsi_max"]
        )
        cond_vol_atr = (
            (not pd.isna(atr_14_v))
            and (not pd.isna(close_v))
            and (close_v > 0)
            and (atr_14_v / close_v > params["min_atr_ratio"])
        )

        # 5 个条件必须全部为真才入场 (AND)
        if not (cond_ma and cond_breakout and cond_vol and cond_rsi and cond_vol_atr):
            return 0.0

        return (
            ew["ma_trend_bull"]
            + ew["price_breakout"]
            + ew["volume_surge"]
            + ew["rsi_healthy"]
            + ew["volatility_active"]
        )

    def get_triggered_signals(self, factors: dict, params: dict, weights: dict) -> list[str]:
        """返回当前 bar 触发的 entry signal 名列表, 供 runner 记录事件用.

        注: 5 个条件必须全部满足才视为入场触发 (与 entry_score 完全一致).
        """
        ma_5_v = factors["ma_5"].iloc[-1]
        ma_20_v = factors["ma_20"].iloc[-1]
        close_v = factors["close"].iloc[-1]
        high_20_v = factors["high_20"].iloc[-1]
        rsi_14_v = factors["rsi_14"].iloc[-1]
        vol_ratio_v = factors["vol_ratio"].iloc[-1]
        atr_14_v = factors["atr_14"].iloc[-1]

        cond_ma = (
            (not pd.isna(ma_5_v))
            and (not pd.isna(ma_20_v))
            and (not pd.isna(close_v))
            and (ma_5_v > ma_20_v)
            and (close_v > ma_20_v)
        )
        cond_breakout = (
            (not pd.isna(close_v)) and (not pd.isna(high_20_v)) and (close_v > high_20_v)
        )
        cond_vol = (not pd.isna(vol_ratio_v)) and check_volume_ratio_above(
            vol_ratio_v, params["vol_breakout_ratio"]
        )
        cond_rsi = (not pd.isna(rsi_14_v)) and check_rsi_in_range(
            rsi_14_v, params["rsi_min"], params["rsi_max"]
        )
        cond_vol_atr = (
            (not pd.isna(atr_14_v))
            and (not pd.isna(close_v))
            and (close_v > 0)
            and (atr_14_v / close_v > params["min_atr_ratio"])
        )

        # 5 个条件全部满足才记录 (与 entry_score 同步)
        if not (cond_ma and cond_breakout and cond_vol and cond_rsi and cond_vol_atr):
            return []

        return [
            "ma_trend_bull",
            "price_breakout",
            "volume_surge",
            "rsi_healthy",
            "volatility_active",
        ]

    def should_exit(self, position: dict, factors: dict, params: dict, weights: dict) -> str | None:
        """出场判断: 按 weight 降序遍历, 一旦任一信号触发立即返回其名称.

        Exit signal 列表 (按 spec):
        - ma_trend_bear (0.30):     ma_5 < ma_20
        - fixed_stop (0.25):        current_price < entry_price * (1 - {fixed_stop_pct})
        - trailing_stop (0.25):     current_price < high_20 * (1 - {trail_stop_pct})
        - time_stop (0.20):         holding_days >= {max_hold_days}

        注意: spec 的 trailing_stop 用 high_20 因子 (20 日最高**收盘价**),
        而非 position["highest"] (入场后最高价). 所以手写, 不调 check_trailing_stop.
        """
        ew = weights["exit"]
        current_price = position["current_price"]
        entry_price = position["entry_price"]

        for sig in sorted(ew, key=ew.get, reverse=True):
            if sig == "ma_trend_bear":
                # 均线死叉
                if factors["ma_5"].iloc[-1] < factors["ma_20"].iloc[-1]:
                    return "ma_trend_bear"
            elif sig == "fixed_stop":
                # 固定止损
                if check_fixed_stop(current_price, entry_price, params["fixed_stop_pct"]):
                    return "fixed_stop"
            elif sig == "trailing_stop":
                # 移动止损: 从 20 日最高收盘价回撤 {trail_stop_pct}
                high_20_v = factors["high_20"].iloc[-1]
                if not pd.isna(high_20_v):
                    threshold = high_20_v * (1.0 - params["trail_stop_pct"])
                    if current_price < threshold:
                        return "trailing_stop"
            elif sig == "time_stop":
                # 时间止损
                if check_time_stop(position["holding_days"], params["max_hold_days"]):
                    return "time_stop"
        return None


# ====================================================================
# 策略回测执行入口
# ====================================================================
if __name__ == "__main__":
    import argparse
    import re
    import threading

    from watchdog.events import FileSystemEvent, FileSystemEventHandler
    from watchdog.observers import Observer

    os.chdir(_HERE.parents[1])

    parser = argparse.ArgumentParser(
        prog="strategy.py",
        description="dma_breakout_vol_rsi_1 策略回测入口",
    )
    parser.add_argument("mode", nargs="?", default="params", choices=["params", "weight"])
    parser.add_argument("--monitor", action="store_true")
    parser.add_argument("--weight-test", default=None)
    parser.add_argument("--start-date", default=None)
    parser.add_argument("--end-date", default=None)
    parser.add_argument("--test-universe", default=None)
    parser.add_argument("--max-stocks", type=int, default=None)
    parser.add_argument("--capital", type=float, default=300_000)
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    def run_once() -> int:
        eff_test_universe = CONFIG.test_universe
        if eff_test_universe is None and args.test_universe:
            eff_test_universe = [s.strip() for s in args.test_universe.split(",") if s.strip()]
        eff_start_date = CONFIG.start_date if CONFIG.start_date is not None else args.start_date
        eff_end_date = CONFIG.end_date if CONFIG.end_date is not None else args.end_date
        eff_limit = CONFIG.limit if CONFIG.limit is not None else args.max_stocks
        eff_weight_test = args.weight_test if args.weight_test else "dma_breakout_vol_rsi_1"

        if eff_test_universe is not None or eff_limit is not None or CONFIG.start_date is not None or CONFIG.end_date is not None or args.weight_test:
            print(f"[CONFIG] test_universe={eff_test_universe} start={eff_start_date} end={eff_end_date} limit={eff_limit} weight_test={eff_weight_test}")

        from subject.cli.main import main
        cli_args = ["run", "--strategy", "dma_breakout_vol_rsi_1", "--mode", args.mode]
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
        observer.join(timeout=2.0)
        print("[monitor] observer stopped")
