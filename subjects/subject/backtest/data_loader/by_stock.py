"""单股时间序列加载 (params 模式数据源).

见 subject.md §3.1 / §3.6.
"""
from __future__ import annotations

import threading
from pathlib import Path

import pandas as pd

from ._paths import STOCK_DIR, STOCK_FILE_SUFFIX
from .preprocess import preprocess


# 必须保留为字符串的列 (含 leading zero 或分类值)
_STRING_COLS = (
    "代码", "名称", "所属行业",
    "是否ST", "是否涨停", "是否融资融券",
    "上市时间", "退市时间", "日期",
)

# ========== 全局缓存机制 ==========
# 使用线程锁保证线程安全
_stock_cache: dict[str, pd.DataFrame] = {}
_cache_lock = threading.Lock()
_cache_hits = 0
_cache_misses = 0


def get_cache_stats() -> tuple[int, int]:
    """返回 (hits, misses) 统计."""
    return _cache_hits, _cache_misses


def clear_stock_cache() -> None:
    """清空股票数据缓存."""
    global _stock_cache, _cache_hits, _cache_misses
    with _cache_lock:
        _stock_cache.clear()
        _cache_hits = 0
        _cache_misses = 0


def load_stock(code: str, use_cache: bool = True) -> pd.DataFrame:
    """加载单只股票全历史 (从上市日 ~ 2026-05-14).

    Args:
        code: 6 位纯数字代码 (如 ``"000001"``).
            函数会查 ``data-by-stock/{code}_金玥数据.csv``.
        use_cache: 是否使用缓存 (默认 True). False 时强制重新读取.

    Returns:
        DataFrame: 单股全历史, 按 ``日期`` 升序, 已执行 5 项预处理 (见 :func:`preprocess`).
        ``df["代码"]`` 列已加交易所后缀.

    Raises:
        FileNotFoundError: 该代码无对应 CSV 文件.
    """
    global _cache_hits, _cache_misses

    # 缓存查找 (加锁保护)
    if use_cache:
        with _cache_lock:
            if code in _stock_cache:
                _cache_hits += 1
                return _stock_cache[code]

    # 磁盘读取
    path: Path = STOCK_DIR / f"{code}{STOCK_FILE_SUFFIX}"
    if not path.exists():
        raise FileNotFoundError(f"No data-by-stock file for code={code!r}: {path}")

    df = pd.read_csv(path, dtype={c: str for c in _STRING_COLS}, keep_default_na=False)
    # 数值列: keep_default_na=False 会导致空字符串留为 "", 使整列变 object
    # 因此手动 coerce 数值列 (不在 _STRING_COLS 中的列大概率是数值)
    for col in df.columns:
        if col not in _STRING_COLS:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    preprocess(df)
    df = df.sort_values("日期").reset_index(drop=True)

    # 写入缓存
    if use_cache:
        with _cache_lock:
            _stock_cache[code] = df
            _cache_misses += 1

    return df
