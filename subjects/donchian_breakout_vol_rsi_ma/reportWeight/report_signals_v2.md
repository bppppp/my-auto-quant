# Weight Mode Report

**strategy**: donchian_breakout_vol_rsi_ma
**test_name**: donchian_breakout_vol_rsi_ma
**version**: v2
**date**: 2026-06-09 09:20:50

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
| 年化收益 | annual_return | 13.9074% |
| 年化收益率 | avg_annual_return_rate | 15.3469% |
| 年化收益额 | avg_annual_return_amount | 46,040.60 |
| 胜率 | win_rate | 38.6783% |
| 盈亏比 | profit_loss_ratio | 2.1194 |
| 夏普 | sharpe | 0.8700 |
| 最大回撤 | max_drawdown | -23.9138% |

## Weights Used

**Entry signals**:
- `breakout_entry`: 0.6
- `trend_entry`: 0.2
- `rsi_entry`: 0.2

**Exit signals**:
- `fixed_stop_loss`: 0.1
- `trailing_stop`: 0.2
- `volatility_stop`: 0.2
- `trend_reversal_exit`: 0.15
- `overbought_reduce`: 0.3
- `time_stop`: 0.25

## Signal Stats

| 信号名 | 触发次数 | 被吞次数 | 跳过次数 | 盈利次数 | 胜率 | 平均收益 | 中位持仓天数 |
|---|---|---|---|---|---|---|---|
| breakout_entry | 25214 | 0 | 0 | 659 | 38.31% | 355.33 | 7.0 |
| trend_entry | 260192 | 0 | 0 | 422 | 37.95% | 396.65 | 8.0 |
| rsi_entry | 138619 | 0 | 0 | 273 | 38.78% | 523.92 | 7.0 |
| fixed_stop_loss | 11 | 1 | 0 | 0 | 0.00% | -7164.75 | 19.0 |
| trailing_stop | 19 | 7 | 0 | 1 | 5.26% | -6056.23 | 14.0 |
| volatility_stop | 1811 | 49 | 0 | 622 | 34.35% | -148.82 | 6.0 |
| trend_reversal_exit | 20 | 0 | 0 | 7 | 35.00% | -1729.61 | 36.5 |
| overbought_reduce | 80 | 0 | 0 | 80 | 100.00% | 12271.20 | 23.5 |
| time_stop | 115 | 0 | 0 | 84 | 73.04% | 2580.88 | 60.0 |

## 持仓天数分布

| 信号名 | ≤5天 | ≤10天 | ≤15天 | ≤20天 | ≤25天 | ≤30天 | >30天 |
|---|---|---|---|---|---|---|---|
| breakout_entry | 771 | 236 | 162 | 112 | 79 | 61 | 299 |
| trend_entry | 452 | 180 | 108 | 66 | 58 | 34 | 214 |
| rsi_entry | 303 | 120 | 64 | 35 | 36 | 15 | 131 |
| fixed_stop_loss | 0 | 0 | 4 | 2 | 0 | 0 | 5 |
| trailing_stop | 2 | 4 | 5 | 2 | 0 | 2 | 4 |
| volatility_stop | 895 | 287 | 173 | 118 | 92 | 58 | 188 |
| trend_reversal_exit | 0 | 0 | 1 | 2 | 2 | 1 | 14 |
| overbought_reduce | 7 | 15 | 13 | 3 | 3 | 5 | 34 |
| time_stop | 0 | 0 | 0 | 0 | 0 | 0 | 115 |

## 盈亏分位数

| 信号名 | P10 | P25 | P50(中位数) | P75 | P90 |
|---|---|---|---|---|---|
| breakout_entry | -3225.23 | -1594.93 | -495.05 | 1082.83 | 4524.22 |
| trend_entry | -3389.08 | -1636.32 | -502.96 | 1218.05 | 5234.73 |
| rsi_entry | -3272.73 | -1518.06 | -429.86 | 1065.61 | 5119.13 |
| fixed_stop_loss | -10159.98 | -8230.49 | -7826.02 | -5292.27 | -4283.54 |
| trailing_stop | -10434.21 | -8548.68 | -6533.14 | -4765.71 | -3026.40 |
| volatility_stop | -3110.21 | -1660.88 | -590.14 | 651.72 | 2971.35 |
| trend_reversal_exit | -4931.87 | -3952.14 | -974.15 | 437.35 | 1451.45 |
| overbought_reduce | 4906.85 | 6379.64 | 9569.10 | 12146.66 | 15481.88 |
| time_stop | -1704.25 | -98.79 | 1984.40 | 4692.35 | 8123.60 |

## Signal Attribution

| signal | return_share | win_share | loss_share | net_attribution |
|---|---|---|---|---|
| breakout_entry | 0.00% | 0.00% | 0.00% | 0.00% |
| trend_entry | 0.00% | 0.00% | 0.00% | 0.00% |
| rsi_entry | 0.00% | 0.00% | 0.00% | 0.00% |
| fixed_stop_loss | -10.06% | 0.00% | 0.87% | -10.06% |
| trailing_stop | -14.69% | 0.13% | 1.43% | -14.69% |
| volatility_stop | -34.40% | 78.14% | 94.22% | -34.40% |
| trend_reversal_exit | -4.42% | 0.88% | 1.03% | -4.42% |
| overbought_reduce | 125.32% | 10.05% | 0.00% | 125.32% |
| time_stop | 37.89% | 10.55% | 2.46% | 37.89% |

## Factor Value Stats

| 因子名 | 最小值 | 最大值 | 均值 | 标准差 | 25分位 | 中位数 | 75分位 |
|---|---|---|---|---|---|---|---|
| donchian_high_20 | 0.2300 | 1070.2000 | 19.9691 | 44.0946 | 2.8600 | 6.1600 | 15.8900 |
| donchian_low_20 | 0.2000 | 860.6300 | 16.1642 | 35.1409 | 2.3800 | 5.1300 | 13.1300 |
| ma_20 | 0.2135 | 940.0665 | 17.9341 | 39.2032 | 2.6070 | 5.6180 | 14.4082 |
| atr_14 | 0.0014 | 96.1671 | 0.7886 | 2.0685 | 0.0800 | 0.2014 | 0.5807 |
| volume_ratio_20 | 0.0022 | 17.4019 | 1.0303 | 0.6401 | 0.6488 | 0.8800 | 1.2189 |
| rsi_14 | 0.0000 | 100.0000 | 50.4210 | 17.0337 | 37.9747 | 50.4464 | 62.7907 |
| close | 1.0400 | 2279.8500 | 34.3052 | 89.1935 | 6.7900 | 14.6800 | 32.2000 |
| ma_60 | 0.2317 | 913.9413 | 17.6726 | 38.3814 | 2.5943 | 5.5718 | 14.2309 |

## 调权依据

- 高 `win_rate` + 高 `avg_return` → 强势信号, 应增加权重
- 低 `win_rate` 或负 `avg_return` → 弱势信号, 应降低权重
- `return_share` 高 + `win_share` 高 → 强势信号, 应加权重
- `loss_share` 显著高于 `win_share` → 弱势信号, 应降权重
- `net_attribution` < 0 → 净拖累, 建议大幅降权或停用
