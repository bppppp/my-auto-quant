"""7 项回测指标. 见 subject.md §6.1 / subject_structure.md §7.1.

| 指标 | 公式 |
|---|---|
| annual_return | (final / initial) ** (365 / days) - 1 |
| avg_annual_return_rate | mean(daily_return) * 252 |
| avg_annual_return_amount | mean(daily_pnl) * 252 |
| win_rate | winning_trades / total_trades |
| profit_loss_ratio | mean(winning_pnl) / abs(mean(losing_pnl)) |
| sharpe | mean(daily_return) / std(daily_return) * sqrt(252) |
| max_drawdown | max((peak - trough) / peak) |
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class Metrics:
    annual_return: float
    avg_annual_return_rate: float
    avg_annual_return_amount: float
    win_rate: float
    profit_loss_ratio: float
    sharpe: float
    max_drawdown: float


def compute_metrics(
    initial_capital: float,
    daily_values: pd.Series,
    trades: pd.DataFrame,
) -> Metrics:
    """计算 7 项指标.

    Args:
        initial_capital: 初始资金.
        daily_values: 每日组合总市值, 按日期升序.
        trades: 交易历史 DataFrame, 必含列 ``pnl`` (单笔盈亏, 元).
            卖单才有 pnl, 买单 pnl = NaN. 由 runner 构造.

    Returns:
        :class:`Metrics` 实例.
    """
    n = len(daily_values)
    if n < 2 or initial_capital <= 0:
        return Metrics(0, 0, 0, 0, 0, 0, 0)

    final = float(daily_values.iloc[-1])
    days = (daily_values.index[-1] - daily_values.index[0]).days
    days = max(days, 1)

    annual_return = (final / initial_capital) ** (365.0 / days) - 1.0

    # 日收益率
    daily_ret = daily_values.pct_change().dropna()
    if len(daily_ret) == 0:
        sharpe = 0.0
        avg_annual_return_rate = 0.0
        avg_annual_return_amount = 0.0
    else:
        std = float(daily_ret.std(ddof=0))
        mean_ret = float(daily_ret.mean())
        sharpe = (mean_ret / std * math.sqrt(252)) if std > 0 else 0.0
        avg_annual_return_rate = mean_ret * 252
        avg_annual_return_amount = mean_ret * initial_capital * 252

    # 胜率 + 盈亏比
    pnls = trades["pnl"].dropna() if "pnl" in trades.columns else pd.Series(dtype=float)
    if len(pnls) == 0:
        win_rate = 0.0
        profit_loss_ratio = 0.0
    else:
        wins = pnls[pnls > 0]
        losses = pnls[pnls < 0]
        win_rate = len(wins) / len(pnls)
        if len(losses) > 0 and losses.mean() != 0:
            profit_loss_ratio = float(wins.mean() / abs(losses.mean())) if len(wins) > 0 else 0.0
        else:
            profit_loss_ratio = 0.0

    # 最大回撤
    peaks = daily_values.cummax()
    drawdowns = (daily_values - peaks) / peaks
    max_drawdown = float(drawdowns.min())  # 负数, 如 -0.15

    return Metrics(
        annual_return=float(annual_return),
        avg_annual_return_rate=float(avg_annual_return_rate),
        avg_annual_return_amount=float(avg_annual_return_amount),
        win_rate=float(win_rate),
        profit_loss_ratio=float(profit_loss_ratio),
        sharpe=float(sharpe),
        max_drawdown=float(max_drawdown),
    )
