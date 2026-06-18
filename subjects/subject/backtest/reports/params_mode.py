"""params 模式报告 (MD 格式). 见 subject.md §6.1 / subject_structure.md §7.1.

报告章节:
1. 元信息
2. Metrics (7 项)
3. Signal Stats (per signal)
4. Factor Value Stats (per factor)
5. monitor_meta (仅 monitor 调用)
"""
from __future__ import annotations

from datetime import datetime
from typing import Iterable

from ..metrics import Metrics
from ..stats import SignalStats, FactorValueStats


def render_params_report(
    strategy: str,
    version: str,
    metrics: Metrics,
    signal_stats: Iterable[SignalStats],
    factor_stats: Iterable[FactorValueStats],
    monitor_meta: dict | None = None,
    extra_notes: list[str] | None = None,
    test_conditions: dict | None = None,
) -> str:
    """渲染 params 模式报告.

    Args:
        strategy: 策略名.
        version: 版本号, 如 ``"v1"``.
        metrics: 7 项指标.
        signal_stats: 各信号统计.
        factor_stats: 各因子值分布.
        monitor_meta: 仅 monitor 调用时传入, 字段见 subject.md §5.1.
        extra_notes: 附加注释 (spec 审查报告等).
        test_conditions: 测试条件 dict (来自 BacktestRunner._build_test_conditions),
            含 test_universe / universe_size / start_date / end_date / limit / weight_test.

    Returns:
        Markdown 报告字符串.
    """
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines: list[str] = []
    lines.append(f"# Params Mode Report")
    lines.append("")
    lines.append(f"**strategy**: {strategy}")
    lines.append(f"**version**: {version}")
    lines.append(f"**date**: {now}")
    lines.append("")

    # === 测试条件 (新) ===
    if test_conditions is not None:
        lines.append("## 测试条件")
        lines.append("")
        lines.append("| 中文名 | 英文名 | 值 |")
        lines.append("|---|---|---|")
        lines.append(f"| 测试集 | test_universe | {test_conditions.get('test_universe', '')} |")
        lines.append(f"| 实际测试股票数 | universe_size | {test_conditions.get('universe_size', '')} |")
        lines.append(f"| 测试起始日期 | start_date | {test_conditions.get('start_date', '')} |")
        lines.append(f"| 测试结束日期 | end_date | {test_conditions.get('end_date', '')} |")
        lines.append(f"| 股票数限制 | limit | {test_conditions.get('limit', '')} |")
        lines.append("")

    # 效率与稳定性（平台无关指标 — 重点摘要）
    lines.append("## 效率与稳定性")
    lines.append("")
    lines.append("| 中文名 | 英文名 | 值 |")
    lines.append("|---|---|---|")
    lines.append(f"| 平均每笔收益率 | avg_trade_return_pct | {metrics.avg_trade_return_pct:.2%} |")
    lines.append(f"| 平均盈利 | avg_win_pct | {metrics.avg_win_pct:.2%} |")
    lines.append(f"| 平均亏损 | avg_loss_pct | {metrics.avg_loss_pct:.2%} |")
    lines.append(f"| 盈亏次数比 | win_loss_count_ratio | {metrics.win_loss_count_ratio:.2f} |")
    lines.append(f"| 月胜率 | monthly_win_rate | {metrics.monthly_win_rate:.2%} |")
    lines.append(f"| 最大连续盈利 | max_consecutive_wins | {metrics.max_consecutive_wins} |")
    lines.append(f"| 最大连续亏损 | max_consecutive_losses | {metrics.max_consecutive_losses} |")
    lines.append("")

    # 收益率分桶分布
    if hasattr(metrics, 'trade_return_dist') and metrics.trade_return_dist:
        d = metrics.trade_return_dist
        total = sum(d.values())
        if total > 0:
            lines.append("## 每笔收益率分布")
            lines.append("")
            lines.append("| 区间 | 笔数 | 占比 |")
            lines.append("|---|---|---|")
            lines.append(f"| 盈利 >10% | {d.get('win_10_plus', 0)} | {d.get('win_10_plus', 0)/total*100:.1f}% |")
            lines.append(f"| 盈利 3%~10% | {d.get('win_3_10', 0)} | {d.get('win_3_10', 0)/total*100:.1f}% |")
            lines.append(f"| 盈利 0~3% | {d.get('win_0_3', 0)} | {d.get('win_0_3', 0)/total*100:.1f}% |")
            lines.append(f"| 亏损 0~3% | {d.get('loss_0_3', 0)} | {d.get('loss_0_3', 0)/total*100:.1f}% |")
            lines.append(f"| 亏损 3%~10% | {d.get('loss_3_10', 0)} | {d.get('loss_3_10', 0)/total*100:.1f}% |")
            lines.append(f"| 亏损 >10% | {d.get('loss_10_plus', 0)} | {d.get('loss_10_plus', 0)/total*100:.1f}% |")
            lines.append("")

    # Metrics（7 项，3 列：中文名 | 英文名 | 值）
    lines.append("## Metrics")
    lines.append("")
    lines.append("| 中文名 | 英文名 | 值 |")
    lines.append("|---|---|---|")
    lines.append(f"| 年化收益 | annual_return | {metrics.annual_return:.4%} |")
    lines.append(f"| 年化收益率 | avg_annual_return_rate | {metrics.avg_annual_return_rate:.4%} |")
    lines.append(f"| 年化收益额 | avg_annual_return_amount | {metrics.avg_annual_return_amount:,.2f} |")
    lines.append(f"| 胜率 | win_rate | {metrics.win_rate:.4%} |")
    lines.append(f"| 盈亏比 | profit_loss_ratio | {metrics.profit_loss_ratio:.4f} |")
    lines.append(f"| 夏普 | sharpe | {metrics.sharpe:.4f} |")
    lines.append(f"| 最大回撤 | max_drawdown | {metrics.max_drawdown:.4%} |")
    lines.append("")

    # Signal Stats
    lines.append("## Signal Stats")
    lines.append("")
    # Bug #2 修复: 新增 '出场次数' 列, 反映"入场-出场"闭环完成度
    lines.append("| 信号名 | 触发次数 | 出场次数 | 被吞次数 | 跳过次数 | 盈利次数 | 胜率 | 平均收益 | 中位持仓天数 |")
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for s in signal_stats:
        lines.append(
            f"| {s.signal} | {s.triggered} | {s.exits} | {s.swallowed} | {s.skipped} | "
            f"{s.win_count} | {s.win_rate:.2%} | {s.avg_return:.2f} | {s.median_holding_days:.1f} |"
        )
    lines.append("")

    # 持仓天数分布
    lines.append("## 持仓天数分布")
    lines.append("")
    lines.append("| 信号名 | ≤5天 | ≤10天 | ≤15天 | ≤20天 | ≤25天 | ≤30天 | >30天 |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for s in signal_stats:
        if s.holding_days_dist:
            hd = s.holding_days_dist
            lines.append(
                f"| {s.signal} | {hd.get(5, 0)} | {hd.get(10, 0)} | {hd.get(15, 0)} | "
                f"{hd.get(20, 0)} | {hd.get(25, 0)} | {hd.get(30, 0)} | {hd.get('+∞', 0)} |"
            )
        else:
            lines.append(f"| {s.signal} | - | - | - | - | - | - | - |")
    lines.append("")

    # 盈亏分位数
    lines.append("## 盈亏分位数")
    lines.append("")
    lines.append("| 信号名 | P10 | P25 | P50(中位数) | P75 | P90 |")
    lines.append("|---|---|---|---|---|---|")
    for s in signal_stats:
        if s.pnl_percentiles:
            p = s.pnl_percentiles
            lines.append(
                f"| {s.signal} | {p.get('p10', 0):.2f} | {p.get('p25', 0):.2f} | "
                f"{p.get('p50', 0):.2f} | {p.get('p75', 0):.2f} | {p.get('p90', 0):.2f} |"
            )
        else:
            lines.append(f"| {s.signal} | - | - | - | - | - |")
    lines.append("")

    # Factor Value Stats
    lines.append("## Factor Value Stats")
    lines.append("")
    lines.append("| 因子名 | 最小值 | 最大值 | 均值 | 标准差 | 25分位 | 中位数 | 75分位 |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for f in factor_stats:
        lines.append(
            f"| {f.factor} | {f.min:.4f} | {f.max:.4f} | {f.mean:.4f} | "
            f"{f.std:.4f} | {f.p25:.4f} | {f.p50:.4f} | {f.p75:.4f} |"
        )
    lines.append("")

    # monitor_meta
    if monitor_meta is not None:
        lines.append("## monitor_meta")
        lines.append("")
        for k, v in monitor_meta.items():
            lines.append(f"- **{k}**: {v}")
        lines.append("")

    # 调参依据
    lines.append("## 调参依据")
    lines.append("")
    lines.append("### 传统指标")
    lines.append("")
    lines.append("- 阈值在 p25 附近 → 偏严, 触发过少, 可考虑下调")
    lines.append("- 阈值远低于 p25 → 过松, 触发过多")
    lines.append("- p75 接近因子上限 → 触发集中在高值区, 阈值可能过严")
    lines.append("- `swallowed_count` 占比高 → 涨跌停日出场信号被吞多, 止损/止盈参数需调整")
    lines.append("- `skipped_count` 占比高 → A 股硬约束触发频繁, 相关过滤参数需调整")
    lines.append("")
    lines.append("### 效率与稳定性（平台无关）")
    lines.append("")
    lines.append("- 月胜率 < 40% → 策略过于依赖少数大盈单，稳定性差，考虑收紧入场条件")
    lines.append("- 最大连续亏损 > 8 → 极端情况下账户压力大，考虑加强止损参数")
    lines.append("- 亏损 3%~10% 占比 > 40% → 趋势反转信号可能延迟出场，考虑收紧 trailing_stop 或 time_stop")
    lines.append("- 盈利 >10% 占比 < 10% → 策略抓不住大行情，考虑放宽止盈或延长持仓")
    lines.append("- 平均亏损绝对值 > 平均盈利绝对值 → 盈亏比失衡，优先调整止损参数")
    lines.append("")

    if extra_notes:
        lines.append("## 附注")
        lines.append("")
        for n in extra_notes:
            lines.append(f"- {n}")
        lines.append("")

    return "\n".join(lines)
