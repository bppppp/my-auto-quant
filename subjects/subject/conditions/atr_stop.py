"""ATR 动态止损. 见 PARTS_SUMMARY.md §2."""
from __future__ import annotations


def check_atr_stop(
    current_price: float,
    highest: float,
    atr: float,
    multiplier: float,
) -> bool:
    """判断当前价是否从最高价回撤 multiplier * ATR.

    Args:
        current_price: 当前价 (scalar 或 pd.Series).
        highest: 入场后最高收盘价.
        atr: ATR 值 (scalar 或 pd.Series, 通常来自 ``factors["atr_14"]``).
        multiplier: ATR 倍数 (如 2.0 表示 2 倍 ATR).

    Returns:
        bool 或 bool Series: True 表示触发 ATR 止损.
    """
    threshold = highest - multiplier * atr
    return current_price < threshold
