"""N 日动量 (Momentum).

见 PARTS_SUMMARY.md §1.

公式: mom_N = close_t / close_{t-N} - 1
"""
from __future__ import annotations

import logging

import pandas as pd

from ._cache import try_get_cached_factor

logger = logging.getLogger(__name__)


def mom(close: pd.Series, period: int) -> pd.Series:
    """计算 period 日动量.

    Args:
        close: 收盘价 Series.
        period: 回看窗口 (>= 1).

    Returns:
        Series: 长度与 close 一致; 前 ``period`` 行为 NaN
            (因 ``close.shift(period)`` 产生空值).
        如果数据不足 period 行，返回全 NaN Series。
    """
    if period < 1:
        raise ValueError(f"period must be >= 1, got {period}")

    series_len = len(close)

    # 1. 预计算 cache 命中: 直接返回预计算的 Series
    # 注: pre-compute 仅有 mom_60. 其他 period 调用走运行时.
    cached = try_get_cached_factor("mom_60", length=series_len)
    if cached is not None:
        return cached

    # 2. 数据不足 period 行
    if series_len < period + 1:
        logger.debug(
            f"[mom] mom_{period}: 数据不足 ({series_len} < {period + 1}), 返回全 NaN"
        )
        return pd.Series([float("nan")] * series_len, index=close.index)

    # 3. 数据充足，正常计算
    return close / close.shift(period) - 1.0
