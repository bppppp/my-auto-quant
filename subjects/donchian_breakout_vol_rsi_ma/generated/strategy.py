# debug_mode: params / monitor
# strategy: donchian_breakout_vol_rsi_ma
# version: v1 (baseline)
# purpose: 由 LLM 从 _original.md 翻译, 配合 subject.cli.run 跑回测 / --monitor 监听
# date: 2026-06-06
# mode: params (默认) | weight   ← positional, 第一参数
# run:   single (默认) | --monitor   ← single 跑一次退出 / --monitor 监听文件夹触发
# --- monitor 监听目录 ---
#   params 模式 → strategiesParam/  下新增 *_v<n>.md          文件触发
#   weight 模式 → strategiesWeight/ 下新增 *_weight_v<n>.md  文件触发
#   debounce 5s, Ctrl+C 退出
# --- monitor cwd 要求 ---
#   monitor 模式下 watch_dir 改用绝对路径 (基于 __file__: _HERE.parents[1] / "strategiesParam"),
#   因此**任意 cwd 都能跑**, 不需要先 cd.
#   __main__ 块中的 os.chdir(_HERE.parents[2]) 是给 run_once() 用的 (runner 期望 cwd = subjects/ 根),
#   monitor 模式不依赖 cwd, watch_dir 解析无冲突.
# --- CONFIG 最高优先级 (覆盖 CLI / spec) ---
#   test_universe: 自定义股票代码列表 (e.g. ["000001.SZ", "600000.SH"])
#   start_date / end_date: 日期范围 (e.g. "2024-01-01")
#   limit: 限制股票数 (e.g. 10)
# command: python generated/strategy.py
# command: python generated/strategy.py params
# command: python generated/strategy.py weight
# command: python generated/strategy.py --monitor
# command: python generated/strategy.py weight --monitor
# command: python generated/strategy.py weight --weight-test donchian_breakout_vol_rsi_ma   ← 覆盖默认 (一般不需要)
# command: python generated/strategy.py --start-date 2024-01-01 --end-date 2024-12-31

"""donchian_breakout_vol_rsi_ma 策略. 由 LLM 从 _original.md 翻译.

按 subject_structure.md §4.6 模式手写. 包含 3 个方法:
- compute_factors(df, params) -> {factor_name: Series}
- entry_score(factors, params, weights) -> float
- should_exit(position, factors, params, weights) -> signal_name | None

权重从 weights 参数读 (不硬编码, 见 §4.9).

**本文件同时作为策略回测执行入口**: 直接 `python strategy.py` 即跑该策略的
params 模式 (默认), `python strategy.py weight` 跑 weight 模式, 加 `--monitor`
进入文件夹监听模式 (params 监听 `strategiesParam/`, weight 监听
`strategiesWeight/`, 新增版本文件触发回测, debounce 5s, Ctrl+C 退出).
顶部 # command 列出全部调用方式.

**关键设计**:
- 策略名隐含在文件路径中 (本文件即 `donchian_breakout_vol_rsi_ma` 策略), 无需 `--strategy`
- `mode` 作**位置参数** (`python strategy.py [params|weight]`), 默认 params
- weight 模式默认从 `strategiesWeight/<strategy_name>_weight_v<n>.md` 读 weight (test name = 策略名)
- `--weight-test <name>` 仅在需要覆盖文件前缀时使用 (默认 = 策略名)
- `--monitor` 用 watchdog 监听对应目录, 匹配 `*_v<n>.md` / `*_weight_v<n>.md` 新文件触发
- **CONFIG** (下方 StrategyConfig 实例): 最高优先级配置, 覆盖 CLI / spec 默认值
- 内部委托给 `subject.cli.main` (`subjects/subject/cli/main.py`)
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pandas as pd

# 提前设置 sys.path: 当本文件被当作 strategy.py 直接运行 (python strategy.py)
# 时, Python 不会自动把 subjects/ 加进来, 但 Strategy 类需要 `from subject.factors import ...`.
# 必须在 import subject.* 之前完成.
_HERE = Path(__file__).resolve()
_SUBJECTS_DIR = _HERE.parents[2]  # subjects/<strategy>/generated/strategy.py → parents[2] = subjects/
if str(_SUBJECTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SUBJECTS_DIR))

from subject.factors import (  # noqa: E402
    donchian_high, donchian_low, ma, atr, volume_ratio, rsi,
)
from subject.conditions import (  # noqa: E402
    check_fixed_stop, check_trailing_stop, check_atr_stop, check_time_stop,
    check_channel_break, check_rsi_in_range, check_rsi_above,
)


# ====================================================================
# 策略执行配置 (最高优先级, 覆盖 CLI / spec 默认值)
# ====================================================================
@dataclass
class StrategyConfig:
    """策略执行配置. 任何字段非 None 时, 覆盖对应 CLI 参数和 spec 默认值.

    Attributes:
        test_universe: 自定义测试股票代码列表 (带后缀, 如 ``["000001.SZ", "600000.SH"]``).
            None = 用 spec.test_universe (默认 HS300).
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
    test_universe=None,  # 例如: ["000001.SZ", "000002.SZ", "600000.SH", "600519.SH"]
    start_date="2016-01-01",      # 例如: "2024-01-01"
    end_date="2026-01-01",        # 例如: "2024-03-31"
    limit=None,           # 例如: 10 (调试时建议 5-10, 全跑慢)
)


