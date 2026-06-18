"""
本地 weight 回测 (与 QMT 完全对齐), 并对比 QMT 结果.
对齐条件:
- 测试集: 296 只 HS300 (与 QMT 脚本完全一致)
- 时间范围: 2023-01-01 ~ 2026-05-01
- 初始资金: 1,000,000
- 策略: trend_momentum_strategy_1_final.md 的 params + weights
"""
from __future__ import annotations

import csv
import json
import os
import sys
from pathlib import Path

# 确保 subject 模块可导入
_PROJ = Path(__file__).resolve().parents[2]
_SUBJECTS = _PROJ / "subjects"
if str(_SUBJECTS) not in sys.path:
    sys.path.insert(0, str(_SUBJECTS))

import pandas as pd
from subject.backtest.runner import BacktestRunner

# ============ 对齐 QMT 的测试集 ============
# 与 QMT/scripts/trend_momentum_strategy_1.py 中 HS300 列表完全一致
HS300 = [
    "000001.SZ","000002.SZ","000063.SZ","000100.SZ","000157.SZ","000166.SZ","000301.SZ","000333.SZ",
    "000338.SZ","000408.SZ","000425.SZ","000538.SZ","000568.SZ","000596.SZ","000617.SZ","000625.SZ",
    "000630.SZ","000651.SZ","000708.SZ","000725.SZ","000768.SZ","000776.SZ","000786.SZ","000807.SZ",
    "000858.SZ","000876.SZ","000895.SZ","000938.SZ","000963.SZ","000975.SZ","000977.SZ","000983.SZ",
    "000999.SZ","001391.SZ","001965.SZ","001979.SZ","002001.SZ","002027.SZ","002028.SZ","002049.SZ",
    "002050.SZ","002074.SZ","002142.SZ","002179.SZ","002230.SZ","002236.SZ","002241.SZ","002252.SZ",
    "002304.SZ","002311.SZ","002352.SZ","002371.SZ","002384.SZ","002415.SZ","002422.SZ","002459.SZ",
    "002460.SZ","002463.SZ","002466.SZ","002475.SZ","002493.SZ","002600.SZ","002601.SZ","002625.SZ",
    "002648.SZ","002709.SZ","002714.SZ","002736.SZ","002916.SZ","002920.SZ","002938.SZ","003816.SZ",
    "300014.SZ","300015.SZ","300033.SZ","300059.SZ","300122.SZ","300124.SZ","300251.SZ","300274.SZ",
    "300308.SZ","300316.SZ","300347.SZ","300394.SZ","300408.SZ","300413.SZ","300418.SZ","300433.SZ",
    "300442.SZ","300476.SZ","300498.SZ","300502.SZ","300661.SZ","300750.SZ","300759.SZ","300760.SZ",
    "300782.SZ","300803.SZ","300832.SZ","300866.SZ","300896.SZ","300979.SZ","300999.SZ","301236.SZ",
    "301269.SZ","302132.SZ",
    "600000.SH","600009.SH","600010.SH","600011.SH","600015.SH","600016.SH","600018.SH","600019.SH",
    "600023.SH","600025.SH","600026.SH","600027.SH","600028.SH","600029.SH","600030.SH","600031.SH",
    "600036.SH","600039.SH","600048.SH","600050.SH","600061.SH","600066.SH","600085.SH","600089.SH",
    "600104.SH","600111.SH","600115.SH","600150.SH","600160.SH","600161.SH","600176.SH","600183.SH",
    "600188.SH","600196.SH","600219.SH","600233.SH","600276.SH","600309.SH","600346.SH","600362.SH",
    "600372.SH","600377.SH","600406.SH","600415.SH","600426.SH","600436.SH","600438.SH","600460.SH",
    "600482.SH","600489.SH","600515.SH","600519.SH","600522.SH","600547.SH","600570.SH","600584.SH",
    "600585.SH","600588.SH","600600.SH","600660.SH","600674.SH","600690.SH","600741.SH","600760.SH",
    "600795.SH","600803.SH","600809.SH","600845.SH","600875.SH","600886.SH","600887.SH","600893.SH",
    "600900.SH","600905.SH","600918.SH","600919.SH","600926.SH","600930.SH","600938.SH","600941.SH",
    "600958.SH","600989.SH","600999.SH","601006.SH","601009.SH","601012.SH","601018.SH","601021.SH",
    "601058.SH","601059.SH","601066.SH","601077.SH","601088.SH","601100.SH","601111.SH","601117.SH",
    "601127.SH","601136.SH","601138.SH","601166.SH","601169.SH","601186.SH","601211.SH","601225.SH",
    "601229.SH","601236.SH","601238.SH","601288.SH","601298.SH","601318.SH","601319.SH","601328.SH",
    "601336.SH","601360.SH","601377.SH","601390.SH","601398.SH","601456.SH","601600.SH","601601.SH",
    "601607.SH","601618.SH","601628.SH","601633.SH","601658.SH","601668.SH","601669.SH","601688.SH",
    "601689.SH","601698.SH","601728.SH","601766.SH","601788.SH","601800.SH","601808.SH","601816.SH",
    "601818.SH","601825.SH","601838.SH","601857.SH","601868.SH","601872.SH","601877.SH","601878.SH",
    "601881.SH","601888.SH","601898.SH","601899.SH","601901.SH","601916.SH","601919.SH","601939.SH",
    "601985.SH","601988.SH","601995.SH","601998.SH","603019.SH","603195.SH","603259.SH","603260.SH",
    "603288.SH","603296.SH","603369.SH","603392.SH","603501.SH","603799.SH","603893.SH","603986.SH",
    "603993.SH","605117.SH","605499.SH","688008.SH","688009.SH","688012.SH","688036.SH","688041.SH",
    "688047.SH","688082.SH","688111.SH","688126.SH","688169.SH","688187.SH","688223.SH","688256.SH",
    "688271.SH","688303.SH","688396.SH","688472.SH","688506.SH","688981.SH",
]

