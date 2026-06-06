"""时间止损. 见 PARTS_SUMMARY.md §2."""
from __future__ import annotations


def check_time_stop(
    holding_days: int,
    max_days: int,
) -> bool:
    """判断持仓天数是否 >= max_days.

    Args:
        holding_days: 持仓天数 (scalar 或 pd.Series).
        max_days: 最大持仓天数阈值.

    Returns:
        bool 或 bool Series: True 表示触发时间止损.
    """
    return holding_days >= max_days
