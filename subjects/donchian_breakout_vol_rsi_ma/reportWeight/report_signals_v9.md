# Weight Mode Report

**strategy**: donchian_breakout_vol_rsi_ma
**test_name**: donchian_breakout_vol_rsi_ma
**version**: v9
**date**: 2026-06-09 10:58:32

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
| 年化收益 | annual_return | 11.7809% |
| 年化收益率 | avg_annual_return_rate | 13.0940% |
| 年化收益额 | avg_annual_return_amount | 39,282.14 |
| 胜率 | win_rate | 37.3757% |
| 盈亏比 | profit_loss_ratio | 2.0924 |
| 夏普 | sharpe | 0.7458 |
| 最大回撤 | max_drawdown | -26.2585% |

## Weights Used

**Entry signals**:
- `breakout_entry`: 0.5
- `trend_entry`: 0.3
- `rsi_entry`: 0.4

**Exit signals**:
- `fixed_stop_loss`: 0.0
- `trailing_stop`: 0.0
- `volatility_stop`: 0.0
- `trend_reversal_exit`: 0.0
- `overbought_reduce`: 0.9
- `time_stop`: 0.5

## Signal Stats

| 信号名 | 触发次数 | 被吞次数 | 跳过次数 | 盈利次数 | 胜率 | 平均收益 | 中位持仓天数 |
|---|---|---|---|---|---|---|---|
| breakout_entry | 24454 | 0 | 0 | 392 | 36.43% | 324.61 | 8.0 |
| trend_entry | 265460 | 0 | 0 | 655 | 37.62% | 323.13 | 7.0 |
| rsi_entry | 142115 | 0 | 0 | 497 | 38.11% | 345.59 | 7.0 |
| fixed_stop_loss | 25 | 3 | 0 | 0 | 0.00% | -6917.37 | 17.0 |
| trailing_stop | 9 | 2 | 0 | 1 | 11.11% | -4359.05 | 16.0 |
| volatility_stop | 1744 | 42 | 0 | 573 | 32.86% | -223.70 | 6.0 |
| trend_reversal_exit | 27 | 0 | 0 | 7 | 25.93% | -2050.89 | 31.0 |
| overbought_reduce | 90 | 1 | 0 | 90 | 100.00% | 11146.74 | 23.5 |
| time_stop | 117 | 0 | 0 | 81 | 69.23% | 2204.65 | 60.0 |

## 持仓天数分布

| 信号名 | ≤5天 | ≤10天 | ≤15天 | ≤20天 | ≤25天 | ≤30天 | >30天 |
|---|---|---|---|---|---|---|---|
| breakout_entry | 454 | 149 | 99 | 65 | 48 | 46 | 215 |
| trend_entry | 737 | 288 | 159 | 102 | 88 | 69 | 298 |
| rsi_entry | 567 | 220 | 127 | 77 | 59 | 44 | 210 |
| fixed_stop_loss | 3 | 2 | 6 | 5 | 1 | 3 | 5 |
| trailing_stop | 1 | 0 | 3 | 2 | 0 | 0 | 3 |
| volatility_stop | 849 | 298 | 174 | 105 | 81 | 61 | 176 |
| trend_reversal_exit | 0 | 1 | 0 | 2 | 6 | 4 | 14 |
| overbought_reduce | 8 | 18 | 10 | 4 | 6 | 10 | 34 |
| time_stop | 0 | 0 | 0 | 0 | 0 | 0 | 117 |

## 盈亏分位数

| 信号名 | P10 | P25 | P50(中位数) | P75 | P90 |
|---|---|---|---|---|---|
| breakout_entry | -3475.29 | -1619.64 | -524.38 | 1001.04 | 4925.92 |
| trend_entry | -3496.92 | -1830.62 | -555.41 | 1246.87 | 5449.47 |
| rsi_entry | -3465.36 | -1809.25 | -523.70 | 1175.55 | 5198.75 |
| fixed_stop_loss | -9617.34 | -8023.28 | -6871.04 | -4822.17 | -4641.39 |
| trailing_stop | -7369.43 | -6374.35 | -5957.41 | -4702.31 | -1199.60 |
| volatility_stop | -3271.49 | -1828.39 | -657.17 | 576.28 | 3143.43 |
| trend_reversal_exit | -5986.21 | -4435.75 | -1373.02 | -193.82 | 862.78 |
| overbought_reduce | 5226.65 | 6657.94 | 9790.95 | 12583.31 | 14800.47 |
| time_stop | -1739.58 | -341.65 | 1569.92 | 3853.11 | 6300.71 |

## Signal Attribution

| signal | return_share | win_share | loss_share | net_attribution |
|---|---|---|---|---|
| breakout_entry | 0.00% | 0.00% | 0.00% | 0.00% |
| trend_entry | 0.00% | 0.00% | 0.00% | 0.00% |
| rsi_entry | 0.00% | 0.00% | 0.00% | 0.00% |
| fixed_stop_loss | -28.66% | 0.00% | 1.98% | -28.66% |
| trailing_stop | -6.50% | 0.13% | 0.63% | -6.50% |
| volatility_stop | -64.65% | 76.20% | 92.94% | -64.65% |
| trend_reversal_exit | -9.18% | 0.93% | 1.59% | -9.18% |
| overbought_reduce | 166.24% | 11.97% | 0.00% | 166.24% |
| time_stop | 42.74% | 10.77% | 2.86% | 42.74% |

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
