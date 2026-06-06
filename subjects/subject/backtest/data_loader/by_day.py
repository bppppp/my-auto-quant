"""单日横截面加载 (weight 模式数据源).

见 subject.md §3.2 / §3.6.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from ._paths import DATA_ROOT
from .preprocess import preprocess


# 必须保留为字符串的列 (含 leading zero 或分类值)
_STRING_COLS = (
    "代码", "名称", "所属行业",
    "是否ST", "是否涨停", "是否融资融券",
    "上市时间", "退市时间", "日期",
)


def load_day(date: str) -> pd.DataFrame:
    """加载单日全市场横截面 (~4000-5000 行).

    Args:
        date: ``YYYY-MM-DD`` 格式交易日.
            函数会查 ``data-by-day/{YYYY}/{date}_金玥数据.csv``.

    Returns:
        DataFrame: 单日全 A, 已执行 5 项预处理. ``df["代码"]`` 列已加交易所后缀.

    Raises:
        FileNotFoundError: 该日期无对应 CSV 文件.
    """
    year = date[:4]
    path: Path = DATA_ROOT / "data-by-day" / year / f"{date}_金玥数据.csv"
    if not path.exists():
        raise FileNotFoundError(f"No data-by-day file for date={date!r}: {path}")

    df = pd.read_csv(path, dtype={c: str for c in _STRING_COLS}, keep_default_na=False)
    preprocess(df)
    return df
