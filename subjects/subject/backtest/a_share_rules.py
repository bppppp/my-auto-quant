"""A 股交易规则. 见 subject.md §4.

涵盖:
- T+1 交割 (check_T_plus_1)
- 涨跌停限制 (主板 ±10% / 创科 ±20% / ST ±5%)
- 板块判定 (get_board, get_limit_pct)
- 一字板判定 (is_one_word_board)
- 流动性判定 (can_buy / can_sell)
"""
from __future__ import annotations

import pandas as pd


# 板块 → 涨跌幅限制 (小数)
_BOARD_LIMITS: dict[str, float] = {
    "main_沪主板": 0.10,    # 60xxxx.SH
    "main_深主板": 0.10,    # 00xxxx.SZ (000/001/002/003)
    "科创板": 0.20,         # 68xxxx.SH
    "创业板": 0.20,         # 30xxxx.SZ
    "北交所": 0.30,         # 92/83xxxx.BJ
}


def get_board(code: str, is_st: bool = False) -> str:
    """根据代码 (带后缀) 和是否 ST 返回板块名.

    Args:
        code: 带后缀代码 (如 ``"000001.SZ"``).
        is_st: 是否 ST 股票.

    Returns:
        板块名: ``"main_沪主板"`` / ``"main_深主板"`` / ``"科创板"`` / ``"创业板"``
        / ``"深B股"`` / ``"北交所"`` / ``"ST"`` / ``"unknown"``.
    """
    if is_st:
        return "ST"
    bare = code.split(".")[0] if "." in code else code
    if bare.startswith("60"):
        return "main_沪主板"
    if bare.startswith("68"):
        return "科创板"
    if bare.startswith(("000", "001", "002", "003")):
        return "main_深主板"
    if bare.startswith("30"):
        return "创业板"
    if bare.startswith("20"):
        return "深B股"
    if bare.startswith(("92", "83")):
        return "北交所"
    return "unknown"


def get_limit_pct(code: str, is_st: bool = False) -> float:
    """返回该股票的涨跌幅限制 (小数, 如 0.10).

    ST 股票统一 ±5%, 深B股 ±10%, 其它按板块.
    """
    if is_st:
        return 0.05
    board = get_board(code, is_st=False)
    if board == "深B股":
        return 0.10
    return _BOARD_LIMITS.get(board, 0.10)


def is_limit_up(row: pd.Series, epsilon: float = 0.5) -> bool:
    """是否涨停.

    优先用数据自带的 ``是否涨停`` 字段 (更准确, 考虑了停牌后第一日等特殊情况).
    Fallback: 用 ``涨幅%`` 与 limit_pct 比较.
    """
    if "是否涨停" in row.index and bool(row["是否涨停"]):
        return True
    pct = float(row.get("涨幅%", 0.0))
    code = row.get("代码", "")
    is_st = bool(row.get("是否ST", False))
    return pct >= get_limit_pct(code, is_st) * 100 - epsilon


def is_limit_down(row: pd.Series, epsilon: float = 0.5) -> bool:
    """是否跌停.

    数据不带"是否跌停"字段, 用 ``涨幅%`` 与 -limit_pct 比较.
    """
    pct = float(row.get("涨幅%", 0.0))
    code = row.get("代码", "")
    is_st = bool(row.get("是否ST", False))
    return pct <= -get_limit_pct(code, is_st) * 100 + epsilon


def is_one_word_board(row: pd.Series) -> bool:
    """是否一字板 (开盘 = 收盘 = 最高 = 最低, 且涨跌停).

    用 ``振幅%`` 极小 + 涨跌停组合判定 (数据无直接的"一字板"字段).
    """
    amplitude = float(row.get("振幅%", 100.0))
    if amplitude > 0.5:  # 振幅 > 0.5% 不算一字板
        return False
    return is_limit_up(row) or is_limit_down(row)


def is_one_word_down(row: pd.Series) -> bool:
    """是否一字跌停. 一字涨停不算 (一字涨停的持仓仍可卖)."""
    amplitude = float(row.get("振幅%", 100.0))
    if amplitude > 0.5:
        return False
    return is_limit_down(row)


def check_T_plus_1(holding_today: bool) -> bool:
    """T+1 判定: 当日买入的股票次日才能卖.

    Args:
        holding_today: 该股票今日已买入 (True 表示今日新增持仓, 不可卖).

    Returns:
        True 表示可以卖 (持有 ≥ 1 日); False 表示 T+1 限制下不可卖.
    """
    return not holding_today


def can_buy(row: pd.Series) -> bool:
    """综合判定: 当日能否买入.

    限制:
    - 涨停 → 不能买入 (排队也买不到, 避免"买到就是跌"陷阱)
    - 一字板 (含一字涨停/跌停) → 不能买入
    - ST 股票 → 不能买入
    """
    if is_limit_up(row):
        return False
    if is_one_word_board(row):
        return False
    if bool(row.get("是否ST", False)):
        return False
    return True


def can_sell(row: pd.Series) -> bool:
    """综合判定: 当日能否卖出.

    限制:
    - 跌停 → 不能卖出 (挂单也卖不出, 避免"卖不出反被埋"陷阱)
    - 一字跌停 → 不能卖出
    - **一字涨停不限制** (一字涨停的持仓可以在涨停价获利了结)

    See Also:
        :func:`is_one_word_down` —— 仅一字跌停的判断.
    """
    if is_limit_down(row):
        return False
    if is_one_word_down(row):
        return False
    return True
