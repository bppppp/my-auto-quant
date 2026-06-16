# debug_mode: params / single
# strategy: trend_breakout_volume_filter_1
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
# command: python generated/strategy.py weight --weight-test trend_breakout_volume_filter_1

"""trend_breakout_volume_filter_1 策略. 由 LLM 从 _original.md 翻译.

按 subject_structure.md §4.6 模式手写. 包含 3 个方法:
- compute_factors(df, params) -> {factor_name: Series}
- entry_score(factors, params, weights) -> float
- should_exit(position, factors, params, weights) -> signal_name | None

策略简介: 趋势突破+量能过滤中周期波段策略.
入场 = 多均线多头 + RSI 非超买 + 突破 Donchian 上轨 + ATR/close 波动率过滤
      + 成交量放大 (> volume_breakout_ratio 倍).
出场 = 固定止损 (0.35) / 移动止损 (0.30) / 目标止盈 (0.25) / 时间止损 (0.10),
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
_SUBJECTS_DIR = _HERE.parents[2]  # subjects/<strategy>/generated/strategy.py → parents[2] = subjects/
if str(_SUBJECTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SUBJECTS_DIR))

from subject.factors import (  # noqa: E402 — 只 import 实际用到的
    ma,
    atr,
    rsi,
    donchian_high,
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
        test_universe: 自定义测试股票代码列表 (带后缀, 如 ``["000001.SZ", "600000.SH"]``).
            None = 不覆盖, runner 用 spec.test_universe.
        start_date: 测试起始日期 ``"YYYY-MM-DD"`` (含). None = 不限.
        end_date: 测试结束日期 ``"YYYY-MM-DD"`` (含). None = 不限.
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
        """
        close = df["收盘价"]
        high = df["最高价"]
        low = df["最低价"]
        volume = df["成交量（股）"]

        return {
            # === 数据列 (trigger 直接比较用) ===
            "close": close,
            "high": high,
            "low": low,
            "open": df["开盘价"],
            "volume": volume,

            # === spec.factors[] ===
            "ma_short": ma(close, params["ma_short_window"]),
            "ma_mid": ma(close, params["ma_mid_window"]),
            "ma_long": ma(close, params["ma_long_window"]),
            "rsi": rsi(close, params["rsi_period"]),
            "donchian_high": donchian_high(high, params["donchian_window"]),
            "atr": atr(high, low, close, params["atr_period"]),
            "volume_ratio": volume_ratio(volume, params["volume_window"]),

            # === highest_close_since_entry ===
            # spec 列入 factors, 但语义是 position state 字段 → 不在 factors dict 中计算.
            # 应在 should_exit 中通过 position["highest"] 访问 (§4.5 强制规则).
        }

    def entry_score(self, factors: dict, params: dict, weights: dict) -> float:
        """入场评分: Σ(触发信号的 weight).

        Entry signals (from spec):
        - trend_breakout (0.6):
            ma_short > ma_mid AND ma_mid > ma_long
            AND rsi > rsi_entry_threshold AND rsi < rsi_overbought
            AND close > donchian_high
            AND atr / close > atr_min_threshold
        - volume_confirm (0.4):
            volume_ratio > volume_breakout_ratio

        两个信号独立判断, 各自加分; 总分由 runner 排序取 top N.
        """
        score = 0.0
        ew = weights["entry"]

        # === trend_breakout (AND) ===
        # 多均线多头 + RSI 区间 + Donchian 突破 + 波动率过滤
        ma_bull = (
            (factors["ma_short"] > factors["ma_mid"]) &
            (factors["ma_mid"] > factors["ma_long"])
        ).iloc[-1]
        rsi_in_range = (
            (factors["rsi"] > params["rsi_entry_threshold"]) &
            (factors["rsi"] < params["rsi_overbought"])
        ).iloc[-1]
        close_break = (factors["close"] > factors["donchian_high"]).iloc[-1]
        vol_filter = (
            factors["atr"] / factors["close"] > params["atr_min_threshold"]
        ).iloc[-1]
        if ma_bull and rsi_in_range and close_break and vol_filter:
            score += ew["trend_breakout"]

        # === volume_confirm (单因子) ===
        if (factors["volume_ratio"] > params["volume_breakout_ratio"]).iloc[-1]:
            score += ew["volume_confirm"]

        return score

    def get_triggered_signals(self, factors: dict, params: dict, weights: dict) -> list[str]:
        """返回触发入场的信号名列表 (供 runner 记录事件用).

        此方法的触发条件必须与 entry_score 中的条件保持一致.
        """
        triggered = []

        # trend_breakout
        ma_bull = (
            (factors["ma_short"] > factors["ma_mid"]) &
            (factors["ma_mid"] > factors["ma_long"])
        ).iloc[-1]
        rsi_in_range = (
            (factors["rsi"] > params["rsi_entry_threshold"]) &
            (factors["rsi"] < params["rsi_overbought"])
        ).iloc[-1]
        close_break = (factors["close"] > factors["donchian_high"]).iloc[-1]
        vol_filter = (
            factors["atr"] / factors["close"] > params["atr_min_threshold"]
        ).iloc[-1]
        if ma_bull and rsi_in_range and close_break and vol_filter:
            triggered.append("trend_breakout")

        # volume_confirm
        if (factors["volume_ratio"] > params["volume_breakout_ratio"]).iloc[-1]:
            triggered.append("volume_confirm")

        return triggered

    def should_exit(self, position: dict, factors: dict, params: dict, weights: dict) -> Optional[str]:
        """出场判断: 按 exit_weights 降序遍历, 第一个触发的信号返回.

        Exit signals (from spec):
        - fixed_stop (0.35): current_price < entry_price * (1 - fixed_stop_pct)
        - trailing_stop (0.30): current_price < highest * (1 - trailing_stop_pct)
        - profit_take (0.25): current_price > entry_price * (1 + profit_take_pct)
        - time_stop (0.10): holding_days >= max_holding_days
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
                if check_trailing_stop(
                    position["current_price"],
                    position["highest"],
                    params["trailing_stop_pct"],
                ):
                    return "trailing_stop"
            elif sig == "profit_take":
                # 当前价 > 入场价 × (1 + profit_take_pct) → 触发止盈
                if position["current_price"] > position["entry_price"] * (
                    1 + params["profit_take_pct"]
                ):
                    return "profit_take"
            elif sig == "time_stop":
                if check_time_stop(
                    position["holding_days"],
                    params["max_holding_days"],
                ):
                    return "time_stop"
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
        description="trend_breakout_volume_filter_1 策略回测入口 (策略名隐含在文件路径中)",
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
        # CLI 参数 → 运行时变量 (CONFIG 在文件级别拥有最高优先级, 仅在 CLI 未指定时生效)
        cli_test_universe = [s.strip() for s in args.test_universe.split(",")] if args.test_universe else None
        # CONFIG 覆盖 (最高优先级): CLI 显式传值时不让 CONFIG 覆盖
        eff_test_universe = cli_test_universe if cli_test_universe is not None else CONFIG.test_universe
        eff_start_date = CONFIG.start_date if CONFIG.start_date is not None else args.start_date
        eff_end_date = CONFIG.end_date if CONFIG.end_date is not None else args.end_date
        eff_limit = args.max_stocks if args.max_stocks is not None else CONFIG.limit
        eff_weight_test = args.weight_test if args.weight_test else "trend_breakout_volume_filter_1"

        if eff_test_universe is not None or eff_limit is not None or CONFIG.start_date is not None or CONFIG.end_date is not None or args.weight_test:
            print(f"[CONFIG] test_universe={eff_test_universe} start={eff_start_date} end={eff_end_date} limit={eff_limit} weight_test={eff_weight_test}")

        from subject.cli.main import main
        cli_args = ["run", "--strategy", "trend_breakout_volume_filter_1", "--mode", args.mode]
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
