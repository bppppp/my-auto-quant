# multi_factor_trend_swing 聚宽移植设计

> 日期: 2026-06-12
> 任务: 将 `subjects/multi_factor_trend_swing/multi_factor_trend_swing_original.md` 翻译为聚宽 (JoinQuant / JQuant) 可执行的回测代码
> 输出: `D:/project/quant/my-quant3/joinQuant/multi_factor_trend_swingJQ.py`

## 1. 目标

将本地回测引擎 (`subjects/subject/backtest/`) 已实现的 `multi_factor_trend_swing` 策略**忠实**翻译为聚宽 (JQuant) 平台代码,使同一份 spec 在两个平台上行为一致:
- 5 个入场信号(权重 0.35/0.20/0.15/0.15/0.15,共 1.0)
- 5 个出场信号(按权重降序: 0.30/0.30/0.20/0.10/0.10)
- 5 个仓位约束(target_holdings / max_single_weight / max_industry_concentration / max_turnover_per_rebalance / rebalance_freq_days)
- 严格的 JQBoson 引擎 Quirks 兼容(§16.1-16.10)

## 2. 架构(参考 donchian_breakout_vol_rsi_ma JQ 示例)

```
┌──────────────────────────────────────────────────────┐
│ initialize(context)         设定基准/费率/日程/g     │
│   ├── set_benchmark('000300.XSHG')                  │
│   ├── set_option('use_real_price', True)             │
│   ├── set_order_cost(... type='stock')              │
│   ├── set_slippage(FixedSlippage(0.0005))           │
│   └── run_daily: 09:00 / 14:55 / 15:00              │
├──────────────────────────────────────────────────────┤
│ before_market_open(context) 09:00                    │
│   ├── 获取 HS300 成分股(get_index_stocks)            │
│   ├── filter_universe(去停牌/ST/上市不足 60 日)      │
│   ├── get_industry_map(stock_list, sw_l1)           │
│   └── g.rebalance_counter += 1                      │
├──────────────────────────────────────────────────────┤
│ market_rebalance(context)  14:55  (调仓日)           │
│   ├── guard: g.rebalance_counter % freq != 0 → return│
│   ├── calc_factors_batch(universe, context)         │
│   ├── 遍历 → entry_score(f, p) → score ≥ 0.50 入选  │
│   ├── 按 score 降序, 取 top target_holdings=10      │
│   └── execute_rebalance(context, target_stocks)     │
│       ├── 应用 max_industry_concentration=0.30 约束  │
│       ├── 应用 max_turnover_per_rebalance=0.40 约束  │
│       ├── 计算 per_target (= min(max_single*tv, 1/N))│
│       └── 调仓: 不在 target → 清仓; 在 target → 买入  │
├──────────────────────────────────────────────────────┤
│ check_stops_daily(context) 15:00                     │
│   ├── 遍历持仓: 更新 holding_days / highest_close    │
│   ├── 跌停当日跳过所有出场                          │
│   ├── exit_decision 按权重降序:                      │
│   │   fixed_stop(0.30) → trailing_stop(0.30) →      │
│   │   trend_reversal(0.20) → time_stop(0.10) →      │
│   │   rsi_overbought(0.10)                          │
│   └── 触发即 order_target_value(stock, 0)            │
└──────────────────────────────────────────────────────┘
```

## 3. 关键设计决策(用户已确认)

| 决策点 | 选定值 | 理由 |
|---|---|---|
| `min_entry_score` | **0.50** | trend_strength(0.35) + 至少 1 个其他信号(≥0.15)。平衡假信号过滤与机会保留 |
| 回测时间范围 | **不在代码中写死** | 由用户在聚宽回测 UI 设定(用户明确"不需要在 JQ 代码中输入") |
| 初始资金 | **不在代码中写死** | 同上,UI 设定 |
| 行业约束 | **启用,sw_l1 申万一级** | 与现有 donchian_breakout_vol_rsi_ma JQ 示例一致 |
| 加减仓 | **不实现** | spec narrative §4 明确"本策略不进行加仓 / 减仓操作" |
| 调仓频率 | **5 个交易日** | spec position_weights.rebalance_freq_days = 5 |
| Universe | **HS300(沪深 300)** | spec test_universe: ['HS300'] |
| 滑点 | **FixedSlippage(0.0005)** | 与示例一致 |

## 4. 因子实现(精确复刻 spec 7 个因子)

| factor | 计算 | 备注 |
|---|---|---|
| `ma_10` | `close.rolling(10).mean()` | 短均线 |
| `ma_30` | `close.rolling(30).mean()` | 中均线 |
| `ma_60` | `close.rolling(60).mean()` | 长均线 |
| `atr_14` | TR.rolling(14).mean(),TR=max(H-L, \|H-prevC\|, \|L-prevC\|) | 与示例 ATR 计算一致 |
| `volume_ratio_20` | `vol.iloc[-1] / vol.rolling(20).mean()` | 用历史 vol(cd 无 volume) |
| `rsi_14` | 100 - 100/(1+avg_gain/avg_loss),14 日 | Wilder 平滑(用 rolling mean 简化) |
| `mom_60` | `close / close.shift(60) - 1` | 60 日动量 |

## 5. 入场信号(权重按 spec 严格)

