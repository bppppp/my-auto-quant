"""weight 模式报告 (MD 格式, 含 signal_attribution). 见 subject.md §6.2 / subject_structure.md §7.2."""
from __future__ import annotations

from datetime import datetime
from typing import Iterable

from ..metrics import Metrics
from ..stats import SignalStats, FactorValueStats


def render_weight_report(
    strategy: str,
    test_name: str,
    version: str,
    weights: dict,
    metrics: Metrics,
    signal_stats: Iterable[SignalStats],
    factor_stats: Iterable[FactorValueStats],
    signal_attribution: Iterable[dict] | None = None,
    monitor_meta: dict | None = None,
    test_conditions: dict | None = None,
) -> str:
    """渲染 weight 模式报告.

    Args:
        strategy: 策略名.
        test_name: weight test 名 (= strategy_name, 详见 subject_structure.md §4.12).
        version: 版本号, 如 ``"v1"``.
        weights: 实际使用的 weight, 形如 ``{"entry": {...}, "exit": {...}}``.
        metrics: 7 项指标.
        signal_stats: 信号统计.
        factor_stats: 因子值统计.
        signal_attribution: 每信号 return_share / win_share / loss_share / net_attribution.
        monitor_meta: 仅 monitor 调用时传入.
        test_conditions: 测试条件 dict (来自 BacktestRunner._build_test_conditions),
            含 test_universe / universe_size / start_date / end_date / limit / weight_test.

    Returns:
        Markdown 报告字符串.
    """
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines: list[str] = []
    lines.append(f"# Weight Mode Report")
    lines.append("")
    lines.append(f"**strategy**: {strategy}")
    lines.append(f"**test_name**: {test_name}")
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
        lines.append(f"| weight_test | weight_test | {test_conditions.get('weight_test', '')} |")
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

    # Weights Used
    lines.append("## Weights Used")
    lines.append("")
    if "entry" in weights:
        lines.append("**Entry signals**:")
        for k, v in weights["entry"].items():
            lines.append(f"- `{k}`: {v}")
        lines.append("")
    if "exit" in weights:
        lines.append("**Exit signals**:")
        for k, v in weights["exit"].items():
            lines.append(f"- `{k}`: {v}")
        lines.append("")

    # Signal Stats
    lines.append("## Signal Stats")
    lines.append("")
    lines.append("| 信号名 | 触发次数 | 被吞次数 | 跳过次数 | 盈利次数 | 胜率 | 平均收益 | 中位持仓天数 |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for s in signal_stats:
        lines.append(
            f"| {s.signal} | {s.triggered} | {s.swallowed} | {s.skipped} | "
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

    # Signal Attribution
    if signal_attribution is not None:
        lines.append("## Signal Attribution")
        lines.append("")
        lines.append("| signal | return_share | win_share | loss_share | net_attribution |")
        lines.append("|---|---|---|---|---|")
        for a in signal_attribution:
            lines.append(
                f"| {a['signal']} | {a.get('return_share', 0):.2%} | "
                f"{a.get('win_share', 0):.2%} | {a.get('loss_share', 0):.2%} | "
                f"{a.get('net_attribution', 0):.2%} |"
            )
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

    # 调权依据
    lines.append("## 调权依据")
    lines.append("")
    lines.append("- 高 `win_rate` + 高 `avg_return` → 强势信号, 应增加权重")
    lines.append("- 低 `win_rate` 或负 `avg_return` → 弱势信号, 应降低权重")
    lines.append("- `return_share` 高 + `win_share` 高 → 强势信号, 应加权重")
    lines.append("- `loss_share` 显著高于 `win_share` → 弱势信号, 应降权重")
    lines.append("- `net_attribution` < 0 → 净拖累, 建议大幅降权或停用")
    lines.append("")

    return "\n".join(lines)
