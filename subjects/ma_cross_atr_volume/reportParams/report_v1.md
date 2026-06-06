# Params Mode Report

**strategy**: ma_cross_atr_volume
**version**: v1
**date**: 2026-06-06 00:31:24

## 测试条件

| 中文名 | 英文名 | 值 |
|---|---|---|
| 测试集 | test_universe | spec.test_universe (300 只, 默认 hs300) |
| 实际测试股票数 | universe_size | 300 |
| 测试起始日期 | start_date | 2024-01-01 |
| 测试结束日期 | end_date | 2025-01-01 |
| 股票数限制 | limit | 不限 |

## Metrics

| 中文名 | 英文名 | 值 |
|---|---|---|
| 年化收益 | annual_return | 15.3333% |
| 年化收益率 | avg_annual_return_rate | 16.8774% |
| 年化收益额 | avg_annual_return_amount | 5,063,206.17 |
| 胜率 | win_rate | 39.8168% |
| 盈亏比 | profit_loss_ratio | 2.3025 |
| 夏普 | sharpe | 1.0401 |
| 最大回撤 | max_drawdown | -10.3983% |

## Signal Stats

| signal | triggered | swallowed | skipped | win_count | win_rate | avg_return | median_holding_days |
|---|---|---|---|---|---|---|---|
| ma_golden_cross | 0 | 0 | 0 | 0 | 0.00% | 0.00 | 0.0 |
| atr_expand | 0 | 0 | 0 | 0 | 0.00% | 0.00 | 0.0 |
| volume_confirm | 0 | 0 | 0 | 0 | 0.00% | 0.00 | 0.0 |
| ma_death_cross | 1873 | 0 | 0 | 473 | 25.25% | -1730.64 | 6.0 |
| trailing_stop | 1480 | 73 | 0 | 652 | 44.05% | 2240.66 | 12.0 |
| fixed_stop | 0 | 0 | 0 | 0 | 0.00% | 0.00 | 0.0 |
| time_stop | 359 | 0 | 0 | 353 | 98.33% | 12230.02 | 35.0 |

## Factor Value Stats

| factor | min | max | mean | std | p25 | p50 | p75 |
|---|---|---|---|---|---|---|---|
| close | 1.3800 | 1659.7400 | 39.7795 | 95.1687 | 8.5300 | 18.9600 | 40.1600 |
| ma_5 | 1.3840 | 1635.1980 | 39.7462 | 95.0810 | 8.5300 | 18.9420 | 40.1380 |
| atr_14 | 0.0214 | 87.2393 | 1.4554 | 2.9018 | 0.2529 | 0.6107 | 1.4714 |
| atr_14_prev | 0.0214 | 87.2393 | 1.4555 | 2.9026 | 0.2529 | 0.6107 | 1.4721 |
| ma_20 | 1.4075 | 1596.1815 | 39.6566 | 94.8457 | 8.5255 | 18.9970 | 39.9416 |
| volume_ratio_20 | 0.0873 | 12.1019 | 1.0298 | 0.5260 | 0.7119 | 0.9025 | 1.1842 |

## 调参依据

- 阈值在 p25 附近 → 偏严, 触发过少, 可考虑下调
- 阈值远低于 p25 → 过松, 触发过多
- p75 接近因子上限 → 触发集中在高值区, 阈值可能过严
- `swallowed_count` 占比高 → 涨跌停日出场信号被吞多, 止损/止盈参数需调整
- `skipped_count` 占比高 → A 股硬约束触发频繁, 相关过滤参数需调整