OUT_DIR = Path(__file__).resolve().parent


def run_local_weight():
    """运行本地 weight 模式回测, 与 QMT 完全对齐"""
    print("=" * 60)
    print("本地 Weight 模式回测 (对齐 QMT)")
    print("=" * 60)
    print("测试集: %s 只 HS300" % len(HS300))
    print("时间: 2023-01-01 ~ 2026-05-01")
    print("初始资金: 1,000,000")
    print("策略: trend_momentum_strategy_1")

    runner = BacktestRunner(
        strategy_name="trend_momentum_strategy_1",
        mode="weight",
        weight_test="trend_momentum_strategy_1",
        test_universe_override=HS300,
        start_date="2023-01-01",
        end_date="2026-05-01",
        max_stocks=None,
        initial_capital=1_000_000,
        subjects_dir=str(_SUBJECTS),
    )
    results = runner.run()

    # 保存 metrics
    m = results.metrics
    summary = {
        "annual_return": getattr(m, 'annual_return', None),
        "total_return": getattr(m, 'total_return', None),
        "win_rate": getattr(m, 'win_rate', None),
        "max_drawdown": getattr(m, 'max_drawdown', None),
        "sharpe": getattr(m, 'sharpe', None),
        "num_trades": getattr(m, 'num_trades', None),
        "total_pnl": getattr(m, 'total_pnl', None),
    }
    summary_path = OUT_DIR / "compare_local_summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, default=str)
    print("\n[SAVED] %s" % summary_path)
    print("本地 Metrics: %s" % json.dumps(summary, indent=2, default=str))

    # 导出交易记录
    if not results.trades.empty:
        trades_path = OUT_DIR / "compare_local_trades.csv"
        results.trades.to_csv(trades_path, index=False, encoding="utf-8-sig")
        print("[SAVED] %s (%s trades)" % (trades_path, len(results.trades)))

    # 导出每日净值
    if not results.daily_values.empty:
        dv_path = OUT_DIR / "compare_local_nav.csv"
        results.daily_values.to_csv(dv_path, index=True, encoding="utf-8-sig")
        print("[SAVED] %s" % dv_path)

    return results


