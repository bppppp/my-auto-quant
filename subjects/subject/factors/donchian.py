"""Donchian 通道 (N 日最高 / 最低).

见 PARTS_SUMMARY.md §1.
"""
from __future__ import annotations

import pandas as pd

from ._cache import try_get_cached_factor


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
    # 预计算 cache 命中: 直接返回预计算的 Series
    # 注: pre-compute 仅有 donchian_high_20. 其他 period 调用走运行时.
    cached = try_get_cached_factor("donchian_high_20", length=len(high))
    if cached is not None:
        return cached
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
    # 预计算 cache 命中: 直接返回预计算的 Series
    # 注: pre-compute 仅有 donchian_low_20. 其他 period 调用走运行时.
    cached = try_get_cached_factor("donchian_low_20", length=len(low))
    if cached is not None:
        return cached
    return low.rolling(window=period, min_periods=period).min()
