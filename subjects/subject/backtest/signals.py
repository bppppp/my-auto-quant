"""信号引擎工具函数. 见 PARTS_SUMMARY.md §3 / subject_structure.md §4.3-§4.4.

本模块**不感知具体策略**——只提供:
- 入场多信号 AND 合并 + 权重求和 + top-N 排名
- 出场信号按权重降序排列
"""
from __future__ import annotations

from typing import TypeVar

T = TypeVar("T")  # signal name type


# ============ 入场侧 ============

def combine_signals_and(triggered: list[bool]) -> bool:
    """多信号 AND 合并: 所有信号触发才返回 True.

    空列表 → True (无约束, 永真).
    """
    if not triggered:
        return True
    out = True
    for t in triggered:
        out = out and bool(t)
    return out


def score_entry(
    triggered: dict[T, bool],
    weights: dict[T, float],
) -> float:
    """入场评分 = Σ(触发信号的 weight).

    Args:
        triggered: {signal_name: True/False}.
        weights: {signal_name: weight}.

    Returns:
        0.0 ~ Σ(weights) 之间的小数.
    """
    s = 0.0
    for name, is_triggered in triggered.items():
        if is_triggered:
            s += float(weights.get(name, 0.0))
    return s


def rank_top_n(
    scores: dict[T, float],
    top_n: int,
) -> list[T]:
    """按 score 降序取 top N (score > 0 才入选).

    Args:
        scores: {key: score}, score 必须 >= 0.
        top_n: 选 top N, N <= 0 视为全选.

    Returns:
        按 score 降序排列的 key 列表.
    """
    if top_n <= 0:
        return [k for k, v in sorted(scores.items(), key=lambda kv: kv[1], reverse=True) if v > 0]
    positives = [(k, v) for k, v in scores.items() if v > 0]
    positives.sort(key=lambda kv: kv[1], reverse=True)
    return [k for k, _ in positives[:top_n]]


# ============ 出场侧 ============

def prioritize_exit_signals(
    exit_weights: dict[T, float],
) -> list[T]:
    """出场信号按 weight 降序排列 (weight 高的先检查).

    Runner / strategy.py 遍历此列表, 第一个触发的信号先 return.
    """
    return sorted(exit_weights.keys(), key=lambda k: exit_weights[k], reverse=True)
