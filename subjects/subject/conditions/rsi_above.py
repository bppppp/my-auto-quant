"""RSI 超买判断. 见 PARTS_SUMMARY.md §2."""
from __future__ import annotations


def check_rsi_above(
    rsi: float,
    threshold: float,
) -> bool:
    """判断 RSI 是否 > threshold.

    Args:
        rsi: RSI 值 (scalar 或 pd.Series).
        threshold: 超买阈值 (如 75).

    Returns:
        bool 或 bool Series: True 表示超买.
    """
    return rsi > threshold
