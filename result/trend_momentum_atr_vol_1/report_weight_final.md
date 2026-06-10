# Weight Mode Report

**strategy**: trend_momentum_atr_vol_1
**test_name**: trend_momentum_atr_vol_1
**version**: v9
**date**: 2026-06-10 01:13:43

## 测试条件

| 中文名 | 英文名 | 值 |
|---|---|---|
| 测试集 | test_universe | spec.test_universe (300 只, 默认 HS300) |
| 实际测试股票数 | universe_size | 300 |
| 测试起始日期 | start_date | 2021-01-01 |
| 测试结束日期 | end_date | 2025-12-31 |
| 股票数限制 | limit | 不限 |
| weight_test | weight_test | trend_momentum_atr_vol_1 |

## Metrics

| 中文名 | 英文名 | 值 |
|---|---|---|
| 年化收益 | annual_return | 15.0134% |
| 年化收益率 | avg_annual_return_rate | 16.3631% |
| 年化收益额 | avg_annual_return_amount | 49,089.34 |
| 胜率 | win_rate | 49.2837% |
| 盈亏比 | profit_loss_ratio | 1.5054 |
| 夏普 | sharpe | 0.8549 |
| 最大回撤 | max_drawdown | -23.0815% |

## Weights Used

**Entry signals**:
- `ma_golden_cross`: 0.5
- `atr_expand`: 0.15
- `volume_confirm`: 0.35

**Exit signals**:
- `fixed_stop`: 0.02
- `trailing_stop`: 0.12
- `time_stop`: 0.06
- `ma_death_cross`: 0.8

## Signal Stats

| 信号名 | 触发次数 | 被吞次数 | 跳过次数 | 盈利次数 | 胜率 | 平均收益 | 中位持仓天数 |
|---|---|---|---|---|---|---|---|
| ma_golden_cross | 174799 | 0 | 0 | 154 | 50.66% | 984.49 | 18.0 |
| atr_expand | 11809 | 0 | 0 | 51 | 49.04% | 258.47 | 12.0 |
| volume_confirm | 9138 | 0 | 0 | 99 | 52.11% | 1405.19 | 22.0 |
| fixed_stop | 20 | 1 | 0 | 0 | 0.00% | -8642.19 | 9.0 |
| trailing_stop | 15 | 1 | 0 | 8 | 53.33% | 6658.37 | 35.0 |
| time_stop | 0 | 0 | 0 | 0 | 0.00% | 0.00 | 0.0 |
| ma_death_cross | 269 | 0 | 0 | 146 | 54.28% | 1383.84 | 18.0 |

## 持仓天数分布

| 信号名 | ≤5天 | ≤10天 | ≤15天 | ≤20天 | ≤25天 | ≤30天 | >30天 |
|---|---|---|---|---|---|---|---|
| ma_golden_cross | 33 | 51 | 46 | 51 | 39 | 41 | 43 |
| atr_expand | 15 | 30 | 19 | 14 | 11 | 4 | 11 |
| volume_confirm | 17 | 17 | 24 | 34 | 27 | 38 | 33 |
| fixed_stop | 3 | 8 | 4 | 3 | 1 | 1 | 0 |
| trailing_stop | 0 | 0 | 2 | 2 | 1 | 2 | 8 |
| time_stop | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| ma_death_cross | 30 | 43 | 40 | 46 | 37 | 38 | 35 |

## 盈亏分位数

| 信号名 | P10 | P25 | P50(中位数) | P75 | P90 |
|---|---|---|---|---|---|
| ma_golden_cross | -6410.11 | -3070.41 | 53.60 | 3378.01 | 8588.84 |
| atr_expand | -5864.02 | -2881.73 | -7.36 | 2490.52 | 6793.54 |
| volume_confirm | -6367.51 | -3037.97 | 182.49 | 3607.83 | 8958.20 |
| fixed_stop | -11978.36 | -9639.98 | -7915.14 | -6905.77 | -6309.42 |
| trailing_stop | -8676.27 | -5181.95 | 2015.99 | 19150.90 | 28178.55 |
| time_stop | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| ma_death_cross | -4788.37 | -2107.40 | 351.67 | 3397.26 | 7771.41 |

## Signal Attribution

| signal | return_share | win_share | loss_share | net_attribution |
|---|---|---|---|---|
| ma_golden_cross | 0.00% | 0.00% | 0.00% | 0.00% |
| atr_expand | 0.00% | 0.00% | 0.00% | 0.00% |
| volume_confirm | 0.00% | 0.00% | 0.00% | 0.00% |
| fixed_stop | -56.61% | 0.00% | 11.30% | -56.61% |
| trailing_stop | 32.71% | 4.65% | 3.95% | 32.71% |
| time_stop | 0.00% | 0.00% | 0.00% | 0.00% |
| ma_death_cross | 121.92% | 84.88% | 69.49% | 121.92% |

## Factor Value Stats

| 因子名 | 最小值 | 最大值 | 均值 | 标准差 | 25分位 | 中位数 | 75分位 |
|---|---|---|---|---|---|---|---|
| close | 1.1200 | 2279.8500 | 44.4911 | 106.7688 | 8.3800 | 19.4400 | 44.8100 |
| ma_10 | 0.2070 | 937.7180 | 18.7734 | 44.1321 | 2.0760 | 4.6610 | 12.8070 |
| ma_30 | 0.2190 | 799.2467 | 18.6409 | 43.6427 | 2.0773 | 4.6467 | 12.7477 |
| atr_14 | 0.0014 | 96.1671 | 0.8427 | 2.3554 | 0.0607 | 0.1507 | 0.4936 |
| volume_ratio_20 | 0.0031 | 17.4019 | 1.0322 | 0.6847 | 0.6299 | 0.8682 | 1.2206 |

## 调权依据

- 高 `win_rate` + 高 `avg_return` → 强势信号, 应增加权重
- 低 `win_rate` 或负 `avg_return` → 弱势信号, 应降低权重
- `return_share` 高 + `win_share` 高 → 强势信号, 应加权重
- `loss_share` 显著高于 `win_share` → 弱势信号, 应降权重
- `net_attribution` < 0 → 净拖累, 建议大幅降权或停用
