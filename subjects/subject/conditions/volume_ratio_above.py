"""量能放大判断. 见 PARTS_SUMMARY.md §2."""
from __future__ import annotations


def check_volume_ratio_above(
    volume_ratio: float,
    threshold: float,
) -> bool:
    """判断 volume_ratio 是否 > threshold.

    Args:
        volume_ratio: 量比值 (scalar 或 pd.Series, 通常来自 ``factors["volume_ratio_20"]``).
        threshold: 阈值 (如 1.5 表示 1.5 倍放量).

    Returns:
        bool 或 bool Series: True 表示放量.
    """
    return volume_ratio > threshold
