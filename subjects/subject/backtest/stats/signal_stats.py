"""信号触发统计. 见 subject.md §6.1.

每个信号 (entry / exit) 单独统计:
- triggered: 触发次数
- swallowed: 触发但未执行次数 (涨跌停被吞)
- skipped: 跳过次数
- win_count: 触发出场且盈利次数
- win_rate: win_count / triggered
- avg_return: 平均盈亏
- median_holding_days: 中位持仓天数
- holding_days_dist: 持仓天数分布 {5: count, 10: count, ...}
- pnl_percentile: 盈亏分位数 {p25: val, p50: val, p75: val, p90: val, ...}

注意: entry 信号会收到 "exit_linked" 事件 (关联到对应出场时的 pnl/holding_days)。
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
) -> SignalStats:
    """计算单个信号的统计.

    Args:
        signal: 信号名.
        events: 事件日志, 必含列:
            - ``signal``: 信号名
            - ``action``: ``"triggered"`` / ``"executed"`` / ``"swallowed"`` / ``"skipped"`` / ``"exit_linked"``
            - ``pnl``: 盈亏 (元, executed/exit_linked 事件有值)
            - ``holding_days``: 持仓天数 (executed/exit_linked 事件有值)

    Returns:
        :class:`SignalStats`.
    """
    sub = events[events["signal"] == signal]
    if len(sub) == 0:
        return SignalStats(
            signal, 0, 0, 0, 0, 0.0, 0.0, 0.0,
            holding_days_dist={5: 0, 10: 0, 15: 0, 20: 0, 25: 0, 30: 0, "+∞": 0},
            pnl_percentiles={"p10": 0.0, "p25": 0.0, "p50": 0.0, "p75": 0.0, "p90": 0.0}
        )

    # triggered: triggered/executed/exit_linked 都算触发
    triggered = int((sub["action"] == "triggered").sum())
    triggered += int((sub["action"] == "executed").sum())
    triggered += int((sub["action"] == "exit_linked").sum())
    swallowed = int((sub["action"] == "swallowed").sum())
    skipped = int((sub["action"] == "skipped").sum())

    # pnl 和 holding_days 来自 executed 和 exit_linked 事件
    pnls = sub.loc[sub["action"].isin(["executed", "exit_linked"]), "pnl"].dropna()
    hd = sub.loc[sub["action"].isin(["executed", "exit_linked"]), "holding_days"].dropna()

    if len(pnls) == 0:
        return SignalStats(
            signal, triggered, swallowed, skipped, 0, 0.0, 0.0, 0.0,
            holding_days_dist={5: 0, 10: 0, 15: 0, 20: 0, 25: 0, 30: 0, "+∞": 0},
            pnl_percentiles={"p10": 0.0, "p25": 0.0, "p50": 0.0, "p75": 0.0, "p90": 0.0}
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
        swallowed=swallowed,
        skipped=skipped,
        win_count=win_count,
        win_rate=win_rate,
        avg_return=avg_return,
        median_holding_days=median_hd,
        holding_days_dist=holding_days_dist,
        pnl_percentiles=pnl_percentiles,
    )
