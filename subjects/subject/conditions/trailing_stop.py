"""移动止损. 见 PARTS_SUMMARY.md §2."""
from __future__ import annotations


def check_trailing_stop(
    current_price: float,
    highest: float,
    pct: float,
) -> bool:
    """判断当前价是否从入场后最高价回撤 pct.

    Args:
        current_price: 当前价 (scalar 或 pd.Series).
        highest: 入场后最高收盘价 (scalar 或 pd.Series, 与 current_price 对齐).
            由 portfolio 维护: 每根 K 线 ``highest = max(prev_highest, close)``.
        pct: 回撤比例, 小数表示 (如 0.06 表示 6%).

    Returns:
        bool 或 bool Series: True 表示触发移动止损.
    """
    threshold = highest * (1.0 - pct)
    return current_price < threshold
