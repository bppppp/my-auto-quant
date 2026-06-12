# debug_mode: params / monitor / top300
# strategy: donchian_breakout_vol_rsi_ma
# version: v1 (baseline)
# purpose: 由 LLM 从 _original.md 翻译
# date: 2026-06-10
# mode: params (默认) | weight | top300   ← positional, 第一参数
# run:   single (默认) | --monitor   ← single 跑一次退出 / --monitor 监听文件夹触发
# command: python generated/strategy.py
# command: python generated/strategy.py params
# command: python generated/strategy.py weight
# command: python generated/strategy.py top300
# command: python generated/strategy.py top300 --rounds 3 --max-retries 3
# command: python generated/strategy.py --monitor
# command: python generated/strategy.py weight --monitor
# command: python generated/strategy.py weight --weight-test donchian_breakout_vol_rsi_ma

"""donchian_breakout_vol_rsi_ma 策略. 由 LLM 从 _original.md 翻译.

按 subject_structure.md §4.6 模式手写. 包含 3 个方法:
- compute_factors(df, params) -> {factor_name: Series}
- entry_score(factors, params, weights) -> float
- should_exit(position, factors, params, weights) -> signal_name | None

**本文件同时作为策略回测执行入口**: 直接 `python strategy.py` 即跑该策略的
params 模式 (默认), `python strategy.py weight` 跑 weight 模式,
`python strategy.py top300` 跑 Top300 测试集筛选, 加 `--monitor`
进入文件夹监听模式 (params 监听 `strategiesParam/`, weight 监听
`strategiesWeight/`, 新增版本文件触发回测, debounce 5s, Ctrl+C 退出).
顶部 # command 列出全部调用方式.
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
    ma, atr, rsi, volume_ratio, donchian_high, donchian_low,
)
from subject.conditions import (  # noqa: E402
    check_fixed_stop, check_trailing_stop, check_time_stop,
)


# ====================================================================
# 策略执行配置 (最高优先级, 覆盖 CLI / spec 默认值)
# ====================================================================
@dataclass
class StrategyConfig:
    """策略执行配置. 任何字段非 None 时, 覆盖对应 CLI 参数和 spec 默认值.

    **两套配置分离**:
    - params / weight 模式: test_universe / start_date / end_date / limit
    - top300 模式: top300_start_date / top300_end_date / top300_limit (时间范围和 limit 仅在 top300 模式生效)

    Attributes:
        test_universe: 自定义测试股票代码列表 (带后缀, 如 ``["000001.SZ", "600000.SH"]``).
            None = 默认从 test_universe/top300.md 读取(存在时),否则用 HS300.
        start_date: 测试起始日期 ``"YYYY-MM-DD"`` (含). None = 不限.
        end_date: 测试结束日期 ``"YYYY-MM-DD"`` (含). None = 不限.
        limit: 限制测试股票数 (取前 N). None = 不限.

        top300_start_date: top300 模式时间范围起始日期. None = 默认 5 年.
        top300_end_date: top300 模式时间范围结束日期. None = 数据末日.
        top300_limit: top300 模式每轮回测的 limit (None = 不限).
    """
    # === params / weight 模式配置 ===
    test_universe: Optional[list[str]] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    limit: Optional[int] = None

    # === top300 模式配置 (仅 top300 模式生效) ===
    top300_start_date: Optional[str] = None
    top300_end_date: Optional[str] = None
    top300_limit: Optional[int] = None


# === 在这里配置 (None = 不覆盖) ===
CONFIG = StrategyConfig(
    # params / weight 模式
    test_universe=None,  # None 时默认从 test_universe/top300.md 读取(存在时),否则用 HS300
    start_date="2021-01-01",
    end_date="2025-12-31",
    limit=None,
    # top300 模式
    top300_start_date=None,
    top300_end_date=None,
    top300_limit=None,
)


class Strategy:
    def compute_factors(self, df: pd.DataFrame, params: dict) -> dict:
        return {
            "close": df["收盘价"],
            "high": df["最高价"],
            "low": df["最低价"],
            "open": df["开盘价"],
            "volume": df["成交量（股）"],
            "ma_20": ma(df["收盘价"], 20),
            "ma_60": ma(df["收盘价"], 60),
            "rsi_14": rsi(df["收盘价"], 14),
            "atr_14": atr(df["最高价"], df["最低价"], df["收盘价"], 14),
            "volume_ratio_20": volume_ratio(df["成交量（股）"], 20),
            "donchian_high_20": donchian_high(df["最高价"], 20),
            "donchian_low_20": donchian_low(df["最低价"], 20),
        }

    def entry_score(self, factors: dict, params: dict, weights: dict) -> float:
        """入场评分.

        Entry signals (from spec):
        - breakout_entry: close > donchian_high_20 AND volume_ratio_20 > vol_breakout_threshold
        - trend_entry: ma_20 > ma_60 AND close > ma_20
        - rsi_entry: rsi_14 > rsi_entry_low AND rsi_14 < rsi_entry_high
        """
        score = 0.0
        ew = weights["entry"]

        # breakout_entry (AND): close > donchian_high_20 AND volume_ratio_20 > vol_breakout_threshold
        if (factors["close"] > factors["donchian_high_20"]).iloc[-1] and (
            factors["volume_ratio_20"] > params["vol_breakout_threshold"]
        ).iloc[-1]:
            score += ew.get("breakout_entry", 0)

        # trend_entry (AND): ma_20 > ma_60 AND close > ma_20
        if (factors["ma_20"] > factors["ma_60"]).iloc[-1] and (
            factors["close"] > factors["ma_20"]
        ).iloc[-1]:
            score += ew.get("trend_entry", 0)

        # rsi_entry (AND): rsi_14 > rsi_entry_low AND rsi_14 < rsi_entry_high
        if (factors["rsi_14"] > params["rsi_entry_low"]).iloc[-1] and (
            factors["rsi_14"] < params["rsi_entry_high"]
        ).iloc[-1]:
            score += ew.get("rsi_entry", 0)

        return score

    def get_triggered_signals(self, factors: dict, params: dict, weights: dict) -> list[str]:
        """返回触发入场的信号名列表（供 runner 记录事件用）。
        此方法的触发条件必须与 entry_score 中的条件保持一致。
        """
        triggered = []

        # breakout_entry
        if (factors["close"] > factors["donchian_high_20"]).iloc[-1] and (
            factors["volume_ratio_20"] > params["vol_breakout_threshold"]
        ).iloc[-1]:
            triggered.append("breakout_entry")

        # trend_entry
        if (factors["ma_20"] > factors["ma_60"]).iloc[-1] and (
            factors["close"] > factors["ma_20"]
        ).iloc[-1]:
            triggered.append("trend_entry")

        # rsi_entry
        if (factors["rsi_14"] > params["rsi_entry_low"]).iloc[-1] and (
            factors["rsi_14"] < params["rsi_entry_high"]
        ).iloc[-1]:
            triggered.append("rsi_entry")

        return triggered

    def should_exit(self, position: dict, factors: dict, params: dict, weights: dict) -> Optional[str]:
        """出场判断.

        Exit signals (from spec):
        - fixed_stop_loss: current_price < entry_price * (1 - fixed_stop_loss_pct)
        - trailing_stop: current_price < highest_close_since_entry * (1 - trailing_stop_pct)
        - volatility_stop: current_price < highest_close_since_entry - atr_stop_multiplier * atr_14
        - trend_reversal_exit: close < donchian_low_20
        - overbought_reduce: rsi_14 > rsi_overbought AND pnl_pct > partial_profit_pct
        - time_stop: holding_days >= max_holding_days
        """
        ew = weights["exit"]
        # 按 exit_weights 降序遍历，weight 高的信号先检查
        for sig in sorted(ew, key=ew.get, reverse=True):
            if sig == "fixed_stop_loss":
                if check_fixed_stop(position["current_price"], position["entry_price"], params["fixed_stop_loss_pct"]):
                    return "fixed_stop_loss"
            elif sig == "trailing_stop":
                if check_trailing_stop(position["current_price"], position["highest"], params["trail_stop_pct"]):
                    return "trailing_stop"
            elif sig == "volatility_stop":
                # volatility_stop: current_price < highest - atr_stop_multiplier * atr_14
                if position["current_price"] < position["highest"] - params["atr_stop_multiplier"] * factors["atr_14"].iloc[-1]:
                    return "volatility_stop"
            elif sig == "trend_reversal_exit":
                if factors["close"].iloc[-1] < factors["donchian_low_20"].iloc[-1]:
                    return "trend_reversal_exit"
            elif sig == "overbought_reduce":
                # overbought_reduce: rsi_14 > rsi_overbought AND pnl_pct > partial_profit_pct
                if (factors["rsi_14"].iloc[-1] > params["rsi_overbought"]) and (
                    position.get("pnl_pct", 0) > params["partial_profit_pct"]
                ):
                    return "overbought_reduce"
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

    from watchdog.events import FileSystemEvent, FileSystemEventHandler
    from watchdog.observers import Observer

    os.chdir(_HERE.parents[1])  # 切到策略目录, 让 report 相对路径正确

    parser = argparse.ArgumentParser(
        prog="strategy.py",
        description="donchian_breakout_vol_rsi_ma 策略回测入口",
    )
    parser.add_argument("mode", nargs="?", default="params", choices=["params", "weight", "top300"])
    parser.add_argument("--monitor", action="store_true")
    parser.add_argument("--weight-test", default=None)
    parser.add_argument("--start-date", default=None)
    parser.add_argument("--end-date", default=None)
    parser.add_argument("--capital", type=float, default=300_000)
    parser.add_argument("--output", default=None)
    parser.add_argument("--rounds", type=int, default=3, help="top300 模式: 调优轮数 (默认 3)")
    parser.add_argument("--max-retries", type=int, default=3, help="top300 模式: LLM 重试上限 (默认 3)")
    parser.add_argument("--limit", type=int, default=None, help="top300 模式: 每轮回测的 limit (默认不限)")
    args = parser.parse_args()

    def run_once() -> int:
        # CONFIG 覆盖 (最高优先级)
        eff_test_universe = CONFIG.test_universe
        eff_start_date = CONFIG.start_date if CONFIG.start_date is not None else args.start_date
        eff_end_date = CONFIG.end_date if CONFIG.end_date is not None else args.end_date
        eff_limit = CONFIG.limit
        eff_weight_test = args.weight_test if args.weight_test else "donchian_breakout_vol_rsi_ma"

        if eff_test_universe is not None or eff_limit is not None or CONFIG.start_date is not None or CONFIG.end_date is not None or args.weight_test:
            print(f"[CONFIG] test_universe={eff_test_universe} start={eff_start_date} end={eff_end_date} limit={eff_limit} weight_test={eff_weight_test}")

        from subject.cli.main import main
        cli_args = ["run", "--strategy", "donchian_breakout_vol_rsi_ma", "--mode", args.mode]
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
        # CONFIG 覆盖 (最高优先级)
        eff_start_date = CONFIG.top300_start_date if CONFIG.top300_start_date is not None else args.start_date
        eff_end_date = CONFIG.top300_end_date if CONFIG.top300_end_date is not None else args.end_date
        eff_limit = CONFIG.top300_limit if CONFIG.top300_limit is not None else args.limit

        result = run_top300_optimize(
            name="donchian_breakout_vol_rsi_ma",
            rounds=args.rounds,
            max_retries=args.max_retries,
            start_date=eff_start_date,
            end_date=eff_end_date,
            limit=eff_limit,
        )
        if result is None:
            print("[ERROR] Top300 筛选失败")
            return 1
        print(f"[OK] Top300 测试集已写入: test_universe/top300.md")
        print(f"      最优轮: Round {result.best_round}, 平均年化收益率: {result.best_avg_return:+.2%}")
        return 0

    # === single 模式: 跑一次退出 ===
    if not args.monitor:
        if args.mode == "top300":
            sys.exit(run_top300())
        sys.exit(run_once())

    # === --monitor 模式: 不支持 top300 ===
    if args.mode == "top300":
        print("ERROR: top300 模式不支持 --monitor", file=sys.stderr)
        sys.exit(1)

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
