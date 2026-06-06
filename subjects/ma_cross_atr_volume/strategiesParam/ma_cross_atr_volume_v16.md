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
  weight: 0.5
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
  weight: 0.3
  factors:
  - ma_5
  - ma_20
  direction: negative
  trigger: ma_5 < ma_20
  logic: AND
- name: trailing_stop
  weight: 0.3
  factors: []
  direction: negative
  trigger: current_price < highest_close_since_entry * (1 - {trailing_stop_pct})
  logic: 单因子
- name: fixed_stop
  weight: 0.2
  factors: []
  direction: negative
  trigger: current_price < entry_price * (1 - {fixed_stop_pct})
  logic: 单因子
- name: time_stop
  weight: 0.2
  factors: []
  direction: negative
  trigger: holding_days >= {max_holding_days}
  logic: 单因子
position_weights:
  max_single_weight: 0.14
  max_industry_concentration: 0.3
  target_holdings: 8
  max_turnover_per_rebalance: 0.35
  rebalance_freq_days: 5
params:
- name: add_position_weight_threshold
  default: 0.05
  range:
  - 0.02
  - 0.1
  type: float
  description: 加仓触发权重阈值（单位：小数）...
  reason: 加仓逻辑仍未触发,v15持仓无加仓,维持0.05
- name: volume_breakout_ratio
  default: 1.15
  range:
  - 1.0
  - 1.8
  type: float
  description: 量能放大倍数（单位：倍数）。含义：要求当日成交量 ≥ 该倍数 × 20 日均量...
  reason: 量能阈值1.15在p75=1.19附近,过滤稳定,维持
- name: max_holding_days
  default: 90
  range:
  - 30
  - 90
  type: int
  description: 最大持仓天数（单位：交易日）...
  reason: time_stop均利67659最高且100%胜率,但已到上限90,维持
- name: rebalance_freq_days
  default: 5
  range:
  - 1
  - 10
  type: int
  description: 再平衡频率（单位：交易日）...
  reason: 5日与波段持仓匹配,v15稳定,维持
- name: fixed_stop_pct
  default: 0.13
  range:
  - 0.05
  - 0.2
  type: float
  description: 固定止损比例（单位：小数）...
  reason: v15 fixed_stop触发0次,0.13已为兜底水平,维持
- name: bear_drawdown_threshold
  default: -0.08
  range:
  - -0.15
  - -0.05
  type: float
  description: 熊市识别阈值（沪深 300 指数 20 日跌幅）。单位：小数。含义：当沪深 300 指数 20 日跌幅 < 该值（默认 -10%）时进入熊市，整体仓位折算（target_holdings
    减半）以控制回撤。熊市判定由 subject/backtest/bear_market.py 实现（详见 subject.md §5.2）。
  reason: v15回撤-14.57%稳定在-15%内,熊市阈值-0.08合理,维持
- name: trailing_stop_pct
  default: 0.14
  range:
  - 0.05
  - 0.18
  type: float
  description: 移动止损比例（单位：小数）...
  reason: v15收紧0.13后触发数1434(v14为1040)均利反降,放宽至0.14
- name: max_turnover_per_rebalance
  default: 0.35
  range:
  - 0.2
  - 0.8
  type: float
  description: 单次再平衡换手上限（单位：小数）...
  reason: 换手0.35成本可控,v15稳定,维持
- name: max_single_weight
  default: 0.14
  range:
  - 0.05
  - 0.2
  type: float
  description: 单票最大权重（单位：小数）...
  reason: 单票0.14集中度合理,v15回撤可控,维持
- name: reduce_position_floor
  default: 0.02
  range:
  - 0.01
  - 0.06
  type: float
  description: 减仓下限权重（单位：小数）...
  reason: 底部减仓灵活,v15减仓稳定,维持
- name: atr_min_threshold
  default: 0.02
  range:
  - 0.008
  - 0.04
  type: float
  description: ATR 波动率最小阈值（单位：小数）。含义：要求 ATR/收盘价 > 该值...
  reason: atr/close均值3.76%远高于0.02,过滤生效,维持
- name: target_holdings
  default: 8
  range:
  - 4
  - 15
  type: int
  description: 目标持仓数（单位：只）...
  reason: 8只分散合理,v15持仓稳定,维持
- name: max_industry_concentration
  default: 0.3
  range:
  - 0.15
  - 0.5
  type: float
  description: 行业暴露上限（单位：小数）...
  reason: 0.30行业暴露平衡,v15稳定,维持
- name: reduce_position_weight_threshold
  default: 0.07
  range:
  - 0.03
  - 0.12
  type: float
  description: 减仓触发权重阈值（单位：小数）...
  reason: 减仓及时性合理,v15稳定,维持0.07
description: 双均线交叉 + ATR 波动率扩张 + 量能确认 + 移动止损
universe: 沪深 300
holding_period: 15-30 个交易日
rebalance_freq: 每 5 个交易日强制再平衡
---

