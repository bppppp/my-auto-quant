# debug_mode: params / single
# strategy: trend_vol_rsi_mtf_1
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
# command: python generated/strategy.py weight --weight-test trend_vol_rsi_mtf_1

"""trend_vol_rsi_mtf_1 策略. 由 LLM 从 _original.md 翻译.

按 subject_structure.md §4.6 模式手写. 包含 3 个方法:
- compute_factors(df, params) -> {factor_name: Series}
- entry_score(factors, params, weights) -> float
- should_exit(position, factors, params, weights) -> signal_name | None

策略简介: 双均线趋势识别 + 成交量放大确认 + RSI动量过滤,
配合三层止损与止盈的中周期波段策略.
入场 = 趋势 (ma_10>ma_30, 0.5) + 量能 (volume_ratio_20>threshold, 0.25)
      + 动量 (rsi_14>threshold, 0.25), 各自加分.
出场 = 固定止损 (0.30) / ATR动态止损 (0.20) / 移动止损 (0.20)
      / 止盈 (0.20) / 时间止损 (0.05) / 趋势反转 (0.05),
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
    volume_ratio,
)
from subject.conditions import (  # noqa: E402 — 只 import 实际用到的
    check_fixed_stop,
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
            "ma_10": ma(close, 10),
            "ma_30": ma(close, 30),
            "atr_14": atr(high, low, close, 14),
            "volume_ratio_20": volume_ratio(volume, 20),
            "rsi_14": rsi(close, 14),
            # max_close_20: 20日最高收盘价 (rolling max of close, spec 计算是 max(close, 20))
            "max_close_20": close.rolling(20).max(),
        }

    def entry_score(self, factors: dict, params: dict, weights: dict) -> float:
        """入场评分: Σ(触发信号的 weight).

        Entry signals (from spec):
        - trend_up (0.5):       ma_10 > ma_30
        - volume_surge (0.25):  volume_ratio_20 > {volume_threshold}
        - rsi_strength (0.25):  rsi_14 > {rsi_threshold}

        spec narrative §3: "总分达到阈值或排名靠前者入选, 只有在短中期趋势
        向上、成交活跃且非超买区才建仓". 取最强信号 trend_up (0.5) 作为
        入场必要条件, 然后叠加其他两个信号加权 — score >= 0.5 才入场,
        避免单纯靠 1 个次信号 (如 rsi>50 几乎永远成立) 触发 over-trade.
        """
        score = 0.0
        ew = weights["entry"]

        # === trend_up (单因子: ma_10 > ma_30) — 必要条件 ===
        if (factors["ma_10"] > factors["ma_30"]).iloc[-1]:
            score += ew["trend_up"]

        # === volume_surge (单因子: volume_ratio_20 > volume_threshold) ===
        if (factors["volume_ratio_20"] > params["volume_threshold"]).iloc[-1]:
            score += ew["volume_surge"]

        # === rsi_strength (单因子: rsi_14 > rsi_threshold) ===
        if (factors["rsi_14"] > params["rsi_threshold"]).iloc[-1]:
            score += ew["rsi_strength"]

        # 至少 trend_up 必须触发 (score >= 0.5), 否则不入场
        if score < 0.5:
            return 0.0
        return score

    def get_triggered_signals(self, factors: dict, params: dict, weights: dict) -> list[str]:
        """返回触发入场的信号名列表 (供 runner 记录事件用).

        此方法的触发条件必须与 entry_score 中的条件保持一致.
        """
        triggered = []

        # trend_up
        if (factors["ma_10"] > factors["ma_30"]).iloc[-1]:
            triggered.append("trend_up")

        # volume_surge
        if (factors["volume_ratio_20"] > params["volume_threshold"]).iloc[-1]:
            triggered.append("volume_surge")

        # rsi_strength
        if (factors["rsi_14"] > params["rsi_threshold"]).iloc[-1]:
            triggered.append("rsi_strength")

        # 必须 trend_up 触发才入场
        if "trend_up" not in triggered:
            return []
        return triggered

    def should_exit(self, position: dict, factors: dict, params: dict, weights: dict) -> Optional[str]:
        """出场判断: 按 exit_weights 降序遍历, 第一个触发的信号返回.

        Exit signals (from spec):
        - fixed_stop (0.30):        current_price < entry_price * (1 - fixed_stop_pct)
        - atr_trailing_stop (0.20): current_price < entry_price - atr_stop_mult * atr_14
        - trailing_stop (0.20):     current_price < max_close_20 * (1 - trailing_stop_pct)
        - take_profit (0.20):       current_price > entry_price * (1 + profit_target_pct)
        - time_stop (0.05):         holding_days >= max_holding_days
        - trend_reverse (0.05):     ma_10 < ma_30
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
            elif sig == "atr_trailing_stop":
                # current_price < entry_price - atr_stop_mult * atr_14
                if position["current_price"] < position["entry_price"] - \
                        params["atr_stop_mult"] * factors["atr_14"].iloc[-1]:
                    return "atr_trailing_stop"
            elif sig == "trailing_stop":
                # current_price < max_close_20 * (1 - trailing_stop_pct)
                if position["current_price"] < factors["max_close_20"].iloc[-1] * \
                        (1 - params["trailing_stop_pct"]):
                    return "trailing_stop"
            elif sig == "take_profit":
                # current_price > entry_price * (1 + profit_target_pct)
                if position["current_price"] > position["entry_price"] * \
                        (1 + params["profit_target_pct"]):
                    return "take_profit"
            elif sig == "time_stop":
                if check_time_stop(
                    position["holding_days"],
                    params["max_holding_days"],
                ):
                    return "time_stop"
            elif sig == "trend_reverse":
                # ma_10 < ma_30 (短期均线跌破中期均线, 趋势反转)
                if factors["ma_10"].iloc[-1] < factors["ma_30"].iloc[-1]:
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
        description="trend_vol_rsi_mtf_1 策略回测入口 (策略名隐含在文件路径中)",
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
        eff_weight_test = args.weight_test if args.weight_test else "trend_vol_rsi_mtf_1"

        if eff_test_universe is not None or eff_limit is not None or CONFIG.start_date is not None or CONFIG.end_date is not None or args.weight_test:
            print(f"[CONFIG] test_universe={eff_test_universe} start={eff_start_date} end={eff_end_date} limit={eff_limit} weight_test={eff_weight_test}")

        from subject.cli.main import main
        cli_args = ["run", "--strategy", "trend_vol_rsi_mtf_1", "--mode", args.mode]
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
