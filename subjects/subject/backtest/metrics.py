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
from dataclasses import dataclass, field

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
    # 平台无关的效率与稳定性指标（有默认值，向后兼容）
    avg_trade_return_pct: float = 0.0
    avg_win_pct: float = 0.0
    avg_loss_pct: float = 0.0
    win_loss_count_ratio: float = 0.0
    monthly_win_rate: float = 0.0
    max_consecutive_losses: int = 0
    max_consecutive_wins: int = 0
    trade_return_dist: dict = field(default_factory=lambda: {
        "win_0_3": 0, "win_3_10": 0, "win_10_plus": 0,
        "loss_0_3": 0, "loss_3_10": 0, "loss_10_plus": 0,
    })


def compute_metrics(
    initial_capital: float,
    daily_values: pd.Series,
    trades: pd.DataFrame,
    daily_high: pd.Series | None = None,
    daily_low: pd.Series | None = None,
) -> Metrics:
    """计算 7 项指标.

    Args:
        initial_capital: 初始资金.
        daily_values: 每日组合总市值, 按日期升序.
        trades: 交易历史 DataFrame, 必含列 ``pnl`` (单笔盈亏, 元).
            卖单才有 pnl, 买单 pnl = NaN. 由 runner 构造.
        daily_high: 组合日内 high (可选, P3 #7 用于 max_drawdown 日内计算).
            None 时退化为 close-based max_drawdown.
        daily_low: 组合日内 low (可选, P3 #7 用于 max_drawdown 日内计算).
            None 时退化为 close-based max_drawdown.

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
    # 日绝对盈亏 (元) — 用 diff() 而不是 pct_change() × capital, 避免相对值误差
    daily_pnl = daily_values.diff().dropna()
    if len(daily_ret) == 0 or len(daily_pnl) == 0:
        sharpe = 0.0
        avg_annual_return_rate = 0.0
        avg_annual_return_amount = 0.0
    else:
        # P2 #10 修复: sharpe 用 ddof=1 (样本标准差) 与行业惯例一致
        # 旧版 ddof=0 (总体标准差) 偏小 ~√(n/(n-1)) 倍, sharpe 偏大约 0.5%-1%
        std = float(daily_ret.std(ddof=1))
        mean_ret = float(daily_ret.mean())
        mean_pnl = float(daily_pnl.mean())
        sharpe = (mean_ret / std * math.sqrt(252)) if std > 0 else 0.0
        avg_annual_return_rate = mean_ret * 252
        # P1 #2 修复: 用 mean(daily_pnl) * 252 才是真正的"年化收益额" (元),
        # 旧版 mean_ret * initial_capital * 252 算的是"按初始资金 × 收益率推算的金额",
        # 当组合规模显著增长时与实际赚的钱差异巨大.
        avg_annual_return_amount = mean_pnl * 252

    # 胜率 + 盈亏比
    pnls = trades["pnl"].dropna() if "pnl" in trades.columns else pd.Series(dtype=float)
    if len(pnls) == 0:
        win_rate = 0.0
        profit_loss_ratio = 0.0
    else:
        wins = pnls[pnls > 0]
        losses = pnls[pnls < 0]
        win_rate = len(wins) / len(pnls)
        # 修复 (P0-2 v3): 盈亏比改为 sum/sum (A 股行业惯例 = payoff ratio).
        # 旧版 mean/mean 在 wins 与 losses 数量不同时会偏离 sum/sum 0.5-2 倍.
        if len(losses) > 0 and losses.sum() != 0:
            profit_loss_ratio = float(wins.sum() / abs(losses.sum())) if len(wins) > 0 else 0.0
        else:
            profit_loss_ratio = 0.0

    # 最大回撤
    # P3 #7 修复: 如果有日内 high/low, 用 high 的 cummax 作 peak, low 作 trough,
    # 算"high-water-mark → 日内低"最大回撤. 否则 fallback 到 close-based.
    if daily_high is not None and daily_low is not None and len(daily_high) == n and len(daily_low) == n:
        # 用 high 的 cummax 作 peak (历史最高 high), 看当日 low 相对历史最高 high 的回撤
        high_peaks = daily_high.cummax()
        drawdowns = (daily_low - high_peaks) / high_peaks
    else:
        peaks = daily_values.cummax()
        drawdowns = (daily_values - peaks) / peaks
    max_drawdown = float(drawdowns.min())  # 负数, 如 -0.15

    # === 平台无关的效率与稳定性指标 ===

    # 每笔收益率% (pnl_pct 由 runner 写入 trades)
    if "pnl_pct" in trades.columns:
        pnl_pcts = trades["pnl_pct"].dropna()
    else:
        pnl_pcts = pd.Series(dtype=float)

    if len(pnl_pcts) > 0:
        avg_trade_return_pct = float(pnl_pcts.mean())
        win_pcts = pnl_pcts[pnl_pcts > 0]
        loss_pcts = pnl_pcts[pnl_pcts < 0]
        avg_win_pct = float(win_pcts.mean()) if len(win_pcts) > 0 else 0.0
        avg_loss_pct = float(loss_pcts.mean()) if len(loss_pcts) > 0 else 0.0
    else:
        avg_trade_return_pct = 0.0
        avg_win_pct = 0.0
        avg_loss_pct = 0.0
        win_pcts = pd.Series(dtype=float)
        loss_pcts = pd.Series(dtype=float)

    # 收益率分桶分布
    trade_return_dist = {
        "win_0_3": 0, "win_3_10": 0, "win_10_plus": 0,
        "loss_0_3": 0, "loss_3_10": 0, "loss_10_plus": 0,
    }
    if len(pnl_pcts) > 0:
        trade_return_dist["win_0_3"] = int(((pnl_pcts > 0) & (pnl_pcts <= 0.03)).sum())
        trade_return_dist["win_3_10"] = int(((pnl_pcts > 0.03) & (pnl_pcts <= 0.10)).sum())
        trade_return_dist["win_10_plus"] = int((pnl_pcts > 0.10).sum())
        trade_return_dist["loss_0_3"] = int(((pnl_pcts < 0) & (pnl_pcts >= -0.03)).sum())
        trade_return_dist["loss_3_10"] = int(((pnl_pcts < -0.03) & (pnl_pcts >= -0.10)).sum())
        trade_return_dist["loss_10_plus"] = int((pnl_pcts < -0.10).sum())

    # 盈亏次数比
    if len(pnls) > 0:
        n_wins = len(pnls[pnls > 0])
        n_losses = len(pnls[pnls < 0])
        win_loss_count_ratio = n_wins / n_losses if n_losses > 0 else 0.0
    else:
        win_loss_count_ratio = 0.0
        n_wins = 0
        n_losses = 0

    # 月胜率
    monthly_win_rate = 0.0
    if len(daily_values) >= 20:  # 至少 20 个交易日 (~1 个月) 才有意义
        monthly_end = daily_values.resample("ME").last().dropna()
        if len(monthly_end) >= 1:
            monthly_ret = monthly_end.pct_change().dropna()
            if len(monthly_ret) > 0:
                monthly_win_rate = float((monthly_ret > 0).sum() / len(monthly_ret))

    # 最大连续盈利/亏损笔数
    max_consecutive_wins = 0
    max_consecutive_losses = 0
    cur_wins = 0
    cur_losses = 0
    for p in pnls:
        if p > 0:
            cur_wins += 1
            cur_losses = 0
            max_consecutive_wins = max(max_consecutive_wins, cur_wins)
        elif p < 0:
            cur_losses += 1
            cur_wins = 0
            max_consecutive_losses = max(max_consecutive_losses, cur_losses)
        # p == 0: 不改变连胜/连亏

    return Metrics(
        annual_return=float(annual_return),
        avg_annual_return_rate=float(avg_annual_return_rate),
        avg_annual_return_amount=float(avg_annual_return_amount),
        win_rate=float(win_rate),
        profit_loss_ratio=float(profit_loss_ratio),
        sharpe=float(sharpe),
        max_drawdown=float(max_drawdown),
        avg_trade_return_pct=avg_trade_return_pct,
        avg_win_pct=avg_win_pct,
        avg_loss_pct=avg_loss_pct,
        win_loss_count_ratio=win_loss_count_ratio,
        monthly_win_rate=monthly_win_rate,
        max_consecutive_losses=max_consecutive_losses,
        max_consecutive_wins=max_consecutive_wins,
        trade_return_dist=trade_return_dist,
    )
