"""简单移动平均线 (Simple Moving Average).

见 PARTS_SUMMARY.md §1.
"""
from __future__ import annotations

import pandas as pd


def ma(series: pd.Series, period: int) -> pd.Series:
    """计算 period 日简单移动平均线 (SMA).

    注意: 参数名是 ``series``, 实际接受任何 pd.Series (不仅是 close).
    也可用于成交量、换手率等任何一维时间序列.

    Args:
        series: 一维 Series (按日期升序). 例如 df["收盘价"] / df["成交量（股）"].
        period: 窗口大小 (>= 1).

    Returns:
        Series: 长度与 series 一致; 前 ``period - 1`` 行为 NaN.

    Examples:
        >>> ma_20 = ma(df["收盘价"], 20)            # 20 日价格均线
        >>> vol_ma_20 = ma(df["成交量（股）"], 20)  # 20 日均量 (量能均线)
    """
    if period < 1:
        raise ValueError(f"period must be >= 1, got {period}")
    return series.rolling(window=period, min_periods=period).mean()