class Strategy:
    def compute_factors(self, df: pd.DataFrame, params: dict) -> dict:
        return {
            "donchian_high_20": donchian_high(df["最高价"], 20),
            "donchian_low_20": donchian_low(df["最低价"], 20),
            "ma_20": ma(df["收盘价"], 20),
            "ma_60": ma(df["收盘价"], 60),
            "atr_14": atr(df["最高价"], df["最低价"], df["收盘价"], 14),
            "volume_ratio_20": volume_ratio(df["成交量（股）"], 20),
            "rsi_14": rsi(df["收盘价"], 14),
            "close": df["收盘价"],
        }

    def entry_score(self, factors: dict, params: dict, weights: dict) -> float:
        # spec narrative §4: 多信号共振, 综合得分 = Σ(触发信号权重)
        # 不强制"至少 2 个信号", 由 spec 描述为"breakout_entry 必触发 + trend_entry/rsi_entry 至少 1 个",
        # 但 spec §4 也说"综合得分 = Σ(触发信号的权重)", 跑出高分靠权重求和即可, 选 top N 在 runner 侧.
        # 严格遵循 §4 文字: score = Σ(触发信号的 weight). 任一信号不触发就少加一项.
        score = 0.0
        ew = weights["entry"]
        # breakout_entry (weight 0.5): close > donchian_high_20 AND volume_ratio_20 > {vol_breakout_threshold}
        if (
            factors["close"].iloc[-1] > factors["donchian_high_20"].iloc[-1]
            and factors["volume_ratio_20"].iloc[-1] > params["vol_breakout_threshold"]
        ):
            score += ew["breakout_entry"]
        # trend_entry (weight 0.3): ma_20 > ma_60 AND close > ma_20
        if (
            factors["ma_20"].iloc[-1] > factors["ma_60"].iloc[-1]
            and factors["close"].iloc[-1] > factors["ma_20"].iloc[-1]
        ):
            score += ew["trend_entry"]
        # rsi_entry (weight 0.2): rsi_14 in [rsi_entry_low, rsi_entry_high]
        if check_rsi_in_range(
            factors["rsi_14"].iloc[-1],
            params["rsi_entry_low"],
            params["rsi_entry_high"],
        ):
            score += ew["rsi_entry"]
        return score

    def should_exit(self, position: dict, factors: dict, params: dict, weights: dict) -> str | None:
        ew = weights["exit"]
        # spec §4 出场优先级 (按 weight 降序):
        #   fixed_stop_loss(0.30) > trailing_stop(0.20) = volatility_stop(0.20) > trend_reversal_exit(0.15) > overbought_reduce(0.10) > time_stop(0.05)
        for sig in sorted(ew, key=ew.get, reverse=True):
            if sig == "fixed_stop_loss":
                if check_fixed_stop(
                    position["current_price"], position["entry_price"],
                    params["fixed_stop_loss_pct"],
                ):
                    return "fixed_stop_loss"
            elif sig == "trailing_stop":
                if check_trailing_stop(
                    position["current_price"], position["highest"],
                    params["trail_stop_pct"],
                ):
                    return "trailing_stop"
            elif sig == "volatility_stop":
                # current_price < highest - atr_stop_multiplier * atr_14
                # 取当前 bar 的 atr_14 (与 ma_cross 同模式: iloc[-1])
                if check_atr_stop(
                    position["current_price"], position["highest"],
                    factors["atr_14"].iloc[-1],
                    params["atr_stop_multiplier"],
                ):
                    return "volatility_stop"
            elif sig == "trend_reversal_exit":
                # close < donchian_low_20: 用 check_channel_break(direction="below")
                if check_channel_break(
                    factors["close"].iloc[-1], factors["donchian_low_20"].iloc[-1], "below",
                ):
                    return "trend_reversal_exit"
            elif sig == "overbought_reduce":
                # rsi_14 > rsi_overbought AND pnl_pct > partial_profit_pct
                if check_rsi_above(
                    factors["rsi_14"].iloc[-1], params["rsi_overbought"],
                ) and position["pnl_pct"] > params["partial_profit_pct"]:
                    return "overbought_reduce"
            elif sig == "time_stop":
                if check_time_stop(position["holding_days"], params["max_holding_days"]):
                    return "time_stop"
        return None

    # TODO: 加仓/减仓机制 — spec 列出 3 个 param (add/reduce_position_weight_threshold, reduce_position_floor)
    # 但 narrative §4 强调"综合得分 = Σ(触发信号的权重)" 由 runner 侧选 top N, 本身不展开加减仓规则.
    # 当前 weight 模式只在调仓日按 top N 全换, 不做单只股票的加减仓.
    # 相关 param (供未来实现参考):
    #   params["add_position_weight_threshold"]    默认 0.7
    #   params["reduce_position_weight_threshold"] 默认 0.3
    #   params["reduce_position_floor"]            默认 0.03


