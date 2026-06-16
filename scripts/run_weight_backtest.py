"""Weight 模式回测 - 使用 trend_momentum_strategy_1_final.md 参数

Usage: python scripts/run_weight_backtest.py
"""
from __future__ import annotations

import sys, os
from pathlib import Path

_PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT / "subjects"))
sys.path.insert(0, str(_PROJECT))

os.environ["DATA_SOURCE"] = "bs"

from subject.backtest.runner import BacktestRunner
from subject.backtest.data_loader import DATA_SOURCE
import yaml

# 1. 读 final spec
final_path = _PROJECT / "result/trend_momentum_strategy_1/trend_momentum_strategy_1_final.md"
with open(final_path, encoding="utf-8") as f:
    content = f.read()

# 解析 frontmatter
parts = content.split("---", 2)
fm_text = parts[1]
spec = yaml.safe_load(fm_text)

print(f"Strategy: {spec['name']}")
print(f"Universe from spec: {spec.get('test_universe', 'N/A')}")
print(f"Params: {list(spec.get('params', []))[0]['name'] if spec.get('params') else 'N/A'}")

# 2. 构建 params dict from final spec
params = {p["name"]: p["default"] for p in spec["params"]}
print(f"\nParams ({len(params)}):")
for k, v in params.items():
    print(f"  {k}: {v}")

# 3. 构建 universe: HS300 + CYB_STAR_50
from data.config import HS300, CYB_STAR_50
universe_codes = sorted(set(HS300 + CYB_STAR_50))
# 转换 6位代码 → 带交易所后缀
def add_suffix(code):
    if code.startswith(("60", "68")): return f"{code}.SH"
    if code.startswith(("00", "30", "20")): return f"{code}.SZ"
    if code.startswith(("92", "83")): return f"{code}.BJ"
    return f"{code}.SZ"
universe = [add_suffix(c) for c in universe_codes]
print(f"\nUniverse: HS300({len(HS300)}) + CYB_STAR_50({len(CYB_STAR_50)}) = {len(universe)} stocks (before dedup)")

# 4. 创建 Runner
runner = BacktestRunner(
    strategy_name="trend_momentum_strategy_1",
    mode="weight",
    weight_test="trend_momentum_strategy_1",
    start_date="2023-01-01",
    end_date="2026-05-31",
    initial_capital=300_000.0,
    subjects_dir=str(_PROJECT / "subjects"),
    test_universe_override=universe,
)
runner.params = params  # override with final params
runner.spec = spec      # override spec

print(f"\n=== Backtest Config ===")
print(f"DATA_SOURCE: {DATA_SOURCE}")
print(f"Date: {runner.start_date} ~ {runner.end_date}")
print(f"Universe: {len(runner.universe)} stocks")
print(f"Params: {runner.params}")

# 5. 运行
print(f"\n=== Running weight backtest ===")
results = runner._run_weight(version="final")

# 6. 生成报告
out_dir = _PROJECT / "result/trend_momentum_strategy_1/LocalData"
out_dir.mkdir(parents=True, exist_ok=True)
out_path = out_dir / "new-20260616_report.md"

metrics = results.metrics
report = f"""# Weight Backtest Report — trend_momentum_strategy_1 (baostock data)

**Generated**: 2026-06-16
**Data source**: baostock (data-by-stock-bs)
**Period**: 2023-01-01 ~ 2026-05-31
**Universe**: HS300 + CYB_STAR_50 ({len(runner.universe)} stocks)
**Initial capital**: 300,000 CNY

## Performance Metrics

| Metric | Value |
|---|---|
| Annual Return | {getattr(metrics, 'annual_return', getattr(metrics, 'cagr', 'N/A'))} |
| Total Return | {getattr(metrics, 'total_return', 'N/A')} |
| Sharpe Ratio | {getattr(metrics, 'sharpe_ratio', 'N/A')} |
| Max Drawdown | {getattr(metrics, 'max_drawdown', 'N/A')} |
| Win Rate | {getattr(metrics, 'win_rate', 'N/A')} |
| Profit/Loss Ratio | {getattr(metrics, 'profit_loss_ratio', 'N/A')} |
| Total Trades | {getattr(metrics, 'total_trades', 'N/A')} |

## Strategy Parameters

"""
for k, v in params.items():
    report += f"- **{k}**: {v}\n"

report += f"""
## Daily Values (first/last)
- First day: {results.daily_values.index[0] if len(results.daily_values) > 0 else 'N/A'}
- Last day: {results.daily_values.index[-1] if len(results.daily_values) > 0 else 'N/A'}
- Starting value: {results.daily_values.iloc[0] if len(results.daily_values) > 0 else 'N/A':,.2f}
- Final value: {results.daily_values.iloc[-1] if len(results.daily_values) > 0 else 'N/A':,.2f}
"""

out_path.write_text(report, encoding="utf-8")
print(f"\n=== Report saved: {out_path} ===")
print("Done!")
