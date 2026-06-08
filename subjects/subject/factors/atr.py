"""平均真实波幅 (Average True Range).

见 PARTS_SUMMARY.md §1.

True Range (TR) = max(high - low, |high - prev_close|, |low - prev_close|)
ATR = period 日 TR 的算术平均.
"""
from __future__ import annotations

import pandas as pd

from ._cache import try_get_cached_factor


def atr(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 14,
) -> pd.Series:
    """计算 period 日 ATR.

    Args:
        high: 最高价 Series.
        low: 最低价 Series.
        close: 收盘价 Series (用于取 prev_close).
        period: 窗口大小, 默认 14.

    Returns:
        Series: 长度与 close 一致; 前 ``period`` 行为 NaN
            (position 0 上 prev_close 是 NaN, 该日 TR 即 NaN).

    Note:
        使用 ``np.maximum.reduce`` (NaN-propagating) 而非 ``pd.concat.max``
        (NaN-ignoring), 保证 position 0 的 NaN 不会被错误地填充为 (high - low).
    """
    if period < 1:
        raise ValueError(f"period must be >= 1, got {period}")
    # 预计算 cache 命中: 直接返回预计算的 Series
    # 注: pre-compute 仅有 atr_14. 其他 period 调用走运行时.
    cached = try_get_cached_factor("atr_14", length=len(close))
    if cached is not None:
        return cached
    prev_close = close.shift(1)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    # element-wise max 保持 NaN-propagating; 用 numpy 在三列之间逐元素取最大
    tr = pd.DataFrame({"a": tr1, "b": tr2, "c": tr3}).max(axis=1)
    return tr.rolling(window=period, min_periods=period).mean()
