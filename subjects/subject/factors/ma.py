"""简单移动平均线 (Simple Moving Average).

见 PARTS_SUMMARY.md §1.
"""
from __future__ import annotations

import logging

import pandas as pd

from ._cache import try_get_cached_factor

logger = logging.getLogger(__name__)


def ma(series: pd.Series, period: int) -> pd.Series:
    """计算 period 日简单移动平均线 (SMA).

    注意: 参数名是 ``series``, 实际接受任何 pd.Series (不仅是 close).
    也可用于成交量、换手率等任何一维时间序列.

    【计算优先级】
    1. 预计算因子缓存命中 → 返回缓存数据
    2. 预计算缺失但数据充足 → 实时计算
    3. 数据不足 → 返回全 NaN（避免错误信号）

    Args:
        series: 一维 Series (按日期升序). 例如 df["收盘价"] / df["成交量（股）"].
        period: 窗口大小 (>= 1).

    Returns:
        Series: 长度与 series 一致; 前 ``period - 1`` 行为 NaN.
        如果数据不足 period 行，返回全 NaN Series。

    Examples:
        >>> ma_20 = ma(df["收盘价"], 20)            # 20 日价格均线
        >>> vol_ma_20 = ma(df["成交量（股）"], 20)  # 20 日均量 (量能均线)
    """
    if period < 1:
        raise ValueError(f"period must be >= 1, got {period}")

    series_len = len(series)

    # 1. 预计算 cache 命中: 直接返回预计算的 Series
    cached = try_get_cached_factor(f"ma_{period}", length=series_len)
    if cached is not None:
        return cached

    # 2. 预计算缺失，尝试实时计算
    if series_len < period:
        # 数据不足 period 行，无法计算有效的 MA
        # 返回全 NaN Series，避免后续比较操作产生错误信号
        logger.debug(
            f"[ma] ma_{period}: 数据不足 ({series_len} < {period}), 返回全 NaN"
        )
        return pd.Series([float("nan")] * series_len, index=series.index)

    # 3. 数据充足，正常计算
    return series.rolling(window=period, min_periods=period).mean()
