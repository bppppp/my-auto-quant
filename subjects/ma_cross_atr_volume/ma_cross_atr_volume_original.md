---
name: ma_cross_atr_volume
targets:
  annual_return: 0.22
  win_rate: 0.48
  profit_loss_ratio: 2.3
  sharpe: 1.3
  max_drawdown: -0.15
  description: 双均线交叉 + ATR 波动率扩张 + 量能确认。期望 22% / 胜率 48% / 盈亏比 2.3 / 夏普 1.3 / 回撤 15%。
test_universe:
- HS300
factors:
- name: ma_5
  description: 5 日简单移动平均线
  calculation: mean(close, 5)
- name: ma_20
  description: 20 日简单移动平均线
  calculation: mean(close, 20)
- name: atr_14
  description: 14 日平均真实波幅
  calculation: atr(high, low, close, 14)
- name: volume_ratio_20
  description: 当日成交量 / 20 日均量
  calculation: volume / mean(volume, 20)
entry_signals:
- name: ma_golden_cross
  weight: 0.50
  factors:
  - ma_5
  - ma_20
  direction: positive
  trigger: ma_5 > ma_20
  logic: AND
- name: atr_expand
  weight: 0.25
  factors:
  - atr_14
  direction: positive
  trigger: atr_14 > atr_14_prev AND atr_14 / close > {atr_min_threshold}
  logic: 单因子
- name: volume_confirm
  weight: 0.25
  factors:
  - volume_ratio_20
  direction: positive
  trigger: volume_ratio_20 > {volume_breakout_ratio}
  logic: 单因子
exit_signals:
- name: ma_death_cross
  weight: 0.30
  factors:
  - ma_5
  - ma_20
  direction: negative
  trigger: ma_5 < ma_20
  logic: AND
- name: trailing_stop
  weight: 0.30
  factors: []
  direction: negative
  trigger: current_price < highest_close_since_entry * (1 - {trailing_stop_pct})
  logic: 单因子
- name: fixed_stop
  weight: 0.20
  factors: []
  direction: negative
  trigger: current_price < entry_price * (1 - {fixed_stop_pct})
  logic: 单因子
- name: time_stop
  weight: 0.20
  factors: []
  direction: negative
  trigger: holding_days >= {max_holding_days}
  logic: 单因子
position_weights:
  max_single_weight: 0.10
  max_industry_concentration: 0.30
  target_holdings: 8
  max_turnover_per_rebalance: 0.50
  rebalance_freq_days: 5
params:
- name: bear_drawdown_threshold
  default: -0.10
  range: [-0.20, -0.05]
  type: float
  description: 熊市识别阈值（沪深 300 指数 20 日跌幅）。单位：小数。含义：当沪深 300 指数 20 日跌幅 < 该值（默认 -10%）时进入熊市，整体仓位折算（target_holdings 减半）以控制回撤。熊市判定由 subject/backtest/bear_market.py 实现（详见 subject.md §5.2）。
- name: atr_min_threshold
  default: 0.015
  range: [0.005, 0.050]
  type: float
  description: ATR 波动率最小阈值（单位：小数）。含义：要求 ATR/收盘价 > 该值...
- name: volume_breakout_ratio
  default: 1.3
  range: [1.0, 3.0]
  type: float
  description: 量能放大倍数（单位：倍数）。含义：要求当日成交量 ≥ 该倍数 × 20 日均量...
- name: fixed_stop_pct
  default: 0.08
  range: [0.05, 0.20]
  type: float
  description: 固定止损比例（单位：小数）...
- name: trailing_stop_pct
  default: 0.05
  range: [0.02, 0.15]
  type: float
  description: 移动止损比例（单位：小数）...
- name: max_holding_days
  default: 30
  range: [10, 60]
  type: int
  description: 最大持仓天数（单位：交易日）...
- name: add_position_weight_threshold
  default: 0.06
  range: [0.02, 0.10]
  type: float
  description: 加仓触发权重阈值（单位：小数）...
- name: reduce_position_weight_threshold
  default: 0.08
  range: [0.03, 0.12]
  type: float
  description: 减仓触发权重阈值（单位：小数）...
- name: reduce_position_floor
  default: 0.03
  range: [0.01, 0.06]
  type: float
  description: 减仓下限权重（单位：小数）...
- name: max_single_weight
  default: 0.10
  range: [0.03, 0.20]
  type: float
  description: 单票最大权重（单位：小数）...
- name: max_industry_concentration
  default: 0.30
  range: [0.15, 0.50]
  type: float
  description: 行业暴露上限（单位：小数）...
- name: target_holdings
  default: 8
  range: [4, 15]
  type: int
  description: 目标持仓数（单位：只）...
- name: max_turnover_per_rebalance
  default: 0.50
  range: [0.20, 0.80]
  type: float
  description: 单次再平衡换手上限（单位：小数）...
- name: rebalance_freq_days
  default: 5
  range: [1, 10]
  type: int
  description: 再平衡频率（单位：交易日）...
description: 双均线交叉 + ATR 波动率扩张 + 量能确认 + 移动止损
universe: 沪深 300
holding_period: 15-30 个交易日
rebalance_freq: 每 5 个交易日强制再平衡
---