```python
def entry_score(f, p):
    score = 0.0
    # trend_strength (0.35): ma_10 > ma_30 > ma_60
    if f['ma_10'] > f['ma_30'] > f['ma_60']:
        score += 0.35
    # atr_filter (0.20): atr_14 / close > atr_threshold(默认 0.01)
    if f['atr_14'] / f['close'] > p['atr_threshold']:
        score += 0.20
    # volume_confirm (0.15): volume_ratio_20 > vol_threshold(默认 1.3)
    if f['volume_ratio_20'] > p['vol_threshold']:
        score += 0.15
    # momentum_filter (0.15): mom_60 > mom_threshold(默认 0.05)
    if f['mom_60'] > p['mom_threshold']:
        score += 0.15
    # rsi_filter (0.15): rsi_14 < rsi_upper(默认 70)
    if f['rsi_14'] < p['rsi_upper']:
        score += 0.15
    return score
```

## 6. 出场信号(按权重降序优先级,符合 spec §4)

```python
def exit_decision(f, h, current_price, p):
    # 1. fixed_stop (0.30): current < entry * (1 - 0.08)
    if current_price < h['entry_price'] * (1 - p['fixed_stop_pct']): return 'fixed_stop'
    # 2. trailing_stop (0.30): current < highest * (1 - 0.05)
    if current_price < h['highest_close'] * (1 - p['trailing_stop_pct']): return 'trailing_stop'
    # 3. trend_reversal (0.20): ma_10 < ma_30
    if f['ma_10'] < f['ma_30']: return 'trend_reversal'
    # 4. time_stop (0.10): holding_days >= max_holding_days
    if h['holding_days'] >= p['max_holding_days']: return 'time_stop'
    # 5. rsi_overbought (0.10): rsi_14 > rsi_overbought
    if f['rsi_14'] > p['rsi_overbought']: return 'rsi_overbought'
    return None
```

## 7. 仓位约束(execute_rebalance 中)

| 约束 | 字段 | 默认 | 实现 |
|---|---|---|---|
| 目标持仓数 | target_holdings | 10 | 取 score top N |
| 单票最大权重 | max_single_weight | 0.12 | per_target = min(0.12*tv, tv/N) |
| 行业集中度 | max_industry_concentration | 0.30 | sw_l1 行业累计 ≤ 0.30*tv |
| 换手率上限 | max_turnover_per_rebalance | 0.40 | 超限按比例缩放 |
| 调仓频率 | rebalance_freq_days | 5 | counter % 5 == 0 才调 |

## 8. JQBoson Quirks 防御性写法(逐条对照 §16)

| Quirk | 防御方式 |
|---|---|
| §16.1 `sum(dict.values())` | 显式 `sum([d[k] for k in d])` |
| §16.2 `order_value` 追加而非调仓 | 调仓用 `order_target_value(stock, 0)`(清仓) |
| §16.3 `cd[s]` KeyError | 全用 `cd.get(s)` + None 守护 |
| §16.4 `get_current_data()` 无 volume | 量比用历史 `attribute_history` 的 volume |
| §16.5 `high_limit/low_limit == 0` | 涨跌停判断加 `> 0` 守护 |
| §16.6 模拟盘 run_daily 每日触发 | 加 `_is_trading_day()` 守卫 |
| §16.7 涨跌停时 order_target_value 自动挂单 | 不需要 None 守卫,直接发单 |
| §16.8 科创板市价单需 LimitOrderStyle | 688xxx 用 `LimitOrderStyle(last_price*1.005)` |
| §16.9 order_target_value 报"数量为 0" | 用 `order(stock, delta_shares)` 显式传股数 |
| §16.10 g.params 长列表丢失 | 长 list 放模块级常量(`HS300_STATIC` 不需要,改用 `get_index_stocks` 动态) |

## 9. 文件结构

`multi_factor_trend_swingJQ.py` 8 大段(参考示例):

1. 文件头注释(docstring + 来源)
2. 导入(`from jqdata import *`, numpy, pandas)
3. PARAMS 配置区(13 个 spec 参数 + 5 个仓位参数)
4. JQ 框架函数(initialize / before_market_open / market_rebalance / check_stops_daily)
5. 因子计算(calc_factors_one / calc_factors_batch)
6. 信号逻辑(entry_score / exit_decision)
7. 调仓执行(execute_rebalance)
8. 工具函数(filter_universe / get_industry_map)

## 10. 不在范围内

- 不写单测(JQ 平台无 pytest,需回测 UI 验证)
- 不写 README(spec 已说明)
- 不写 `if __name__ == '__main__'` 块(JQ 不支持)
- 不写 unit test(`jqdata` 需在 JQ 平台运行)
- 不引入未在 spec 列出的因子(保持忠实)
- 不修改 spec 的 params 默认值

## 11. 验收标准

| # | 检查项 |
|---|---|
| 1 | Python 语法通过(`python -c "import ast; ast.parse(open('...').read())"`) |
| 2 | spec 5 个入场信号全部实现(权重 0.35/0.20/0.15/0.15/0.15) |
| 3 | spec 5 个出场信号全部实现(权重 0.30/0.30/0.20/0.10/0.10),优先级与 spec 一致 |
| 4 | 5 个仓位约束全部实现(target=10, single=0.12, industry=0.30, turnover=0.40, freq=5) |
| 5 | 13 个 params 字段全部纳入 PARAMS,默认值与 spec 一致 |
| 6 | 严格遵守 16.1-16.10 全部 10 条 JQ Quirks |
| 7 | 不在代码中写死回测时间/资金(用户确认) |
| 8 | 严格不写加仓/减仓(spec 明确不做) |
