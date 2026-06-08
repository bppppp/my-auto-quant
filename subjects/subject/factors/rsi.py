"""相对强弱指标 (Relative Strength Index).

见 PARTS_SUMMARY.md §1.

公式: RSI = 100 - 100 / (1 + RS)
  RS = mean(gain, period) / mean(loss, period)
  gain = max(close_diff, 0)
  loss = max(-close_diff, 0)
"""
from __future__ import annotations

import pandas as pd

from ._cache import try_get_cached_factor


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """计算 period 日 RSI.

    Args:
        close: 收盘价 Series.
        period: 窗口大小, 默认 14.

    Returns:
        Series: 范围 0-100; 前 ``period`` 行为 NaN.
    """
    if period < 1:
        raise ValueError(f"period must be >= 1, got {period}")
    # 预计算 cache 命中: 直接返回预计算的 Series
    # 注: pre-compute 仅有 rsi_14. 其他 period 调用走运行时.
    cached = try_get_cached_factor("rsi_14", length=len(close))
    if cached is not None:
        return cached
    diff = close.diff()
    gain = diff.clip(lower=0.0)
    loss = (-diff).clip(lower=0.0)
    avg_gain = gain.rolling(window=period, min_periods=period).mean()
    avg_loss = loss.rolling(window=period, min_periods=period).mean()
    rs = avg_gain / avg_loss
    return 100.0 - 100.0 / (1.0 + rs)
