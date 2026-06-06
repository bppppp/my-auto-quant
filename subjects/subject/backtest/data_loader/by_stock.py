"""单股时间序列加载 (params 模式数据源).

见 subject.md §3.1 / §3.6.
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


def load_stock(code: str) -> pd.DataFrame:
    """加载单只股票全历史 (从上市日 ~ 2026-05-14).

    Args:
        code: 6 位纯数字代码 (如 ``"000001"``).
            函数会查 ``data-by-stock/{code}_金玥数据.csv``.

    Returns:
        DataFrame: 单股全历史, 按 ``日期`` 升序, 已执行 5 项预处理 (见 :func:`preprocess`).
        ``df["代码"]`` 列已加交易所后缀.

    Raises:
        FileNotFoundError: 该代码无对应 CSV 文件.
    """
    path: Path = DATA_ROOT / "data-by-stock" / f"{code}_金玥数据.csv"
    if not path.exists():
        raise FileNotFoundError(f"No data-by-stock file for code={code!r}: {path}")

    df = pd.read_csv(path, dtype={c: str for c in _STRING_COLS}, keep_default_na=False)
    preprocess(df)
    df = df.sort_values("日期").reset_index(drop=True)
    return df
