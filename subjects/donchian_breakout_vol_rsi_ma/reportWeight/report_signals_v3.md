# Weight Mode Report

**strategy**: donchian_breakout_vol_rsi_ma
**test_name**: donchian_breakout_vol_rsi_ma
**version**: v3
**date**: 2026-06-09 09:33:53

## 测试条件

| 中文名 | 英文名 | 值 |
|---|---|---|
| 测试集 | test_universe | spec.test_universe (300 只, 默认 HS300) |
| 实际测试股票数 | universe_size | 300 |
| 测试起始日期 | start_date | 2016-01-01 |
| 测试结束日期 | end_date | 2026-01-01 |
| 股票数限制 | limit | 不限 |
| weight_test | weight_test | donchian_breakout_vol_rsi_ma |

## Metrics

| 中文名 | 英文名 | 值 |
|---|---|---|
| 年化收益 | annual_return | 14.9281% |
| 年化收益率 | avg_annual_return_rate | 15.9501% |
| 年化收益额 | avg_annual_return_amount | 47,850.28 |
| 胜率 | win_rate | 38.8969% |
| 盈亏比 | profit_loss_ratio | 2.1513 |
| 夏普 | sharpe | 0.9154 |
| 最大回撤 | max_drawdown | -24.2282% |

## Weights Used

**Entry signals**:
- `breakout_entry`: 0.6
- `trend_entry`: 0.2
- `rsi_entry`: 0.2

**Exit signals**:
- `fixed_stop_loss`: 0.05
- `trailing_stop`: 0.05
- `volatility_stop`: 0.1
- `trend_reversal_exit`: 0.05
- `overbought_reduce`: 0.45
- `time_stop`: 0.3

## Signal Stats

| 信号名 | 触发次数 | 被吞次数 | 跳过次数 | 盈利次数 | 胜率 | 平均收益 | 中位持仓天数 |
|---|---|---|---|---|---|---|---|
| breakout_entry | 25793 | 0 | 0 | 669 | 38.38% | 381.02 | 7.0 |
| trend_entry | 264250 | 0 | 0 | 442 | 38.84% | 458.11 | 8.0 |
| rsi_entry | 140948 | 0 | 0 | 278 | 38.56% | 541.96 | 7.0 |
| fixed_stop_loss | 15 | 2 | 0 | 0 | 0.00% | -8218.89 | 19.0 |
| trailing_stop | 5 | 0 | 0 | 0 | 0.00% | -6208.19 | 16.0 |
| volatility_stop | 1840 | 52 | 0 | 631 | 34.29% | -150.77 | 6.0 |
| trend_reversal_exit | 20 | 0 | 0 | 7 | 35.00% | -1482.56 | 38.5 |
| overbought_reduce | 84 | 0 | 0 | 84 | 100.00% | 12592.05 | 27.5 |
| time_stop | 119 | 0 | 0 | 87 | 73.11% | 2397.40 | 60.0 |

## 持仓天数分布

| 信号名 | ≤5天 | ≤10天 | ≤15天 | ≤20天 | ≤25天 | ≤30天 | >30天 |
|---|---|---|---|---|---|---|---|
| breakout_entry | 778 | 240 | 166 | 114 | 79 | 67 | 299 |
| trend_entry | 472 | 181 | 106 | 67 | 58 | 39 | 215 |
| rsi_entry | 312 | 124 | 64 | 39 | 33 | 16 | 133 |
| fixed_stop_loss | 0 | 2 | 4 | 3 | 0 | 0 | 6 |
| trailing_stop | 1 | 0 | 1 | 1 | 1 | 0 | 1 |
| volatility_stop | 906 | 294 | 181 | 123 | 89 | 65 | 182 |
| trend_reversal_exit | 0 | 0 | 0 | 2 | 2 | 1 | 15 |
| overbought_reduce | 7 | 13 | 13 | 3 | 4 | 7 | 37 |
| time_stop | 0 | 0 | 0 | 0 | 0 | 0 | 119 |

