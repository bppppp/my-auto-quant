"""组合管理: 调仓 / 加减仓 / 5 个仓位约束函数.

见 PARTS_SUMMARY.md §3 / subject_structure.md §5 / §4.7-§4.8.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import pandas as pd

from .data_loader.by_day import load_day
from .fees import calc_buy_fee, calc_sell_fee


# =========================
# Position: 单只股票持仓
# =========================

@dataclass
class Position:
    code: str
    shares: int
    entry_price: float
    entry_date: pd.Timestamp
    highest: float
    holding_days: int = 0
    """入场后最高收盘价. 组合层每根 K 线更新: highest = max(previous_highest, close)."""

    def to_state_dict(self) -> dict:
        """转成 strategy.should_exit(position, ...) 需要的 dict. 见 PARTS_SUMMARY.md §2.5."""
        return {
            "code": self.code,
            "current_price": None,  # 由 caller 注入
            "entry_price": self.entry_price,
            "highest": self.highest,
            "holding_days": self.holding_days,
            "pnl_pct": None,        # 由 caller 注入
            "shares": self.shares,
        }


# =========================
# Portfolio: 组合管理
# =========================

@dataclass
class Portfolio:
    initial_capital: float
    cash: float
    positions: dict[str, Position] = field(default_factory=dict)
    """当前持仓 {code: Position}."""
    history: list[dict] = field(default_factory=list)
    """交易历史, 每条 {date, code, action, shares, price, fee, amount}."""

    # ----- 基础查询 -----
    def get_position(self, code: str) -> Position | None:
        return self.positions.get(code)

    def total_value(self, prices: dict[str, float]) -> float:
        """组合总市值 = 现金 + Σ(shares × price)."""
        v = self.cash
        for code, pos in self.positions.items():
            p = prices.get(code, pos.entry_price)
            v += pos.shares * p
        return v

    def weights(self, prices: dict[str, float]) -> dict[str, float]:
        """当前每只股票的 weight = (shares × price) / total_value."""
        tv = self.total_value(prices)
        if tv <= 0:
            return {}
        out: dict[str, float] = {}
        for code, pos in self.positions.items():
            p = prices.get(code, pos.entry_price)
            out[code] = pos.shares * p / tv
        return out

    # ----- 交易执行 -----
    def buy(
        self,
        code: str,
        price: float,
        shares: int,
        date: pd.Timestamp,
    ) -> tuple[int, float]:
        """执行买入 (假设 100 股整数倍 + T+1 检查由 caller 保证).

        entry_price = (amount + fee) / shares  —— **含费用调整** (见 PARTS_SUMMARY §2.5).
        加仓时, new entry_price 为**含费总成本**的加权平均.

        Returns:
            (actual_shares, total_cost). total_cost = amount + fee, 从 cash 扣除.
        """
        if shares <= 0:
            return 0, 0.0
        if shares % 100 != 0:
            # 自动向下取整到 100 倍 (A 股最小买入 100 股)
            shares = (shares // 100) * 100
            if shares == 0:
                return 0, 0.0
        amount = price * shares
        fee = calc_buy_fee(amount, code)
        total_cost = amount + fee
        if total_cost > self.cash:
            return 0, 0.0  # 现金不足, 拒绝
        self.cash -= total_cost
        # 含费 entry_price (PARTS_SUMMARY §2.5)
        effective_entry = (amount + fee) / shares
        if code in self.positions:
            # 加仓: 含费总成本 / 新股数
            pos = self.positions[code]
            new_shares = pos.shares + shares
            new_total_cost = pos.entry_price * pos.shares + effective_entry * shares
            pos.shares = new_shares
            pos.entry_price = new_total_cost / new_shares
            pos.highest = max(pos.highest, price)
        else:
            self.positions[code] = Position(
                code=code, shares=shares,
                entry_price=effective_entry, entry_date=date,
                highest=price, holding_days=0,
            )
        self.history.append({
            "date": date, "code": code, "action": "buy",
            "shares": shares, "price": price, "fee": fee, "amount": amount,
        })
        return shares, total_cost

    def sell(
        self,
        code: str,
        price: float,
        date: pd.Timestamp,
    ) -> float:
        """执行卖出全部持仓.

        Returns:
            proceeds (卖出净额 = amount - fee, 加到 cash).
        """
        pos = self.positions.get(code)
        if pos is None or pos.shares <= 0:
            return 0.0
        shares = pos.shares
        amount = price * shares
        fee = calc_sell_fee(amount, code)
        proceeds = amount - fee
        self.cash += proceeds
        del self.positions[code]
        self.history.append({
            "date": date, "code": code, "action": "sell",
            "shares": shares, "price": price, "fee": fee, "amount": amount,
        })
        return proceeds

    # ----- 每根 K 线更新 -----
    def update_after_bar(self, code: str, close: float) -> None:
        """每根 K 线收盘后更新 position 状态 (highest, holding_days).

        T+1: 持仓首日的 holding_days=0, 下一日开始 +1, 即第 2 日 holding_days=1.
        """
        pos = self.positions.get(code)
        if pos is None:
            return
        pos.highest = max(pos.highest, close)
        pos.holding_days += 1


# =========================
# 5 个仓位约束函数 (subject_structure.md §5)
# =========================

def enforce_max_single_weight(
    weights: dict[str, float],
    max_pct: float,
) -> dict[str, float]:
    """约束单票最大权重, 超出部分等比缩放.

    Args:
        weights: {code: target_weight}, 总和 = 1.
        max_pct: 单票上限 (小数, 如 0.10).

    Returns:
        调整后 weights, 总和仍 = 1.
    """
    if not weights or max_pct <= 0:
        return weights
    out: dict[str, float] = {}
    excess = 0.0
    for code, w in weights.items():
        if w > max_pct:
            excess += w - max_pct
            out[code] = max_pct
        else:
            out[code] = w
    # 多出的 weight 按比例加到其他未触顶的股票
    if excess > 0:
        others = {k: v for k, v in out.items() if v < max_pct}
        others_total = sum(others.values())
        if others_total > 0:
            scale = (others_total + excess) / others_total
            for k in others:
                out[k] *= scale
        else:
            # 全部触顶 → 等比缩放
            for k in out:
                out[k] = max_pct
    return out


def enforce_industry_concentration(
    weights: dict[str, float],
    industry_map: dict[str, str],
    max_pct: float,
) -> dict[str, float]:
    """约束单一行业总权重, 超出部分按比例缩放.

    Args:
        weights: {code: weight}.
        industry_map: {code: industry_name} (由 :func:`load_industry_map` 构造).
        max_pct: 单一行业上限 (小数, 如 0.30).
    """
    if not weights or max_pct <= 0:
        return weights
    # 按行业聚合
    industry_total: dict[str, float] = {}
    for code, w in weights.items():
        ind = industry_map.get(code, "unknown")
        industry_total[ind] = industry_total.get(ind, 0.0) + w
    # 找出超限的行业, 缩放
    scale: dict[str, float] = {}
    for ind, total in industry_total.items():
        if total > max_pct:
            scale[ind] = max_pct / total
        else:
            scale[ind] = 1.0
    out: dict[str, float] = {}
    for code, w in weights.items():
        ind = industry_map.get(code, "unknown")
        out[code] = w * scale[ind]
    # 重新归一化到 1
    s = sum(out.values())
    if s > 0 and abs(s - 1.0) > 1e-6:
        out = {k: v / s for k, v in out.items()}
    return out


def rebalance_to_target_holdings(
    current_holdings: list[str],
    target: int,
    candidates: list[tuple[str, float]],
) -> tuple[list[str], dict[str, float]]:
    """从候选中选 top N 替换当前持仓, 输出新持仓与等权 weight 映射.

    Args:
        current_holdings: 当前持仓代码列表.
        target: 目标持仓数 (N).
        candidates: [(code, score)] 按 score 降序排列, 由 :func:`signals.rank_top_n` 生成.

    Returns:
        (new_holdings, new_weights). new_holdings 保留 current_holdings 中仍在 candidates top-N 内的;
        新进 top-N 的填入; 剩下的卖出. weights 等权 1/N.
    """
    if target <= 0:
        return [], {}
    top_codes = [c for c, _ in candidates[:target]]
    new_holdings = [c for c in top_codes]
    weight = 1.0 / target
    new_weights = {c: weight for c in new_holdings}
    return new_holdings, new_weights


def enforce_max_turnover(
    current: dict[str, float],
    target: dict[str, float],
    max_pct: float,
) -> dict[str, float]:
    """限制单次再平衡换手上限. 换手率 = (|target - current| 总和) / 2.

    Args:
        current: 当前 weight.
        target: 目标 weight.
        max_pct: 换手上限 (小数, 如 0.50 表示最多换 50%).

    Returns:
        调整后 target (向 current 方向回退, 换手率 <= max_pct).
    """
    if not target or max_pct <= 0:
        return target
    turnover = sum(abs(target.get(c, 0.0) - current.get(c, 0.0)) for c in set(target) | set(current)) / 2.0
    if turnover <= max_pct:
        return target
    # 超限: 目标向当前方向回退
    scale = max_pct / turnover
    out: dict[str, float] = {}
    all_codes = set(target) | set(current)
    for c in all_codes:
        cur = current.get(c, 0.0)
        tgt = target.get(c, 0.0)
        out[c] = cur + (tgt - cur) * scale
    return out


def should_rebalance(
    bar_index: int,
    freq_bars: int,
) -> bool:
    """判断今天是否应再平衡 (基于 bar 计数, 即**交易日**计数).

    Args:
        bar_index: 0-based 交易日索引 (runner 顺序迭代 trading_dates 时的下标).
        freq_bars: 再平衡频率 (交易日, 如 5 表示每 5 个交易日).

    Returns:
        True 表示应再平衡 (含首次, 即 bar_index=0).

    Examples:
        freq_bars=5 → 在 bar_index = 0, 5, 10, 15, ... 触发.
    """
    if freq_bars <= 0:
        return False
    return bar_index % freq_bars == 0


# =========================
# 行业映射加载 (subject_structure.md §4.7)
# =========================

def load_industry_map(
    universe_codes: list[str],
    date: str,
) -> dict[str, str]:
    """从 data_by_day 单日横截面读 universe 的行业映射.

    Args:
        universe_codes: 带后缀代码列表.
        date: ``YYYY-MM-DD`` 日期.

    Returns:
        {code: industry_name}.
    """
    df = load_day(date)
    sub = df[df["代码"].isin(set(universe_codes))]
    return dict(zip(sub["代码"], sub["所属行业"]))
