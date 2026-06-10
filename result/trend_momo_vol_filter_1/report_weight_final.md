# Weight Mode Report

**strategy**: trend_momo_vol_filter_1
**test_name**: trend_momo_vol_filter_1
**version**: v11
**date**: 2026-06-10 07:23:09

## 测试条件

| 中文名 | 英文名 | 值 |
|---|---|---|
| 测试集 | test_universe | spec.test_universe (300 只, 默认 HS300) |
| 实际测试股票数 | universe_size | 300 |
| 测试起始日期 | start_date | 2021-01-01 |
| 测试结束日期 | end_date | 2025-12-31 |
| 股票数限制 | limit | 不限 |
| weight_test | weight_test | trend_momo_vol_filter_1 |

## Metrics

| 中文名 | 英文名 | 值 |
|---|---|---|
| 年化收益 | annual_return | 12.8414% |
| 年化收益率 | avg_annual_return_rate | 14.5790% |
| 年化收益额 | avg_annual_return_amount | 43,737.10 |
| 胜率 | win_rate | 44.5298% |
| 盈亏比 | profit_loss_ratio | 1.7170 |
| 夏普 | sharpe | 0.7214 |
| 最大回撤 | max_drawdown | -21.5233% |

## Weights Used

**Entry signals**:
- `ma_golden_cross`: 0.44
- `macd_positive`: 0.01
- `volume_surge`: 0.45
- `atr_normal_range`: 0.1

**Exit signals**:
- `fixed_stop_loss`: 0.02
- `trailing_stop`: 0.28
- `time_stop`: 0.7

## Signal Stats

| 信号名 | 触发次数 | 被吞次数 | 跳过次数 | 盈利次数 | 胜率 | 平均收益 | 中位持仓天数 |
|---|---|---|---|---|---|---|---|
| ma_golden_cross | 175194 | 0 | 0 | 232 | 44.53% | 391.01 | 35.0 |
| macd_positive | 172991 | 0 | 0 | 177 | 42.65% | 259.18 | 35.0 |
| volume_surge | 64076 | 0 | 0 | 232 | 44.53% | 391.01 | 35.0 |
| atr_normal_range | 161841 | 0 | 0 | 230 | 44.40% | 368.84 | 35.0 |
| fixed_stop_loss | 205 | 5 | 0 | 0 | 0.00% | -2163.26 | 12.0 |
| trailing_stop | 34 | 5 | 0 | 14 | 41.18% | 1080.98 | 21.0 |
| time_stop | 282 | 0 | 0 | 218 | 77.30% | 2164.65 | 35.0 |

## 持仓天数分布

| 信号名 | ≤5天 | ≤10天 | ≤15天 | ≤20天 | ≤25天 | ≤30天 | >30天 |
|---|---|---|---|---|---|---|---|
| ma_golden_cross | 44 | 43 | 46 | 39 | 34 | 16 | 299 |
| macd_positive | 36 | 37 | 33 | 30 | 30 | 14 | 235 |
| volume_surge | 44 | 43 | 46 | 39 | 34 | 16 | 299 |
| atr_normal_range | 44 | 43 | 46 | 39 | 34 | 16 | 296 |
| fixed_stop_loss | 44 | 41 | 41 | 30 | 23 | 14 | 12 |
| trailing_stop | 0 | 2 | 5 | 9 | 11 | 2 | 5 |
| time_stop | 0 | 0 | 0 | 0 | 0 | 0 | 282 |

## 盈亏分位数

| 信号名 | P10 | P25 | P50(中位数) | P75 | P90 |
|---|---|---|---|---|---|
| ma_golden_cross | -2548.79 | -1998.74 | -520.12 | 1623.97 | 4595.02 |
| macd_positive | -2634.18 | -2044.51 | -595.81 | 1481.74 | 4430.24 |
| volume_surge | -2548.79 | -1998.74 | -520.12 | 1623.97 | 4595.02 |
| atr_normal_range | -2559.05 | -2000.33 | -521.65 | 1613.15 | 4548.94 |
| fixed_stop_loss | -2990.30 | -2422.40 | -2071.43 | -1761.04 | -1498.19 |
| trailing_stop | -3159.64 | -2587.02 | -1175.08 | 3931.79 | 8056.73 |
| time_stop | -600.63 | 74.80 | 1211.47 | 3037.93 | 5821.49 |

## Signal Attribution

| signal | return_share | win_share | loss_share | net_attribution |
|---|---|---|---|---|
| ma_golden_cross | 0.00% | 0.00% | 0.00% | 0.00% |
| macd_positive | 0.00% | 0.00% | 0.00% | 0.00% |
| volume_surge | 0.00% | 0.00% | 0.00% | 0.00% |
| atr_normal_range | 0.00% | 0.00% | 0.00% | 0.00% |
| fixed_stop_loss | -217.69% | 0.00% | 70.93% | -217.69% |
| trailing_stop | 18.04% | 6.03% | 6.92% | 18.04% |
| time_stop | 299.65% | 93.97% | 22.15% | 299.65% |

## Factor Value Stats

| 因子名 | 最小值 | 最大值 | 均值 | 标准差 | 25分位 | 中位数 | 75分位 |
|---|---|---|---|---|---|---|---|
| close | 1.1200 | 2279.8500 | 44.4911 | 106.7688 | 8.3800 | 19.4400 | 44.8100 |
| ma_10 | 0.2070 | 937.7180 | 18.7734 | 44.1321 | 2.0760 | 4.6610 | 12.8070 |
| ma_30 | 0.2190 | 799.2467 | 18.6409 | 43.6427 | 2.0773 | 4.6467 | 12.7477 |
| macd_diff | -108.6229 | 143.2492 | 0.0796 | 2.9765 | -0.2728 | -0.0059 | 0.2388 |
| volume_ratio_20 | 0.0031 | 17.4019 | 1.0322 | 0.6847 | 0.6299 | 0.8682 | 1.2206 |
| atr_14 | 0.0014 | 96.1671 | 0.8427 | 2.3554 | 0.0607 | 0.1507 | 0.4936 |

## 调权依据

- 高 `win_rate` + 高 `avg_return` → 强势信号, 应增加权重
- 低 `win_rate` 或负 `avg_return` → 弱势信号, 应降低权重
- `return_share` 高 + `win_share` 高 → 强势信号, 应加权重
- `loss_share` 显著高于 `win_share` → 弱势信号, 应降权重
- `net_attribution` < 0 → 净拖累, 建议大幅降权或停用
