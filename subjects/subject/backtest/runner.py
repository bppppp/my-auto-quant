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
import time
from pathlib import Path
from typing import Any, Literal

import pandas as pd

from .a_share_rules import can_buy, can_buy_at_open, can_sell, can_sell_at_open
from .data_loader import load_day, load_stock
from .fees import calc_buy_fee, calc_sell_fee
from .log_utils import setup_backtest_logger
from .metrics import compute_metrics
from subject.factors._cache import (  # 预计算因子 cache
    bind_current_code, bind_current_date, bind_factor_cache,
    reset_current_code, reset_current_date,
)
from subject.backtest.data_loader.by_stock_factor import (  # 预计算因子 loader
    try_load_stock_factor,
)
from ..parser import parse_strategy_spec
from .portfolio import (
    Portfolio,
    Position,
    enforce_industry_concentration,
    enforce_max_single_weight,
    enforce_max_turnover,
    fill_cash_with_remaining_candidates,
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



def _to_float(value: Any) -> float:
    """安全转 float，处理复数等异常情况."""
    if isinstance(value, complex):
        # 复数取实部
        value = value.real
    try:
        return float(value)
    except (ValueError, TypeError):
        return 0.0


@dataclass
class StockBacktestSummary:
    """单只股票回测汇总结果（用于 top300 筛选）."""

    code: str # 股票代码，含交易所后缀
    name: str           # 股票名称
    annual_return: float  # 年化收益率
    total_return: float   # 总收益率 (final / initial - 1)
    total_pnl: float      # 总盈亏（元）
    win_rate: float        # 胜率
    num_trades: int # 交易次数
    max_drawdown: float # 最大回撤
    holding_days_avg: float  # 平均持仓天数


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

        # === Profiling timing 累加器 (profiler 跑时填, 平时保持空) ===
        self.timing: dict = self._init_timing()

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

    # ===== 热启动天数计算 =====
    _warmup_days: int | None = None  # 类属性缓存，避免重复计算

    def _get_warmup_days(self) -> int:
        """动态计算策略需要的热启动天数。

        通过解析 strategy.py 源代码，提取因子函数调用的最大周期。
        确保加载足够的历史数据，使所有因子在测试期开始时就能产生有效值。

        返回:
            热启动天数 = max(因子周期) + 20 天 buffer
        """
        # 缓存：只计算一次
        if BacktestRunner._warmup_days is not None:
            return BacktestRunner._warmup_days

        import re

        strategy_path = self.subjects_dir / self.strategy_name / "generated" / "strategy.py"
        if not strategy_path.exists():
            BacktestRunner._warmup_days = 70
            return 70

        try:
            code = strategy_path.read_text(encoding="utf-8")
        except Exception:
            BacktestRunner._warmup_days = 70
            return 70

        max_period = 0
        # 匹配 ma(..., N), atr(..., N), rsi(..., N), volume_ratio(..., N), mom(..., N)
        patterns = [
            r'\bma\s*\([^)]+,\s*(\d+)\)',
            r'\batr\s*\([^)]+,\s*(\d+)\)',
            r'\brsi\s*\([^)]+,\s*(\d+)\)',
            r'\bvolume_ratio\s*\([^)]+,\s*(\d+)\)',
            r'\bmom\s*\([^)]+,\s*(\d+)\)',
            r'\bdonchian_high\s*\([^)]+,\s*(\d+)\)',
            r'\bdonchian_low\s*\([^)]+,\s*(\d+)\)',
        ]

        for pattern in patterns:
            for match in re.finditer(pattern, code):
                period = int(match.group(1))
                max_period = max(max_period, period)

        # 至少 20 天 buffer，确保因子稳定
        warmup_days = max(max_period + 20, 70)
        BacktestRunner._warmup_days = warmup_days
        self.logger.info(f"[warmup] 策略最大因子周期: {max_period} 天, 热启动: {warmup_days} 天")
        return warmup_days

    # ===== 加载 =====
    def _load_spec(self) -> dict:
        """加载策略 spec。

        - 优先读 <name>_original.md（Stage A 生成的原版 spec）
        - weight 模式下 _original.md 缺失时，回退到 strategiesWeight/ 最新版本
          （_load_params / _load_weights 在 weight 模式也走 strategiesWeight/，保持一致）
        """
        path = self.subjects_dir / self.strategy_name / f"{self.strategy_name}_original.md"
        if not path.exists() and self.mode == "weight":
            weight_path = self._pick_latest_version(
                "strategiesWeight", prefix=f"{self.weight_test}_weight_v"
            )
            if weight_path is not None:
                return parse_strategy_spec(weight_path)
        return parse_strategy_spec(path)

    def _load_params(self) -> dict:
        """加载参数。

        - params 模式：从 strategiesParam 读取最新 params
        - weight 模式：从 strategiesWeight 读取最新 params（weight 文件中的 params 由 factor_weights 调优）
        """
        if self.mode == "weight":
            version_file = self._pick_latest_version(
                "strategiesWeight", prefix=f"{self.weight_test}_weight_v"
            )
            if version_file is not None:
                spec = parse_strategy_spec(version_file)
                return {p["name"]: p["default"] for p in spec["params"]}
            # weight 文件不存在时 fallback 到 original 的 params
            return {p["name"]: p["default"] for p in self.spec["params"]}

        # params 模式
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
                # === 预计算公共因子 bind (包住整只股的回测) ===
                code6 = code.split(".")[0]
                factor_df = try_load_stock_factor(code6)
                # 关键: factor_df 必须按 df 的日期范围过滤 + 排序 + reset_index,
                # 否则 try_get_cached_factor 的 iloc[:length] 位置切片会取到
                # 错误日期的因子值 (factor_df 是完整历史数据, df 已被 start/end 过滤).
                if factor_df is not None:
                    min_date = df["日期"].min()
                    max_date = df["日期"].max()
                    factor_df = factor_df[
                        (factor_df["日期"] >= min_date) & (factor_df["日期"] <= max_date)
                    ]
                    factor_df = factor_df.sort_values("日期").reset_index(drop=True)
                bind_factor_cache(code6, factor_df)
                token = bind_current_code(code6)
                try:
                    res = self._backtest_single_stock(df, code)
                finally:
                    reset_current_code(token)
                    # 清理因子缓存，防止跨股票泄漏
                    from subject.factors._cache import reset_factor_cache
                    reset_factor_cache()
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
        # 修复 (P0 #3): 不再用 ffill + fillna(0), 改为 sum(min_count=1)
        # - ffill 会把退市股票的最后一日 value 错误地"carry forward"到退市之后所有日期,
        #   虚高 late-period sum, 拉高 final → annual_return 虚高
        # - fillna(0) 把"未上市"和"上市但 value=0"语义混淆
        # 现在: pre-IPO / post-delist / 数据缺口 都用 NaN, sum 跳过 (等价 0 贡献),
        #   全 NaN 的日期 (实际不会发生) 保留为 NaN 而不是 0.
        if per_stock_daily:
            all_dates = sorted(set().union(*[set(s.index) for s in per_stock_daily.values()]))
            agg = pd.concat(
                [s.reindex(pd.DatetimeIndex(all_dates)) for s in per_stock_daily.values()],
                axis=1,
            )
            agg.columns = list(per_stock_daily.keys())
            dv_series = agg.sum(axis=1, min_count=1)
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

    # ===== Top300 筛选专用方法 =====

    @staticmethod
    def _init_timing() -> dict:
        """初始化 profiling 累加器 (8 个区段)."""
        return {
            "load_stock_io": [],          # P1: 每次 load_stock 耗时 (秒)
            "load_stock_cache_hits": 0,    # P1: 命中次数
            "load_stock_cache_misses": 0,  # P1: miss 次数
            "try_load_factor": [],         # P2: 每次 try_load_stock_factor 耗时
            "factor_precomputed_hits": 0,  # P2: 预计算命中
            "factor_realtime_misses": 0,   # P2: 预计算未命中 → 实时算
            "warmup": [],                  # P3: 单股 warmup 阶段耗时
            "main_loop": [],               # P4: 单股 _backtest_single_stock 整段
            "compute_factors_per_bar": [], # P5: per-bar compute_factors (秒)
            "signal_eval_per_bar": [],     # P6: per-bar should_exit + entry_score + triggered
            "n_bars_total": 0,             # P5/P6 累计 bar 数
            "n_stocks": 0,                 # P1-P4 累计 stock 数
        }

    def _dump_timing_to_json(self, path: str, total_wall_s: float | None = None) -> dict:
        """聚合 timing 数据 + 写 JSON 文件. Returns summary dict."""
        import json as _json
        t = self.timing
        from .data_loader.by_stock_factor import get_factor_cache_stats
        from subject.factors._cache import get_aggregate_cache_stats

        factor_hits, factor_misses = get_aggregate_cache_stats()
        stock_hits = t["load_stock_cache_hits"]
        stock_misses = t["load_stock_cache_misses"]

        def _stats(arr: list[float]) -> dict:
            if not arr:
                return {"n": 0, "total_s": 0.0, "mean_s": 0.0, "p50_s": 0.0, "p95_s": 0.0, "p99_s": 0.0}
            s = sorted(arr)
            n = len(s)
            return {
                "n": n,
                "total_s": round(sum(s), 4),
                "mean_s": round(sum(s) / n, 6),
                "p50_s": round(s[n // 2], 6),
                "p95_s": round(s[min(n - 1, int(n * 0.95))], 6),
                "p99_s": round(s[min(n - 1, int(n * 0.99))], 6),
            }

        def _stats_us(arr: list[float]) -> dict:
            """per-bar 数据转 μs."""
            s = _stats(arr)
            if s["n"] == 0:
                return s
            return {
                "n": s["n"],
                "total_us": round(s["total_s"] * 1e6, 2),
                "mean_us": round(s["mean_s"] * 1e6, 2),
                "p50_us": round(s["p50_s"] * 1e6, 2),
                "p95_us": round(s["p95_s"] * 1e6, 2),
                "p99_us": round(s["p99_s"] * 1e6, 2),
            }

        summary = {
            "wall_time_s": round(total_wall_s, 3) if total_wall_s else None,
            "n_stocks": t["n_stocks"],
            "n_bars_total": t["n_bars_total"],
            "load_stock_io": _stats(t["load_stock_io"]),
            "load_stock_cache": {
                "hits": stock_hits,
                "misses": stock_misses,
                "hit_rate_pct": round(stock_hits / max(1, stock_hits + stock_misses) * 100, 2),
            },
            "try_load_factor": _stats(t["try_load_factor"]),
            "factor_precompute": {
                "precomputed_hits": t["factor_precomputed_hits"],
                "realtime_misses": t["factor_realtime_misses"],
                "precompute_coverage_pct": round(
                    t["factor_precomputed_hits"] / max(1, t["n_stocks"]) * 100, 2
                ),
            },
            "warmup": _stats(t["warmup"]),
            "main_loop": _stats(t["main_loop"]),
            "compute_factors_per_bar_us": _stats_us(t["compute_factors_per_bar"]),
            "signal_eval_per_bar_us": _stats_us(t["signal_eval_per_bar"]),
            "factor_cache_per_bar": {
                "hits": factor_hits,
                "misses": factor_misses,
                "hit_rate_pct": round(
                    factor_hits / max(1, factor_hits + factor_misses) * 100, 2
                ),
            },
        }

        # 占比
        if total_wall_s:
            cat = {
                "load_stock_io": summary["load_stock_io"]["total_s"],
                "try_load_factor": summary["try_load_factor"]["total_s"],
                "warmup": summary["warmup"]["total_s"],
                "main_loop": summary["main_loop"]["total_s"],
            }
            summary["pct_of_wall"] = {
                k: round(v / total_wall_s * 100, 2) for k, v in cat.items()
            }
            known = sum(cat.values())
            summary["pct_of_wall"]["other"] = round(
                max(0.0, (total_wall_s - known) / total_wall_s * 100), 2
            )

        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(_json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        return summary

    @staticmethod
    def get_all_stock_codes() -> list[str]:
        """获取 data-by-stock/ 下全部股票代码列表（含交易所后缀）.

        Returns:
            股票代码列表，如 ["000001.SZ", "000002.SZ", ...]
        """
        from .data_loader import DATA_ROOT
        stock_dir = DATA_ROOT / "data-by-stock"
        if not stock_dir.exists():
            return []
        codes = []
        for f in stock_dir.iterdir():
            if f.suffix == ".csv" and "_金玥数据" in f.name:
                # 文件名格式: XXXXXX_金玥数据.csv
                code6 = f.stem.split("_")[0]
                # 根据代码前缀判断交易所
                if code6.startswith("6"):
                    exchange = "SH"
                elif code6.startswith(("0", "3")):
                    exchange = "SZ"
                elif code6.startswith("8") or code6.startswith("4"):
                    exchange = "BJ"
                else:
                    exchange = "SZ"
                codes.append(f"{code6}.{exchange}")
        return sorted(codes)

    def backtest_all_stocks_summary(
        self,
        all_codes: list[str] | None = None,
        min_bars: int | None = None,
    ) -> list[StockBacktestSummary]:
        """遍历全部股票，返回每只的年化收益率汇总（用于 top300 筛选）.

        Args:
            all_codes: 股票代码列表，默认使用全部股票
            min_bars: 最小 K 线数，默认使用 self.min_bars

        Returns:
            StockBacktestSummary 列表，按 annual_return 降序排列
        """
        import math

        if all_codes is None:
            all_codes = self.get_all_stock_codes()
        if min_bars is None:
            min_bars = self.min_bars

        results: list[StockBacktestSummary] = []
        total = len(all_codes)
        self.logger.info(f"=== top300 scan: processing {total} stocks ===")
        skipped_data_missing = 0
        skipped_too_few = 0
        t_start = datetime.now()

        #进度日志: 每 5% 汇总一次
        log_every_n = max(1, total // 20)
        next_log_at = log_every_n

        for i, code in enumerate(all_codes, 1):
            code6 = code.split(".")[0]

            # ===== P1: load_stock I/O + cache 统计 =====
            t1 = time.perf_counter()
            try:
                df = load_stock(code6)
            except FileNotFoundError:
                self.logger.warning(f"[{i}/{total}] {code} - data not found")
                skipped_data_missing += 1
                continue
            load_dt = time.perf_counter() - t1
            self.timing["load_stock_io"].append(load_dt)
            # 区分冷启/热启: 0.05s 阈值 (冷启 ~30ms+, 热启 ~1ms)
            if load_dt < 0.005:
                self.timing["load_stock_cache_hits"] += 1
            else:
                self.timing["load_stock_cache_misses"] += 1

            # 退市过滤：从全量数据检查（直接用已加载的 df）
            if "退市时间" in df.columns and df["退市时间"].notna().any():
                delist_df = df.dropna(subset=["退市时间"])
                if len(delist_df) > 0:
                    last_row = delist_df.iloc[-1]
                    delist_date = last_row["退市时间"]
                    test_end_date = df["日期"].max()
                    if pd.notna(delist_date) and delist_date <= test_end_date:
                        # 该股票已退市，跳过
                        skipped_too_few += 1
                        continue

            # 获取股票名称（从已加载数据中获取，无需重新加载）
            name = ""
            if "名称" in df.columns and len(df) > 0:
                name = df["名称"].iloc[0]

            # 日期过滤
            if self.start_date:
                df = df[df["日期"] >= pd.Timestamp(self.start_date)]
            if self.end_date:
                df = df[df["日期"] <= pd.Timestamp(self.end_date)]
            df = df.sort_values("日期").reset_index(drop=True)
            if len(df) < min_bars:
                skipped_too_few += 1
                continue

            try:
                # ===== P2: try_load_stock_factor 预计算命中检测 =====
                t2 = time.perf_counter()
                factor_df = try_load_stock_factor(code6)
                factor_load_dt = time.perf_counter() - t2
                self.timing["try_load_factor"].append(factor_load_dt)
                if factor_df is not None:
                    self.timing["factor_precomputed_hits"] += 1
                    min_date = df["日期"].min()
                    max_date = df["日期"].max()
                    factor_df = factor_df[
                        (factor_df["日期"] >= min_date) & (factor_df["日期"] <= max_date)
                    ]
                    factor_df = factor_df.sort_values("日期").reset_index(drop=True)
                else:
                    self.timing["factor_realtime_misses"] += 1
                bind_factor_cache(code6, factor_df)
                token = bind_current_code(code6)
                try:
                    # ===== P4: 单股整段回测 =====
                    t4 = time.perf_counter()
                    res = self._backtest_single_stock(df, code)
                    self.timing["main_loop"].append(time.perf_counter() - t4)
                    self.timing["n_stocks"] += 1
                finally:
                    reset_current_code(token)
                    # 清理因子缓存，防止跨股票泄漏
                    from subject.factors._cache import reset_factor_cache
                    reset_factor_cache()
            except Exception as e:
                self.logger.error(f"[{i}/{total}] {code} - backtest failed: {e}")
                continue

            # 计算该股的年化收益率
            # P1 #4 修复: per_stock_capital 不再乘 max_single_weight
            # 旧版: per_stock_capital = initial_capital * max_single_weight (3 万)
            #   - 含义错位: max_single_weight 是"组合内单票上限" (weight 模式用),
            #     不应被当作"单股本金" (params 模式用)
            #   - 导致 params 与 weight 模式调 max_single_weight 行为不一致
            # 新版: per_stock_capital = initial_capital, 每只股票独立用全部本金回测
            #   - 这把 params 模式变成"信号纯度测试": 若把 30 万全押一只股按信号交易, 收益如何
            #   - 与 weight 模式的"组合管理 + 调仓 + 行业约束"维度正交
            per_stock_capital = self.initial_capital
            trades = res["trades"]
            daily_values = res["daily_values"]

            if daily_values:
                dates, vals = zip(*daily_values)
                dv_series = pd.Series(vals, index=pd.DatetimeIndex(dates))
                initial = per_stock_capital
                final = float(dv_series.iloc[-1])
                n_days = (dv_series.index[-1] - dv_series.index[0]).days
                n_days = max(n_days, 1)
                annual_return = (final / initial) ** (365.0 / n_days) - 1.0
                total_return = (final / initial) - 1.0
            else:
                annual_return = 0.0
                total_return = 0.0

            # 计算 PnL、胜率等
            total_pnl = sum(t.get("pnl", 0) or 0 for t in trades)
            pnls = [t.get("pnl", 0) or 0 for t in trades]
            n_wins = sum(1 for p in pnls if p > 0)
            win_rate = n_wins / len(pnls) if pnls else 0.0

            # 平均持仓天数
            holding_days = [t.get("holding_days", 0) or 0 for t in trades]
            holding_days_avg = sum(holding_days) / len(holding_days) if holding_days else 0.0

            # 最大回撤（从 daily_values 计算）
            max_drawdown = 0.0
            if daily_values:
                dates, vals = zip(*daily_values)
                dv_series = pd.Series(vals, index=pd.DatetimeIndex(dates))
                peaks = dv_series.cummax()
                drawdowns = (dv_series - peaks) / peaks
                max_drawdown = float(drawdowns.min())

            results.append(StockBacktestSummary(
                code=code,
                name=name,
                annual_return=_to_float(annual_return),
                total_return=_to_float(total_return),
                total_pnl=float(total_pnl),
                win_rate=float(win_rate),
                num_trades=len(trades),
                max_drawdown=float(max_drawdown),
                holding_days_avg=float(holding_days_avg),
            ))

            # 5% 汇总日志
            if i >= next_log_at or i == total:
                pct = i / total * 100
                self.logger.info(f"[stock {i}/{total}] {pct:.0f}% done | results={len(results)}")
                while next_log_at <= i:
                    next_log_at += log_every_n

        # 按年化收益率降序排列
        results.sort(key=lambda x: x.annual_return, reverse=True)

        # 检查有效结果是否少于 300 只
        total_skipped = skipped_data_missing + skipped_too_few
        if len(results) < 300:
            self.logger.warning(
                f"[top300] ⚠️ 有效股票仅 {len(results)} 只 (< 300), "
                f"可能原因: 数据缺失({skipped_data_missing}) / 退市({skipped_too_few}) / 时间范围"
            )

        wall_time = datetime.now() - t_start
        self.logger.info(f"=== top300 scan complete ===")
        self.logger.info(f"total stocks: {total}, processed: {len(results)}, skipped: {skipped_data_missing + skipped_too_few}")
        self.logger.info(f"wall time: {wall_time}")

        # 打印缓存统计
        from .data_loader.by_stock import get_cache_stats
        from .data_loader.by_stock_factor import get_factor_cache_stats
        stock_hits, stock_misses = get_cache_stats()
        factor_hits, factor_misses = get_factor_cache_stats()
        total_requests = stock_hits + stock_misses
        if total_requests > 0:
            stock_hit_rate = stock_hits / total_requests * 100
            self.logger.info(f"📦 数据缓存: hits={stock_hits}, misses={stock_misses}, hit_rate={stock_hit_rate:.1f}%")
        total_factor_requests = factor_hits + factor_misses
        if total_factor_requests > 0:
            factor_hit_rate = factor_hits / total_factor_requests * 100
            self.logger.info(f"📦 因子缓存: hits={factor_hits}, misses={factor_misses}, hit_rate={factor_hit_rate:.1f}%")

        return results

    def _backtest_single_stock(self, df: pd.DataFrame, code: str) -> dict:
        """单只股票时间序列回测.

        **执行时序 (T-1 因子 + T 开盘交易)**
        1. 跳过 Bar[0] (无 T-1 数据, 不能交易)
        2. compute_factors(df.iloc[:i]) → 用 T-1 及之前数据
        3. should_exit / entry_score 用 T-1 因子决策
        4. 用 bar[i].open 成交 (而非 close, 避免 look-ahead)
        5. 收盘时更新 highest / holding_days, 记录 daily_value
        6. 期末 (Bar[-1]) 强制平仓

        资金视角: 每只股票从 ``per_stock_capital`` 开始, 累计已实现 PnL 持续累加.
        无持仓时 value = per_stock_capital + cumulative_pnl.
        有持仓时 value = per_stock_capital + cumulative_pnl + (close - entry) * shares.
        """
        # === 热启动: 为因子计算加载足够的 lookback 数据 ===
        # 动态计算策略需要的最大因子窗口，避免硬编码
        warmup_days = self._get_warmup_days()
        # ===== P3: warmup 阶段耗时 =====
        t3 = time.perf_counter()
        if self.start_date is not None and len(df) > 0:
            test_start = pd.Timestamp(self.start_date)
            warmup_start = test_start - pd.Timedelta(days=warmup_days)
            # 重新从完整历史加载, 取 warmup_start之后的全部数据
            try:
                full_df = load_stock(code.split(".")[0])
                warmup_df = full_df[full_df["日期"] >= warmup_start]
                # 修复 (P0 新发现): 截到 end_date 之前, 避免 daily_values 跨测试期
                if self.end_date is not None:
                    warmup_df = warmup_df[warmup_df["日期"] <= pd.Timestamp(self.end_date)]
                if len(warmup_df) >= warmup_days:
                    df = warmup_df.sort_values("日期").reset_index(drop=True)
                    # === 修复: warmup 后重新绑定因子缓存 ===
                    # 否则 factor cache 长度(不含 warmup) 与 df长度(含 warmup) 不匹配,
                    # 导致 try_get_cached_factor 每次都 miss 并打印 warning.
                    code6 = code.split(".")[0]
                    factor_df = try_load_stock_factor(code6)
                    if factor_df is not None:
                        factor_min_date = df["日期"].min()
                        factor_max_date = df["日期"].max()
                        factor_df = factor_df[
                            (factor_df["日期"] >= factor_min_date) &
                            (factor_df["日期"] <= factor_max_date)
                        ]
                        factor_df = factor_df.sort_values("日期").reset_index(drop=True)
                    bind_factor_cache(code6, factor_df)
            except Exception:
                # 回退到原始 df (数据不够长)
                pass
        self.timing["warmup"].append(time.perf_counter() - t3)

        trades: list[dict] = []
        events: list[dict] = []
        factor_values: dict[str, list[float]] = {}
        daily_values: list[tuple[pd.Timestamp, float]] = []
        pos: Position | None = None
        # P1 #4 修复: per_stock_capital 不再乘 max_single_weight
        # 旧版: per_stock_capital = initial_capital * max_single_weight (3 万)
        #   - 含义错位: max_single_weight 是"组合内单票上限" (weight 模式用),
        #     不应被当作"单股本金" (params 模式用)
        #   - 导致 params 与 weight 模式调 max_single_weight 行为不一致
        # 新版: per_stock_capital = initial_capital, 每只股票独立用全部本金回测
        #   - 这把 params 模式变成"信号纯度测试": 若把 30 万全押一只股按信号交易, 收益如何
        #   - 与 weight 模式的"组合管理 + 调仓 + 行业约束"维度正交
        per_stock_capital = self.initial_capital
        cumulative_pnl: float = 0.0  # 累计已实现 PnL
        prev_close: float | None = None  # T-1 收盘价 (供 T 日开盘执行/limit 判断用)

        for i in range(len(df)):
            bar = df.iloc[i]
            date: pd.Timestamp = bar["日期"]
            open_px: float = float(bar["开盘价"])
            close: float = float(bar["收盘价"])

            # 1. 跳过 Bar[0] (无 T-1 数据), 只记录初始 value
            if i == 0:
                daily_values.append((date, per_stock_capital))
                prev_close = close
                continue

            # 2. compute_factors (用 T-1 数据, 即 df.iloc[:i], 不含今天的 Bar[i])
            #    设置 T-1 日期用于因子缓存的日期精确匹配 (v2 修复)
            t1_date = df.iloc[i - 1]["日期"]
            date_token = bind_current_date(t1_date)
            # ===== P5: per-bar compute_factors =====
            t5 = time.perf_counter()
            try:
                factors = self.strategy.compute_factors(df.iloc[:i], self.params)
                self.timing["compute_factors_per_bar"].append(time.perf_counter() - t5)
                self.timing["n_bars_total"] += 1
            except Exception as e:
                reset_current_date(date_token)
                events.append({"code": code, "signal": "compute_factors", "action": "skipped", "error": str(e), "pnl": None, "holding_days": None})
                # 因子计算失败, 仍记录 daily_value (维持仓位估值)
                if pos is not None:
                    unrealized = (close - pos.entry_price) * pos.shares
                    value = per_stock_capital + cumulative_pnl + unrealized
                else:
                    value = per_stock_capital + cumulative_pnl
                daily_values.append((date, value))
                pos.highest = max(pos.highest, close) if pos is not None else None
                if pos is not None:
                    # P2 #5 修复: holding_days 统一为 1-based 交易日
                    if pos.entry_bar_idx >= 0:
                        pos.holding_days = i - pos.entry_bar_idx + 1
                prev_close = close
                continue
            for k, v in factors.items():
                if isinstance(v, pd.Series) and len(v) > 0 and not pd.isna(v.iloc[-1]):
                    factor_values.setdefault(k, []).append(float(v.iloc[-1]))
            reset_current_date(date_token)  # v2 修复: 因子计算完成后 reset 日期

            # 3. 检查出场 → at bar[i].open 成交
            # ===== P6: per-bar signal eval (should_exit + entry_score + triggered) =====
            t6 = time.perf_counter()
            if pos is not None:
                # pos_dict 用 prev_close (T-1 收盘) 作为 "当前价格"
                # - 决策时点: T-1 收盘后, 还没到 T 开盘
                # - 所以策略看到的 "当前价" 应该是 T-1 收盘价
                pos_dict = pos.to_state_dict()
                pos_dict["current_price"] = prev_close
                pos_dict["pnl_pct"] = (prev_close - pos.entry_price) / pos.entry_price if pos.entry_price > 0 else 0.0
                try:
                    exit_sig = self.strategy.should_exit(pos_dict, factors, self.params, self.weights)
                except Exception:
                    exit_sig = None
                if exit_sig:
                    if can_sell_at_open(bar, prev_close, code):
                        # PnL 用 open 价 (T 开盘成交)
                        sell_amount = open_px * pos.shares
                        pnl = (open_px - pos.entry_price) * pos.shares - calc_sell_fee(sell_amount, code)
                        cumulative_pnl += pnl
                        trades.append({"code": code, "pnl": pnl, "holding_days": pos.holding_days, "signal": exit_sig})
                        events.append({"code": code, "signal": exit_sig, "action": "executed", "pnl": pnl, "holding_days": pos.holding_days})
                        if pos.entry_signals:
                            for sig_name in pos.entry_signals:
                                events.append({"code": code, "signal": sig_name, "action": "exit_linked", "pnl": pnl, "holding_days": pos.holding_days})
                        pos = None
                    else:
                        events.append({"code": code, "signal": exit_sig, "action": "swallowed", "pnl": None, "holding_days": pos.holding_days})

            # 4. 检查入场 → at bar[i].open 成交
            if pos is None:
                try:
                    score = self.strategy.entry_score(factors, self.params, self.weights)
                except Exception:
                    score = 0
                if score > 0 and can_buy_at_open(bar, prev_close, code):
                    amount = per_stock_capital
                    shares = int(amount / open_px / 100) * 100
                    if shares > 0:
                        fee = calc_buy_fee(shares * open_px, code)
                        effective_entry = (shares * open_px + fee) / shares
                        triggered_signals = self.strategy.get_triggered_signals(factors, self.params, self.weights)
                        pos = Position(
                            code=code, shares=shares,
                            entry_price=effective_entry, entry_date=date,
                            highest=open_px, holding_days=0,
                            entry_signals=triggered_signals,
                            # P2 #5: 记录入场 bar 索引, 后续 holding_days 用 bar 差算 1-based 交易日
                            entry_bar_idx=i,
                        )
                        # P2 #5: holding_days 改为 1-based 交易日 (与 weight 模式一致)
                        # entry 当日 = 1, 次日 = 2, ...
                        pos.holding_days = 1
                        events.append({"code": code, "signal": "entry_combined", "action": "executed", "pnl": None, "holding_days": 1})
                        for sig_name in triggered_signals:
                            # P2 #5: entry 当日的 triggered 事件 holding_days 也用 1
                            events.append({"code": code, "signal": sig_name, "action": "triggered", "pnl": None, "holding_days": 1})
            # ===== P6 收尾: 每个 bar 都累计 signal eval 耗时 =====
            self.timing["signal_eval_per_bar"].append(time.perf_counter() - t6)

            # 5. 收盘更新 highest / holding_days + 记录 daily value
            if pos is not None:
                pos.highest = max(pos.highest, close)
                # P2 #5 修复: holding_days 改为 1-based 交易日 (与 weight 模式一致)
                # 旧版用 (date - entry_date).days 是日历日, 周末/节假日也算 1 天
                # 新版用 bar 索引差, 跨模式统一口径
                if pos.entry_bar_idx >= 0:
                    pos.holding_days = i - pos.entry_bar_idx + 1
                unrealized = (close - pos.entry_price) * pos.shares
                value = per_stock_capital + cumulative_pnl + unrealized
            else:
                value = per_stock_capital + cumulative_pnl
            daily_values.append((date, value))
            prev_close = close

        # 6. 期末强制平仓 (防止 Bar[-1] 触发出场但无法 T+1 开盘成交的"挂单"被丢弃)
        # 用 Bar[-1].close 估算当日价值后清仓
        if pos is not None:
            last_bar = df.iloc[-1]
            last_close = float(last_bar["收盘价"])
            last_date = last_bar["日期"]
            # 期末 PnL 用 last_close 结算
            pnl = (last_close - pos.entry_price) * pos.shares - calc_sell_fee(last_close * pos.shares, code)
            cumulative_pnl += pnl
            trades.append({"code": code, "pnl": pnl, "holding_days": pos.holding_days, "signal": "end_of_data"})
            events.append({"code": code, "signal": "end_of_data", "action": "executed", "pnl": pnl, "holding_days": pos.holding_days})
            if pos.entry_signals:
                for sig_name in pos.entry_signals:
                    events.append({"code": code, "signal": sig_name, "action": "exit_linked", "pnl": pnl, "holding_days": pos.holding_days})
            pos = None
            # 修复: 把 daily_values 最后一帧同步到 final_cash (= per_stock_capital + cumulative_pnl),
            # 否则 diff = unrealized PnL 残留 (跟 weight 模式 P3-新 3 修复同源)
            if daily_values:
                daily_values[-1] = (last_date, per_stock_capital + cumulative_pnl)

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
        # P3 #7 修复: 追踪组合的日高/日低 (用于日内 max_drawdown)
        # 组合 high = Σ(shares × high_price) over 持仓股
        # 组合 low  = Σ(shares × low_price)  over 持仓股
        all_daily_high: list[tuple[pd.Timestamp, float]] = []
        all_daily_low: list[tuple[pd.Timestamp, float]] = []
        # B1/B2 fix: 跟踪最近一次成功加载的 prices.
        # 用途: (1) 跳过日补 daily_value (避免序列空洞) (2) 期末强平未覆盖的代码 fallback.
        last_prices: dict[str, float] = {}

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

        # === 预计算公共因子 preload (与 stock_history 并行加载, 缺则不存) ===
        # 关键: factor_df 必须按 stock_history[code] 的日期范围过滤 + 排序 + reset_index,
        # 否则 try_get_cached_factor 的 iloc[:length] 位置切片会取到错误日期的因子值
        # (stock_history 已带 buffer 过滤日期, factor_df 是完整历史数据).
        stock_factor_history: dict[str, pd.DataFrame] = {}
        for code in stock_history:
            factor_df = try_load_stock_factor(code.split(".")[0])
            if factor_df is not None:
                hist = stock_history[code]
                min_date = hist["日期"].min()
                max_date = hist["日期"].max()
                factor_df = factor_df[
                    (factor_df["日期"] >= min_date) & (factor_df["日期"] <= max_date)
                ]
                factor_df = factor_df.sort_values("日期").reset_index(drop=True)
                stock_factor_history[code.split(".")[0]] = factor_df
        self.logger.info(
            f"preloaded factors for {len(stock_factor_history)}/{len(stock_history)} stocks"
        )

        freq = int(self.params.get("rebalance_freq_days", 5))
        target_n = int(self.params.get("target_holdings", 8))
        max_single = float(self.params.get("max_single_weight", 0.10))
        max_industry = float(self.params.get("max_industry_concentration", 0.30))
        max_turnover = float(self.params.get("max_turnover_per_rebalance", 0.50))

        # P1 #6 修复: 移除 bear_market 死代码. spec 里的 bear_drawdown_threshold
        # 参数保留 (spec 不可修改), 但 engine 不再读取/使用. 等后续接入沪深 300
        # 指数数据后再激活.

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
                # B2 fix: 跳过日仍记录 daily_value (用 last_prices), 避免 pct_change 跨日跳变.
                # 若 last_prices 为空 (首日即缺失), 用空 dict — portfolio.total_value 会回退到 cash.
                tv = portfolio.total_value(last_prices)
                all_daily_values.append((date, tv))
                continue
            df = exclude_bj(df)
            df = exclude_st(df)
            df = df[df["代码"].isin(set(self.universe))].copy()
            df = df.reset_index(drop=True)
            if len(df) == 0:
                n_skipped_days += 1
                # B2 fix: 同上
                tv = portfolio.total_value(last_prices)
                all_daily_values.append((date, tv))
                continue
            day_data: dict[str, pd.Series] = {row["代码"]: row for _, row in df.iterrows()}
            prices: dict[str, float] = {code: float(r["收盘价"]) for code, r in day_data.items()}
            last_prices = prices  # B1 fix: 记录最新有效 prices, 供期末强平使用

            # === T-1 因子模型: Bar[0] (bar_idx=1) 无 T-1 数据, 跳过所有交易, 只记录初始 value ===
            if bar_idx == 1:
                tv = portfolio.total_value(prices)
                all_daily_values.append((date, tv))
                if bar_idx == 1 or bar_idx % log_every_n_days == 0 or bar_idx == total_days:
                    stage_return = (tv / self.initial_capital) - 1.0
                    self.logger.info(
                        f"[day {bar_idx}/{total_days}] {date_str} | "
                        f"阶段收益率={stage_return:+.2%} | "
                        f"总市值={tv:,.0f} | "
                        f"持仓数=0 | 已调仓次数=0 (day 0: 初始化, 无 T-1 数据)"
                    )
                continue

            # 2. 算因子 + entry score
            # 关键: 用 T-1 数据 (hist.iloc[:idx_today], 不含今天), 决策基于 T-1 收盘后的视角.
            scores: dict[str, float] = {}
            factors_by_code: dict[str, dict] = {}
            prev_close_by_code: dict[str, float] = {}  # T-1 收盘价 (供 T 日开盘成交/limit 判断用)
            for code, row in day_data.items():
                if code not in stock_history:
                    continue
                hist = stock_history[code]
                # 找 hist 中 date <= today (T) 的最大索引
                mask = hist["日期"] <= date
                if not mask.any():
                    continue
                idx_today = hist.index[mask][-1]  # 最后一个 <= today 的位置
                if idx_today == 0:
                    # T 是 hist 中的第 1 行, 没有 T-1 数据, 跳过
                    continue
                hist_t1 = hist.iloc[:idx_today]  # T-1 及之前的历史
                # T-1 收盘价 (用于 can_buy_at_open / can_sell_at_open 和 pos_dict.current_price)
                prev_close_by_code[code] = float(hist_t1["收盘价"].iloc[-1])
                # === 预计算公共因子 bind ===
                code6 = code.split(".")[0]
                factor_df = stock_factor_history.get(code6)
                bind_factor_cache(code6, factor_df)
                token = bind_current_code(code6)
                # === v2 修复: 设置 T-1 日期用于因子缓存的日期精确匹配 ===
                t1_date = hist_t1["日期"].iloc[-1]
                date_token = bind_current_date(t1_date)
                try:
                    factors = self.strategy.compute_factors(hist_t1, self.params)
                except Exception as e:
                    reset_current_date(date_token)
                    reset_current_code(token)
                    all_events.append({
                        "code": code, "signal": "compute", "action": "skipped",
                        "error": str(e), "pnl": None, "holding_days": None,
                    })
                    continue
                reset_current_date(date_token)  # v2 修复
                reset_current_code(token)
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

            # 3. 检查出场 (用 T-1 因子决策, at bar[i].open 成交)
            # 重要: 先检查 exit，再用 update_after_bar 更新 highest（与 params 模式一致）
            for code in list(portfolio.positions.keys()):
                if code not in day_data:
                    continue
                if code not in factors_by_code or code not in prev_close_by_code:
                    continue
                pos = portfolio.positions[code]
                bar_series = day_data[code]
                open_px = float(bar_series["开盘价"])
                close = float(bar_series["收盘价"])
                prev_close = prev_close_by_code[code]

                factors = factors_by_code[code]
                pos_dict = pos.to_state_dict()
                pos_dict["current_price"] = prev_close  # 决策时看到的"当前价" = T-1 收盘
                pos_dict["pnl_pct"] = (prev_close - pos.entry_price) / pos.entry_price if pos.entry_price > 0 else 0.0
                try:
                    exit_sig = self.strategy.should_exit(pos_dict, factors, self.params, self.weights)
                except Exception:
                    exit_sig = None
                if exit_sig:
                    if can_sell_at_open(bar_series, prev_close, code):
                        # PnL 需扣 sell_fee. 用 open 价 (T 开盘成交).
                        sell_amount = open_px * pos.shares
                        pnl = (open_px - pos.entry_price) * pos.shares - calc_sell_fee(sell_amount, code)
                        _, sold_pos = portfolio.sell(code, open_px, date)
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

            # 收盘后更新所有剩余持仓的 highest 和 holding_days（exit 检查之后，与 params 模式一致）
            for code in list(portfolio.positions.keys()):
                if code in day_data:
                    close = float(day_data[code]["收盘价"])
                    portfolio.update_after_bar(code, close)

            # 4. 调仓日
            if should_rebalance_fn(bar_idx, freq):
                top_codes = rank_top_n(scores, target_n, seed=42)
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
                    # P3 #9/#11 修复: cash 沉淀 → 用剩余候选股填满
                    # 如果 turnover 限制或行业约束导致 target_weights sum < 1,
                    # 从 scores 里按 score 降序挑选候选补齐
                    try:
                        target_weights = fill_cash_with_remaining_candidates(
                            target_weights=target_weights,
                            scores=scores,
                            target_n=target_n,
                            max_single=max_single,
                            industry_map=industry_map,
                            max_industry=max_industry,
                        )
                    except Exception as e:
                        self.logger.warning(f"[{date_str}] fill_cash failed: {e}")

                    tv = portfolio.total_value(prices)
                    # 卖出不在 target 的 (at open)
                    for code in list(portfolio.positions.keys()):
                        if code not in target_weights:
                            if code in day_data and code in prev_close_by_code:
                                pos = portfolio.positions[code]
                                bar_series = day_data[code]
                                prev_close = prev_close_by_code[code]
                                if can_sell_at_open(bar_series, prev_close, code):
                                    open_px = float(bar_series["开盘价"])
                                    # PnL 需扣 sell_fee (同 exit 卖出)
                                    sell_amount = open_px * pos.shares
                                    pnl = (open_px - pos.entry_price) * pos.shares - calc_sell_fee(sell_amount, code)
                                    _, sold_pos = portfolio.sell(code, open_px, date)
                                    all_trades.append({
                                        "code": code, "pnl": pnl,
                                        "holding_days": pos.holding_days, "signal": "rebalance",
                                    })
                                    all_events.append({
                                        "code": code, "signal": "rebalance_out", "action": "executed",
                                        "pnl": pnl, "holding_days": pos.holding_days,
                                    })
                                    # Bug #1 修复: 调仓卖出也要为触发入场的 entry signals 补 exit_linked 事件
                                    # (与正常 exit 块 (line 1310-1315) 和期末强平块 (line 1502-1508) 对齐)
                                    if sold_pos and sold_pos.entry_signals:
                                        for sig_name in sold_pos.entry_signals:
                                            all_events.append({
                                                "code": code, "signal": sig_name, "action": "exit_linked",
                                                "pnl": pnl, "holding_days": pos.holding_days,
                                            })
                    # 买入新增的 (at open)
                    for code, weight in target_weights.items():
                        if code in portfolio.positions:
                            continue
                        if code not in day_data or code not in prev_close_by_code:
                            continue
                        bar_series = day_data[code]
                        prev_close = prev_close_by_code[code]
                        if not can_buy_at_open(bar_series, prev_close, code):
                            all_events.append({
                                "code": code, "signal": "entry", "action": "skipped",
                                "reason": "limit_up_at_open", "pnl": None, "holding_days": None,
                            })
                            continue
                        open_px = float(bar_series["开盘价"])
                        amount = tv * weight
                        shares = int(amount / open_px / 100) * 100
                        if shares > 0:
                            # 获取触发入场的信号列表（调用策略方法）
                            if code in factors_by_code:
                                triggered_signals = self.strategy.get_triggered_signals(
                                    factors_by_code[code], self.params, self.weights
                                )
                            else:
                                triggered_signals = []
                            actual, cost = portfolio.buy(code, open_px, shares, date, entry_signals=triggered_signals)
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

            # P3 #7: 记录组合日内 high/low (用于日内 max_drawdown)
            # 计算逻辑: 组合 high = cash + Σ(shares × high), 组合 low = cash + Σ(shares × low)
            # cash 不受价格波动影响, 持仓部分按当日 high/low 估
            if portfolio.positions:
                port_high = portfolio.cash
                port_low = portfolio.cash
                for code, pos in portfolio.positions.items():
                    if code in day_data:
                        h = float(day_data[code].get("最高价", pos.entry_price))
                        l = float(day_data[code].get("最低价", pos.entry_price))
                        port_high += pos.shares * h
                        port_low += pos.shares * l
                    else:
                        # 横截面缺失: 用 entry_price 兜底 (此时 high == low == entry)
                        port_high += pos.shares * pos.entry_price
                        port_low += pos.shares * pos.entry_price
                all_daily_high.append((date, port_high))
                all_daily_low.append((date, port_low))
            else:
                # 空仓: high == low == tv == cash
                all_daily_high.append((date, tv))
                all_daily_low.append((date, tv))

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

        # 6. 期末强制平仓 (B1 fix: 与 params 模式 _backtest_single_stock 末尾的 end_of_data 逻辑保持一致)
        #    防止最后一批持仓的未实现 PnL 永远不算实现, 导致 win_rate/profit_loss_ratio 漏算交易,
        #    且与 annual_return (基于 dv_series 含未实现) 的口径不一致.
        if portfolio.positions:
            n_remaining = len(portfolio.positions)
            end_date = pd.Timestamp(trading_dates[-1]) if trading_dates else None
            for code in list(portfolio.positions.keys()):
                pos = portfolio.positions[code]
                # P2 #8 修复: 期末 close fallback 优先级
                # 旧版: last_prices.get(code, pos.entry_price) — 退市股在最后一日横截面中
                #   缺失时, 用 entry_price 算 PnL = 0 - sell_fee, 严重低估深度被套持仓的亏损
                # 新版: 三级 fallback
                #   1) last_prices (最后一日横截面 close, 最准)
                #   2) stock_history[code] 最后一行 close (横截面缺但 by-stock 数据在)
                #   3) entry_price (极端 fallback, 此时 PnL 仍按 entry 算 = 0 - sell_fee)
                if code in last_prices:
                    close_px = last_prices[code]
                elif code in stock_history and len(stock_history[code]) > 0:
                    close_px = float(stock_history[code]["收盘价"].iloc[-1])
                else:
                    close_px = pos.entry_price
                    self.logger.warning(
                        f"[end-of-data] {code}: 既无横截面 close 也无 by-stock 历史, "
                        f"fallback 到 entry_price (PnL=0)"
                    )
                sell_amount = close_px * pos.shares
                pnl = (close_px - pos.entry_price) * pos.shares - calc_sell_fee(sell_amount, code)
                _, sold_pos = portfolio.sell(code, close_px, end_date)
                all_trades.append({
                    "code": code, "pnl": pnl,
                    "holding_days": pos.holding_days, "signal": "end_of_data",
                })
                all_events.append({
                    "code": code, "signal": "end_of_data", "action": "executed",
                    "pnl": pnl, "holding_days": pos.holding_days,
                })
                # 将期末平仓的 pnl/holding_days 关联到触发入场的 entry 信号 (与正常 exit 一致)
                if sold_pos and sold_pos.entry_signals:
                    for sig_name in sold_pos.entry_signals:
                        all_events.append({
                            "code": code, "signal": sig_name, "action": "exit_linked",
                            "pnl": pnl, "holding_days": pos.holding_days,
                        })
            self.logger.info(f"[end-of-data] force-closed {n_remaining} remaining positions")

        # 7. 构造 dv_series (weight 模式天然按 trading_dates 顺序, 直接转 Series)
        if all_daily_values:
            dates, vals = zip(*all_daily_values)
            dv_series = pd.Series(vals, index=pd.DatetimeIndex(dates))
        else:
            dv_series = pd.Series(dtype=float)

        # P3 #7: 构造日内 high/low Series (weight 模式追踪, 用于日内 max_drawdown)
        dv_high = None
        dv_low = None
        if all_daily_high and all_daily_low and len(all_daily_high) == len(all_daily_values) == len(all_daily_low):
            h_dates, h_vals = zip(*all_daily_high)
            l_dates, l_vals = zip(*all_daily_low)
            dv_high = pd.Series(h_vals, index=pd.DatetimeIndex(h_dates))
            dv_low = pd.Series(l_vals, index=pd.DatetimeIndex(l_dates))
        else:
            # 长度不一致或为空: fallback 到 close-based max_drawdown
            pass  # dv_high / dv_low 已在上面初始化为 None

        # 期末 force-close 后修正最后一帧: 之前记录的 daily_value 含未实现 position value,
        # 但 sell_fee 已被扣. 真实 final_cash = daily_value - position_value + sell_proceeds
        #                              = daily_value - sum(sell_fee for end-of-data trades)
        # 为保持 sum(trade.pnl) == final - initial 的对账, 把最后一日的 daily_value 替换为 final_cash
        if len(dv_series) > 0 and all_trades:
            final_cash = portfolio.cash
            # 仅当 force-close 真的发生 (有 end_of_data trades) 时修正
            has_force_close = any(t.get('signal') == 'end_of_data' for t in all_trades)
            if has_force_close and abs(dv_series.iloc[-1] - final_cash) > 0.01:
                self.logger.info(
                    f"[end-of-data] 修正最后一日 daily_value: "
                    f"{dv_series.iloc[-1]:.2f} -> {final_cash:.2f} "
                    f"(扣 {dv_series.iloc[-1] - final_cash:.2f} = 期末 sell_fees 总和)"
                )
                dv_series.iloc[-1] = final_cash
                # P3 #7: 同步修正 high/low
                if dv_high is not None and len(dv_high) > 0:
                    dv_high.iloc[-1] = final_cash
                if dv_low is not None and len(dv_low) > 0:
                    dv_low.iloc[-1] = final_cash

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

        result = self._build_results(all_trades, all_events, factor_values, dv_series, version=version, dv_high=dv_high, dv_low=dv_low)
        result.signal_attribution = attribution
        return result

    def _compute_signal_attribution(self, trades, events) -> list[dict]:
        """weight 模式专属: 计算每个信号的 return_share / win_share / loss_share.

        修复 (P0 #1):
        - 旧版本只从 trades 收集 pnl, 但 trades 的 signal 字段是 exit signal, entry signal 完全漏算
        - 旧版本的 total_pnl 是 per_sig_pnl 各项 sum, 概念上 OK 但 entry signal 都为 0 不可信
        - 新版本:
          * exit signals 的 pnl 从 trades 收集 (每笔 trade 一次, 对应一个 exit signal)
          * entry signals 的 pnl 从 events (action=exit_linked) 收集 (每笔 trade 一次, 对应每个 entry signal)
          * total_pnl = unique trades 的 pnl 总和 (每笔 trade 只算一次)
          * 因此 sum(return_share) 可能 > 1 (一笔交易被 N+1 个信号分摊), 这是合理的

        注意: trades 里的非信号字段 (rebalance / end_of_data) 仍会算入 total_pnl, 但不会出现在
        signal_attribution 表 (因为不在 spec 的 entry/exit_signals 里).
        """
        from collections import defaultdict

        # 1. total_pnl / total_wins / total_losses: 基于 unique trades
        if not trades:
            return []
        trade_pnls = [t.get("pnl", 0.0) or 0.0 for t in trades]
        total_pnl = sum(trade_pnls)
        total_wins = sum(1 for p in trade_pnls if p > 0)
        total_losses = sum(1 for p in trade_pnls if p < 0)

        # 2. exit signals 的 pnl/wins/losses (从 trades)
        exit_pnl: dict[str, list[float]] = defaultdict(list)
        for t in trades:
            sig = t.get("signal", "unknown")
            pnl = t.get("pnl", 0.0) or 0.0
            exit_pnl[sig].append(pnl)

        # 3. entry signals 的 pnl (从 events, action=exit_linked)
        entry_pnl: dict[str, list[float]] = defaultdict(list)
        if events is not None and len(events) > 0:
            events_df = events if isinstance(events, pd.DataFrame) else pd.DataFrame(events)
            linked = events_df[events_df["action"] == "exit_linked"]
            for _, row in linked.iterrows():
                sig = row.get("signal", "unknown")
                pnl = row.get("pnl", 0.0) or 0.0
                if pd.notna(pnl):
                    entry_pnl[sig].append(float(pnl))

        # 4. entry / exit 信号名集合 (用于分类)
        entry_sig_names = {s["name"] for s in self.spec["entry_signals"]}
        exit_sig_names = {s["name"] for s in self.spec["exit_signals"]}

        # 5. 对 spec 中的每个 signal 输出 attribution
        out = []
        for sig_name in list(entry_sig_names) + list(exit_sig_names):
            # 决定 pnl 来源: entry signal 从 entry_pnl, exit signal 从 exit_pnl
            # 如果 signal 同时在 entry 和 exit 中 (不常见), 用 exit_pnl (exit 决策是闭环终点)
            if sig_name in exit_pnl:
                pnls = exit_pnl[sig_name]
            elif sig_name in entry_pnl:
                pnls = entry_pnl[sig_name]
            else:
                pnls = []
            sig_pnl = sum(pnls) if pnls else 0.0
            sig_wins = sum(1 for p in pnls if p > 0)
            sig_losses = sum(1 for p in pnls if p < 0)
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
        dv_high: pd.Series | None = None,
        dv_low: pd.Series | None = None,
    ) -> RunResults:
        """从主循环结果构建 RunResults.

        **capital_base 计算**:
        - params 模式: per-stock 投入 = max_single_weight × initial_capital, 实际 = tested × per_stock
        - weight 模式: 全部 initial_capital (1 个组合管理, 不用 per-stock)
        - 无交易 / 无数值时: 用 self.initial_capital (避免除零或极端 annual_return)

        **P3 #7 新增**: dv_high / dv_low 是组合日内 high/low (weight 模式追踪, params 模式 None).
        传入 compute_metrics 用于日内 max_drawdown 计算.
        """
        trades_df = pd.DataFrame(trades) if trades else pd.DataFrame(columns=["code", "pnl", "holding_days", "signal"])
        events_df = pd.DataFrame(events) if events else pd.DataFrame(columns=["code", "signal", "action", "pnl", "holding_days"])

        if self.mode == "weight":
            # weight 模式: 单一账户，初始资本固定
            capital_base = self.initial_capital
        else:
            # params 模式: daily_values 起点是动态的（受 day0 前没上市的股影响），
            # 用 dv_series.iloc[0] 作为分母，而非写死的 len(universe)*per_stock
            # P0 #3 修复: dv_series 可能在首日为 NaN (reindex 没数据 → min_count=1 失败),
            # 用 dropna().iloc[0] 取第一个有效值
            cleaned = dv_series.dropna()
            if len(cleaned) > 0 and cleaned.iloc[0] > 0:
                capital_base = float(cleaned.iloc[0])
            else:
                capital_base = self.initial_capital  # fallback

        # P3 #7: 传入日内 high/low (weight 模式有, params 模式为 None → fallback close-based)
        metrics = compute_metrics(capital_base, dv_series, trades_df, daily_high=dv_high, daily_low=dv_low)

        ss = [compute_signal_stats(s["name"], events_df, signal_type="entry") for s in self.spec["entry_signals"]]
        ss += [compute_signal_stats(s["name"], events_df, signal_type="exit") for s in self.spec["exit_signals"]]
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


# ===== 工具函数 (从 portfolio.py 统一导入) =====
# should_rebalance_fn 是 portfolio.should_rebalance 的别名, 保持向后兼容
from .portfolio import should_rebalance as should_rebalance_fn