## 盈亏分位数

| 信号名 | P10 | P25 | P50(中位数) | P75 | P90 |
|---|---|---|---|---|---|
| breakout_entry | -3247.33 | -1618.31 | -516.96 | 1066.06 | 4613.76 |
| trend_entry | -3445.94 | -1620.72 | -472.08 | 1329.78 | 5390.23 |
| rsi_entry | -3320.20 | -1512.25 | -458.05 | 1080.18 | 5133.36 |
| fixed_stop_loss | -11081.78 | -10110.93 | -8183.18 | -6674.36 | -5007.95 |
| trailing_stop | -8123.03 | -6936.30 | -6158.93 | -5295.47 | -4359.83 |
| volatility_stop | -3232.90 | -1674.18 | -609.57 | 606.23 | 2958.26 |
| trend_reversal_exit | -4605.80 | -3573.33 | -806.01 | 437.35 | 1462.56 |
| overbought_reduce | 5062.61 | 6641.03 | 10135.60 | 12947.08 | 16066.54 |
| time_stop | -2168.24 | -69.35 | 1808.30 | 4415.31 | 8521.44 |

## Signal Attribution

| signal | return_share | win_share | loss_share | net_attribution |
|---|---|---|---|---|
| breakout_entry | 0.00% | 0.00% | 0.00% | 0.00% |
| trend_entry | 0.00% | 0.00% | 0.00% | 0.00% |
| rsi_entry | 0.00% | 0.00% | 0.00% | 0.00% |
| fixed_stop_loss | -13.94% | 0.00% | 1.18% | -13.94% |
| trailing_stop | -3.51% | 0.00% | 0.39% | -3.51% |
| volatility_stop | -31.36% | 77.81% | 94.90% | -31.36% |
| trend_reversal_exit | -3.35% | 0.86% | 1.02% | -3.35% |
| overbought_reduce | 119.57% | 10.36% | 0.00% | 119.57% |
| time_stop | 32.25% | 10.73% | 2.51% | 32.25% |

## Factor Value Stats

| 因子名 | 最小值 | 最大值 | 均值 | 标准差 | 25分位 | 中位数 | 75分位 |
|---|---|---|---|---|---|---|---|
| donchian_high_20 | 0.2300 | 1070.2000 | 19.7371 | 43.7726 | 2.8300 | 6.0900 | 15.6700 |
| donchian_low_20 | 0.2000 | 860.6300 | 15.9758 | 34.8848 | 2.3500 | 5.0700 | 12.9600 |
| ma_20 | 0.2135 | 940.0665 | 17.7256 | 38.9173 | 2.5795 | 5.5570 | 14.2185 |
| atr_14 | 0.0014 | 96.1671 | 0.7793 | 2.0529 | 0.0793 | 0.1986 | 0.5729 |
| volume_ratio_20 | 0.0022 | 17.4019 | 1.0305 | 0.6416 | 0.6479 | 0.8797 | 1.2194 |
| rsi_14 | 0.0000 | 100.0000 | 50.3995 | 17.0404 | 37.9310 | 50.4065 | 62.7907 |
| close | 1.0400 | 2279.8500 | 33.9539 | 88.5225 | 6.7500 | 14.5300 | 31.7600 |
| ma_60 | 0.2317 | 913.9413 | 17.4687 | 38.1004 | 2.5700 | 5.5120 | 14.0471 |

## 调权依据

- 高 `win_rate` + 高 `avg_return` → 强势信号, 应增加权重
- 低 `win_rate` 或负 `avg_return` → 弱势信号, 应降低权重
- `return_share` 高 + `win_share` 高 → 强势信号, 应加权重
- `loss_share` 显著高于 `win_share` → 弱势信号, 应降权重
- `net_attribution` < 0 → 净拖累, 建议大幅降权或停用
