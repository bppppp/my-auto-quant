"""5 项必做数据预处理. 见 subject.md §3.5.

1. ``代码`` 补后缀: ``000001`` → ``000001.SZ`` (60/68 → SH; 00/30/20 → SZ; 92/83 → BJ)
2. ``名称`` 去全角空格: ``万  科Ａ`` → ``万科A``
3. ``退市时间`` ``-`` → ``NaT`` (pd.to_datetime coerce)
4. ``日期`` → ``pd.Timestamp``
5. ``是否ST`` / ``是否涨停`` / ``是否融资融券`` → ``bool``
"""
from __future__ import annotations

import pandas as pd


_BOOL_MAP = {"是": True, "否": False, "": False, "True": True, "False": False, "true": True, "false": False}


def _add_exchange_suffix(code: str) -> str:
    """6 位纯数字代码 → 带交易所后缀."""
    if not isinstance(code, str):
        code = str(code)
    if code.startswith(("60", "68")):
        return code + ".SH"
    if code.startswith(("00", "30", "20")):
        return code + ".SZ"
    if code.startswith(("92", "83")):
        return code + ".BJ"
    return code  # 未知前缀, 保持原样


def preprocess(df: pd.DataFrame) -> pd.DataFrame:
    """对从 CSV 读出的 DataFrame 执行 5 项必做处理 (in-place + return).

    Args:
        df: 刚从 ``pd.read_csv`` 出来的 DataFrame (38 列, 见 subject.md §3.3).

    Returns:
        同样的 DataFrame, 列已转换.
    """
    # 1. 代码补后缀
    df["代码"] = df["代码"].map(_add_exchange_suffix)

    # 2. 名称去全角空格
    df["名称"] = df["名称"].astype(str).str.replace(r"\s+", "", regex=True)

    # 3. 退市时间 "-" → NaT
    df["退市时间"] = pd.to_datetime(df["退市时间"], errors="coerce", format="%Y-%m-%d")

    # 4. 日期 → pd.Timestamp
    df["日期"] = pd.to_datetime(df["日期"])

    # 5. bool 列
    for col in ("是否ST", "是否涨停", "是否融资融券"):
        if col in df.columns:
            df[col] = df[col].replace(_BOOL_MAP).astype(bool)

    return df
