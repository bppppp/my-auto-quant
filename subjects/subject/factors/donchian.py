"""Donchian 通道 (N 日最高 / 最低).

见 PARTS_SUMMARY.md §1.
"""
from __future__ import annotations

import logging

import pandas as pd

from ._cache import try_get_cached_factor

logger = logging.getLogger(__name__)


def donchian_high(high: pd.Series, period: int) -> pd.Series:
    """计算 period 日最高价 (Donchian 通道上轨).

    Args:
        high: 最高价 Series.
        period: 窗口大小 (>= 1).

    Returns:
        Series: 长度与 high 一致; 前 ``period - 1`` 行为 NaN.
        如果数据不足 period 行，返回全 NaN Series。
    """
    if period < 1:
        raise ValueError(f"period must be >= 1, got {period}")

    series_len = len(high)

    # 1. 预计算 cache 命中: 直接返回预计算的 Series
    # 注: pre-compute 仅有 donchian_high_20. 其他 period 调用走运行时.
    cached = try_get_cached_factor("donchian_high_20", length=series_len)
    if cached is not None:
        return cached

    # 2. 数据不足 period 行
    if series_len < period:
        logger.debug(
            f"[donchian_high] donchian_high_{period}: 数据不足 ({series_len} < {period}), 返回全 NaN"
        )
        return pd.Series([float("nan")] * series_len, index=high.index)

    # 3. 数据充足，正常计算
    return high.rolling(window=period, min_periods=period).max()


def donchian_low(low: pd.Series, period: int) -> pd.Series:
    """计算 period 日最低价 (Donchian 通道下轨).

    Args:
        low: 最低价 Series.
        period: 窗口大小 (>= 1).

    Returns:
        Series: 长度与 low 一致; 前 ``period - 1`` 行为 NaN.
        如果数据不足 period 行，返回全 NaN Series。
    """
    if period < 1:
        raise ValueError(f"period must be >= 1, got {period}")

    series_len = len(low)

    # 1. 预计算 cache 命中: 直接返回预计算的 Series
    # 注: pre-compute 仅有 donchian_low_20. 其他 period 调用走运行时.
    cached = try_get_cached_factor("donchian_low_20", length=series_len)
    if cached is not None:
        return cached

    # 2. 数据不足 period 行
    if series_len < period:
        logger.debug(
            f"[donchian_low] donchian_low_{period}: 数据不足 ({series_len} < {period}), 返回全 NaN"
        )
        return pd.Series([float("nan")] * series_len, index=low.index)

    # 3. 数据充足，正常计算
    return low.rolling(window=period, min_periods=period).min()
