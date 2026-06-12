"""按股票代码读 data-by-stock-factor/{code}_factor.csv.

失败模式 (返回 None, 不抛):
- 文件不存在
- CSV 解析失败
- 缺少'日期'列 (用 pd.to_datetime 会失败)
"""
from __future__ import annotations

import threading
from typing import Optional

import pandas as pd

from ._paths import DATA_ROOT


# ========== 全局因子缓存机制 ==========
_factor_cache: dict[str, pd.DataFrame] = {}
_factor_cache_lock = threading.Lock()
_factor_cache_hits = 0
_factor_cache_misses = 0


def get_factor_cache_stats() -> tuple[int, int]:
    """返回 (hits, misses) 统计."""
    return _factor_cache_hits, _factor_cache_misses


def clear_factor_cache() -> None:
    """清空因子缓存."""
    global _factor_cache, _factor_cache_hits, _factor_cache_misses
    with _factor_cache_lock:
        _factor_cache.clear()
        _factor_cache_hits = 0
        _factor_cache_misses = 0


def try_load_stock_factor(code: str, use_cache: bool = True) -> Optional[pd.DataFrame]:
    """读 data-by-stock-factor/{code}_factor.csv, 返回 DataFrame 或 None.

    Args:
        code: 6 位股票代码 (如 "000001"). 不带后缀.
        use_cache: 是否使用缓存 (默认 True). False 时强制重新读取.

    Returns:
        DataFrame (含 '日期' 列已转 datetime), 或 None (文件缺失/损坏).
    """
    global _factor_cache_hits, _factor_cache_misses

    # 缓存查找
    if use_cache:
        with _factor_cache_lock:
            if code in _factor_cache:
                _factor_cache_hits += 1
                return _factor_cache[code]

    # 磁盘读取
    path = DATA_ROOT / "data-by-stock-factor" / f"{code}_factor.csv"
    if not path.exists():
        return None
    try:
        # 注: 不能用 keep_default_na=False, 因为 CSV 里 NaN 被写为空字符串,
        # 读回来必须是 NaN 才能让下游 v.iloc[-1] 在 NaN 时走 pd.isna 分支.
        # 日期列转 datetime, 其他列保留默认(空 = NaN).
        df = pd.read_csv(path, dtype={"日期": str})
        df["日期"] = pd.to_datetime(df["日期"])
    except Exception:
        return None

    # 写入缓存
    if use_cache:
        with _factor_cache_lock:
            _factor_cache[code] = df
            _factor_cache_misses += 1

    return df


__all__ = [
    "try_load_stock_factor",
    "get_factor_cache_stats",
    "clear_factor_cache",
]
