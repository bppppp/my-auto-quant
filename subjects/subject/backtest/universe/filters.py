"""A 股硬约束过滤函数. 见 subject.md §4.3 / §3.4.

每个函数返回一个新 DataFrame (不修改原 df).
"""
from __future__ import annotations

import pandas as pd


def apply_universe(df: pd.DataFrame, codes: list[str]) -> pd.DataFrame:
    """保留 ``df["代码"]`` 在 codes 列表内的行.

    Args:
        df: 单日横截面 DataFrame.
        codes: 带后缀的代码列表 (如 ``["000001.SZ", "600000.SH"]``).
    """
    return df[df["代码"].isin(set(codes))].copy()


def exclude_bj(df: pd.DataFrame) -> pd.DataFrame:
    """排除北交所股票 (代码以 ``.BJ`` 结尾)."""
    return df[~df["代码"].str.endswith(".BJ")].copy()


def exclude_st(df: pd.DataFrame) -> pd.DataFrame:
    """排除 ST 股票 (``是否ST == True``)."""
    return df[~df["是否ST"]].copy()


def exclude_delisted(df: pd.DataFrame, ref_date: pd.Timestamp) -> pd.DataFrame:
    """排除在 ref_date 之前已退市的股票 (``退市时间 < ref_date``)."""
    mask = df["退市时间"].isna() | (df["退市时间"] >= ref_date)
    return df[mask].copy()


def exclude_new(
    df: pd.DataFrame,
    ref_date: pd.Timestamp,
    min_days: int = 60,
) -> pd.DataFrame:
    """排除上市未满 ``min_days`` 个交易日的股票.

    注: 简化用日历日 (与"交易日"略有差异, 实测差异 < 5%).
    """
    cutoff = ref_date - pd.Timedelta(days=min_days)
    return df[df["上市时间"] <= cutoff].copy()


def exclude_suspended(df: pd.DataFrame) -> pd.DataFrame:
    """排除停牌日 (``成交量（股） == 0``)."""
    return df[df["成交量（股）"] > 0].copy()
