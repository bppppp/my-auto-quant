# Weight Mode Report

**strategy**: donchian_breakout_vol_rsi_ma
**test_name**: donchian_breakout_vol_rsi_ma
**version**: v7
**date**: 2026-06-09 10:28:07

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
- `fixed_stop_loss`: 0.0
- `trailing_stop`: 0.0
- `volatility_stop`: 0.0
- `trend_reversal_exit`: 0.0
- `overbought_reduce`: 0.8
- `time_stop`: 0.4

## Signal Stats

| 信号名 | 触发次数 | 被吞次数 | 跳过次数 | 盈利次数 | 胜率 | 平均收益 | 中位持仓天数 |
|---|---|---|---|---|---|---|---|
| breakout_entry | 25793 | 0 | 0 | 669 | 38.38% | 381.02 | 7.0 |
| trend_entry | 264250 | 0 | 0 | 442 | 38.84% | 458.11 | 8.0 |
| rsi_entry | 140948 | 0 | 0 | 278 | 38.56% | 541.96 | 7.0 |
| fixed_stop_loss | 28 | 5 | 0 | 0 | 0.00% | -7693.58 | 13.5 |
| trailing_stop | 11 | 3 | 0 | 1 | 9.09% | -3856.53 | 16.0 |
| volatility_stop | 1821 | 46 | 0 | 630 | 34.60% | -95.49 | 6.0 |
| trend_reversal_exit | 20 | 0 | 0 | 7 | 35.00% | -1482.56 | 38.5 |
| overbought_reduce | 84 | 0 | 0 | 84 | 100.00% | 12592.05 | 27.5 |
| time_stop | 119 | 0 | 0 | 87 | 73.11% | 2397.40 | 60.0 |

## 持仓天数分布

| 信号名 | ≤5天 | ≤10天 | ≤15天 | ≤20天 | ≤25天 | ≤30天 | >30天 |
|---|---|---|---|---|---|---|---|
| breakout_entry | 778 | 240 | 166 | 114 | 79 | 67 | 299 |
| trend_entry | 472 | 181 | 106 | 67 | 58 | 39 | 215 |
| rsi_entry | 312 | 124 | 64 | 39 | 33 | 16 | 133 |
| fixed_stop_loss | 3 | 5 | 8 | 3 | 0 | 3 | 6 |
| trailing_stop | 1 | 0 | 4 | 1 | 1 | 1 | 3 |
| volatility_stop | 903 | 291 | 174 | 123 | 89 | 61 | 180 |
| trend_reversal_exit | 0 | 0 | 0 | 2 | 2 | 1 | 15 |
| overbought_reduce | 7 | 13 | 13 | 3 | 4 | 7 | 37 |
| time_stop | 0 | 0 | 0 | 0 | 0 | 0 | 119 |

## 盈亏分位数

| 信号名 | P10 | P25 | P50(中位数) | P75 | P90 |
|---|---|---|---|---|---|
| breakout_entry | -3247.33 | -1618.31 | -516.96 | 1066.06 | 4613.76 |
| trend_entry | -3445.94 | -1620.72 | -472.08 | 1329.78 | 5390.23 |
| rsi_entry | -3320.20 | -1512.25 | -458.05 | 1080.18 | 5133.36 |
| fixed_stop_loss | -10973.88 | -9198.14 | -7635.48 | -6347.42 | -4620.90 |
| trailing_stop | -7187.07 | -6547.62 | -4947.40 | -3586.03 | -1427.74 |
| volatility_stop | -3137.54 | -1634.42 | -594.98 | 645.17 | 2988.56 |
| trend_reversal_exit | -4605.80 | -3573.33 | -806.01 | 437.35 | 1462.56 |
| overbought_reduce | 5062.61 | 6641.03 | 10135.60 | 12947.08 | 16066.54 |
| time_stop | -2168.24 | -69.35 | 1808.30 | 4415.31 | 8521.44 |

## Signal Attribution

| signal | return_share | win_share | loss_share | net_attribution |
|---|---|---|---|---|
| breakout_entry | 0.00% | 0.00% | 0.00% | 0.00% |
| trend_entry | 0.00% | 0.00% | 0.00% | 0.00% |
| rsi_entry | 0.00% | 0.00% | 0.00% | 0.00% |
| fixed_stop_loss | -24.35% | 0.00% | 2.20% | -24.35% |
| trailing_stop | -4.80% | 0.12% | 0.78% | -4.80% |
| volatility_stop | -19.66% | 77.68% | 93.49% | -19.66% |
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
