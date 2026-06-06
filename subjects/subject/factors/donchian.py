"""Donchian 通道 (N 日最高 / 最低).

见 PARTS_SUMMARY.md §1.
"""
from __future__ import annotations

import pandas as pd


def donchian_high(high: pd.Series, period: int) -> pd.Series:
    """计算 period 日最高价 (Donchian 通道上轨).

    Args:
        high: 最高价 Series.
        period: 窗口大小 (>= 1).

    Returns:
        Series: 长度与 high 一致; 前 ``period - 1`` 行为 NaN.
    """
    if period < 1:
        raise ValueError(f"period must be >= 1, got {period}")
    return high.rolling(window=period, min_periods=period).max()


def donchian_low(low: pd.Series, period: int) -> pd.Series:
    """计算 period 日最低价 (Donchian 通道下轨).

    Args:
        low: 最低价 Series.
        period: 窗口大小 (>= 1).

    Returns:
        Series: 长度与 low 一致; 前 ``period - 1`` 行为 NaN.
    """
    if period < 1:
        raise ValueError(f"period must be >= 1, got {period}")
    return low.rolling(window=period, min_periods=period).min()
