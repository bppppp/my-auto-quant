"""固定止损. 见 PARTS_SUMMARY.md §2."""
from __future__ import annotations


def check_fixed_stop(
    current_price: float,
    entry_price: float,
    pct: float,
) -> bool:
    """判断当前价是否跌破入场价的 (1 - pct).

    Args:
        current_price: 当前价 (scalar 或 pd.Series).
        entry_price: 入场价 (scalar 或 pd.Series, 与 current_price 对齐).
        pct: 止损比例, 小数表示 (如 0.08 表示 8%).

    Returns:
        bool 或 bool Series: True 表示触发止损.

    Note:
        接受 scalar (返回 bool) 或 Series (返回 bool Series).
        Series 与 Series 必须**等长且索引对齐**, 否则触发 pandas 广播错误.
    """
    threshold = entry_price * (1.0 - pct)
    return current_price < threshold
