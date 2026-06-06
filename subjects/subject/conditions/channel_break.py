"""通道突破 / 跌破判断. 见 PARTS_SUMMARY.md §2."""
from __future__ import annotations


def check_channel_break(
    close: float,
    channel_value: float,
    direction: str = "above",
) -> bool:
    """判断 close 是否突破 / 跌破 channel_value.

    Args:
        close: 当前价 (scalar 或 pd.Series).
        channel_value: 通道值 (scalar 或 pd.Series, 通常是 donchian_high_xx 或 donchian_low_xx).
        direction: ``"above"`` (向上突破, close > channel_value)
            或 ``"below"`` (向下突破, close < channel_value).

    Returns:
        bool 或 bool Series: True 表示突破 / 跌破.

    Examples:
        入场::

            if check_channel_break(close, donchian_high_20, "above"):
                score += entry_weights["<signal_name>"]

        出场::

            if check_channel_break(close, donchian_low_20, "below"):
                return "trend_reversal"
    """
    if direction == "above":
        return close > channel_value
    if direction == "below":
        return close < channel_value
    raise ValueError(f"direction must be 'above' or 'below', got {direction!r}")
