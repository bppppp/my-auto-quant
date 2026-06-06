# Weight Mode Report

**strategy**: ma_cross_atr_volume
**test_name**: ma_cross_atr_volume
**version**: v1
**date**: 2026-06-06 17:45:08

## 测试条件

| 中文名 | 英文名 | 值 |
|---|---|---|
| 测试集 | test_universe | spec.test_universe (5 只, 默认 hs300) |
| 实际测试股票数 | universe_size | 5 |
| 测试起始日期 | start_date | 2024-09-01 |
| 测试结束日期 | end_date | 2024-12-31 |
| 股票数限制 | limit | 5 |
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
| 年化收益 | annual_return | 29.5196% |
| 年化收益率 | avg_annual_return_rate | 31.7588% |
| 年化收益额 | avg_annual_return_amount | 95,276.33 |
| 胜率 | win_rate | 28.5714% |
| 盈亏比 | profit_loss_ratio | 3.7987 |
| 夏普 | sharpe | 1.0410 |
| 最大回撤 | max_drawdown | -18.0397% |

## Signal Stats

| signal | triggered | swallowed | skipped | win_count | win_rate | avg_return | median_holding_days |
|---|---|---|---|---|---|---|---|
| ma_golden_cross | 0 | 0 | 0 | 0 | 0.00% | 0.00 | 0.0 |
| atr_expand | 0 | 0 | 0 | 0 | 0.00% | 0.00 | 0.0 |
| volume_confirm | 0 | 0 | 0 | 0 | 0.00% | 0.00 | 0.0 |
| ma_death_cross | 7 | 0 | 0 | 2 | 28.57% | 2467.74 | 11.0 |
| trailing_stop | 0 | 0 | 0 | 0 | 0.00% | 0.00 | 0.0 |
| fixed_stop | 0 | 0 | 0 | 0 | 0.00% | 0.00 | 0.0 |
| time_stop | 0 | 0 | 0 | 0 | 0.00% | 0.00 | 0.0 |

## Signal Attribution

| signal | return_share | win_share | loss_share | net_attribution |
|---|---|---|---|---|
| ma_golden_cross | 0.00% | 0.00% | 0.00% | 0.00% |
| atr_expand | 0.00% | 0.00% | 0.00% | 0.00% |
| volume_confirm | 0.00% | 0.00% | 0.00% | 0.00% |
| ma_death_cross | 100.00% | 100.00% | 100.00% | 100.00% |
| trailing_stop | 0.00% | 0.00% | 0.00% | 0.00% |
| fixed_stop | 0.00% | 0.00% | 0.00% | 0.00% |
| time_stop | 0.00% | 0.00% | 0.00% | 0.00% |

## Factor Value Stats

| factor | min | max | mean | std | p25 | p50 | p75 |
|---|---|---|---|---|---|---|---|
| ma_5 | 3.6360 | 39.3000 | 11.9315 | 9.3379 | 6.3505 | 8.5860 | 11.1145 |
| ma_20 | 3.7565 | 34.1100 | 11.6402 | 8.9338 | 6.0284 | 8.5363 | 11.0239 |
| atr_14 | 0.0814 | 2.0914 | 0.4289 | 0.4312 | 0.1629 | 0.2332 | 0.5113 |
| volume_ratio_20 | 0.2548 | 4.9277 | 1.1395 | 0.7691 | 0.6578 | 0.9007 | 1.2957 |
| close | 3.5700 | 40.2000 | 12.0340 | 9.5060 | 6.3200 | 8.6250 | 11.1600 |
| atr_14_prev | 0.0814 | 1.9729 | 0.4250 | 0.4232 | 0.1629 | 0.2332 | 0.5113 |

## 调权依据

- 高 `win_rate` + 高 `avg_return` → 强势信号, 应增加权重
- 低 `win_rate` 或负 `avg_return` → 弱势信号, 应降低权重
- `return_share` 高 + `win_share` 高 → 强势信号, 应加权重
- `loss_share` 显著高于 `win_share` → 弱势信号, 应降权重
- `net_attribution` < 0 → 净拖累, 建议大幅降权或停用
