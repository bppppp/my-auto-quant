"""因子值分布统计. 见 subject.md §6.1.

每因子输出: min / max / mean / std / p25 / p50 / p75.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class FactorValueStats:
    factor: str
    min: float
    max: float
    mean: float
    std: float
    p25: float
    p50: float
    p75: float


def compute_factor_value_stats(
    factor: str,
    values: pd.Series,
) -> FactorValueStats:
    """计算单个因子的值分布.

    Args:
        factor: 因子名.
        values: 因子值 Series, NaN 会被 skip.

    Returns:
        :class:`FactorValueStats`.
    """
    v = values.dropna()
    if len(v) == 0:
        return FactorValueStats(factor, 0, 0, 0, 0, 0, 0, 0)
    return FactorValueStats(
        factor=factor,
        min=float(v.min()),
        max=float(v.max()),
        mean=float(v.mean()),
        std=float(v.std(ddof=0)),
        p25=float(v.quantile(0.25)),
        p50=float(v.quantile(0.50)),
        p75=float(v.quantile(0.75)),
    )
