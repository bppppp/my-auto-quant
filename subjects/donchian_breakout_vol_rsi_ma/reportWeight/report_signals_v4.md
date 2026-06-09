# Weight Mode Report

**strategy**: donchian_breakout_vol_rsi_ma
**test_name**: donchian_breakout_vol_rsi_ma
**version**: v4
**date**: 2026-06-09 09:48:07

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
| 年化收益 | annual_return | 10.7496% |
| 年化收益率 | avg_annual_return_rate | 12.1351% |
| 年化收益额 | avg_annual_return_amount | 36,405.23 |
| 胜率 | win_rate | 37.2371% |
| 盈亏比 | profit_loss_ratio | 2.0807 |
| 夏普 | sharpe | 0.6912 |
| 最大回撤 | max_drawdown | -24.8360% |

## Weights Used

**Entry signals**:
- `breakout_entry`: 0.5
- `trend_entry`: 0.2
- `rsi_entry`: 0.3

**Exit signals**:
- `fixed_stop_loss`: 0.02
- `trailing_stop`: 0.02
- `volatility_stop`: 0.03
- `trend_reversal_exit`: 0.03
- `overbought_reduce`: 0.5
- `time_stop`: 0.4

## Signal Stats

| 信号名 | 触发次数 | 被吞次数 | 跳过次数 | 盈利次数 | 胜率 | 平均收益 | 中位持仓天数 |
|---|---|---|---|---|---|---|---|
| breakout_entry | 24917 | 0 | 0 | 480 | 36.73% | 243.68 | 7.0 |
| trend_entry | 265178 | 0 | 0 | 592 | 37.00% | 237.90 | 7.0 |
| rsi_entry | 141860 | 0 | 0 | 453 | 38.49% | 360.40 | 7.0 |
| fixed_stop_loss | 13 | 0 | 0 | 0 | 0.00% | -6420.91 | 14.0 |
| trailing_stop | 4 | 0 | 0 | 0 | 0.00% | -5670.92 | 15.0 |
| volatility_stop | 1850 | 54 | 0 | 606 | 32.76% | -205.83 | 5.0 |
| trend_reversal_exit | 26 | 1 | 0 | 6 | 23.08% | -2408.60 | 30.0 |
| overbought_reduce | 85 | 1 | 0 | 85 | 100.00% | 9941.64 | 22.0 |
| time_stop | 114 | 0 | 0 | 82 | 71.93% | 1896.79 | 60.0 |

## 持仓天数分布

| 信号名 | ≤5天 | ≤10天 | ≤15天 | ≤20天 | ≤25天 | ≤30天 | >30天 |
|---|---|---|---|---|---|---|---|
| breakout_entry | 575 | 188 | 117 | 77 | 58 | 54 | 238 |
| trend_entry | 696 | 262 | 151 | 88 | 71 | 59 | 273 |
| rsi_entry | 530 | 193 | 115 | 62 | 50 | 37 | 190 |
| fixed_stop_loss | 0 | 4 | 3 | 2 | 0 | 0 | 4 |
| trailing_stop | 1 | 0 | 2 | 1 | 0 | 0 | 0 |
| volatility_stop | 928 | 305 | 179 | 105 | 80 | 68 | 185 |
| trend_reversal_exit | 1 | 1 | 1 | 3 | 4 | 3 | 13 |
| overbought_reduce | 8 | 17 | 12 | 5 | 5 | 6 | 32 |
| time_stop | 0 | 0 | 0 | 0 | 0 | 0 | 114 |

## 盈亏分位数

| 信号名 | P10 | P25 | P50(中位数) | P75 | P90 |
|---|---|---|---|---|---|
| breakout_entry | -2903.24 | -1468.62 | -494.95 | 913.23 | 4335.81 |
| trend_entry | -3064.06 | -1601.97 | -515.55 | 997.04 | 4762.86 |
| rsi_entry | -2918.37 | -1495.29 | -442.40 | 992.13 | 4543.42 |
| fixed_stop_loss | -8806.07 | -8435.92 | -6240.33 | -5080.09 | -4537.09 |
| trailing_stop | -7110.42 | -6494.05 | -5595.37 | -4772.24 | -4291.86 |
| volatility_stop | -2905.55 | -1600.56 | -600.40 | 497.38 | 2863.74 |
| trend_reversal_exit | -5950.04 | -3722.95 | -2448.99 | -475.49 | 770.24 |
| overbought_reduce | 4865.16 | 6033.10 | 8389.47 | 10674.61 | 13687.38 |
| time_stop | -1680.56 | -240.42 | 1681.45 | 3284.45 | 5791.70 |

## Signal Attribution

| signal | return_share | win_share | loss_share | net_attribution |
|---|---|---|---|---|
| breakout_entry | 0.00% | 0.00% | 0.00% | 0.00% |
| trend_entry | 0.00% | 0.00% | 0.00% | 0.00% |
| rsi_entry | 0.00% | 0.00% | 0.00% | 0.00% |
| fixed_stop_loss | -16.31% | 0.00% | 0.99% | -16.31% |
| trailing_stop | -4.43% | 0.00% | 0.30% | -4.43% |
| volatility_stop | -74.41% | 77.79% | 94.74% | -74.41% |
| trend_reversal_exit | -12.24% | 0.77% | 1.52% | -12.24% |
| overbought_reduce | 165.14% | 10.91% | 0.00% | 165.14% |
| time_stop | 42.26% | 10.53% | 2.44% | 42.26% |

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
