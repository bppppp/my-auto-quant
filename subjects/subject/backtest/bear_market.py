"""熊市识别 + 仓位折算. 见 PARTS_SUMMARY.md §3 / subject.md §5.2.

核心函数: 给定沪深 300 指数价格序列, 判断当前是否处于熊市.
"""
from __future__ import annotations

import pandas as pd

# 公共默认阈值 (subject.md §5.2)
DEFAULT_BEAR_DRAW_DOWN_THRESHOLD: float = -0.10
"""熊市识别默认阈值: 20 日跌幅 < -10% 即认为进入熊市."""


def is_bear_market(
    hs300_close: pd.Series,
    lookback: int = 20,
    threshold: float = DEFAULT_BEAR_DRAW_DOWN_THRESHOLD,
) -> bool:
    """判断当前是否处于熊市.

    Args:
        hs300_close: 沪深 300 指数收盘价 Series (按日期升序).
        lookback: 回看天数, 默认 20.
        threshold: 跌幅阈值 (负数, 如 -0.10 表示跌 10%), 默认 ``-0.10``.

    Returns:
        True 表示处于熊市 (20 日跌幅 < threshold).
    """
    if len(hs300_close) < lookback + 1:
        return False
    cur = float(hs300_close.iloc[-1])
    prev = float(hs300_close.iloc[-(lookback + 1)])
    if prev <= 0 or pd.isna(cur) or pd.isna(prev):
        return False
    ret = cur / prev - 1.0
    return ret < threshold


def bear_position_scale(bear: bool) -> float:
    """熊市仓位折算系数.

    熊市时建议降低 target_holdings (减半) 和 max_single_weight (降低).
    返回一个 0-1 之间的 scale, 乘到目标持仓数 / 单票权重上.

    Args:
        bear: 是否处于熊市 (:func:`is_bear_market` 结果).

    Returns:
        0.5 (熊市) 或 1.0 (非熊市).
    """
    return 0.5 if bear else 1.0
