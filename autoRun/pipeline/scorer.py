"""
pipeline.scorer — 评分函数 (用户确认: 极简版)

score = annual_return
argmax(score) 选最优
"""
from __future__ import annotations

from typing import Iterable


def score(metrics: dict) -> float:
    """极简版评分: 仅看 annual_return.

    Args:
        metrics: parser.parse_report() 返回的指标 dict

    Returns:
        越大越好. 无 annual_return 时返回 -inf.
    """
    return metrics.get("annual_return", float("-inf"))


def pick_best(versions: Iterable[tuple[str, dict]]):
    """从 [(version, metrics), ...] 中选 annual_return 最大的.

    Args:
        versions: iterable of (version_str, metrics_dict)

    Returns:
        (best_version, best_metrics)

    Raises:
        ValueError: versions 为空
    """
    versions_list = list(versions)
    if not versions_list:
        raise ValueError("versions 为空, 无候选")
    return max(versions_list, key=lambda vm: score(vm[1]))


__all__ = ["score", "pick_best"]
