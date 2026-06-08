"""按股票代码读 data-by-stock-factor/{code}_factor.csv.

失败模式 (返回 None, 不抛):
- 文件不存在
- CSV 解析失败
- 缺少'日期'列 (用 pd.to_datetime 会失败)
"""
from __future__ import annotations

from typing import Optional

import pandas as pd

from ._paths import DATA_ROOT


def try_load_stock_factor(code: str) -> Optional[pd.DataFrame]:
    """读 data-by-stock-factor/{code}_factor.csv, 返回 DataFrame 或 None.

    Args:
        code: 6 位股票代码 (如 "000001"). 不带后缀.

    Returns:
        DataFrame (含 '日期' 列已转 datetime), 或 None (文件缺失/损坏).
    """
    path = DATA_ROOT / "data-by-stock-factor" / f"{code}_factor.csv"
    if not path.exists():
        return None
    try:
        # 注: 不能用 keep_default_na=False, 因为 CSV 里 NaN 被写为空字符串,
        # 读回来必须是 NaN 才能让下游 v.iloc[-1] 在 NaN 时走 pd.isna 分支.
        # 日期列转 datetime, 其他列保留默认(空 = NaN).
        df = pd.read_csv(path, dtype={"日期": str})
        df["日期"] = pd.to_datetime(df["日期"])
        return df
    except Exception:
        return None


__all__ = ["try_load_stock_factor"]