# ====================================================================
# 策略回测执行入口
# ====================================================================
if __name__ == "__main__":
    import argparse
    import re
    import threading

    from watchdog.events import FileSystemEvent, FileSystemEventHandler
    from watchdog.observers import Observer

    # 切到 subjects/ 根目录. runner 的 subjects_dir="." 期望 cwd = subjects/ 根,
    # 这样相对路径 "<strategy_name>/reportParams/report_v1.md" 才能正确解析.
    os.chdir(_HERE.parents[2])

    # === argparse: 位置参数 mode + single/monitor 控制 ===
    parser = argparse.ArgumentParser(
        prog="strategy.py",
        description="donchian_breakout_vol_rsi_ma 策略回测入口 (策略名隐含在文件路径中)",
        epilog="示例: python strategy.py weight --monitor",
    )
    parser.add_argument(
        "mode", nargs="?", default="params", choices=["params", "weight"],
        help="回测模式: params (按股时间序列, 默认) / weight (按日横截面)",
    )
    parser.add_argument(
        "--monitor", action="store_true",
        help="monitor 模式: 监听对应目录新增版本文件触发回测 (params→strategiesParam/, weight→strategiesWeight/, debounce 5s, Ctrl+C 退出)",
    )
    parser.add_argument(
        "--weight-test", default=None,
        help="weight 模式: 覆盖自动选择的 weight 场景名 (不传则按 strategiesWeight/ 下 v 数字最大的 _weight_v<n>.md)",
    )
    parser.add_argument("--start-date", default=None, help="起始日期 YYYY-MM-DD")
    parser.add_argument("--end-date", default=None, help="结束日期 YYYY-MM-DD")
    parser.add_argument("--capital", type=float, default=1_000_000, help="初始资金 (默认 1,000,000)")
    parser.add_argument("--output", default=None, help="报告输出路径 (默认按 mode 规则)")
    args = parser.parse_args()

    # === 委托给 subject.cli.main 跑 (单次) ===
    def run_once() -> int:
        # === CONFIG 覆盖 (最高优先级): CONFIG 非 None 时压过 CLI / spec 默认值 ===
        eff_test_universe = CONFIG.test_universe
        eff_start_date = CONFIG.start_date if CONFIG.start_date is not None else args.start_date
        eff_end_date = CONFIG.end_date if CONFIG.end_date is not None else args.end_date
        eff_limit = CONFIG.limit
        # weight test name: --weight-test 覆盖, 否则默认 = 策略名 (因 strategiesWeight/ 文件命名规则是 `<name>_weight_v<n>.md`, test name 即策略名)
        eff_weight_test = args.weight_test if args.weight_test else "donchian_breakout_vol_rsi_ma"

        # 打印生效的配置 (便于调试)
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
        if args.capital != 1_000_000:
            cli_args += ["--capital", str(args.capital)]
        if args.output:
            cli_args += ["--output", args.output]
        return main(cli_args)

    # === single 模式: 跑一次退出 ===
    if not args.monitor:
        sys.exit(run_once())

    # === --monitor 模式: 用 watchdog 监听目录, 触发回测 ===
    # watch_dir 必须用绝对路径 (基于 __file__), 不能用相对路径:
    #   上面的 os.chdir(_HERE.parents[2]) 已把 cwd 改到 subjects/ 根,
    #   若 watch_dir = Path("strategiesParam") 会解析成 subjects/strategiesParam/ (不存在)
    #   正确: <subjects_root>/<strategy_name>/strategiesParam/
    if args.mode == "params":
        watch_dir = _HERE.parents[1] / "strategiesParam"
        watch_pattern = re.compile(r".+_v\d+\.md$")
    else:  # weight
        watch_dir = _HERE.parents[1] / "strategiesWeight"
        watch_pattern = re.compile(r".+_weight_v\d+\.md$")

    if not watch_dir.exists():
        print(f"ERROR: monitor 模式需要 {watch_dir}/ 目录, 不存在", file=sys.stderr)
        sys.exit(1)

    trigger_event = threading.Event()
    stop_event = threading.Event()  # Ctrl+C 后置位, 主循环下次 wait 时立即跳出

    class _WatchHandler(FileSystemEventHandler):
        """watchdog handler: 文件创建/修改若匹配 pattern 则 set trigger."""
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

    # === Ctrl+C 优雅退出 ===
    # 注册 SIGINT 处理器置位 stop_event, 主循环里用带 timeout 的 wait 轮询,
    # 一旦 stop_event 置位立即跳出循环; finally 块 observer.join() 加 timeout.
    import signal as _signal
    def _handle_sigint(signum, frame):
        stop_event.set()
    try:
        _signal.signal(_signal.SIGINT, _handle_sigint)
    except (ValueError, OSError):
        # 子线程或非主线程下 signal.signal 会抛, 不影响 watchdog 工作
        pass

    DEBOUNCE_SECONDS = 5.0
    print(f"[monitor] watching: {watch_dir.resolve()}/")
    print(f"[monitor] pattern:  {watch_pattern.pattern}")
    print(f"[monitor] debounce: {DEBOUNCE_SECONDS}s, Ctrl+C 退出")

    try:
        while not stop_event.is_set():
            # 阻塞直到首个事件, 但每 1s 检查 stop_event 一次 (Ctrl+C 后立即响应)
            if not trigger_event.wait(timeout=1.0):
                continue  # timeout, 回到 while 顶部检查 stop_event
            trigger_event.clear()
            # debounce: DEBOUNCE_SECONDS 内若无新事件, 才触发回测
            while not stop_event.is_set():
                fired_again = trigger_event.wait(timeout=DEBOUNCE_SECONDS)
                if fired_again:
                    trigger_event.clear()
                    # 延长 debounce 窗口
                else:
                    break
            if stop_event.is_set():
                break
            print(f"[trigger] new version file in {watch_dir.name}/, running backtest...")
            rc = run_once()
            print(f"[trigger] backtest exit code: {rc}")
    except KeyboardInterrupt:
        # 兜底: 即使 signal handler 没注册上 (e.g. Windows 子线程), 也能走到这里
        stop_event.set()
        print("\n[monitor] stopped (KeyboardInterrupt)")
    finally:
        observer.stop()
        # observer.join() 加 timeout, 避免 Windows 上 watchdog 线程 syscall 卡死
        observer.join(timeout=3.0)
        if observer.is_alive():
            print("[monitor] warning: watchdog observer 未在 3s 内退出, 强制丢弃")
