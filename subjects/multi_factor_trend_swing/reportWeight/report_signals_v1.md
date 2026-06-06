# Weight Mode Report

**strategy**: multi_factor_trend_swing
**test_name**: multi_factor_trend_swing
**version**: v1
**date**: 2026-06-06 07:58:58

## 测试条件

| 中文名 | 英文名 | 值 |
|---|---|---|
| 测试集 | test_universe | spec.test_universe (5 只, 默认 hs300) |
| 实际测试股票数 | universe_size | 5 |
| 测试起始日期 | start_date | 2024-01-01 |
| 测试结束日期 | end_date | 2024-02-29 |
| 股票数限制 | limit | 5 |
| weight_test | weight_test | multi_factor_trend_swing |

## Weights Used

**Entry signals**:
- `trend_strength`: 0.35
- `atr_filter`: 0.2
- `volume_confirm`: 0.15
- `momentum_filter`: 0.15
- `rsi_filter`: 0.15

**Exit signals**:
- `fixed_stop`: 0.3
- `trailing_stop`: 0.3
- `trend_reversal`: 0.2
- `time_stop`: 0.1
- `rsi_overbought`: 0.1

## Metrics

| 中文名 | 英文名 | 值 |
|---|---|---|
| 年化收益 | annual_return | 58.3570% |
| 年化收益率 | avg_annual_return_rate | 52.4169% |
| 年化收益额 | avg_annual_return_amount | 157,250.73 |
| 胜率 | win_rate | 72.0000% |
| 盈亏比 | profit_loss_ratio | 1.3385 |
| 夏普 | sharpe | 3.3167 |
| 最大回撤 | max_drawdown | -3.2707% |

## Signal Stats

| signal | triggered | swallowed | skipped | win_count | win_rate | avg_return | median_holding_days |
|---|---|---|---|---|---|---|---|
| trend_strength | 0 | 0 | 0 | 0 | 0.00% | 0.00 | 0.0 |
| atr_filter | 0 | 0 | 0 | 0 | 0.00% | 0.00 | 0.0 |
| volume_confirm | 0 | 0 | 0 | 0 | 0.00% | 0.00 | 0.0 |
| momentum_filter | 0 | 0 | 0 | 0 | 0.00% | 0.00 | 0.0 |
| rsi_filter | 0 | 0 | 0 | 0 | 0.00% | 0.00 | 0.0 |
| fixed_stop | 0 | 0 | 0 | 0 | 0.00% | 0.00 | 0.0 |
| trailing_stop | 1 | 0 | 0 | 0 | 0.00% | -3256.14 | 12.0 |
| trend_reversal | 17 | 0 | 0 | 14 | 82.35% | 697.69 | 1.0 |
| time_stop | 0 | 0 | 0 | 0 | 0.00% | 0.00 | 0.0 |
| rsi_overbought | 7 | 0 | 0 | 4 | 57.14% | 1824.46 | 1.0 |

## Signal Attribution

| signal | return_share | win_share | loss_share | net_attribution |
|---|---|---|---|---|
| trend_strength | 0.00% | 0.00% | 0.00% | 0.00% |
| atr_filter | 0.00% | 0.00% | 0.00% | 0.00% |
| volume_confirm | 0.00% | 0.00% | 0.00% | 0.00% |
| momentum_filter | 0.00% | 0.00% | 0.00% | 0.00% |
| rsi_filter | 0.00% | 0.00% | 0.00% | 0.00% |
| fixed_stop | 0.00% | 0.00% | 0.00% | 0.00% |
| trailing_stop | -15.23% | 0.00% | 14.29% | -15.23% |
| trend_reversal | 55.49% | 77.78% | 42.86% | 55.49% |
| time_stop | 0.00% | 0.00% | 0.00% | 0.00% |
| rsi_overbought | 59.75% | 22.22% | 42.86% | 59.75% |

## Factor Value Stats

| factor | min | max | mean | std | p25 | p50 | p75 |
|---|---|---|---|---|---|---|---|
| ma_10 | 3.9240 | 24.8230 | 10.3013 | 6.6693 | 5.9300 | 8.0520 | 9.9850 |
| ma_30 | 3.9473 | 24.7840 | 10.3742 | 6.9173 | 5.7923 | 8.0597 | 10.3443 |
| atr_14 | 0.0821 | 1.2786 | 0.3365 | 0.2995 | 0.1443 | 0.2064 | 0.3664 |
| volume_ratio_20 | 0.5507 | 3.3095 | 1.1996 | 0.4281 | 0.9093 | 1.0935 | 1.3464 |
| rsi_14 | 13.6364 | 85.1064 | 56.1253 | 16.3344 | 44.4015 | 55.4217 | 70.6897 |
| close | 3.9000 | 28.5900 | 10.3955 | 6.7283 | 5.9800 | 8.1300 | 10.0400 |
| ma_60 | 4.0085 | 24.5567 | 10.5420 | 7.0672 | 5.9194 | 8.2221 | 10.5930 |
| mom_60 | -0.2279 | 0.2612 | -0.0111 | 0.1380 | -0.1272 | -0.0248 | 0.0778 |

## 调权依据

- 高 `win_rate` + 高 `avg_return` → 强势信号, 应增加权重
- 低 `win_rate` 或负 `avg_return` → 弱势信号, 应降低权重
- `return_share` 高 + `win_share` 高 → 强势信号, 应加权重
- `loss_share` 显著高于 `win_share` → 弱势信号, 应降权重
- `net_attribution` < 0 → 净拖累, 建议大幅降权或停用
