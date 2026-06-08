"""subject.factors 内部 cache: ContextVar 传递当前 stock code + 模块级 cache.

API:
    bind_current_code(code) -> Token         # 设置当前 stock code
    reset_current_code(token) -> None        # reset (配对使用)
    bind_factor_cache(code, df) -> None      # 注入/移除某只股的 factor DF
    try_get_cached_factor(col, length=None) -> pd.Series | None

使用场景: runner 在主循环内 bind_current_code, factor 函数 try_get_cached_factor 命中.
"""
from __future__ import annotations

import contextvars
from typing import Optional

import pandas as pd

_current_code: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "factor_current_code", default=None
)
_factor_cache: dict[str, pd.DataFrame] = {}


def bind_current_code(code: Optional[str]) -> contextvars.Token:
    """设置当前激活的 stock code, 返回 Token 用于 reset."""
    return _current_code.set(code)


def reset_current_code(token: contextvars.Token) -> None:
    """重置 current code (配对 bind_current_code 使用)."""
    _current_code.reset(token)


def bind_factor_cache(code: str, factor_df: Optional[pd.DataFrame]) -> None:
    """注入/移除某只股的 factor DataFrame. None = 移除 (禁用 cache)."""
    if factor_df is not None:
        _factor_cache[code] = factor_df
    else:
        _factor_cache.pop(code, None)


def try_get_cached_factor(col: str, length: int | None = None) -> Optional[pd.Series]:
    """查当前 stock 的预计算 Series. col 不存在 / code 未设 / length 截取 后返回 None."""
    code = _current_code.get()
    if code is None:
        return None
    df = _factor_cache.get(code)
    if df is None or col not in df.columns:
        return None
    series = df[col]
    if length is not None and len(series) > length:
        series = series.iloc[:length].reset_index(drop=True)
    return series


__all__ = [
    "bind_current_code",
    "reset_current_code",
    "bind_factor_cache",
    "try_get_cached_factor",
]
