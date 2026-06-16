# debug_mode: params / single
# strategy: trend_mtm_vol_filter_1
# version: v1 (baseline)
# purpose: 由 LLM 从 _original.md 翻译
# date: 2026-06-15
# mode: params (默认) | weight
# run:   single (默认) | --monitor
# command: python generated/strategy.py
# command: python generated/strategy.py params
# command: python generated/strategy.py weight
# command: python generated/strategy.py --monitor
# command: python generated/strategy.py weight --monitor
# command: python generated/strategy.py weight --weight-test trend_mtm_vol_filter_1

"""trend_mtm_vol_filter_1 策略. 由 LLM 从 _original.md 翻译.

按 subject_structure.md §4.6 模式手写. 包含 3 个方法 + get_triggered_signals:
- compute_factors(df, params) -> {factor_name: Series}
- entry_score(factors, params, weights) -> float
- should_exit(position, factors, params, weights) -> signal_name | None

策略简介: 多因子趋势跟踪与波动率过滤的中周期波段策略.
入场 = 趋势动量 (ma_20>ma_60, return_20d, volume_ratio_20, 0.4)
      + RSI动量 (rsi_14 in [rsi_min, rsi_max], 0.3)
      + 波动率扩张 (atr_14>atr_14_prev, atr_14/close>thr, 0.3).
出场 = 固定止损 (0.4) / 移动止损 (0.3) / 时间止损 (0.2) / 趋势反转 (0.1),
按权重降序检查.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pandas as pd

_HERE = Path(__file__).resolve()
_SUBJECTS_DIR = _HERE.parents[2]  # subjects/<strategy>/generated/strategy.py -> parents[2] = subjects/
if str(_SUBJECTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SUBJECTS_DIR))

from subject.factors import (  # noqa: E402 — 只 import 实际用到的
    ma,
    atr,
    rsi,
    mom,
    volume_ratio,
)
from subject.conditions import (  # noqa: E402 — 只 import 实际用到的
    check_fixed_stop,
    check_trailing_stop,
    check_time_stop,
)


# ====================================================================
# 策略执行配置 (最高优先级, 覆盖 CLI / spec 默认值)
# ====================================================================
@dataclass
class StrategyConfig:
    """策略执行配置. 任何字段非 None 时, 覆盖对应 CLI 参数和 spec 默认值.

    Attributes:
        test_universe: 自定义测试股票代码列表 (带后缀, 如 ["000001.SZ", "600000.SH"]).
            None = 不覆盖, runner 用 spec.test_universe.
        start_date: 测试起始日期 "YYYY-MM-DD" (含). None = 不限.
        end_date: 测试结束日期 "YYYY-MM-DD" (含). None = 不限.
        limit: 限制测试股票数 (取前 N). None = 不限.
    """
    test_universe: Optional[list[str]] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    limit: Optional[int] = None


# === 在这里配置 (None = 不覆盖) ===
CONFIG = StrategyConfig(
    test_universe=None,
    start_date=None,
    end_date=None,
    limit=None,
)


class Strategy:
    def compute_factors(self, df: pd.DataFrame, params: dict) -> dict:
        """计算 spec 中声明的所有因子 + trigger 用到的数据列.

        factor 名字 (dict key) 必须与 spec.factors[i].name 一字不差.
        数据列 (close/high/low/open/volume) 按 §4.2.4 A 类规则加入, 用于 trigger 比较.
        ``highest_since_entry`` 是 position 状态字段 (PARTS_SUMMARY §2.5), 不进 factors.
        """
        close = df["收盘价"]
        high = df["最高价"]
        low = df["最低价"]
        volume = df["成交量（股）"]

        # 先算 atr_14 再 shift, 避免 dict literal 内引用 self
        atr_14_series = atr(high, low, close, 14)

        return {
            # === 数据列 (trigger 直接比较用) ===
            "close": close,
            "high": high,
            "low": low,
            "open": df["开盘价"],
            "volume": volume,

            # === spec.factors[] ===
            "ma_20": ma(close, 20),
            "ma_60": ma(close, 60),
            "atr_14": atr_14_series,
            "rsi_14": rsi(close, 14),
            "volume_ratio_20": volume_ratio(volume, 20),
            "return_20d": mom(close, 20),     # close / close.shift(20) - 1
            "atr_14_prev": atr_14_series.shift(1),
            # highest_since_entry 不算因子, 持仓时由 runner 维护, 在 should_exit 用 position["highest"]
        }

    def entry_score(self, factors: dict, params: dict, weights: dict) -> float:
        """入场评分: Σ(触发信号的 weight).

        Entry signals (from spec):
        - trend_momentum_filter (0.4): ma_20 > ma_60 AND return_20d > min_return_20d
                                       AND volume_ratio_20 > vol_min
        - rsi_filter (0.3):            rsi_14 > rsi_min AND rsi_14 < rsi_max
        - volatility_expansion (0.3):  atr_14 > atr_14_prev AND atr_14/close > atr_min_pct

        三个信号独立评估, 加权得分 = Σ(weight × 触发状态). runner 用 score 排名选 top N,
        spec.params.entry_score_threshold 阈值由 portfolio / runner 层比较.
        """
        score = 0.0
        ew = weights["entry"]

        # === trend_momentum_filter (AND 3 条件) ===
        cond_trend = (
            (factors["ma_20"] > factors["ma_60"])
            & (factors["return_20d"] > params["min_return_20d"])
            & (factors["volume_ratio_20"] > params["vol_min"])
        ).iloc[-1]
        if bool(cond_trend):
            score += ew["trend_momentum_filter"]

        # === rsi_filter (AND 2 条件: rsi_min < rsi_14 < rsi_max) ===
        cond_rsi = (
            (factors["rsi_14"] > params["rsi_min"])
            & (factors["rsi_14"] < params["rsi_max"])
        ).iloc[-1]
        if bool(cond_rsi):
            score += ew["rsi_filter"]

        # === volatility_expansion (AND 2 条件: atr 放大 + atr/close > 阈值) ===
        cond_vol = (
            (factors["atr_14"] > factors["atr_14_prev"])
            & ((factors["atr_14"] / factors["close"]) > params["atr_min_pct"])
        ).iloc[-1]
        if bool(cond_vol):
            score += ew["volatility_expansion"]

        return score

    def get_triggered_signals(self, factors: dict, params: dict, weights: dict) -> list[str]:
        """返回触发入场的信号名列表 (供 runner 记录事件用).

        此方法的触发条件必须与 entry_score 中的条件保持一致.
        """
        triggered = []

        # trend_momentum_filter
        cond_trend = (
            (factors["ma_20"] > factors["ma_60"])
            & (factors["return_20d"] > params["min_return_20d"])
            & (factors["volume_ratio_20"] > params["vol_min"])
        ).iloc[-1]
        if bool(cond_trend):
            triggered.append("trend_momentum_filter")

        # rsi_filter
        cond_rsi = (
            (factors["rsi_14"] > params["rsi_min"])
            & (factors["rsi_14"] < params["rsi_max"])
        ).iloc[-1]
        if bool(cond_rsi):
            triggered.append("rsi_filter")

        # volatility_expansion
        cond_vol = (
            (factors["atr_14"] > factors["atr_14_prev"])
            & ((factors["atr_14"] / factors["close"]) > params["atr_min_pct"])
        ).iloc[-1]
        if bool(cond_vol):
            triggered.append("volatility_expansion")

        return triggered

    def should_exit(self, position: dict, factors: dict, params: dict, weights: dict) -> Optional[str]:
        """出场判断: 按 exit_weights 降序遍历, 第一个触发的信号返回.

        Exit signals (from spec, 优先级 = 权重降序):
        - fixed_stop (0.4):       current_price < entry_price * (1 - fixed_stop_pct)
        - trailing_stop (0.3):    current_price < highest * (1 - trailing_stop_pct)
        - time_stop (0.2):        holding_days >= max_holding_days
        - trend_reverse (0.1):    ma_20 < ma_60 AND rsi_14 < rsi_weakness
        """
        ew = weights["exit"]
        # 按 weight 降序遍历, 优先级高的信号先检查
        for sig in sorted(ew, key=ew.get, reverse=True):
            if sig == "fixed_stop":
                if check_fixed_stop(
                    position["current_price"],
                    position["entry_price"],
                    params["fixed_stop_pct"],
                ):
                    return "fixed_stop"
            elif sig == "trailing_stop":
                # current_price < highest_since_entry * (1 - trailing_stop_pct)
                if check_trailing_stop(
                    position["current_price"],
                    position["highest"],
                    params["trailing_stop_pct"],
                ):
                    return "trailing_stop"
            elif sig == "time_stop":
                if check_time_stop(
                    position["holding_days"],
                    params["max_holding_days"],
                ):
                    return "time_stop"
            elif sig == "trend_reverse":
                # ma_20 < ma_60 AND rsi_14 < rsi_weakness
                cond = (
                    (factors["ma_20"] < factors["ma_60"])
                    & (factors["rsi_14"] < params["rsi_weakness"])
                ).iloc[-1]
                if bool(cond):
                    return "trend_reverse"
        return None


# ====================================================================
# 策略回测执行入口 (与 translate.md 模板一致)
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
        description="trend_mtm_vol_filter_1 策略回测入口 (策略名隐含在文件路径中)",
    )
    parser.add_argument("mode", nargs="?", default="params", choices=["params", "weight"])
    parser.add_argument("--monitor", action="store_true")
    parser.add_argument("--weight-test", default=None)
    parser.add_argument("--start-date", default=None)
    parser.add_argument("--end-date", default=None)
    parser.add_argument("--capital", type=float, default=300_000)
    parser.add_argument("--output", default=None)
    parser.add_argument("--test-universe", default=None, help="逗号分隔股票代码列表 (如 000001.SZ,600000.SH)")
    parser.add_argument("--max-stocks", type=int, default=None, help="限制测试股票数 (test_universe 取前 N)")
    args = parser.parse_args()

    def run_once() -> int:
        # CLI 参数 -> 运行时变量 (CONFIG 在文件级别拥有最高优先级, 仅在 CLI 未指定时生效)
        cli_test_universe = [s.strip() for s in args.test_universe.split(",")] if args.test_universe else None
        # CONFIG 覆盖 (最高优先级): CLI 显式传值时不让 CONFIG 覆盖
        eff_test_universe = cli_test_universe if cli_test_universe is not None else CONFIG.test_universe
        eff_start_date = CONFIG.start_date if CONFIG.start_date is not None else args.start_date
        eff_end_date = CONFIG.end_date if CONFIG.end_date is not None else args.end_date
        eff_limit = args.max_stocks if args.max_stocks is not None else CONFIG.limit
        eff_weight_test = args.weight_test if args.weight_test else "trend_mtm_vol_filter_1"

        if eff_test_universe is not None or eff_limit is not None or CONFIG.start_date is not None or CONFIG.end_date is not None or args.weight_test:
            print(f"[CONFIG] test_universe={eff_test_universe} start={eff_start_date} end={eff_end_date} limit={eff_limit} weight_test={eff_weight_test}")

        from subject.cli.main import main
        cli_args = ["run", "--strategy", "trend_mtm_vol_filter_1", "--mode", args.mode]
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

    # === single 模式: 跑一次退出 ===
    if not args.monitor:
        sys.exit(run_once())

    # === --monitor 模式: watchdog 监听目录 ===
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
