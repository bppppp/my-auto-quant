"""信号触发统计. 见 subject.md §6.1.

每个信号 (entry / exit) 单独统计:
- triggered: 入场触发次数 (action=='triggered')
- exits: 出场次数 (action=='exit_linked'), 与 triggered 一起反映"入场-出场"闭环完成度
- swallowed: 触发但未执行次数 (涨跌停被吞)
- skipped: 跳过次数
- win_count: 触发出场且盈利次数
- win_rate: win_count / len(pnls)  (注意: 不是 / triggered)
- avg_return: 平均盈亏
- median_holding_days: 中位持仓天数
- holding_days_dist: 持仓天数分布 {5: count, 10: count, ...}
- pnl_percentile: 盈亏分位数 {p25: val, p50: val, p75: val, p90: val, ...}

注意: entry 信号会收到 "exit_linked" 事件 (关联到对应出场时的 pnl/holding_days)。
Bug #2 修复: triggered 不再含 exit_linked 计数, 避免被翻倍.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd


@dataclass
class SignalStats:
    signal: str
    triggered: int
    """入场触发次数 (action=='triggered'). Bug #2 修复: 不再含 executed/exit_linked."""
    exits: int
    """出场次数 (action=='exit_linked'). 与 triggered 一起反映"入场-出场"闭环完成度."""
    swallowed: int
    skipped: int
    win_count: int
    win_rate: float
    avg_return: float
    median_holding_days: float
    # 新增：持仓天数分布
    holding_days_dist: dict[int, int]  # {5: count, 10: count, 15: count, 20: count, 25: count, 30: count, "+∞": count}
    # 新增：盈亏分位数
    pnl_percentiles: dict[str, float]  # {"p10": val, "p25": val, "p50": val, "p75": val, "p90": val}


def compute_holding_days_distribution(pnls: pd.Series, hd: pd.Series, thresholds: list[int] = None) -> dict[int, int]:
    """计算持仓天数分布."""
    if thresholds is None:
        thresholds = [5, 10, 15, 20, 25, 30]

    dist = {t: 0 for t in thresholds}
    dist["+∞"] = 0

    for days in hd.dropna():
        days = int(days)
        found = False
        for t in thresholds:
            if days <= t:
                dist[t] += 1
                found = True
                break
        if not found:
            dist["+∞"] += 1

    return dist


def compute_pnl_percentiles(pnls: pd.Series) -> dict[str, float]:
    """计算盈亏分位数."""
    if len(pnls) == 0:
        return {"p10": 0.0, "p25": 0.0, "p50": 0.0, "p75": 0.0, "p90": 0.0}

    return {
        "p10": float(np.percentile(pnls, 10)),
        "p25": float(np.percentile(pnls, 25)),
        "p50": float(np.percentile(pnls, 50)),
        "p75": float(np.percentile(pnls, 75)),
        "p90": float(np.percentile(pnls, 90)),
    }


def compute_signal_stats(
    signal: str,
    events: pd.DataFrame,
    signal_type: str = "entry",
) -> SignalStats:
    """计算单个信号的统计.

    Args:
        signal: 信号名.
        events: 事件日志, 必含列:
            - ``signal``: 信号名
            - ``action``: ``"triggered"`` / ``"executed"`` / ``"swallowed"`` / ``"skipped"`` / ``"exit_linked"``
            - ``pnl``: 盈亏 (元, executed/exit_linked 事件有值)
            - ``holding_days``: 持仓天数 (executed/exit_linked 事件有值)
        signal_type: ``"entry"`` (入场信号) 或 ``"exit"`` (出场信号).
            - entry 信号: triggered 字段 = action=='triggered' 次数 (入场触发)
            - exit 信号: triggered 字段 = action in [executed, swallowed, skipped] 次数 (出场触发)
              因为 exit 信号的事件流没有 action='triggered' (它直接到 executed/swallowed),
              必须按 exit 信号的事件流统计, 否则 triggered 会=0.

    Returns:
        :class:`SignalStats`.
    """
    sub = events[events["signal"] == signal]
    if len(sub) == 0:
        return SignalStats(
            signal, 0, 0, 0, 0, 0, 0.0, 0.0, 0.0,
            holding_days_dist={5: 0, 10: 0, 15: 0, 20: 0, 25: 0, 30: 0, "+∞": 0},
            pnl_percentiles={"p10": 0.0, "p25": 0.0, "p50": 0.0, "p75": 0.0, "p90": 0.0}
        )

    # Bug #2 修复 (round 2): 按 signal_type 区分 triggered 统计口径.
    # - entry 信号: triggered = action=='triggered' (入场触发)
    # - exit 信号: triggered = action in [executed, swallowed, skipped] (出场触发)
    #   原因: exit 信号的事件流没有 action='triggered', 只有 executed/swallowed/skipped
    #   (line 1305/1317/1498: 直接从策略 should_exit 返回到成交/被吞, 不经过 triggered 中间态)
    if signal_type == "exit":
        triggered = int(sub["action"].isin(["executed", "swallowed", "skipped"]).sum())
    else:
        triggered = int((sub["action"] == "triggered").sum())
    exits = int((sub["action"] == "exit_linked").sum())
    swallowed = int((sub["action"] == "swallowed").sum())
    skipped = int((sub["action"] == "skipped").sum())

    # pnl 和 holding_days 来自 executed 和 exit_linked 事件
    pnls = sub.loc[sub["action"].isin(["executed", "exit_linked"]), "pnl"].dropna()
    hd = sub.loc[sub["action"].isin(["executed", "exit_linked"]), "holding_days"].dropna()

    if len(pnls) == 0:
        # 修复 (P1-1 v3): 11 个字段全部按位置参数顺序传, 不再混合 keyword.
        # 旧版传了 10 个位置参数 + 2 个 keyword, holding_days_dist 字段被冲突赋值.
        return SignalStats(
            signal,           # signal
            triggered,        # triggered
            exits,            # exits
            swallowed,        # swallowed
            skipped,          # skipped
            0,                # win_count
            0,                # win_rate
            0.0,              # avg_return
            0.0,              # median_holding_days
            {5: 0, 10: 0, 15: 0, 20: 0, 25: 0, 30: 0, "+∞": 0},  # holding_days_dist
            {"p10": 0.0, "p25": 0.0, "p50": 0.0, "p75": 0.0, "p90": 0.0},  # pnl_percentiles
        )

    win_count = int((pnls > 0).sum())
    win_rate = win_count / len(pnls)
    avg_return = float(pnls.mean())
    median_hd = float(hd.median()) if len(hd) > 0 else 0.0

    # 新增统计
    holding_days_dist = compute_holding_days_distribution(pnls, hd)
    pnl_percentiles = compute_pnl_percentiles(pnls)

    return SignalStats(
        signal=signal,
        triggered=triggered,
        exits=exits,
        swallowed=swallowed,
        skipped=skipped,
        win_count=win_count,
        win_rate=win_rate,
        avg_return=avg_return,
        median_holding_days=median_hd,
        holding_days_dist=holding_days_dist,
        pnl_percentiles=pnl_percentiles,
    )