def compare_with_qmt():
    """对比本地和 QMT 结果"""
    print("\n" + "=" * 60)
    print("对比分析")
    print("=" * 60)

    # 读取 QMT CSV
    qmt_paths = [
        "C:/Users/10915/Desktop/沪深300_NEWNEWNEW1.csv",
        "C:/Users/10915/Desktop/沪深300_NEWNEWNEW2023.csv",
        "C:/Users/10915/Desktop/沪深300_NEWNEWNEW.csv",
    ]
    qmt_csv = None
    for p in qmt_paths:
        if os.path.exists(p):
            qmt_csv = p
            print("QMT 数据: %s" % p)
            break

    if qmt_csv is None:
        print("[WARN] 未找到 QMT CSV 文件, 跳过对比")
        return

    # 读取 QMT 每日净值 (编码可能是 gbk)
    try:
        qmt = pd.read_csv(qmt_csv, encoding="gbk")
    except Exception:
        qmt = pd.read_csv(qmt_csv, encoding="utf-8")

    # 列名修复
    cols = list(qmt.columns)
    print("QMT columns: %s" % cols)

    # 第1列=时间, 第2列=单位净值(策略), 第3列=基准净值
    date_col = cols[0]
    nav_col = cols[1]
    bench_col = cols[2]

    qmt[date_col] = pd.to_datetime(qmt[date_col])
    qmt = qmt.sort_values(date_col)

    # 截取 2023-01-01 ~ 2026-05-01
    qmt_period = qmt[(qmt[date_col] >= "2023-01-01") & (qmt[date_col] <= "2026-05-01")]

    if len(qmt_period) < 10:
        print("[WARN] QMT 数据中 2023-2026 期间不足 10 条, 可能是数据范围不同")
        print("QMT 最早日期: %s" % qmt[date_col].min())
        print("QMT 最晚日期: %s" % qmt[date_col].max())
        return

    qmt_nav_start = float(qmt_period[nav_col].iloc[0])
    qmt_nav_end = float(qmt_period[nav_col].iloc[-1])
    qmt_bench_start = float(qmt_period[bench_col].iloc[0])
    qmt_bench_end = float(qmt_period[bench_col].iloc[-1])

    qmt_return = (qmt_nav_end / qmt_nav_start - 1) * 100
    qmt_bench_return = (qmt_bench_end / qmt_bench_start - 1) * 100

    # 计算最大回撤
    qmt_nav_series = qmt_period[nav_col].astype(float)
    qmt_peak = qmt_nav_series.cummax()
    qmt_dd = ((qmt_nav_series - qmt_peak) / qmt_peak).min() * 100

    print("\n--- QMT 回测结果 (2023-01-01 ~ 2026-05-01) ---")
    print("起始日期: %s" % qmt_period[date_col].iloc[0].strftime("%Y-%m-%d"))
    print("结束日期: %s" % qmt_period[date_col].iloc[-1].strftime("%Y-%m-%d"))
    print("策略总收益: %.2f%%" % qmt_return)
    print("基准总收益: %.2f%%" % qmt_bench_return)
    print("最大回撤: %.2f%%" % qmt_dd)

    # 读取本地 metrics
    summary_path = OUT_DIR / "compare_local_summary.json"
    if summary_path.exists():
        with open(summary_path, "r", encoding="utf-8") as f:
            local = json.load(f)
        print("\n--- 本地回测 Metrics ---")
        print(json.dumps(local, indent=2, default=str))

        # 对比
        print("\n--- 对比 ---")
        if local.get("total_return"):
            lr = local["total_return"] * 100
            print("本地总收益: %.2f%%" % lr)
            print("QMT 总收益: %.2f%%" % qmt_return)
            print("差异: %.2f%%" % (qmt_return - lr))
        if local.get("max_drawdown"):
            print("本地最大回撤: %.2f%%" % (local["max_drawdown"] * 100))
            print("QMT 最大回撤: %.2f%%" % qmt_dd)
        if local.get("win_rate"):
            print("本地胜率: %.2f%%" % (local["win_rate"] * 100))
        if local.get("num_trades"):
            print("本地交易笔数: %s" % local["num_trades"])


if __name__ == "__main__":
    os.chdir(_SUBJECTS)
    run_local_weight()
    compare_with_qmt()
