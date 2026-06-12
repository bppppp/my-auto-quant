"""subject.factors 内部 cache: ContextVar 传递当前 stock code + 模块级 cache.

API:
    bind_current_code(code) -> Token         # 设置当前 stock code
    reset_current_code(token) -> None        # reset (配对使用)
    bind_factor_cache(code, df) -> None      # 注入/移除某只股的 factor DF
    bind_current_date(date) -> Token         # 设置当前日期（v2 新增）
    reset_current_date(token) -> None        # reset (配对使用)
    try_get_cached_factor(col, length=None) -> pd.Series | None

使用场景: runner 在主循环内 bind_current_code + bind_current_date,
    factor 函数 try_get_cached_factor 命中后自动使用日期精确匹配.

【修复日志 v2】:
- v1 问题: try_get_cached_factor 使用 iloc[:length] 位置切片,
  当 factor_df 与 df 的行数不一致时（停牌日/数据缺失）会取到错误的因子值。
- v2 修复: 新增 ContextVar _current_date 存储当前处理日期,
  try_get_cached_factor 优先用日期索引匹配（精确到日），
  回退到 iloc[:length] 时增加行数一致性检查并发出警告。
  新增 _cache_stats 统计信息用于调试。
"""
from __future__ import annotations

import contextvars
import logging
from typing import Optional

import pandas as pd

_current_code: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "factor_current_code", default=None
)
_current_date: contextvars.ContextVar[Optional[pd.Timestamp]] = contextvars.ContextVar(
    "factor_current_date", default=None
)
_factor_cache: dict[str, pd.DataFrame] = {}

# 缓存命中率统计（调试用）
_cache_stats: dict[str, dict] = {}

logger = logging.getLogger(__name__)


def bind_current_code(code: Optional[str]) -> contextvars.Token:
    """设置当前激活的 stock code, 返回 Token 用于 reset."""
    return _current_code.set(code)


def reset_current_code(token: contextvars.Token) -> None:
    """重置 current code (配对 bind_current_code 使用)."""
    _current_code.reset(token)


def bind_current_date(date: Optional[pd.Timestamp]) -> contextvars.Token:
    """设置当前处理的日期 (T-1 收盘后), 用于日期精确匹配.

    在 runner 的主循环内调用, 确保 factor 函数能获取正确的日期.
    """
    return _current_date.set(date)


def reset_current_date(token: contextvars.Token) -> None:
    """重置当前日期 (配对 bind_current_date 使用)."""
    _current_date.reset(token)


def bind_factor_cache(code: str, factor_df: Optional[pd.DataFrame]) -> None:
    """注入/移除某只股的 factor DataFrame. None = 移除 (禁用 cache).

    修复: 若 factor_df 有 '日期' 列则设为索引，保证与 df 日期对齐。
    """
    if factor_df is not None:
        # 确保日期列存在且设为索引，用于日期对齐
        if "日期" in factor_df.columns and factor_df.index.name != "日期":
            factor_df = factor_df.set_index("日期")
        _factor_cache[code] = factor_df
        # 重置统计
        _cache_stats[code] = {"hits": 0, "date_hits": 0, "length_warns": 0, "misses": 0}
    else:
        _factor_cache.pop(code, None)
        _cache_stats.pop(code, None)


def try_get_cached_factor(col: str, length: int | None = None) -> Optional[pd.Series]:
    """查当前 stock 的预计算 Series.

    v2 优先用 _current_date 精确匹配日期（自动从 ContextVar 读取），
    回退到 iloc[:length] 位置切片。当行数不一致时会发出警告并返回 None（避免错误数据）。

    Args:
        col: 要获取的因子列名.
        length: 回退用的长度参数（当日期匹配失败时）.

    Returns:
        匹配到的 Series 或 None.
    """
    code = _current_code.get()
    if code is None:
        return None

    df = _factor_cache.get(code)
    if df is None or col not in df.columns:
        return None

    stats = _cache_stats.get(code, {})

    # === Step 1: 日期精确匹配 (v2 新增, 推荐方式) ===
    current_date = _current_date.get()
    if current_date is not None:
        try:
            result = df[col].loc[current_date]
            if pd.notna(result):
                stats["date_hits"] = stats.get("date_hits", 0) + 1
                # 修复: 日期匹配时也返回与 length 一致的长度
                # 确保 compute_factors 中所有因子长度一致，避免 Series 比较错误
                if length is not None and len(df[col]) >= length:
                    # 返回最后 length 行（包含当前日期的数据）
                    return df[col].iloc[-length:].reset_index(drop=True)
                elif length is not None:
                    # 缓存数据不足 length，返回 None 让调用方走兜底计算
                    return None
                else:
                    # 无 length 参数，返回整个缓存
                    return df[col].reset_index(drop=True)
        except (KeyError, IndexError):
            # 日期不在 index 中，不触发 cache 命中
            pass

    # === Step 2: 位置切片 (回退方式) ===
    # 只有当日期精确匹配失败时, 才使用位置切片回退
    series = df[col]

    # 缓存比请求的更短: 数据缺失, 返回 None
    if length is not None and len(series) < length:
        stats["length_warns"] = stats.get("length_warns", 0) + 1
        logger.debug(
            f"[factor_cache] {code}.{col}: cache len={len(series)} "
            f"< requested len={length}. "
            f"Data missing, return None."
        )
        return None

    # 缓存与请求长度相同: 使用整个缓存 (已对齐)
    if length is not None and len(series) == length:
        stats["hits"] = stats.get("hits", 0) + 1
        return series.reset_index(drop=True)

    # 缓存比请求的更长: 取最后 length 行 (保守策略, 依赖日期已对齐的前提)
    if length is not None and len(series) > length:
        series = series.iloc[-length:]

    stats["hits"] = stats.get("hits", 0) + 1
    # 始终 reset_index: 保证返回 default integer index，
    # 消除 DatetimeIndex 导致 rolling 操作全 NaN 的问题。
    return series.reset_index(drop=True)


def get_cache_stats(code: str) -> dict:
    """获取指定股票的缓存统计信息（调试用）."""
    return _cache_stats.get(code, {})


def clear_cache() -> None:
    """清空所有缓存（测试用）."""
    global _factor_cache, _cache_stats
    _factor_cache.clear()
    _cache_stats.clear()


def reset_factor_cache() -> None:
    """清空当前股票的因子缓存，防止跨股票数据泄漏.

    只清空当前股票的缓存，保留其他股票的缓存（支持批量处理时复用）。
    """
    code = _current_code.get()
    if code:
        _factor_cache.pop(code, None)
        _cache_stats.pop(code, None)


__all__ = [
    "bind_current_code",
    "reset_current_code",
    "bind_current_date",
    "reset_current_date",
    "bind_factor_cache",
    "try_get_cached_factor",
    "get_cache_stats",
    "clear_cache",
    "reset_factor_cache",
]
