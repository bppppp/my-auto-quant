"""简单移动平均线 (Simple Moving Average).

见 PARTS_SUMMARY.md §1.
"""
from __future__ import annotations

import pandas as pd


def ma(close: pd.Series, period: int) -> pd.Series:
    """计算 period 日简单移动平均线.

    Args:
        close: 收盘价 Series (按日期升序).
        period: 窗口大小 (>= 1).

    Returns:
        Series: 长度与 close 一致; 前 ``period - 1`` 行为 NaN.

    Examples:
        >>> ma_20 = ma(df["收盘价"], 20)
    """
    if period < 1:
        raise ValueError(f"period must be >= 1, got {period}")
    return close.rolling(window=period, min_periods=period).mean()
