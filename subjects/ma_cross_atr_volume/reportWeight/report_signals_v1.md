# Weight Mode Report

**strategy**: ma_cross_atr_volume
**test_name**: ma_cross_atr_volume
**version**: v1
**date**: 2026-06-07 23:20:36

## 测试条件

| 中文名 | 英文名 | 值 |
|---|---|---|
| 测试集 | test_universe | spec.test_universe (10 只, 默认 HS300) |
| 实际测试股票数 | universe_size | 10 |
| 测试起始日期 | start_date | 2024-01-01 |
| 测试结束日期 | end_date | 2025-01-01 |
| 股票数限制 | limit | 10 |
| weight_test | weight_test | ma_cross_atr_volume |

## Weights Used

**Entry signals**:
- `ma_golden_cross`: 0.5
- `atr_expand`: 0.25
- `volume_confirm`: 0.25

**Exit signals**:
- `ma_death_cross`: 0.3
- `trailing_stop`: 0.3
- `fixed_stop`: 0.2
- `time_stop`: 0.2

## Metrics

| 中文名 | 英文名 | 值 |
|---|---|---|
| 年化收益 | annual_return | 15.8471% |
| 年化收益率 | avg_annual_return_rate | 17.5032% |
| 年化收益额 | avg_annual_return_amount | 52,509.53 |
| 胜率 | win_rate | 42.2222% |
| 盈亏比 | profit_loss_ratio | 2.2410 |
| 夏普 | sharpe | 0.8424 |
| 最大回撤 | max_drawdown | -11.7581% |

## Signal Stats

| 信号名 | 触发次数 | 被吞次数 | 跳过次数 | 盈利次数 | 胜率 | 平均收益 | 中位持仓天数 |
|---|---|---|---|---|---|---|---|
| ma_golden_cross | 809 | 0 | 0 | 18 | 40.91% | 907.82 | 11.0 |
| atr_expand | 691 | 0 | 0 | 17 | 45.95% | 1414.24 | 13.0 |
| volume_confirm | 487 | 0 | 0 | 12 | 44.44% | 1118.67 | 11.0 |
| ma_death_cross | 43 | 0 | 0 | 17 | 39.53% | 813.44 | 11.0 |
| trailing_stop | 1 | 0 | 0 | 1 | 100.00% | 4966.27 | 19.0 |
| fixed_stop | 0 | 0 | 0 | 0 | 0.00% | 0.00 | 0.0 |
| time_stop | 0 | 0 | 0 | 0 | 0.00% | 0.00 | 0.0 |

## Signal Attribution

| signal | return_share | win_share | loss_share | net_attribution |
|---|---|---|---|---|
| ma_golden_cross | 0.00% | 0.00% | 0.00% | 0.00% |
| atr_expand | 0.00% | 0.00% | 0.00% | 0.00% |
| volume_confirm | 0.00% | 0.00% | 0.00% | 0.00% |
| ma_death_cross | 86.32% | 89.47% | 100.00% | 86.32% |
| trailing_stop | 12.26% | 5.26% | 0.00% | 12.26% |
| fixed_stop | 0.00% | 0.00% | 0.00% | 0.00% |
| time_stop | 0.00% | 0.00% | 0.00% | 0.00% |

## Factor Value Stats

| factor | min | max | mean | std | p25 | p50 | p75 |
|---|---|---|---|---|---|---|---|
| ma_5 | 3.6360 | 73.8020 | 17.0308 | 16.8910 | 6.5885 | 9.4440 | 23.9430 |
| ma_20 | 3.7490 | 71.6060 | 16.8984 | 16.6653 | 6.6110 | 9.4585 | 23.9603 |
| atr_14 | 0.0607 | 3.7129 | 0.5137 | 0.5311 | 0.1677 | 0.2789 | 0.6787 |
| volume_ratio_20 | 0.2548 | 5.4182 | 1.0424 | 0.5195 | 0.7287 | 0.9200 | 1.2097 |
| close | 3.5700 | 76.0200 | 17.0668 | 16.9547 | 6.5775 | 9.4500 | 23.9600 |
| atr_14_prev | 0.0607 | 3.7129 | 0.5128 | 0.5299 | 0.1671 | 0.2782 | 0.6787 |

## 调权依据

- 高 `win_rate` + 高 `avg_return` → 强势信号, 应增加权重
- 低 `win_rate` 或负 `avg_return` → 弱势信号, 应降低权重
- `return_share` 高 + `win_share` 高 → 强势信号, 应加权重
- `loss_share` 显著高于 `win_share` → 弱势信号, 应降权重
- `net_attribution` < 0 → 净拖累, 建议大幅降权或停用
