# Weight Mode Report

**strategy**: donchian_breakout_vol_rsi_ma
**test_name**: donchian_breakout_vol_rsi_ma
**version**: v8
**date**: 2026-06-09 10:43:10

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
| 年化收益 | annual_return | 14.9775% |
| 年化收益率 | avg_annual_return_rate | 15.9997% |
| 年化收益额 | avg_annual_return_amount | 47,999.13 |
| 胜率 | win_rate | 39.2344% |
| 盈亏比 | profit_loss_ratio | 2.1262 |
| 夏普 | sharpe | 0.9167 |
| 最大回撤 | max_drawdown | -23.3088% |

## Weights Used

**Entry signals**:
- `breakout_entry`: 0.6
- `trend_entry`: 0.2
- `rsi_entry`: 0.3

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
| breakout_entry | 25799 | 0 | 0 | 676 | 38.72% | 382.43 | 7.0 |
| trend_entry | 264244 | 0 | 0 | 444 | 39.12% | 459.25 | 8.0 |
| rsi_entry | 140944 | 0 | 0 | 284 | 39.50% | 544.79 | 7.0 |
| fixed_stop_loss | 29 | 5 | 0 | 0 | 0.00% | -7738.73 | 14.0 |
| trailing_stop | 11 | 3 | 0 | 1 | 9.09% | -3776.84 | 16.0 |
| volatility_stop | 1827 | 47 | 0 | 640 | 35.03% | -85.11 | 6.0 |
| trend_reversal_exit | 20 | 0 | 0 | 7 | 35.00% | -1454.82 | 38.5 |
| overbought_reduce | 83 | 0 | 0 | 83 | 100.00% | 12625.84 | 27.0 |
| time_stop | 118 | 0 | 0 | 87 | 73.73% | 2452.37 | 60.0 |

## 持仓天数分布

| 信号名 | ≤5天 | ≤10天 | ≤15天 | ≤20天 | ≤25天 | ≤30天 | >30天 |
|---|---|---|---|---|---|---|---|
| breakout_entry | 776 | 245 | 170 | 113 | 77 | 66 | 299 |
| trend_entry | 468 | 184 | 105 | 67 | 57 | 39 | 215 |
| rsi_entry | 310 | 124 | 64 | 38 | 34 | 16 | 133 |
| fixed_stop_loss | 3 | 5 | 8 | 3 | 0 | 3 | 7 |
| trailing_stop | 1 | 0 | 4 | 1 | 1 | 1 | 3 |
| volatility_stop | 904 | 297 | 176 | 121 | 87 | 61 | 181 |
| trend_reversal_exit | 0 | 0 | 0 | 2 | 2 | 1 | 15 |
| overbought_reduce | 7 | 14 | 13 | 3 | 4 | 6 | 36 |
| time_stop | 0 | 0 | 0 | 0 | 0 | 0 | 118 |

## 盈亏分位数

| 信号名 | P10 | P25 | P50(中位数) | P75 | P90 |
|---|---|---|---|---|---|
| breakout_entry | -3274.32 | -1594.81 | -494.90 | 1033.01 | 4668.54 |
| trend_entry | -3481.59 | -1616.72 | -463.14 | 1288.52 | 5538.27 |
| rsi_entry | -3321.69 | -1454.73 | -424.75 | 1086.69 | 5200.93 |
| fixed_stop_loss | -10959.77 | -9116.64 | -7800.41 | -6360.88 | -4658.65 |
| trailing_stop | -7187.07 | -6290.72 | -4964.50 | -3593.71 | -1447.57 |
| volatility_stop | -3151.39 | -1608.82 | -577.75 | 657.29 | 3059.27 |
| trend_reversal_exit | -4478.64 | -3469.35 | -806.01 | 424.49 | 1440.33 |
| overbought_reduce | 5136.25 | 6649.11 | 9666.30 | 12819.87 | 16206.33 |
| time_stop | -2161.48 | -46.03 | 1710.60 | 4332.67 | 8845.58 |

## Signal Attribution

| signal | return_share | win_share | loss_share | net_attribution |
|---|---|---|---|---|
| breakout_entry | 0.00% | 0.00% | 0.00% | 0.00% |
| trend_entry | 0.00% | 0.00% | 0.00% | 0.00% |
| rsi_entry | 0.00% | 0.00% | 0.00% | 0.00% |
| fixed_stop_loss | -25.22% | 0.00% | 2.28% | -25.22% |
| trailing_stop | -4.67% | 0.12% | 0.79% | -4.67% |
| volatility_stop | -17.48% | 78.05% | 93.46% | -17.48% |
| trend_reversal_exit | -3.27% | 0.85% | 1.02% | -3.27% |
| overbought_reduce | 117.78% | 10.12% | 0.00% | 117.78% |
| time_stop | 32.52% | 10.61% | 2.44% | 32.52% |

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
