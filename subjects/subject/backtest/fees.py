"""A 股交易费用. 见 subject.md §4.4.

| 费用项 | 费率 | 备注 |
|---|---|---|
| 买入佣金 | 万 2.5 | 最低 5 元 |
| 沪市过户费 | 万 0.1 | 仅沪市 (.SH) 收取 |
| 卖出印花税 | 万 10 | 卖出时加收 |
"""
from __future__ import annotations

# 费率 (小数)
_BUY_COMMISSION_RATE = 0.00025
_TRANSFER_FEE_RATE = 0.00001  # 沪市过户费
_SELL_STAMP_TAX_RATE = 0.001
_MIN_COMMISSION = 5.0  # 元


def _commission(amount: float) -> float:
    """佣金 = 交易额 × 万 2.5, 最低 5 元."""
    return max(amount * _BUY_COMMISSION_RATE, _MIN_COMMISSION)


def calc_buy_fee(amount: float, code: str) -> float:
    """计算买入总费用.

    Args:
        amount: 买入交易额 (元) = 成交价 × 股数.
        code: 带后缀代码 (如 ``"000001.SZ"`` / ``"600000.SH"``).

    Returns:
        总费用 (元), 含佣金 + 沪市过户费 (如适用).
    """
    fee = _commission(amount)
    if code.endswith(".SH"):
        fee += amount * _TRANSFER_FEE_RATE
    return fee


def calc_sell_fee(amount: float, code: str) -> float:
    """计算卖出总费用.

    Args:
        amount: 卖出交易额 (元) = 成交价 × 股数.
        code: 带后缀代码.

    Returns:
        总费用 (元), 含佣金 + 沪市过户费 + 卖出印花税.
    """
    fee = _commission(amount)
    if code.endswith(".SH"):
        fee += amount * _TRANSFER_FEE_RATE
    fee += amount * _SELL_STAMP_TAX_RATE
    return fee
