# debug_mode: params / single
# strategy: ma_rsi_vol_atr_breakout_1
# version: v1 (baseline)
# purpose: 由 LLM 从 _original.md 翻译
# date: 2026-06-16
# mode: params (默认) | weight
# run:   single (默认) | --monitor
# command: python generated/strategy.py
# command: python generated/strategy.py params
# command: python generated/strategy.py weight
# command: python generated/strategy.py --monitor
# command: python generated/strategy.py weight --monitor
# command: python generated/strategy.py weight --weight-test ma_rsi_vol_atr_breakout_1

"""ma_rsi_vol_atr_breakout_1 策略. 由 LLM 从 _original.md 翻译.

策略业务逻辑:
- 入场: 双均线趋势 (ma_10 > ma_30) + RSI 区间 ({rsi_lower}~{rsi_upper}) + 量比放大 (>{volume_breakout})
  两个 entry signal 同时触发才打分 (AND 关系)
- 出场优先级 (按 weight 降序): atr_stop -> trailing_stop -> ma_death_cross -> time_stop
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

from subject.factors import ma, atr, rsi, volume_ratio
from subject.conditions import check_trailing_stop, check_time_stop


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

        注意: highest_close_since_entry 是 position state 字段, 不放入 factors dict
        (由 portfolio 层每根 K 线更新, 通过 position["highest"] 访问).
        """
        ma_10_s = ma(df["收盘价"], 10)
        ma_30_s = ma(df["收盘价"], 30)
        rsi_14_s = rsi(df["收盘价"], 14)
        atr_14_s = atr(df["最高价"], df["最低价"], df["收盘价"], 14)
        vol_ratio_20_s = volume_ratio(df["成交量（股）"], 20)
        return {
            "ma_10": ma_10_s,
            "ma_30": ma_30_s,
            "rsi_14": rsi_14_s,
            "atr_14": atr_14_s,
            "volume_ratio_20": vol_ratio_20_s,
            # A 类数据列 (trigger 中会用到)
            "close": df["收盘价"],
            "high": df["最高价"],
            "low": df["最低价"],
            "open": df["开盘价"],
            "volume": df["成交量（股）"],
        }

    def entry_score(self, factors: dict, params: dict, weights: dict) -> float:
        """入场评分: 两个 entry signal 必须同时满足才打分 (AND 关系).

        - trend_momentum_confirm: ma_10 > ma_30 AND rsi_14 > {rsi_lower} AND rsi_14 < {rsi_upper}
        - volume_breakout: volume_ratio_20 > {volume_breakout}
        """
        score = 0.0
        ew = weights["entry"]

        # 1) trend_momentum_confirm: 趋势 + RSI 动量过滤
        ma_cross_ok = factors["ma_10"].iloc[-1] > factors["ma_30"].iloc[-1]
        rsi_lower_ok = factors["rsi_14"].iloc[-1] > params["rsi_lower"]
        rsi_upper_ok = factors["rsi_14"].iloc[-1] < params["rsi_upper"]
        if ma_cross_ok and rsi_lower_ok and rsi_upper_ok:
            score += ew["trend_momentum_confirm"]

        # 2) volume_breakout: 量比放大
        if factors["volume_ratio_20"].iloc[-1] > params["volume_breakout"]:
            score += ew["volume_breakout"]

        return score

    def get_triggered_signals(self, factors: dict, params: dict, weights: dict) -> list[str]:
        """返回当前 bar 触发的 entry signal 名列表, 供 runner 记录事件用.

        触发条件与 entry_score 完全一致.
        """
        triggered: list[str] = []

        ma_cross_ok = factors["ma_10"].iloc[-1] > factors["ma_30"].iloc[-1]
        rsi_lower_ok = factors["rsi_14"].iloc[-1] > params["rsi_lower"]
        rsi_upper_ok = factors["rsi_14"].iloc[-1] < params["rsi_upper"]
        if ma_cross_ok and rsi_lower_ok and rsi_upper_ok:
            triggered.append("trend_momentum_confirm")

        if factors["volume_ratio_20"].iloc[-1] > params["volume_breakout"]:
            triggered.append("volume_breakout")

        return triggered

    def should_exit(self, position: dict, factors: dict, params: dict, weights: dict) -> str | None:
        """出场判断: 按 weight 降序遍历, 一旦任一信号触发立即返回其名称.

        Exit signal 列表 (按 spec):
        - atr_stop (0.35):       close < entry_price - {atr_stop_multiple} * atr_14
        - trailing_stop (0.30):  close < highest * (1 - {trailing_stop_pct})
        - ma_death_cross (0.20): ma_10 < ma_30
        - time_stop (0.15):      holding_days >= {max_holding_days}
        """
        ew = weights["exit"]
        current_price = position["current_price"]

        for sig in sorted(ew, key=ew.get, reverse=True):
            if sig == "atr_stop":
                # ATR 自适应初始止损: 以入场价为基准向下 atr_stop_multiple 倍 ATR
                threshold = position["entry_price"] - params["atr_stop_multiple"] * factors["atr_14"].iloc[-1]
                if current_price < threshold:
                    return "atr_stop"
            elif sig == "trailing_stop":
                # 移动止损: 从入场后最高收盘价回撤 trailing_stop_pct
                if check_trailing_stop(current_price, position["highest"], params["trailing_stop_pct"]):
                    return "trailing_stop"
            elif sig == "ma_death_cross":
                # 均线死叉
                if factors["ma_10"].iloc[-1] < factors["ma_30"].iloc[-1]:
                    return "ma_death_cross"
            elif sig == "time_stop":
                # 时间止损
                if check_time_stop(position["holding_days"], params["max_holding_days"]):
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

    os.chdir(_HERE.parents[1])

    parser = argparse.ArgumentParser(
        prog="strategy.py",
        description="ma_rsi_vol_atr_breakout_1 策略回测入口 (策略名隐含在文件路径中)",
    )
    parser.add_argument("mode", nargs="?", default="params", choices=["params", "weight"])
    parser.add_argument("--monitor", action="store_true")
    parser.add_argument("--weight-test", default=None)
    parser.add_argument("--start-date", default=None)
    parser.add_argument("--end-date", default=None)
    parser.add_argument("--test-universe", default=None, help="逗号分隔的股票代码列表 (覆盖默认测试集)")
    parser.add_argument("--max-stocks", type=int, default=None, help="限制测试股票数")
    parser.add_argument("--capital", type=float, default=300_000)
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    def run_once() -> int:
        # CLI 传入的 test-universe 优先级: CONFIG > CLI > 默认
        eff_test_universe = CONFIG.test_universe
        if eff_test_universe is None and args.test_universe:
            eff_test_universe = [s.strip() for s in args.test_universe.split(",") if s.strip()]
        eff_start_date = CONFIG.start_date if CONFIG.start_date is not None else args.start_date
        eff_end_date = CONFIG.end_date if CONFIG.end_date is not None else args.end_date
        eff_limit = CONFIG.limit if CONFIG.limit is not None else args.max_stocks
        eff_weight_test = args.weight_test if args.weight_test else "ma_rsi_vol_atr_breakout_1"

        if eff_test_universe is not None or eff_limit is not None or CONFIG.start_date is not None or CONFIG.end_date is not None or args.weight_test:
            print(f"[CONFIG] test_universe={eff_test_universe} start={eff_start_date} end={eff_end_date} limit={eff_limit} weight_test={eff_weight_test}")

        from subject.cli.main import main
        cli_args = ["run", "--strategy", "ma_rsi_vol_atr_breakout_1", "--mode", args.mode]
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
