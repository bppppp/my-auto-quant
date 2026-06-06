"""量比 (当日量 / period 日均量).

见 PARTS_SUMMARY.md §1.
"""
from __future__ import annotations

import pandas as pd


def volume_ratio(volume: pd.Series, period: int = 20) -> pd.Series:
    """计算 period 日量比.

    公式: volume_t / mean(volume_{t-period+1..t}, period).

    Args:
        volume: 成交量 Series.
        period: 窗口大小, 默认 20.

    Returns:
        Series: 长度与 volume 一致; 前 ``period - 1`` 行为 NaN.
        停牌日 volume = 0, 返回 0.
    """
    if period < 1:
        raise ValueError(f"period must be >= 1, got {period}")
    avg = volume.rolling(window=period, min_periods=period).mean()
    return volume / avg