## 策略业务逻辑叙事

### 1. 策略思路 / edge 来源
本策略基于 **A 股中短期均线交叉的趋势延续效应**。核心 edge：5 日均线（ma_5）上穿 20 日均线（ma_20）的"金叉"出现后，A 股沪深 300 成分股往往进入 2-4 周的趋势性行情，散户资金追随、动量惯性使趋势有较高概率延续。**仅金叉不足以过滤假突破**，因此叠加两个辅助信号：① ATR 14 扩张 + 相对波动率过滤（要求波动率本身在扩大、且相对当前价格足够大），剔除低波动的"无意义金叉"；② 量能放大（成交量 ≥ 1.3 倍 20 日均量）确认资金参与。三信号共同作用下，期望捕获趋势启动前 5-15 日的明确主升段。出场采用多重防线：均线死叉（趋势反转）、固定止损（8% 硬性损失）、移动止损（5% 浮盈回撤保护）、时间止损（30 日强制平仓），任何一道触发即离场。

### 2. 市场环境假设
- **A 股沪深 300 成分股**存在显著的中短期动量惯性：个股金叉后常有 10-20 个交易日的方向延续，失败率约 40-50%
- 流动性充裕（沪深 300 成分股日均成交额 1 亿+），冲击成本可控，适合中频策略
- **T+1 制度** + **涨跌停** 制度下，止损信号当日可能被吞，策略接受这种"信号失效"作为正常事件，不视为策略缺陷
- **不适用**：连续一字板新股、长期停牌后复牌、ST 股票、退市整理期（这些股票直接被 universe 过滤）

### 3. 牛 / 熊 / 震荡 3 环境处理（**所有阈值 param 化**）
- **牛市**：趋势明显、信号频繁有效。**降低** `atr_min_threshold`（0.01-0.012）和 `volume_breakout_ratio`（1.1-1.2）让更多信号通过；**提高** `max_holding_days`（40-50）让利润充分发展；**放宽** `trailing_stop_pct`（0.06-0.08）避免被洗出。
- **熊市**：反弹持续性差，需要更严苛的入场过滤。**提高** `atr_min_threshold`（0.025-0.035）和 `volume_breakout_ratio`（1.5-2.0）减少假信号；**缩短** `max_holding_days`（15-20）快速兑现；**收紧** `fixed_stop_pct`（0.05-0.06）和 `trailing_stop_pct`（0.03-0.04）；**降低** `target_holdings`（4-6）减少总暴露。
- **震荡市**：频繁假金叉/死叉，需用时间止损 + 信号稀疏化应对。**缩短** `max_holding_days`（15-20）防止套牢；**适度提高** `volume_breakout_ratio`（1.4-1.6）过滤无量金叉；**保持** `fixed_stop_pct` 中性；**延长** `rebalance_freq_days`（7-10）减少无效交易。

### 4. 多信号逻辑关系
- **入场时机**：**至少 2 个信号同时触发**（ma_golden_cross 必触发为核心条件，atr_expand / volume_confirm 至少 1 个满足）。综合得分 = Σ(触发信号的 weight)，系统按得分排序选 top N（`target_holdings=8`）。任一信号缺失即放弃该股，确保入场质量。
- **出场优先级**（按 weight 降序）：`ma_death_cross`（0.30，趋势反转）> `trailing_stop`（0.30，浮盈保护）> `fixed_stop`（0.20，硬性止损）> `time_stop`（0.20，防止套牢）。多个信号同时触发时按优先级链执行，前一信号返回则后续不检查。**死叉优先级最高**，因为它代表"趋势已破坏"——比"已浮亏"更应优先响应。

### 5. 风险机制
- **熊市识别**：沪深 300 指数 20 日跌幅 < `{bear_drawdown_threshold}` 时（默认 -10%），整体仓位折算（`target_holdings` 减半），单票权重降低，避免系统性下跌放大回撤。
- **涨跌停挤不出场**：当日跌停的股票所有出场信号被吞，系统记录为"信号被吞"，不视为已实现止损；下一交易日开盘后若条件仍满足则继续执行。涨停买入同样被吞，不强行排队避免"买到就是跌"。
- **早期数据 NaN 处理**（**A 股硬约束**）：
  - 上市未满 N 日（ma_5 / ma_20 / atr_14 等 N 日窗口因子 NaN）→ 该股票该日不参与信号计算（不剔除出 universe），待满足窗口后自然纳入
  - 长期停牌 → 复牌当日不立即入场，等 N 个交易日数据回填后再参与信号计算
  - 涨跌停日 → 出场信号被吞；入场信号正常基于开盘前数据判断（开板可成交时即买入）
  - 一字板 / 退市 → 默认跳过（不参与回测）

### 6. 与其他策略区别
本策略以 **ma_golden_cross 为唯一核心入场条件**（必须有金叉才考虑入场），与 donchian_breakout_vol_rsi_ma 的"突破+多过滤"和 multi_factor_trend_swing 的"多因子等权共振"均不同。区别于单纯均线策略：本策略额外要求 ATR 扩张 + 量能放大两道过滤，假信号率显著更低。区别于纯动量策略：用 5/20 短均线对短期反转敏感，反应快但持仓周期短（15-30 日），换手适中。
