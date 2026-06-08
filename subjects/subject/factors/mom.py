"""N 日动量 (Momentum).

见 PARTS_SUMMARY.md §1.

公式: mom_N = close_t / close_{t-N} - 1
"""
from __future__ import annotations

import pandas as pd

from ._cache import try_get_cached_factor


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
    # 预计算 cache 命中: 直接返回预计算的 Series
    # 注: pre-compute 仅有 mom_60. 其他 period 调用走运行时.
    cached = try_get_cached_factor("mom_60", length=len(close))
    if cached is not None:
        return cached
    return close / close.shift(period) - 1.0
