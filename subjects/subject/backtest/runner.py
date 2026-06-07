"""BacktestRunner: 完整主回测引擎.

见 subject.md §5 / subject_structure.md §6.

两种模式:
- **params 模式** (by_stock): 逐股时间序列回测, 每只股票独立 backtest, 聚合 metrics
- **weight 模式** (by_day): 每日横截面选股, 多股票组合管理, 调仓

公共主循环 (per bar):
1. compute_factors → 收集 factor 值
2. 检查已有持仓的 should_exit → 卖出
3. 检查入场 → 调仓日时选 top N, 否则只新增 (per-stock 模式不调仓)
4. update_after_bar → 维护 highest, holding_days
5. 记录 daily_value
"""
from __future__ import annotations

import importlib.util
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

import pandas as pd

from .a_share_rules import can_buy, can_sell
from .data_loader import load_day, load_stock
from .fees import calc_buy_fee, calc_sell_fee
from .log_utils import setup_backtest_logger
from .metrics import compute_metrics
from ..parser import parse_strategy_spec
from .portfolio import (
    Portfolio,
    Position,
    enforce_industry_concentration,
    enforce_max_single_weight,
    enforce_max_turnover,
    load_industry_map,
)
from .reports import render_params_report, render_weight_report
from .signals import rank_top_n
from .stats import compute_factor_value_stats, compute_signal_stats
from .universe import HS300_CODES, CSI1000_CODES, CYB_STAR_50_CODES, exclude_bj, exclude_st


# 模式 → 数据源
MODE_DATA_SOURCE: dict[str, str] = {
    "params": "data-by-stock",
    "weight": "data-by-day",
}


@dataclass
class RunResults:
    """回测结果汇总."""

    metrics: Any
    signal_stats: list = field(default_factory=list)
    factor_stats: list = field(default_factory=list)
    trades: pd.DataFrame = field(default_factory=pd.DataFrame)
    daily_values: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))
    events: pd.DataFrame = field(default_factory=pd.DataFrame)
    signal_attribution: list = field(default_factory=list)
    # 实际跑用的策略版本 (params: strategiesParam/<name>_v<n>.md / weight: strategiesWeight/<test>_weight_v<n>.md)
    # 由 _run_params / _run_weight 在 _pick_latest_version 后填入, 供 cli 命名 report 文件用.
    version: str = "v1"


