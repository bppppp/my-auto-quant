# Weight Mode Report

**strategy**: donchian_breakout_vol_rsi_ma
**test_name**: donchian_breakout_vol_rsi_ma
**version**: v1
**date**: 2026-06-06 07:57:12

## 测试条件

| 中文名 | 英文名 | 值 |
|---|---|---|
| 测试集 | test_universe | spec.test_universe (5 只, 默认 hs300) |
| 实际测试股票数 | universe_size | 5 |
| 测试起始日期 | start_date | 2024-01-01 |
| 测试结束日期 | end_date | 2024-02-29 |
| 股票数限制 | limit | 5 |
| weight_test | weight_test | donchian_breakout_vol_rsi_ma |

## Weights Used

**Entry signals**:
- `breakout_entry`: 0.5
- `trend_entry`: 0.3
- `rsi_entry`: 0.2

**Exit signals**:
- `fixed_stop_loss`: 0.3
- `trailing_stop`: 0.2
- `volatility_stop`: 0.2
- `trend_reversal_exit`: 0.15
- `overbought_reduce`: 0.1
- `time_stop`: 0.05

## Metrics

| 中文名 | 英文名 | 值 |
|---|---|---|
| 年化收益 | annual_return | 114.9208% |
| 年化收益率 | avg_annual_return_rate | 87.0985% |
| 年化收益额 | avg_annual_return_amount | 870,985.15 |
| 胜率 | win_rate | 100.0000% |
| 盈亏比 | profit_loss_ratio | 0.0000 |
| 夏普 | sharpe | 4.5139 |
| 最大回撤 | max_drawdown | -4.3991% |

## Signal Stats

| signal | triggered | swallowed | skipped | win_count | win_rate | avg_return | median_holding_days |
|---|---|---|---|---|---|---|---|
| breakout_entry | 0 | 0 | 0 | 0 | 0.00% | 0.00 | 0.0 |
| trend_entry | 0 | 0 | 0 | 0 | 0.00% | 0.00 | 0.0 |
| rsi_entry | 0 | 0 | 0 | 0 | 0.00% | 0.00 | 0.0 |
| fixed_stop_loss | 0 | 0 | 0 | 0 | 0.00% | 0.00 | 0.0 |
| trailing_stop | 0 | 0 | 0 | 0 | 0.00% | 0.00 | 0.0 |
| volatility_stop | 0 | 0 | 0 | 0 | 0.00% | 0.00 | 0.0 |
| trend_reversal_exit | 0 | 0 | 0 | 0 | 0.00% | 0.00 | 0.0 |
| overbought_reduce | 1 | 0 | 0 | 1 | 100.00% | 33676.46 | 5.0 |
| time_stop | 1 | 0 | 0 | 1 | 100.00% | 71431.25 | 25.0 |

## Signal Attribution

| signal | return_share | win_share | loss_share | net_attribution |
|---|---|---|---|---|
| breakout_entry | 0.00% | 0.00% | 0.00% | 0.00% |
| trend_entry | 0.00% | 0.00% | 0.00% | 0.00% |
| rsi_entry | 0.00% | 0.00% | 0.00% | 0.00% |
| fixed_stop_loss | 0.00% | 0.00% | 0.00% | 0.00% |
| trailing_stop | 0.00% | 0.00% | 0.00% | 0.00% |
| volatility_stop | 0.00% | 0.00% | 0.00% | 0.00% |
| trend_reversal_exit | 0.00% | 0.00% | 0.00% | 0.00% |
| overbought_reduce | 32.04% | 50.00% | 0.00% | 32.04% |
| time_stop | 67.96% | 50.00% | 0.00% | 67.96% |

## Factor Value Stats

| factor | min | max | mean | std | p25 | p50 | p75 |
|---|---|---|---|---|---|---|---|
| donchian_high_20 | 4.1700 | 28.7000 | 11.0983 | 7.4390 | 6.0100 | 8.3900 | 10.7600 |
| donchian_low_20 | 3.7500 | 23.3400 | 9.5838 | 6.1804 | 5.4600 | 7.7700 | 9.4400 |
| ma_20 | 3.9125 | 24.6310 | 10.3110 | 6.7909 | 5.8525 | 8.0270 | 10.1205 |
| atr_14 | 0.0821 | 1.2786 | 0.3365 | 0.2995 | 0.1443 | 0.2064 | 0.3664 |
| volume_ratio_20 | 0.5507 | 3.3095 | 1.1996 | 0.4281 | 0.9093 | 1.0935 | 1.3464 |
| rsi_14 | 13.6364 | 85.1064 | 56.1253 | 16.3344 | 44.4015 | 55.4217 | 70.6897 |
| close | 3.9000 | 28.5900 | 10.3955 | 6.7283 | 5.9800 | 8.1300 | 10.0400 |
| ma_60 | 4.0085 | 24.5567 | 10.5420 | 7.0672 | 5.9194 | 8.2221 | 10.5930 |

## 调权依据

- 高 `win_rate` + 高 `avg_return` → 强势信号, 应增加权重
- 低 `win_rate` 或负 `avg_return` → 弱势信号, 应降低权重
- `return_share` 高 + `win_share` 高 → 强势信号, 应加权重
- `loss_share` 显著高于 `win_share` → 弱势信号, 应降权重
- `net_attribution` < 0 → 净拖累, 建议大幅降权或停用
