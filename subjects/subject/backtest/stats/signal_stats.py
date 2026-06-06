"""信号触发统计. 见 subject.md §6.1.

每个信号 (entry / exit) 单独统计:
- triggered: 触发次数
- swallowed: 触发但未执行次数 (涨跌停被吞)
- skipped: 跳过次数
- win_count: 触发出场且盈利次数
- win_rate: win_count / triggered
- avg_return: 平均盈亏
- median_holding_days: 中位持仓天数
"""
from __future__ import annotations

from dataclasses import dataclass

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


def compute_signal_stats(
    signal: str,
    events: pd.DataFrame,
) -> SignalStats:
    """计算单个信号的统计.

    Args:
        signal: 信号名.
        events: 事件日志, 必含列:
            - ``signal``: 信号名
            - ``action``: ``"triggered"`` / ``"swallowed"`` / ``"skipped"`` / ``"executed"``
            - ``pnl``: 盈亏 (元, 仅 executed 且已平仓事件有值)
            - ``holding_days``: 持仓天数 (仅已平仓事件有值)

    Returns:
        :class:`SignalStats`.
    """
    sub = events[events["signal"] == signal]
    if len(sub) == 0:
        return SignalStats(signal, 0, 0, 0, 0, 0.0, 0.0, 0.0)

    triggered = int((sub["action"] == "triggered").sum() + (sub["action"] == "executed").sum())
    swallowed = int((sub["action"] == "swallowed").sum())
    skipped = int((sub["action"] == "skipped").sum())

    pnls = sub.get("pnl", pd.Series(dtype=float)).dropna()
    if len(pnls) == 0:
        return SignalStats(signal, triggered, swallowed, skipped, 0, 0.0, 0.0, 0.0)

    win_count = int((pnls > 0).sum())
    win_rate = win_count / len(pnls)
    avg_return = float(pnls.mean())

    hd = sub.get("holding_days", pd.Series(dtype=float)).dropna()
    median_hd = float(hd.median()) if len(hd) > 0 else 0.0

    return SignalStats(
        signal=signal,
        triggered=triggered,
        swallowed=swallowed,
        skipped=skipped,
        win_count=win_count,
        win_rate=win_rate,
        avg_return=avg_return,
        median_holding_days=median_hd,
    )