class BacktestRunner:
    """主回测调度器.

    Attributes:
        strategy_name: 策略目录名.
        mode: ``"params"`` 或 ``"weight"``.
        weight_test: weight 模式 test name. 默认 = strategy_name (即 strategiesWeight/
            下 `<strategy_name>_weight_v<n>.md` 的 test name = strategy_name). 仅在
            需要覆盖文件前缀时才传.
        start_date / end_date: 日期范围 (可选).
        initial_capital: 初始资金.
        subjects_dir: 工作目录 (默认当前目录, 期望 subjects/ 根).
        max_stocks: 限制测试股票数 (取前 N, None = 不限).
        test_universe_override: 自定义测试股票代码列表 (如 ``["000001.SZ", "600000.SH"]``),
            非 None 时**覆盖** spec.test_universe 的解析结果, 然后再应用 max_stocks.
    """

    def __init__(
        self,
        strategy_name: str,
        mode: Literal["params", "weight"],
        weight_test: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        initial_capital: float = 300_000.0,
        subjects_dir: str | Path = ".",
        max_stocks: int | None = None,
        test_universe_override: list[str] | None = None,
        min_bars: int = 20,
    ):
        if mode not in MODE_DATA_SOURCE:
            raise ValueError(f"mode must be one of {list(MODE_DATA_SOURCE)}, got {mode!r}")

        self.strategy_name = strategy_name
        self.mode = mode
        # weight 模式: test name 默认 = strategy_name (因为 strategiesWeight/ 下的文件命名规则是
        # `<strategy_name>_weight_v<n>.md`, 不存在"多 test 场景"概念). 传 weight_test 可覆盖.
        self.weight_test = weight_test if weight_test else strategy_name
        self.start_date = start_date
        self.end_date = end_date
        self.initial_capital = initial_capital
        self.subjects_dir = Path(subjects_dir)
        self.max_stocks = max_stocks
        self.test_universe_override = test_universe_override
        self.min_bars = min_bars  # params 模式下, 单只股票至少需要多少根 K 线

        # === 默认时间范围: 若用户未指定, 设为"以数据末日为基准往前推 5 年" ===
        # 解决直接调 CLI 不传 start_date/end_date 时跑全 2018-2026 的问题.
        if self.start_date is None and self.end_date is None:
            self._apply_default_date_range_5y()

        # 加载基础数据
        self.spec = self._load_spec()
        self.params: dict = self._load_params()
        self.weights: dict = self._load_weights()
        self.strategy = self._load_strategy_class()

        # universe: test_universe_override 优先, 否则用 spec 解析, 最后截 max_stocks
        if self.test_universe_override is not None:
            self.universe = list(self.test_universe_override)
        else:
            self.universe = self._resolve_universe()
        if self.max_stocks is not None:
            self.universe = self.universe[: self.max_stocks]

        # === 设置 logger (双 handler: 文件 + console) ===
        self.logger, self.log_file = setup_backtest_logger(
            strategy_name=self.strategy_name,
            subjects_dir=self.subjects_dir,
        )
        self.logger.info(f"=== BacktestRunner init ===")
        self.logger.info(f"mode: {self.mode}")
        self.logger.info(f"weight_test: {self.weight_test}")
        self.logger.info(f"date_range: {self.start_date or '不限'} ~ {self.end_date or '不限'}")
        self.logger.info(f"initial_capital: {self.initial_capital:,.2f}")
        if self.test_universe_override is not None:
            self.logger.info(f"test_universe: 自定义 {len(self.test_universe_override)} 只")
        else:
            self.logger.info(f"test_universe: spec.test_universe (默认 HS300)")
        if self.max_stocks is not None:
            self.logger.info(f"max_stocks (limit): {self.max_stocks}")
        self.logger.info(f"actual universe size: {len(self.universe)}")

    # ===== 加载 =====
    def _load_spec(self) -> dict:
        path = self.subjects_dir / self.strategy_name / f"{self.strategy_name}_original.md"
        return parse_strategy_spec(path)

    def _load_params(self) -> dict:
        version_file = self._pick_latest_version("strategiesParam", prefix=f"{self.strategy_name}_v")
        if version_file is None:
            return {p["name"]: p["default"] for p in self.spec["params"]}
        spec = parse_strategy_spec(version_file)
        return {p["name"]: p["default"] for p in spec["params"]}

    def _load_weights(self) -> dict:
        if self.mode == "params":
            entry = {s["name"]: s["weight"] for s in self.spec["entry_signals"]}
            exit_w = {s["name"]: s["weight"] for s in self.spec["exit_signals"]}
            return {"entry": entry, "exit": exit_w}
        version_file = self._pick_latest_version(
            "strategiesWeight", prefix=f"{self.weight_test}_weight_v"
        )
        if version_file is None:
            raise FileNotFoundError(
                f"weight mode requires strategiesWeight/{self.weight_test}_weight_v*.md, none found"
            )
        spec = parse_strategy_spec(version_file)
        entry = {s["name"]: s["weight"] for s in spec["entry_signals"]}
        exit_w = {s["name"]: s["weight"] for s in spec["exit_signals"]}
        return {"entry": entry, "exit": exit_w}

    def _load_strategy_class(self) -> Any:
        path = self.subjects_dir / self.strategy_name / "generated" / "strategy.py"
        if not path.exists():
            raise FileNotFoundError(
                f"strategy.py not found: {path}\n"
                f"请先 LLM 翻译 _original.md → generated/strategy.py"
            )
        spec = importlib.util.spec_from_file_location(
            f"{self.strategy_name}_strategy", path
        )
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot load strategy.py: {path}")
        mod = importlib.util.module_from_spec(spec)
        # 必须注册到 sys.modules, 否则 dataclass 装饰器在 module-level 找 cls.__module__ 失败.
        import sys as _sys
        _sys.modules[spec.name] = mod
        spec.loader.exec_module(mod)
        return mod.Strategy()

    def _pick_latest_version(self, subdir: str, prefix: str) -> Path | None:
        d = self.subjects_dir / self.strategy_name / subdir
        if not d.exists():
            return None
        pattern = re.compile(re.escape(prefix) + r"(\d+)\.md$")
        best_n = -1
        best = None
        for p in d.iterdir():
            m = pattern.search(p.name)
            if m:
                n = int(m.group(1))
                if n > best_n:
                    best_n = n
                    best = p
        return best

    def _resolve_universe(self) -> list[str]:
        """从 spec.test_universe 解析股票代码列表.

        支持的 test_universe 值 (大小写不敏感, 但建议用大写):
          - "HS300" / "hs300"   → 沪深 300 (300 只)
          - "CSI1000" / "csi1000" → 中证 1000 (1000 只)
          - "CYB_STAR_50" / "cyb_star_50" → 创业板 50 + 科创板 50 (~100 只)

        多选: ["HS300", "CSI1000"] → 取并集 (去重).

        无效值或全空 → fallback 沪深 300.
        """
        u = self.spec.get("test_universe", [])
        # 大小写归一化
        uni_set = {str(x).strip().upper() for x in u if x}
        codes: set[str] = set()
        if "HS300" in uni_set:
            codes.update(HS300_CODES)
        if "CSI1000" in uni_set:
            codes.update(CSI1000_CODES)
        if "CYB_STAR_50" in uni_set:
            codes.update(CYB_STAR_50_CODES)
        if not codes:
            # fallback: 默认沪深 300 (兼容旧的空 / 非法值)
            codes.update(HS300_CODES)
        # 保持稳定顺序: HS300 -> CSI1000 -> CYB_STAR_50
        ordered: list[str] = []
        seen: set[str] = set()
        for pool in (HS300_CODES, CSI1000_CODES, CYB_STAR_50_CODES):
            for c in pool:
                if c in codes and c not in seen:
                    ordered.append(c)
                    seen.add(c)
        return ordered

    # ===== 主入口 =====
    def run(self) -> RunResults:
        # 实际跑的策略版本 (供 cli 命名 report 文件用, 避免硬编码 v1)
        version = self._resolve_report_version()
        if self.mode == "params":
            return self._run_params(version)
        return self._run_weight(version)

    # ===== params 模式: 逐股独立 backtest =====
    def _run_params(self, version: str = "v1") -> RunResults:
        """逐股时间序列回测, 聚合 metrics.

        每只股票独立: 评估入场信号 → 满仓买入 → 评估出场信号 → 全仓卖出.
        ``max_stocks`` 限制单次跑的股票数 (避免一次性全量).

        **daily_values 聚合**: 每只股票的 daily_values 是其自身时间序列,
        跨股票日期**不对齐** (有的股 200 天, 有的 220 天). 聚合时按日期 groupby 求和.
        """
        all_trades: list[dict] = []
        all_events: list[dict] = []
        factor_values: dict[str, list[float]] = {}
        per_stock_daily: dict[str, pd.Series] = {}  # code -> per-stock daily values

        total_stocks = len(self.universe)
        self.logger.info(f"=== params mode: processing {total_stocks} stocks ===")
        skipped_data_missing = 0
        skipped_too_few = 0
        t_start = datetime.now()

        # === 进度日志: 每 5% 汇总一次, 不再逐只打印 ===
        # 300 只时 5% = 15 只, 一次汇总打印. 避免 600+ 行日志淹没用户.
        log_every_n = max(1, total_stocks // 20)  # 至少 20 次汇总
        next_log_at = log_every_n  # 下次打印的累计编号
        # 累计计数 (汇总用)
        cum_entries = 0
        cum_exits = 0
        cum_swallowed = 0
        cum_trades = 0

        for i, code in enumerate(self.universe, 1):
            try:
                df = load_stock(code.split(".")[0])
            except FileNotFoundError as e:
                self.logger.warning(f"[{i}/{total_stocks}] {code} - data not found: {e}")
                skipped_data_missing += 1
                continue
            # 日期过滤
            if self.start_date:
                df = df[df["日期"] >= pd.Timestamp(self.start_date)]
            if self.end_date:
                df = df[df["日期"] <= pd.Timestamp(self.end_date)]
            df = df.sort_values("日期").reset_index(drop=True)
            if len(df) < self.min_bars:  # 数据太少, 跳过 (默认 20 根 K 线)
                self.logger.warning(
                    f"[{i}/{total_stocks}] {code} - too few bars ({len(df)} < {self.min_bars}), skip"
                )
                skipped_too_few += 1
                continue

            try:
                res = self._backtest_single_stock(df, code)
            except Exception as e:
                self.logger.error(f"[{i}/{total_stocks}] {code} - backtest failed: {e}", exc_info=True)
                continue

            # 累计摘要 (不立即打印)
            n_entries = sum(1 for ev in res["events"] if ev.get("action") == "executed" and "entry" in str(ev.get("signal", "")))
            n_exits = sum(1 for ev in res["events"] if ev.get("action") == "executed" and ev.get("signal") not in ("entry_combined",))
            n_swallowed = sum(1 for ev in res["events"] if ev.get("action") == "swallowed")
            cum_entries += n_entries
            cum_exits += n_exits
            cum_swallowed += n_swallowed
            cum_trades += len(res["trades"])

            # 5% 汇总 (i == next_log_at 或最后一只)
            if i >= next_log_at or i == total_stocks:
                pct = i / total_stocks * 100
                self.logger.info(
                    f"[stock {i}/{total_stocks}] {pct:.0f}% done | "
                    f"entries={cum_entries}, exits={cum_exits}, swallowed={cum_swallowed}, "
                    f"trades={cum_trades}"
                )
                cum_entries = cum_exits = cum_swallowed = cum_trades = 0
                # 下一个 5% 节点
                while next_log_at <= i:
                    next_log_at += log_every_n

            all_trades.extend(res["trades"])
            all_events.extend(res["events"])
            for k, v in res["factors"].items():
                factor_values.setdefault(k, []).extend(v)
            # daily_values: 转成 Series 索引日期
            if res["daily_values"]:
                dates, vals = zip(*res["daily_values"])
                per_stock_daily[code] = pd.Series(vals, index=pd.DatetimeIndex(dates))

        # 跨股票按日期求和 (reindex + sum, 用 concat 避免 DataFrame fragmentation)
        if per_stock_daily:
            all_dates = sorted(set().union(*[set(s.index) for s in per_stock_daily.values()]))
            agg = pd.concat(
                [s.reindex(pd.DatetimeIndex(all_dates)) for s in per_stock_daily.values()],
                axis=1,
            )
            agg.columns = list(per_stock_daily.keys())
            agg = agg.ffill().fillna(0)  # 缺失日期用前一天值填充, 最早期用 0
            dv_series = agg.sum(axis=1)
        else:
            dv_series = pd.Series(dtype=float)

        # === Run summary ===
        wall_time = datetime.now() - t_start
        n_trades = len(all_trades)
        n_wins = sum(1 for t in all_trades if (t.get("pnl") or 0) > 0)
        n_losses = sum(1 for t in all_trades if (t.get("pnl") or 0) < 0)
        self.logger.info(f"=== Run summary ===")
        self.logger.info(f"stocks processed: {total_stocks - skipped_data_missing - skipped_too_few}/{total_stocks}")
        self.logger.info(f"stocks skipped (data missing): {skipped_data_missing}")
        self.logger.info(f"stocks skipped (too few bars): {skipped_too_few}")
        self.logger.info(f"trades: {n_trades} (wins: {n_wins}, losses: {n_losses})")
        self.logger.info(f"wall time: {wall_time}")
        self.logger.info(f"log file: {self.log_file}")

        return self._build_results(all_trades, all_events, factor_values, dv_series, version=version)

    def _backtest_single_stock(self, df: pd.DataFrame, code: str) -> dict:
        """单只股票时间序列回测.

        资金视角: 每只股票从 ``per_stock_capital`` 开始, 累计已实现 PnL 持续累加.
        无持仓时 value = per_stock_capital + cumulative_pnl (相当于全部变现为现金).
        有持仓时 value = per_stock_capital + cumulative_pnl + (close - entry) * shares.
        """
        trades: list[dict] = []
        events: list[dict] = []
        factor_values: dict[str, list[float]] = {}
        daily_values: list[tuple[pd.Timestamp, float]] = []
        pos: Position | None = None
        per_stock_capital = self.initial_capital * self.params.get("max_single_weight", 0.10)
        cumulative_pnl: float = 0.0  # 累计已实现 PnL

        for i in range(len(df)):
            bar = df.iloc[i]
            date: pd.Timestamp = bar["日期"]
            close: float = float(bar["收盘价"])

            # 1. compute_factors
            try:
                factors = self.strategy.compute_factors(df.iloc[: i + 1], self.params)
            except Exception as e:
                events.append({"code": code, "signal": "compute_factors", "action": "skipped", "error": str(e), "pnl": None, "holding_days": None})
                continue
            for k, v in factors.items():
                if isinstance(v, pd.Series) and len(v) > 0 and not pd.isna(v.iloc[-1]):
                    factor_values.setdefault(k, []).append(float(v.iloc[-1]))

            # 2. 检查出场
            if pos is not None:
                pos.highest = max(pos.highest, close)
                pos.holding_days = (date - pos.entry_date).days
                pos_dict = pos.to_state_dict()
                pos_dict["current_price"] = close
                pos_dict["pnl_pct"] = (close - pos.entry_price) / pos.entry_price if pos.entry_price > 0 else 0.0
                try:
                    exit_sig = self.strategy.should_exit(pos_dict, factors, self.params, self.weights)
                except Exception:
                    exit_sig = None
                if exit_sig:
                    if can_sell(bar):
                        # PnL 需扣 sell_fee (印花税 0.1% + 佣金 0.025% + 沪市过户 0.001%)
                        # entry_price 已是含费均价, 故 (close - entry_price) * shares 是毛利,
                        # 实际净 PnL = 毛利 - sell_fee
                        sell_amount = close * pos.shares
                        pnl = (close - pos.entry_price) * pos.shares - calc_sell_fee(sell_amount, code)
                        cumulative_pnl += pnl
                        trades.append({"code": code, "pnl": pnl, "holding_days": pos.holding_days, "signal": exit_sig})
                        events.append({"code": code, "signal": exit_sig, "action": "executed", "pnl": pnl, "holding_days": pos.holding_days})
                        # 将 exit 的 pnl/holding_days 关联到触发入场的 entry 信号
                        if pos.entry_signals:
                            for sig_name in pos.entry_signals:
                                events.append({"code": code, "signal": sig_name, "action": "exit_linked", "pnl": pnl, "holding_days": pos.holding_days})
                        pos = None
                    else:
                        events.append({"code": code, "signal": exit_sig, "action": "swallowed", "pnl": None, "holding_days": pos.holding_days})

            # 3. 检查入场 (无持仓时)
            if pos is None:
                try:
                    score = self.strategy.entry_score(factors, self.params, self.weights)
                except Exception:
                    score = 0
                if score > 0 and can_buy(bar):
                    amount = per_stock_capital
                    shares = int(amount / close / 100) * 100
                    if shares > 0:
                        fee = calc_buy_fee(shares * close, code)
                        effective_entry = (shares * close + fee) / shares
                        # 调用策略的 get_triggered_signals 方法获取触发入场的信号列表
                        triggered_signals = self.strategy.get_triggered_signals(factors, self.params, self.weights)
                        pos = Position(
                            code=code, shares=shares,
                            entry_price=effective_entry, entry_date=date,
                            highest=close, holding_days=0,
                            entry_signals=triggered_signals,
                        )
                        # 记录 entry_combined 事件（用于统计有信号触发的次数）
                        events.append({"code": code, "signal": "entry_combined", "action": "executed", "pnl": None, "holding_days": 0})
                        # 同时为每个具体 entry 信号记录事件（用于 Signal Stats 报告）
                        for sig_name in triggered_signals:
                            events.append({"code": code, "signal": sig_name, "action": "triggered", "pnl": None, "holding_days": 0})

            # 4. 记录 daily value
            if pos is not None:
                unrealized = (close - pos.entry_price) * pos.shares
                value = per_stock_capital + cumulative_pnl + unrealized
            else:
                value = per_stock_capital + cumulative_pnl
            daily_values.append((date, value))

        return {"trades": trades, "events": events, "factors": factor_values, "daily_values": daily_values}

    # ===== weight 模式: 每日横截面 + 多股票组合 =====
    def _run_weight(self, version: str = "v1") -> RunResults:
        """每日横截面选股, 多股票组合管理, 调仓.

        主循环 (per bar):
        1. load_day → 过滤 universe
        2. compute_factors + entry_score for all stocks
        3. 检查已有持仓的 should_exit → 卖出
        4. 调仓日 (should_rebalance) → 选 top N → enforce 5 约束 → 调仓 (sell/buy)
        5. update_after_bar → 维护 highest, holding_days
        6. 记录 daily_value

        **factor 计算架构**:
        策略的 compute_factors 需要多日历史 (ma_20 需 20 行, atr_14 需 14 行等).
        若每日只传 1 行, 所有因子都是 NaN → 永远不入场.
        解决: 在主循环之前, 对每只股票预加载 by-stock 历史 (含 start_date 之前 ~30 天
        buffer, 保证因子窗口够), 主循环时按当日日期取 ``hist.iloc[:i+1]`` 传给
        compute_factors, 与 params 模式语义一致.
        """
        portfolio = Portfolio(initial_capital=self.initial_capital, cash=self.initial_capital)
        all_events: list[dict] = []
        all_trades: list[dict] = []
        factor_values: dict[str, list[float]] = {}
        all_daily_values: list[tuple[pd.Timestamp, float]] = []

        trading_dates = self._enumerate_trading_dates()
        if not trading_dates:
            raise RuntimeError("No trading dates found in data-by-day/")

        # === 预加载每只股票的 by-stock 历史 (含 buffer) ===
        # buffer=60 天, 保证 ma_20 / atr_14 / volume_ratio_20 在 start_date 时已有足够样本.
        HISTORY_BUFFER_DAYS = 60
        earliest_needed = None
        if trading_dates and self.start_date:
            earliest_needed = (
                pd.Timestamp(self.start_date) - pd.Timedelta(days=HISTORY_BUFFER_DAYS)
            )
        stock_history: dict[str, pd.DataFrame] = {}
        skipped_history = 0
        for code in self.universe:
            try:
                hist = load_stock(code.split(".")[0])
            except FileNotFoundError:
                skipped_history += 1
                continue
            if earliest_needed is not None:
                hist = hist[hist["日期"] >= earliest_needed]
            if self.end_date:
                hist = hist[hist["日期"] <= pd.Timestamp(self.end_date)]
            hist = hist.sort_values("日期").reset_index(drop=True)
            if len(hist) < 20:  # 至少需要 20 行 (ma_20)
                skipped_history += 1
                continue
            stock_history[code] = hist
        self.logger.info(
            f"preloaded history for {len(stock_history)}/{len(self.universe)} stocks "
            f"(skipped: {skipped_history})"
        )

        freq = int(self.params.get("rebalance_freq_days", 5))
        target_n = int(self.params.get("target_holdings", 8))
        max_single = float(self.params.get("max_single_weight", 0.10))
        max_industry = float(self.params.get("max_industry_concentration", 0.30))
        max_turnover = float(self.params.get("max_turnover_per_rebalance", 0.50))

        # TODO: 熊市折算 — spec narrative §5 要求熊市时 target_holdings 减半.
        # 当前 data-by-day/ 目录无沪深 300 指数文件 (只有个股横截面), 无法直接调
        # subject.backtest.bear_market.is_bear_market. 暂按非熊市处理.
        # 补全方式: 加载 data/index/000300.csv (用户提供) → 取 close 序列 →
        #   bear = is_bear_market(hs300_close, threshold=params["bear_drawdown_threshold"])
        #   scale = bear_position_scale(bear)
        #   target_n = int(target_n * scale)
        # 注意: scale 后的 target_n 在调仓日内有效即可, 无需每日重算 (但应每日重算).

        total_days = len(trading_dates)
        self.logger.info(f"=== weight mode: processing {total_days} trading days ===")
        self.logger.info(f"rebalance_freq: every {freq} days, target_holdings: {target_n}")
        t_start = datetime.now()
        n_rebalances = 0
        n_skipped_days = 0
        log_every_n_days = max(1, total_days // 20)  # 至少 20 次进度日志

        for bar_idx, date_str in enumerate(trading_dates, 1):
            date = pd.Timestamp(date_str)

            # (进度日志移到 # 5 之后, 跟阶段收益一起打印)

            # 1. 加载当日横截面
            try:
                df = load_day(date_str)
            except FileNotFoundError as e:
                self.logger.warning(f"[{date_str}] data file not found, skip: {e}")
                n_skipped_days += 1
                continue
            df = exclude_bj(df)
            df = exclude_st(df)
            df = df[df["代码"].isin(set(self.universe))].copy()
            df = df.reset_index(drop=True)
            if len(df) == 0:
                n_skipped_days += 1
                continue
            day_data: dict[str, pd.Series] = {row["代码"]: row for _, row in df.iterrows()}

            # 2. 算因子 + entry score
            # 关键: compute_factors 需要多日历史, 传当日 1 行 → 全部 NaN.
            # 解决: 用预加载的 stock_history, 取 "到今日为止" 的累计历史传给 compute_factors.
            scores: dict[str, float] = {}
            factors_by_code: dict[str, dict] = {}
            for code, row in day_data.items():
                if code not in stock_history:
                    continue
                hist = stock_history[code]
                # 找 hist 中 date <= today 的最大索引 (即 "到今日为止" 的累计)
                # 累计数据要含今日 → iloc[:i+1]
                mask = hist["日期"] <= date
                if not mask.any():
                    continue
                idx = hist.index[mask][-1]  # 最后一个 <= today 的位置
                try:
                    factors = self.strategy.compute_factors(hist.iloc[: idx + 1], self.params)
                except Exception as e:
                    all_events.append({
                        "code": code, "signal": "compute", "action": "skipped",
                        "error": str(e), "pnl": None, "holding_days": None,
                    })
                    continue
                factors_by_code[code] = factors
                for k, v in factors.items():
                    if isinstance(v, pd.Series) and len(v) > 0 and not pd.isna(v.iloc[-1]):
                        factor_values.setdefault(k, []).append(float(v.iloc[-1]))
                try:
                    score = self.strategy.entry_score(factors, self.params, self.weights)
                except Exception as e:
                    score = 0.0
                scores[code] = score
                if score > 0:
                    # 记录 entry_combined 事件（用于统计有信号触发的股票数）
                    all_events.append({
                        "code": code, "signal": "entry_combined", "action": "triggered",
                        "score": score, "pnl": None, "holding_days": None,
                    })
                    # 调用策略的 get_triggered_signals 方法获取触发入场的信号列表
                    triggered_signals = self.strategy.get_triggered_signals(factors, self.params, self.weights)
                    for sig_name in triggered_signals:
                        sig_weight = self.weights.get("entry", {}).get(sig_name, 0.0)
                        all_events.append({
                            "code": code, "signal": sig_name, "action": "triggered",
                            "score": sig_weight, "pnl": None, "holding_days": None,
                        })

            prices: dict[str, float] = {code: float(r["收盘价"]) for code, r in day_data.items()}

            # 3. 检查出场
            for code in list(portfolio.positions.keys()):
                if code not in day_data:
                    continue
                pos = portfolio.positions[code]
                bar_series = day_data[code]
                close = float(bar_series["收盘价"])
                portfolio.update_after_bar(code, close)

                if code not in factors_by_code:
                    continue
                factors = factors_by_code[code]
                pos_dict = pos.to_state_dict()
                pos_dict["current_price"] = close
                pos_dict["pnl_pct"] = (close - pos.entry_price) / pos.entry_price if pos.entry_price > 0 else 0.0
                try:
                    exit_sig = self.strategy.should_exit(pos_dict, factors, self.params, self.weights)
                except Exception:
                    exit_sig = None
                if exit_sig:
                    if can_sell(bar_series):
                        # PnL 需扣 sell_fee (见 calc_sell_fee). portfolio.sell 内部已扣 fee 加到 cash,
                        # 但这里 runner 自己算的 pnl 是给 trade/event 用的, 必须独立扣一次.
                        sell_amount = close * pos.shares
                        pnl = (close - pos.entry_price) * pos.shares - calc_sell_fee(sell_amount, code)
                        _, sold_pos = portfolio.sell(code, close, date)
                        all_trades.append({
                            "code": code, "pnl": pnl,
                            "holding_days": pos.holding_days, "signal": exit_sig,
                        })
                        all_events.append({
                            "code": code, "signal": exit_sig, "action": "executed",
                            "pnl": pnl, "holding_days": pos.holding_days,
                        })
                        # 将 exit 的 pnl/holding_days 关联到触发入场的 entry 信号
                        if sold_pos and sold_pos.entry_signals:
                            for sig_name in sold_pos.entry_signals:
                                all_events.append({
                                    "code": code, "signal": sig_name, "action": "exit_linked",
                                    "pnl": pnl, "holding_days": pos.holding_days,
                                })
                    else:
                        all_events.append({
                            "code": code, "signal": exit_sig, "action": "swallowed",
                            "pnl": None, "holding_days": pos.holding_days,
                        })

            # 4. 调仓日
            if should_rebalance_fn(bar_idx, freq):
                top_codes = rank_top_n(scores, target_n)
                if top_codes:
                    n_rebalances += 1
                    # 不再打印 top N 列表, 阶段收益会在 5% 进度日志统一输出
                    target_weights = {c: 1.0 / target_n for c in top_codes}
                    target_weights = enforce_max_single_weight(target_weights, max_single)
                    try:
                        industry_map = load_industry_map(self.universe, date_str)
                        target_weights = enforce_industry_concentration(target_weights, industry_map, max_industry)
                    except Exception as e:
                        self.logger.warning(f"[{date_str}] industry_concentration failed: {e}")
                    current_weights = portfolio.weights(prices)
                    target_weights = enforce_max_turnover(current_weights, target_weights, max_turnover)

                    tv = portfolio.total_value(prices)
                    # 卖出不在 target 的
                    for code in list(portfolio.positions.keys()):
                        if code not in target_weights:
                            if code in day_data and can_sell(day_data[code]):
                                pos = portfolio.positions[code]
                                close = float(day_data[code]["收盘价"])
                                # PnL 需扣 sell_fee (同 exit 卖出)
                                sell_amount = close * pos.shares
                                pnl = (close - pos.entry_price) * pos.shares - calc_sell_fee(sell_amount, code)
                                portfolio.sell(code, close, date)
                                all_trades.append({
                                    "code": code, "pnl": pnl,
                                    "holding_days": pos.holding_days, "signal": "rebalance",
                                })
                                all_events.append({
                                    "code": code, "signal": "rebalance_out", "action": "executed",
                                    "pnl": pnl, "holding_days": pos.holding_days,
                                })
                    # 买入新增的
                    for code, weight in target_weights.items():
                        if code in portfolio.positions:
                            continue
                        if code not in day_data:
                            continue
                        if not can_buy(day_data[code]):
                            all_events.append({
                                "code": code, "signal": "entry", "action": "skipped",
                                "reason": "limit_up", "pnl": None, "holding_days": None,
                            })
                            continue
                        close = float(day_data[code]["收盘价"])
                        amount = tv * weight
                        shares = int(amount / close / 100) * 100
                        if shares > 0:
                            # 获取触发入场的信号列表（调用策略方法）
                            if code in factors_by_code:
                                triggered_signals = self.strategy.get_triggered_signals(
                                    factors_by_code[code], self.params, self.weights
                                )
                            else:
                                triggered_signals = []
                            actual, cost = portfolio.buy(code, close, shares, date, entry_signals=triggered_signals)
                            if actual > 0:
                                all_events.append({
                                    "code": code, "signal": "entry_combined", "action": "executed",
                                    "pnl": None, "holding_days": 0,
                                })
                                # 为每个具体 entry 信号记录事件
                                for sig_name in triggered_signals:
                                    all_events.append({
                                        "code": code, "signal": sig_name, "action": "triggered",
                                        "pnl": None, "holding_days": 0,
                                    })
                            else:
                                all_events.append({
                                    "code": code, "signal": "entry", "action": "skipped",
                                    "reason": "insufficient_cash", "pnl": None, "holding_days": None,
                                })

            # 5. 记录 daily value
            tv = portfolio.total_value(prices)
            all_daily_values.append((date, tv))

            # === 阶段收益日志 (每 5% 一次, 不再逐调仓打印 top N) ===
            # 阶段收益率 = 当前 tv / 期初本金 - 1; 持仓数 = portfolio.positions 数量.
            if bar_idx == 1 or bar_idx % log_every_n_days == 0 or bar_idx == total_days:
                stage_return = (tv / self.initial_capital) - 1.0
                n_holdings = len(portfolio.positions)
                # 持仓额 = 持仓总市值 = tv - cash (现金部分)
                position_value = tv - portfolio.cash
                self.logger.info(
                    f"[day {bar_idx}/{total_days}] {date_str} | "
                    f"阶段收益率={stage_return:+.2%} | "
                    f"总市值={tv:,.0f} | "
                    f"持仓额={position_value:,.0f} | "
                    f"持仓数={n_holdings} | "
                    f"已调仓次数={n_rebalances}"
                )

        # 6. 构造 dv_series (weight 模式天然按 trading_dates 顺序, 直接转 Series)
        if all_daily_values:
            dates, vals = zip(*all_daily_values)
            dv_series = pd.Series(vals, index=pd.DatetimeIndex(dates))
        else:
            dv_series = pd.Series(dtype=float)

        # 计算 signal_attribution (weight 模式)
        attribution = self._compute_signal_attribution(all_trades, all_events)

        # === Run summary ===
        wall_time = datetime.now() - t_start
        n_trades = len(all_trades)
        n_wins = sum(1 for t in all_trades if (t.get("pnl") or 0) > 0)
        n_losses = sum(1 for t in all_trades if (t.get("pnl") or 0) < 0)
        self.logger.info(f"=== Run summary ===")
        self.logger.info(f"days processed: {total_days - n_skipped_days}/{total_days}")
        self.logger.info(f"days skipped: {n_skipped_days}")
        self.logger.info(f"rebalances: {n_rebalances}")
        self.logger.info(f"trades: {n_trades} (wins: {n_wins}, losses: {n_losses})")
        self.logger.info(f"wall time: {wall_time}")
        self.logger.info(f"log file: {self.log_file}")

        result = self._build_results(all_trades, all_events, factor_values, dv_series, version=version)
        result.signal_attribution = attribution
        return result

    def _compute_signal_attribution(self, trades, events) -> list[dict]:
        """weight 模式专属: 计算每个信号的 return_share / win_share / loss_share."""
        from collections import defaultdict
        per_sig_pnl: dict[str, list[float]] = defaultdict(list)
        per_sig_wins: dict[str, int] = defaultdict(int)
        per_sig_losses: dict[str, int] = defaultdict(int)
        for t in trades:
            sig = t.get("signal", "unknown")
            pnl = t.get("pnl", 0.0) or 0.0
            per_sig_pnl[sig].append(pnl)
            if pnl > 0:
                per_sig_wins[sig] += 1
            elif pnl < 0:
                per_sig_losses[sig] += 1
        total_pnl = sum(sum(v) for v in per_sig_pnl.values())
        total_wins = sum(per_sig_wins.values())
        total_losses = sum(per_sig_losses.values())
        out = []
        for sig in list(self.spec["entry_signals"]) + list(self.spec["exit_signals"]):
            sig_name = sig["name"]
            pnls = per_sig_pnl.get(sig_name, [])
            sig_pnl = sum(pnls)
            sig_wins = per_sig_wins.get(sig_name, 0)
            sig_losses = per_sig_losses.get(sig_name, 0)
            out.append({
                "signal": sig_name,
                "return_share": sig_pnl / total_pnl if total_pnl else 0.0,
                "win_share": sig_wins / total_wins if total_wins else 0.0,
                "loss_share": sig_losses / total_losses if total_losses else 0.0,
                "net_attribution": sig_pnl / abs(total_pnl) if total_pnl else 0.0,
            })
        return out

    def _build_results(
        self,
        trades: list[dict],
        events: list[dict],
        factor_values: dict[str, list[float]],
        dv_series: pd.Series,
        version: str = "v1",
    ) -> RunResults:
        """从主循环结果构建 RunResults.

        **capital_base 计算**:
        - params 模式: per-stock 投入 = max_single_weight × initial_capital, 实际 = tested × per_stock
        - weight 模式: 全部 initial_capital (1 个组合管理, 不用 per-stock)
        - 无交易 / 无数值时: 用 self.initial_capital (避免除零或极端 annual_return)
        """
        trades_df = pd.DataFrame(trades) if trades else pd.DataFrame(columns=["code", "pnl", "holding_days", "signal"])
        events_df = pd.DataFrame(events) if events else pd.DataFrame(columns=["code", "signal", "action", "pnl", "holding_days"])

        if self.mode == "weight":
            # weight 模式: 整个组合用 initial_capital
            capital_base = self.initial_capital
        else:
            # params 模式: per-stock base = len(self.universe) * per_stock_capital.
            # 必须用 self.universe 长度, 不用 len(tested_codes), 因为 dv_series 是把
            # universe 里所有股票 (含无交易的) 的 daily_value 加总, 所以分母也得对得上.
            per_stock_capital = self.initial_capital * self.params.get("max_single_weight", 0.10)
            if self.universe:
                capital_base = len(self.universe) * per_stock_capital
            else:
                capital_base = self.initial_capital  # 无 universe fallback

        metrics = compute_metrics(capital_base, dv_series, trades_df)

        ss = [compute_signal_stats(s["name"], events_df) for s in self.spec["entry_signals"]]
        ss += [compute_signal_stats(s["name"], events_df) for s in self.spec["exit_signals"]]
        fs = [compute_factor_value_stats(name, pd.Series(vals)) for name, vals in factor_values.items()]

        return RunResults(
            metrics=metrics,
            signal_stats=ss,
            factor_stats=fs,
            trades=trades_df,
            daily_values=dv_series,
            events=events_df,
            version=version,
        )

    # ===== 日期枚举 =====
    def _enumerate_trading_dates(self) -> list[str]:
        from .data_loader import DATA_ROOT
        root = DATA_ROOT / "data-by-day"
        if not root.exists():
            return []
        out: list[str] = []
        for year_dir in sorted(root.iterdir()):
            if not year_dir.is_dir():
                continue
            year = year_dir.name
            for f in sorted(year_dir.iterdir()):
                if f.suffix == ".csv" and f.stem.startswith(f"{year}-"):
                    date = f.stem.split("_")[0]
                    if self.start_date and date < self.start_date:
                        continue
                    if self.end_date and date > self.end_date:
                        continue
                    out.append(date)
        return out

    def _apply_default_date_range_5y(self) -> None:
        """当用户未指定 start_date/end_date 时, 设为"以数据末日为基准往前推 5 年".

        从 data-by-day/ 枚举所有 CSV 文件的日期, 取最晚一天作为 end, 往前推 5 年作为 start.
        这样能保证跑的是"最近 5 年完整数据", 而不是从 2018 跑到 2026 浪费时间.
        """
        from .data_loader import DATA_ROOT
        root = DATA_ROOT / "data-by-day"
        if not root.exists():
            return
        all_dates: list[str] = []
        for year_dir in sorted(root.iterdir()):
            if not year_dir.is_dir():
                continue
            year = year_dir.name
            for f in year_dir.iterdir():
                if f.suffix == ".csv" and f.stem.startswith(f"{year}-"):
                    all_dates.append(f.stem.split("_")[0])
        if not all_dates:
            return
        all_dates.sort()
        end_str = all_dates[-1]
        # start = end - 5 年 (减 1825 天, 含闰年余量)
        end_ts = pd.Timestamp(end_str)
        start_ts = end_ts - pd.Timedelta(days=1825)
        self.start_date = start_ts.strftime("%Y-%m-%d")
        self.end_date = end_str

    def _resolve_report_version(self) -> str:
        """从 strategiesParam/strategiesWeight 读实际用的 version 文件名 (如 "v2").

        之前 write_report 硬编码 "v1", 监控模式下用户改了 v2 报告仍写 v1, 易误判.
        修复: 调 _pick_latest_version 拿真实文件, 提取 v 数字.
        """
        if self.mode == "params":
            vf = self._pick_latest_version("strategiesParam", prefix=f"{self.strategy_name}_v")
        else:
            vf = self._pick_latest_version(
                "strategiesWeight", prefix=f"{self.weight_test}_weight_v"
            )
        if vf is None:
            return "v1"
        # 文件名形如 "ma_cross_atr_volume_v2.md" / "ma_cross_atr_volume_weight_v3.md"
        m = re.search(r"_v(\d+)\.md$", vf.name)
        if m:
            return f"v{m.group(1)}"
        return "v1"

    # ===== 报告 =====
    def _build_test_conditions(self) -> dict:
        """构造测试条件 dict, 报告渲染时显示.

        Returns:
            {
                "test_universe": str (描述来源 + 数量),
                "universe_size": int (实际跑的数量),
                "start_date": str (YYYY-MM-DD 或 "不限"),
                "end_date": str (YYYY-MM-DD 或 "不限"),
                "limit": str (max_stocks 或 "不限"),
                "weight_test": str (weight 模式专用),
            }
        """
        # 测试集来源描述
        if self.test_universe_override is not None:
            tu_desc = f"自定义 {len(self.test_universe_override)} 只"
        else:
            tu_desc = f"spec.test_universe ({len(self.universe)} 只, 默认 HS300)"
        # 实际跑了多少 (受 max_stocks 影响)
        actual_size = len(self.universe)
        if self.max_stocks is not None and self.max_stocks < actual_size:
            tu_desc += f", 实际跑 {actual_size} 只 (受 max_stocks={self.max_stocks} 限制)"

        return {
            "test_universe": tu_desc,
            "universe_size": str(actual_size),
            "start_date": self.start_date or "不限",
            "end_date": self.end_date or "不限",
            "limit": str(self.max_stocks) if self.max_stocks is not None else "不限",
            "weight_test": self.weight_test or "",
        }

    def write_report(
        self,
        results: RunResults,
        output_path: str | Path,
        monitor_meta: dict | None = None,
    ) -> None:
        test_conditions = self._build_test_conditions()
        # === 算实际跑的 version ===
        # 之前硬编码 "v1", 改成从 _pick_latest_version 读, 这样 v2 / v3 的报告能正确标注.
        # weight 模式读 strategiesWeight/ 下的最新, params 模式读 strategiesParam/ 下的最新.
        version_label = self._resolve_report_version()
        if self.mode == "params":
            md = render_params_report(
                strategy=self.strategy_name,
                version=version_label,
                metrics=results.metrics,
                signal_stats=results.signal_stats,
                factor_stats=results.factor_stats,
                monitor_meta=monitor_meta,
                test_conditions=test_conditions,
            )
        else:
            md = render_weight_report(
                strategy=self.strategy_name,
                test_name=self.weight_test or "",
                version=version_label,
                weights=self.weights,
                metrics=results.metrics,
                signal_stats=results.signal_stats,
                factor_stats=results.factor_stats,
                signal_attribution=results.signal_attribution,
                monitor_meta=monitor_meta,
                test_conditions=test_conditions,
            )
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_text(md, encoding="utf-8")


# ===== 工具函数 (别名) =====
def should_rebalance_fn(bar_index: int, freq_bars: int) -> bool:
    """bar_index: 0-based 交易日索引. 在 bar_index = 0, freq, 2*freq, ... 触发."""
    if freq_bars <= 0:
        return False
    return bar_index % freq_bars == 0
