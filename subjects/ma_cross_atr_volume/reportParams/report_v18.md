# Params Mode Report

**strategy**: ma_cross_atr_volume
**version**: v18
**date**: 2026-06-06 20:55:36

## 测试条件

| 中文名 | 英文名 | 值 |
|---|---|---|
| 测试集 | test_universe | spec.test_universe (5 只, 默认 HS300) |
| 实际测试股票数 | universe_size | 5 |
| 测试起始日期 | start_date | 2024-06-01 |
| 测试结束日期 | end_date | 2024-06-30 |
| 股票数限制 | limit | 5 |

## Metrics

| 中文名 | 英文名 | 值 |
|---|---|---|
| 年化收益 | annual_return | 0.0000% |
| 年化收益率 | avg_annual_return_rate | 0.0000% |
| 年化收益额 | avg_annual_return_amount | 0.00 |
| 胜率 | win_rate | 0.0000% |
| 盈亏比 | profit_loss_ratio | 0.0000 |
| 夏普 | sharpe | 0.0000 |
| 最大回撤 | max_drawdown | 0.0000% |

## Signal Stats

| signal | triggered | swallowed | skipped | win_count | win_rate | avg_return | median_holding_days |
|---|---|---|---|---|---|---|---|
| ma_golden_cross | 0 | 0 | 0 | 0 | 0.00% | 0.00 | 0.0 |
| atr_expand | 0 | 0 | 0 | 0 | 0.00% | 0.00 | 0.0 |
| volume_confirm | 0 | 0 | 0 | 0 | 0.00% | 0.00 | 0.0 |
| ma_death_cross | 0 | 0 | 0 | 0 | 0.00% | 0.00 | 0.0 |
| trailing_stop | 0 | 0 | 0 | 0 | 0.00% | 0.00 | 0.0 |
| fixed_stop | 0 | 0 | 0 | 0 | 0.00% | 0.00 | 0.0 |
| time_stop | 0 | 0 | 0 | 0 | 0.00% | 0.00 | 0.0 |

## Factor Value Stats

| factor | min | max | mean | std | p25 | p50 | p75 |
|---|---|---|---|---|---|---|---|

## 调参依据

- 阈值在 p25 附近 → 偏严, 触发过少, 可考虑下调
- 阈值远低于 p25 → 过松, 触发过多
- p75 接近因子上限 → 触发集中在高值区, 阈值可能过严
- `swallowed_count` 占比高 → 涨跌停日出场信号被吞多, 止损/止盈参数需调整
- `skipped_count` 占比高 → A 股硬约束触发频繁, 相关过滤参数需调整
