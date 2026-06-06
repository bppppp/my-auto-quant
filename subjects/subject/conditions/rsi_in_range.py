"""RSI 区间判断. 见 PARTS_SUMMARY.md §2."""
from __future__ import annotations


def check_rsi_in_range(
    rsi: float,
    low: float,
    high: float,
) -> bool:
    """判断 RSI 是否在 [low, high] 区间内 (含两端).

    Args:
        rsi: RSI 值 (scalar 或 pd.Series, 通常来自 ``factors["rsi_14"]``).
        low: 区间下限.
        high: 区间上限.

    Returns:
        bool 或 bool Series: True 表示 RSI 在区间内.

    Examples:
        >>> if check_rsi_in_range(factors["rsi_14"], 40, 70).iloc[-1]:
        ...     score += entry_weights["<signal_name>"]
    """
    return (rsi >= low) & (rsi <= high)
