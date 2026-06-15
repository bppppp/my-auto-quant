# Weight Mode Report (Detail Mode)

**strategy**: donchian_adx_volume_entry_1
**test_name**: donchian_adx_volume_entry_1
**version**: v1 (source = strategiesWeight/donchian_adx_volume_entry_1_weight_v1.md)
**date**: 2026-06-13 11:18:45
**note**: 使用 v1 weight 文件 (临时复制为 v99 跑回测,跑完已删除). 详细交易记录见同目录 weightDetail/.



---

## 原始报告

**strategy**: donchian_adx_volume_entry_1
**test_name**: donchian_adx_volume_entry_1
**version**: v1
**date**: 2026-06-13 11:18:45

## 测试条件

| 中文名 | 英文名 | 值 |
|---|---|---|
| 测试集 | test_universe | 自定义 300 只 |
| 实际测试股票数 | universe_size | 300 |
| 测试起始日期 | start_date | 2021-01-01 |
| 测试结束日期 | end_date | 2025-12-31 |
| 股票数限制 | limit | 不限 |
| weight_test | weight_test | donchian_adx_volume_entry_1 |

## Metrics

| 中文名 | 英文名 | 值 |
|---|---|---|
| 年化收益 | annual_return | -5.5302% |
| 年化收益率 | avg_annual_return_rate | -5.3195% |
| 年化收益额 | avg_annual_return_amount | -15,958.62 |
| 胜率 | win_rate | 0.0000% |
| 盈亏比 | profit_loss_ratio | 0.0000 |
| 夏普 | sharpe | -0.4944 |
| 最大回撤 | max_drawdown | -27.3917% |

## Weights Used

**Entry signals**:
- `breakout`: 0.5
- `trend_confirm`: 0.3
- `volume_confirm`: 0.2

**Exit signals**:
- `fixed_stop`: 0.6
- `trailing_stop`: 0.5
- `trend_reversal`: 0.4
- `time_stop`: 0.3

## Signal Stats

| 信号名 | 触发次数 | 被吞次数 | 跳过次数 | 盈利次数 | 胜率 | 平均收益 | 中位持仓天数 |
|---|---|---|---|---|---|---|---|
| breakout | 26 | 0 | 0 | 0 | 0.00% | -37082.84 | 24.0 |
| trend_confirm | 26 | 0 | 0 | 0 | 0.00% | -37082.84 | 24.0 |
| volume_confirm | 26 | 0 | 0 | 0 | 0.00% | -37082.84 | 24.0 |
| fixed_stop | 0 | 0 | 0 | 0 | 0.00% | 0.00 | 0.0 |
| trailing_stop | 2 | 0 | 0 | 0 | 0.00% | -37082.84 | 24.0 |
| trend_reversal | 0 | 0 | 0 | 0 | 0.00% | 0.00 | 0.0 |
| time_stop | 0 | 0 | 0 | 0 | 0.00% | 0.00 | 0.0 |

## 持仓天数分布

| 信号名 | ≤5天 | ≤10天 | ≤15天 | ≤20天 | ≤25天 | ≤30天 | >30天 |
|---|---|---|---|---|---|---|---|
| breakout | 1 | 0 | 0 | 0 | 0 | 0 | 1 |
| trend_confirm | 1 | 0 | 0 | 0 | 0 | 0 | 1 |
| volume_confirm | 1 | 0 | 0 | 0 | 0 | 0 | 1 |
| fixed_stop | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| trailing_stop | 1 | 0 | 0 | 0 | 0 | 0 | 1 |
| trend_reversal | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| time_stop | 0 | 0 | 0 | 0 | 0 | 0 | 0 |

## 盈亏分位数

| 信号名 | P10 | P25 | P50(中位数) | P75 | P90 |
|---|---|---|---|---|---|
| breakout | -38834.33 | -38177.52 | -37082.84 | -35988.16 | -35331.36 |
| trend_confirm | -38834.33 | -38177.52 | -37082.84 | -35988.16 | -35331.36 |
| volume_confirm | -38834.33 | -38177.52 | -37082.84 | -35988.16 | -35331.36 |
| fixed_stop | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| trailing_stop | -38834.33 | -38177.52 | -37082.84 | -35988.16 | -35331.36 |
| trend_reversal | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| time_stop | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |

## Signal Attribution

| signal | return_share | win_share | loss_share | net_attribution |
|---|---|---|---|---|
| breakout | -0.00% | 0.00% | 0.00% | 0.00% |
| trend_confirm | -0.00% | 0.00% | 0.00% | 0.00% |
| volume_confirm | -0.00% | 0.00% | 0.00% | 0.00% |
| fixed_stop | -0.00% | 0.00% | 0.00% | 0.00% |
| trailing_stop | 100.00% | 0.00% | 100.00% | -100.00% |
| trend_reversal | -0.00% | 0.00% | 0.00% | 0.00% |
| time_stop | -0.00% | 0.00% | 0.00% | 0.00% |

## Factor Value Stats

| 因子名 | 最小值 | 最大值 | 均值 | 标准差 | 25分位 | 中位数 | 75分位 |
|---|---|---|---|---|---|---|---|
| close | 0.7600 | 483.0300 | 12.7302 | 24.0335 | 4.5900 | 6.8500 | 11.7800 |
| high | 0.7900 | 485.8200 | 12.9770 | 24.5074 | 4.6600 | 6.9600 | 12.0100 |
| low | 0.7400 | 471.6700 | 12.4941 | 23.5741 | 4.5100 | 6.7400 | 11.5600 |
| volume | 59206.0000 | 3884664320.0000 | 29422459.5555 | 62316954.0861 | 6207100.0000 | 12802543.0000 | 28764469.0000 |
| hh_20 | 1.8500 | 157.4000 | 15.1381 | 19.3301 | 5.7700 | 9.4000 | 15.8200 |
| ll_10 | 1.6600 | 131.3800 | 12.9028 | 16.4980 | 5.0200 | 7.9100 | 13.0800 |
| adx_14 | 5.6985 | 100.0000 | 25.0269 | 10.0216 | 17.5598 | 23.1006 | 30.6889 |
| ma_20 | 1.7225 | 144.1450 | 13.8462 | 17.7322 | 5.3085 | 8.3415 | 13.9765 |
| ma_60 | 1.7457 | 153.1562 | 14.1818 | 18.9380 | 5.4275 | 8.3633 | 14.5162 |
| volume_ratio_20 | 0.3026 | 4.9270 | 0.9957 | 0.5689 | 0.6968 | 0.8440 | 1.1478 |

## 调权依据

- 高 `win_rate` + 高 `avg_return` → 强势信号, 应增加权重
- 低 `win_rate` 或负 `avg_return` → 弱势信号, 应降低权重
- `return_share` 高 + `win_share` 高 → 强势信号, 应加权重
- `loss_share` 显著高于 `win_share` → 弱势信号, 应降权重
- `net_attribution` < 0 → 净拖累, 建议大幅降权或停用
