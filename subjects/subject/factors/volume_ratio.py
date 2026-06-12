"""量比 (当日量 / period 日均量).

见 PARTS_SUMMARY.md §1.
"""
from __future__ import annotations

import logging

import pandas as pd

from ._cache import try_get_cached_factor

logger = logging.getLogger(__name__)


def volume_ratio(volume: pd.Series, period: int = 20) -> pd.Series:
    """计算 period 日量比.

    公式: volume_t / mean(volume_{t-period+1..t}, period).

    Args:
        volume: 成交量 Series.
        period: 窗口大小, 默认 20.

    Returns:
        Series: 长度与 volume 一致; 前 ``period - 1`` 行为 NaN.
        停牌日 volume = 0, 返回 0.
        如果数据不足 period 行，返回全 NaN Series。
    """
    if period < 1:
        raise ValueError(f"period must be >= 1, got {period}")

    series_len = len(volume)

    # 1. 预计算 cache 命中: 直接返回预计算的 Series
    # 注: pre-compute 仅有 volume_ratio_20. 其他 period 调用走运行时.
    cached = try_get_cached_factor("volume_ratio_20", length=series_len)
    if cached is not None:
        return cached

    # 2. 数据不足 period 行，无法计算有效的量比
    if series_len < period:
        logger.debug(
            f"[volume_ratio] volume_ratio_{period}: 数据不足 ({series_len} < {period}), 返回全 NaN"
        )
        return pd.Series([float("nan")] * series_len, index=volume.index)

    # 3. 数据充足，正常计算
    avg = volume.rolling(window=period, min_periods=period).mean()
    return volume / avg
