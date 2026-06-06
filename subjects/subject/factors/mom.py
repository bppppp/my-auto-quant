"""N 日动量 (Momentum).

见 PARTS_SUMMARY.md §1.

公式: mom_N = close_t / close_{t-N} - 1
"""
from __future__ import annotations

import pandas as pd


def mom(close: pd.Series, period: int) -> pd.Series:
    """计算 period 日动量.

    Args:
        close: 收盘价 Series.
        period: 回看窗口 (>= 1).

    Returns:
        Series: 长度与 close 一致; 前 ``period`` 行为 NaN
            (因 ``close.shift(period)`` 产生空值).
    """
    if period < 1:
        raise ValueError(f"period must be >= 1, got {period}")
    return close / close.shift(period) - 1.0
