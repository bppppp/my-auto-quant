# Weight Mode Report

**strategy**: donchian_breakout_vol_rsi_ma
**test_name**: donchian_breakout_vol_rsi_ma
**version**: v1
**date**: 2026-06-07 23:28:02

## 测试条件

| 中文名 | 英文名 | 值 |
|---|---|---|
| 测试集 | test_universe | spec.test_universe (10 只, 默认 HS300) |
| 实际测试股票数 | universe_size | 10 |
| 测试起始日期 | start_date | 2024-01-01 |
| 测试结束日期 | end_date | 2025-01-01 |
| 股票数限制 | limit | 10 |
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
| 年化收益 | annual_return | 21.7735% |
| 年化收益率 | avg_annual_return_rate | 22.3291% |
| 年化收益额 | avg_annual_return_amount | 66,987.44 |
| 胜率 | win_rate | 36.6337% |
| 盈亏比 | profit_loss_ratio | 2.4263 |
| 夏普 | sharpe | 1.1819 |
| 最大回撤 | max_drawdown | -20.5907% |

## Signal Stats

| 信号名 | 触发次数 | 被吞次数 | 跳过次数 | 盈利次数 | 胜率 | 平均收益 | 中位持仓天数 |
|---|---|---|---|---|---|---|---|
| breakout_entry | 0 | 0 | 0 | 0 | 0.00% | 0.00 | 0.0 |
| trend_entry | 826 | 0 | 0 | 10 | 27.03% | -664.35 | 13.0 |
| rsi_entry | 1571 | 0 | 0 | 26 | 35.14% | 802.08 | 11.0 |
| fixed_stop_loss | 1 | 0 | 0 | 0 | 0.00% | -5949.55 | 2.0 |
| trailing_stop | 42 | 3 | 0 | 6 | 14.29% | -1805.29 | 9.0 |
| volatility_stop | 27 | 0 | 0 | 7 | 25.93% | -992.69 | 11.0 |
| trend_reversal_exit | 0 | 0 | 0 | 0 | 0.00% | 0.00 | 0.0 |
| overbought_reduce | 12 | 0 | 0 | 12 | 100.00% | 10868.09 | 12.0 |
| time_stop | 5 | 0 | 0 | 5 | 100.00% | 4562.85 | 25.0 |

## Signal Attribution

| signal | return_share | win_share | loss_share | net_attribution |
|---|---|---|---|---|
| breakout_entry | 0.00% | 0.00% | 0.00% | 0.00% |
| trend_entry | 0.00% | 0.00% | 0.00% | 0.00% |
| rsi_entry | 0.00% | 0.00% | 0.00% | 0.00% |
| fixed_stop_loss | -11.06% | 0.00% | 1.56% | -11.06% |
| trailing_stop | -140.89% | 16.22% | 56.25% | -140.89% |
| volatility_stop | -49.80% | 18.92% | 31.25% | -49.80% |
| trend_reversal_exit | 0.00% | 0.00% | 0.00% | 0.00% |
| overbought_reduce | 242.34% | 32.43% | 0.00% | 242.34% |
| time_stop | 42.39% | 13.51% | 0.00% | 42.39% |

## Factor Value Stats

| 因子名 | 最小值 | 最大值 | 均值 | 标准差 | 25分位 | 中位数 | 75分位 |
|---|---|---|---|---|---|---|---|
| donchian_high_20 | 3.8900 | 79.3100 | 18.2482 | 17.7920 | 7.1600 | 10.2100 | 25.6300 |
| donchian_low_20 | 3.5200 | 67.4000 | 15.7978 | 15.6859 | 6.2000 | 9.0300 | 22.0900 |
| ma_20 | 3.7490 | 71.6060 | 16.8984 | 16.6653 | 6.6110 | 9.4585 | 23.9603 |
| atr_14 | 0.0607 | 3.7129 | 0.5137 | 0.5311 | 0.1677 | 0.2789 | 0.6787 |
| volume_ratio_20 | 0.2548 | 5.4182 | 1.0424 | 0.5195 | 0.7287 | 0.9200 | 1.2097 |
| rsi_14 | 2.6119 | 98.3133 | 50.8302 | 16.4243 | 38.7867 | 50.0000 | 62.9921 |
| close | 3.5700 | 76.0200 | 17.0668 | 16.9547 | 6.5775 | 9.4500 | 23.9600 |
| ma_60 | 3.8377 | 69.7603 | 16.7212 | 16.3492 | 6.5885 | 9.4755 | 24.2860 |

## 调权依据

- 高 `win_rate` + 高 `avg_return` → 强势信号, 应增加权重
- 低 `win_rate` 或负 `avg_return` → 弱势信号, 应降低权重
- `return_share` 高 + `win_share` 高 → 强势信号, 应加权重
- `loss_share` 显著高于 `win_share` → 弱势信号, 应降权重
- `net_attribution` < 0 → 净拖累, 建议大幅降权或停用
