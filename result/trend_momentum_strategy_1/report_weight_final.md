# Weight Mode Report

**strategy**: trend_momentum_strategy_1
**test_name**: trend_momentum_strategy_1
**version**: v25
**date**: 2026-06-14 13:20:02

## 测试条件

| 中文名 | 英文名 | 值 |
|---|---|---|
| 测试集 | test_universe | 自定义 300 只 |
| 实际测试股票数 | universe_size | 300 |
| 测试起始日期 | start_date | 2019-01-01 |
| 测试结束日期 | end_date | 2023-12-31 |
| 股票数限制 | limit | 不限 |
| weight_test | weight_test | trend_momentum_strategy_1 |

## Metrics

| 中文名 | 英文名 | 值 |
|---|---|---|
| 年化收益 | annual_return | 10.9557% |
| 年化收益率 | avg_annual_return_rate | 14.1108% |
| 年化收益额 | avg_annual_return_amount | 42,332.53 |
| 胜率 | win_rate | 36.1795% |
| 盈亏比 | profit_loss_ratio | 2.0404 |
| 夏普 | sharpe | 0.5469 |
| 最大回撤 | max_drawdown | -45.5469% |

## Weights Used

**Entry signals**:
- `trend_momentum_entry`: 1.0

**Exit signals**:
- `trend_reversal`: 1e-08
- `fixed_stop`: 1e-08
- `trailing_stop`: 0.5
- `time_stop`: 0.3
- `rsi_overbought_stop`: 3.0

## Signal Stats

| 信号名 | 触发次数 | 被吞次数 | 跳过次数 | 盈利次数 | 胜率 | 平均收益 | 中位持仓天数 |
|---|---|---|---|---|---|---|---|
| trend_momentum_entry | 31261 | 0 | 0 | 238 | 35.31% | 257.11 | 9.0 |
| trend_reversal | 503 | 0 | 0 | 116 | 23.06% | -1279.46 | 10.0 |
| fixed_stop | 7 | 0 | 0 | 0 | 0.00% | -8529.35 | 2.0 |
| trailing_stop | 60 | 0 | 0 | 22 | 36.67% | -68.51 | 11.0 |
| time_stop | 1 | 0 | 0 | 1 | 100.00% | 128167.86 | 75.0 |
| rsi_overbought_stop | 103 | 0 | 0 | 99 | 96.12% | 7305.94 | 5.0 |

## 持仓天数分布

| 信号名 | ≤5天 | ≤10天 | ≤15天 | ≤20天 | ≤25天 | ≤30天 | >30天 |
|---|---|---|---|---|---|---|---|
| trend_momentum_entry | 187 | 196 | 136 | 57 | 32 | 35 | 31 |
| trend_reversal | 116 | 157 | 112 | 46 | 22 | 24 | 26 |
| fixed_stop | 7 | 0 | 0 | 0 | 0 | 0 | 0 |
| trailing_stop | 11 | 15 | 14 | 7 | 6 | 5 | 2 |
| time_stop | 0 | 0 | 0 | 0 | 0 | 0 | 1 |
| rsi_overbought_stop | 53 | 24 | 10 | 4 | 4 | 6 | 2 |

## 盈亏分位数

| 信号名 | P10 | P25 | P50(中位数) | P75 | P90 |
|---|---|---|---|---|---|
| trend_momentum_entry | -5064.54 | -2711.36 | -1118.47 | 1601.65 | 5906.26 |
| trend_reversal | -4646.94 | -2828.71 | -1495.22 | -113.56 | 2424.37 |
| fixed_stop | -13274.86 | -9859.38 | -7385.59 | -6129.17 | -5342.77 |
| trailing_stop | -9749.30 | -5395.20 | -1769.73 | 4308.59 | 13047.82 |
| time_stop | 128167.86 | 128167.86 | 128167.86 | 128167.86 | 128167.86 |
| rsi_overbought_stop | 759.03 | 1943.99 | 4862.81 | 8373.70 | 16344.97 |

## Signal Attribution

| signal | return_share | win_share | loss_share | net_attribution |
|---|---|---|---|---|
| trend_momentum_entry | 0.00% | 0.00% | 0.00% | 0.00% |
| trend_reversal | -320.53% | 46.40% | 87.76% | -320.53% |
| fixed_stop | -29.74% | 0.00% | 1.59% | -29.74% |
| trailing_stop | -2.05% | 8.80% | 8.62% | -2.05% |
| time_stop | 63.83% | 0.40% | 0.00% | 63.83% |
| rsi_overbought_stop | 374.79% | 39.60% | 0.91% | 374.79% |

## Factor Value Stats

| 因子名 | 最小值 | 最大值 | 均值 | 标准差 | 25分位 | 中位数 | 75分位 |
|---|---|---|---|---|---|---|---|
| ma_5 | 1.0620 | 2166.2920 | 38.3106 | 99.4625 | 6.9400 | 16.0620 | 37.5945 |
| ma_20 | 1.0765 | 1976.6680 | 38.1766 | 99.2179 | 6.9184 | 16.0000 | 37.3282 |
| atr_14 | 0.0093 | 109.0971 | 1.5173 | 3.3893 | 0.1950 | 0.5450 | 1.4264 |
| rsi_14 | 0.0000 | 99.7330 | 50.0440 | 16.8968 | 37.7593 | 50.0000 | 62.2752 |
| macd_line | -108.6229 | 109.9470 | 0.1182 | 2.7505 | -0.2090 | -0.0010 | 0.2526 |
| macd_signal | -88.7830 | 87.5558 | 0.1192 | 2.5847 | -0.1923 | 0.0001 | 0.2409 |
| volume_ratio_20 | 0.0097 | 16.1791 | 1.0207 | 0.5082 | 0.7014 | 0.9019 | 1.1937 |
| close | 1.0400 | 2279.8500 | 38.3459 | 99.5348 | 6.9400 | 16.0800 | 37.6200 |
| ma_60 | 1.0947 | 1859.3170 | 38.0881 | 99.0531 | 6.9198 | 15.9427 | 37.1613 |

## 调权依据

- 高 `win_rate` + 高 `avg_return` → 强势信号, 应增加权重
- 低 `win_rate` 或负 `avg_return` → 弱势信号, 应降低权重
- `return_share` 高 + `win_share` 高 → 强势信号, 应加权重
- `loss_share` 显著高于 `win_share` → 弱势信号, 应降权重
- `net_attribution` < 0 → 净拖累, 建议大幅降权或停用
