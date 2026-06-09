# Weight Mode Report

**strategy**: donchian_breakout_vol_rsi_ma
**test_name**: donchian_breakout_vol_rsi_ma
**version**: v1
**date**: 2026-06-09 08:56:51

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
| 年化收益 | annual_return | 6.7388% |
| 年化收益率 | avg_annual_return_rate | 8.2877% |
| 年化收益额 | avg_annual_return_amount | 24,863.06 |
| 胜率 | win_rate | 37.1281% |
| 盈亏比 | profit_loss_ratio | 1.9957 |
| 夏普 | sharpe | 0.4762 |
| 最大回撤 | max_drawdown | -32.3585% |

## Weights Used

**Entry signals**:
- `breakout_entry`: 0.5
- `trend_entry`: 0.3
- `rsi_entry`: 0.2

**Exit signals**:
- `fixed_stop_loss`: 0.3
- `trailing_stop`: 0.2
- `volatility_stop`: 0.2
- `trend_reversal_exit`: 0.15
- `overbought_reduce`: 0.1
- `time_stop`: 0.05

## Signal Stats

| 信号名 | 触发次数 | 被吞次数 | 跳过次数 | 盈利次数 | 胜率 | 平均收益 | 中位持仓天数 |
|---|---|---|---|---|---|---|---|
| breakout_entry | 19260 | 0 | 0 | 399 | 37.86% | 147.73 | 7.0 |
| trend_entry | 224076 | 0 | 0 | 516 | 37.10% | 88.64 | 7.0 |
| rsi_entry | 118150 | 0 | 0 | 348 | 35.84% | 115.17 | 6.0 |
| fixed_stop_loss | 29 | 6 | 0 | 0 | 0.00% | -3906.08 | 13.0 |
| trailing_stop | 12 | 2 | 0 | 1 | 8.33% | -953.05 | 25.5 |
| volatility_stop | 1532 | 35 | 0 | 523 | 34.14% | -76.44 | 5.0 |
| trend_reversal_exit | 18 | 1 | 0 | 2 | 11.11% | -1233.33 | 29.0 |
| overbought_reduce | 67 | 0 | 0 | 67 | 100.00% | 5654.54 | 21.0 |
| time_stop | 89 | 0 | 0 | 56 | 62.92% | 974.53 | 60.0 |

## 持仓天数分布

| 信号名 | ≤5天 | ≤10天 | ≤15天 | ≤20天 | ≤25天 | ≤30天 | >30天 |
|---|---|---|---|---|---|---|---|
| breakout_entry | 475 | 154 | 103 | 76 | 47 | 32 | 167 |
| trend_entry | 618 | 221 | 120 | 91 | 63 | 57 | 221 |
| rsi_entry | 450 | 171 | 84 | 55 | 43 | 43 | 125 |
| fixed_stop_loss | 3 | 9 | 6 | 2 | 1 | 5 | 3 |
| trailing_stop | 0 | 1 | 2 | 1 | 2 | 1 | 5 |
| volatility_stop | 781 | 265 | 136 | 103 | 63 | 49 | 135 |
| trend_reversal_exit | 0 | 1 | 1 | 1 | 4 | 3 | 8 |
| overbought_reduce | 5 | 10 | 11 | 6 | 5 | 6 | 24 |
| time_stop | 0 | 0 | 0 | 0 | 0 | 0 | 89 |

## 盈亏分位数

| 信号名 | P10 | P25 | P50(中位数) | P75 | P90 |
|---|---|---|---|---|---|
| breakout_entry | -1798.83 | -908.71 | -307.09 | 650.63 | 2401.95 |
| trend_entry | -1861.73 | -1013.26 | -377.95 | 650.57 | 2585.53 |
| rsi_entry | -1865.68 | -989.89 | -356.21 | 628.84 | 2467.47 |
| fixed_stop_loss | -4965.36 | -4466.81 | -3798.72 | -3125.03 | -2698.57 |
| trailing_stop | -2583.41 | -2241.79 | -1951.27 | -1296.31 | -597.12 |
| volatility_stop | -1732.57 | -948.95 | -375.99 | 410.31 | 1592.38 |
| trend_reversal_exit | -2633.26 | -1858.02 | -1376.56 | -797.58 | 3.94 |
| overbought_reduce | 3192.00 | 3773.93 | 4667.98 | 5518.92 | 7897.83 |
| time_stop | -1508.68 | -554.13 | 848.65 | 2292.90 | 3513.34 |

## Signal Attribution

| signal | return_share | win_share | loss_share | net_attribution |
|---|---|---|---|---|
| breakout_entry | 0.00% | 0.00% | 0.00% | 0.00% |
| trend_entry | 0.00% | 0.00% | 0.00% | 0.00% |
| rsi_entry | 0.00% | 0.00% | 0.00% | 0.00% |
| fixed_stop_loss | -56.20% | 0.00% | 2.64% | -56.20% |
| trailing_stop | -5.67% | 0.15% | 1.00% | -5.67% |
| volatility_stop | -58.10% | 80.59% | 91.81% | -58.10% |
| trend_reversal_exit | -11.01% | 0.31% | 1.46% | -11.01% |
| overbought_reduce | 187.97% | 10.32% | 0.00% | 187.97% |
| time_stop | 43.03% | 8.63% | 3.00% | 43.03% |

## Factor Value Stats

| 因子名 | 最小值 | 最大值 | 均值 | 标准差 | 25分位 | 中位数 | 75分位 |
|---|---|---|---|---|---|---|---|
| donchian_high_20 | 0.2300 | 1070.2000 | 22.3953 | 47.2628 | 3.2100 | 7.0200 | 18.3300 |
| donchian_low_20 | 0.2000 | 860.6300 | 18.1263 | 37.6596 | 2.6600 | 5.8300 | 15.0000 |
| ma_20 | 0.2135 | 940.0665 | 20.1095 | 42.0154 | 2.9320 | 6.3990 | 16.5520 |
| ma_60 | 0.2317 | 913.9413 | 19.7233 | 41.0288 | 2.9012 | 6.3152 | 16.1308 |
| atr_14 | 0.0021 | 96.1671 | 0.8860 | 2.2216 | 0.0893 | 0.2314 | 0.6829 |
| volume_ratio_20 | 0.0022 | 17.2317 | 1.0315 | 0.6222 | 0.6582 | 0.8862 | 1.2193 |
| rsi_14 | 0.0000 | 100.0000 | 50.6039 | 17.0502 | 38.1220 | 50.7353 | 63.0435 |
| close | 1.0400 | 2279.8500 | 37.8424 | 95.6978 | 7.2100 | 16.1900 | 36.7775 |

## 调权依据

- 高 `win_rate` + 高 `avg_return` → 强势信号, 应增加权重
- 低 `win_rate` 或负 `avg_return` → 弱势信号, 应降低权重
- `return_share` 高 + `win_share` 高 → 强势信号, 应加权重
- `loss_share` 显著高于 `win_share` → 弱势信号, 应降权重
- `net_attribution` < 0 → 净拖累, 建议大幅降权或停用
