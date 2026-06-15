---
name: multi_factor_trend_swing
targets:
  annual_return: 0.22
  win_rate: 0.52
  profit_loss_ratio: 2.9
  sharpe: 1.35
  max_drawdown: -0.12
  description: 基于多因子（均线趋势、ATR波动、量能、动量、RSI）过滤的中期波段策略。目标年化22%，胜率52%，盈亏比2.9，夏普1.35，回撤12%。
test_universe:
- HS300
factors:
- name: ma_10
  description: 10日简单移动平均线
  calculation: mean(close, 10)
- name: ma_30
  description: 30日简单移动平均线
  calculation: mean(close, 30)
- name: ma_60
  description: 60日简单移动平均线
  calculation: mean(close, 60)
- name: atr_14
  description: 14日平均真实波幅
  calculation: atr(high, low, close, 14)
- name: volume_ratio_20
  description: 当日成交量 / 20日均量
  calculation: volume / mean(volume, 20)
- name: rsi_14
  description: 14日相对强弱指标
  calculation: rsi(close, 14)
- name: mom_60
  description: 60日动量（当日收盘 / 60日前收盘 - 1）
  calculation: (close / lag(close, 60) - 1)
entry_signals:
- name: trend_strength
  weight: 0.35
  factors:
  - ma_10
  - ma_30
  - ma_60
  direction: positive
  trigger: ma_10 > ma_30 AND ma_30 > ma_60
  logic: AND
- name: atr_filter
  weight: 0.2
  factors:
  - atr_14
  direction: positive
  trigger: atr_14 / close > {atr_threshold}
  logic: 单因子
- name: volume_confirm
  weight: 0.15
  factors:
  - volume_ratio_20
  direction: positive
  trigger: volume_ratio_20 > {vol_threshold}
  logic: 单因子
- name: momentum_filter
  weight: 0.15
  factors:
  - mom_60
  direction: positive
  trigger: mom_60 > {mom_threshold}
  logic: 单因子
- name: rsi_filter
  weight: 0.15
  factors:
  - rsi_14
  direction: positive
  trigger: rsi_14 < {rsi_upper}
  logic: 单因子
exit_signals:
- name: fixed_stop
  weight: 0.3
  factors: []
  direction: negative
  trigger: current_price < entry_price * (1 - {fixed_stop_pct})
  logic: 单因子
- name: trailing_stop
  weight: 0.3
  factors: []
  direction: negative
  trigger: current_price < highest_close_since_entry * (1 - {trailing_stop_pct})
  logic: 单因子
- name: trend_reversal
  weight: 0.2
  factors:
  - ma_10
  - ma_30
  direction: negative
  trigger: ma_10 < ma_30
  logic: AND
- name: time_stop
  weight: 0.1
  factors: []
  direction: negative
  trigger: holding_days >= {max_holding_days}
  logic: 单因子
- name: rsi_overbought
  weight: 0.1
  factors:
  - rsi_14
  direction: negative
  trigger: rsi_14 > {rsi_overbought}
  logic: 单因子
position_weights:
  max_single_weight: 0.1
  max_industry_concentration: 0.3
  target_holdings: 12
  max_turnover_per_rebalance: 0.3
  rebalance_freq_days: 5
params:
- name: rebalance_freq_days
  default: 5
  range:
  - 3
  - 15
  type: int
  description: 再平衡频率，单位：交易日。含义：每隔多少交易日进行一次组合再平衡，典型取值1-10，默认5，理由：每周再平衡，平衡时效性与交易成本。
  reason: 5天再平衡平衡时效性，维持
- name: rsi_upper
  default: 60
  range:
  - 55
  - 80
  type: int
  description: RSI入场上限，单位：数值。含义：入场时RSI须低于此值，典型取值60-85，默认70，理由：避免在超买区域追高。
  reason: RSI中位63，降至60避免超买区域入场，提高胜率
- name: target_holdings
  default: 12
  range:
  - 5
  - 25
  type: int
  description: 目标持仓数量，单位：只。含义：组合中持有的股票数量目标，典型取值5-20，默认10，理由：平衡分散度与持仓集中度，便于管理。
  reason: 增加持股至12只提高分散度，降低组合回撤
- name: max_industry_concentration
  default: 0.3
  range:
  - 0.15
  - 0.5
  type: float
  description: 行业集中度上限，单位：小数。含义：单一行业权重占比上限，典型取值0.20-0.50，默认0.30，理由：控制行业风险暴露。
  reason: 行业集中度0.3合理，维持不变
- name: fixed_stop_pct
  default: 0.13
  range:
  - 0.05
  - 0.25
  type: float
  description: 固定止损比例，单位：小数。含义：股价较入场价下跌超过该比例则止损，典型取值0.03-0.20，默认0.08，理由：平衡最大损失容忍度与正常波动。
  reason: 稍放宽至0.13进一步减少误止损，降低回撤，但需控制单笔亏损
- name: max_holding_days
  default: 45
  range:
  - 15
  - 80
  type: int
  description: 最大持仓天数，单位：交易日。含义：持仓达到该天数后强制出场，典型取值10-60，默认30，理由：约1.5个月，符合中周期波段特征。
  reason: 时间止损胜率84%且盈利高，延长至45天让趋势充分发展
- name: trailing_stop_pct
  default: 0.09
  range:
  - 0.03
  - 0.2
  type: float
  description: 移动止损比例，单位：小数。含义：从持仓最高价回落超过该比例则止盈/止损，典型取值0.02-0.15，默认0.05，理由：保护浮盈同时避免过早离场。
  reason: 提升至0.09减少过早止盈，让趋势发展，提高盈亏比
- name: max_turnover_per_rebalance
  default: 0.3
  range:
  - 0.1
  - 0.6
  type: float
  description: 单次再平衡最大换手率，单位：小数。含义：再平衡时买入卖出合计占组合的比例上限，典型取值0.20-0.80，默认0.40，理由：控制交易成本和冲击。
  reason: 换手0.3控制成本，暂维持
- name: mom_threshold
  default: 0.12
  range:
  - 0.0
  - 0.3
  type: float
  description: 60日动量最低阈值，单位：小数。含义：过去60日涨幅须超过该值，典型取值0.0-0.2，默认0.05，理由：确保中期上升趋势存在。
  reason: 提升至0.12进一步筛选强动量，提升胜率和盈亏比
- name: vol_threshold
  default: 1.4
  range:
  - 1.2
  - 3.0
  type: float
  description: 量能放大倍数阈值，单位：倍数。含义：当日成交量/20日均量须大于该值，典型取值1.0-2.5，默认1.3，理由：1.3倍均量确认资金介入。
  reason: 1.4已高于75分位，平衡信号数量与质量，暂维持
- name: max_single_weight
  default: 0.1
  range:
  - 0.03
  - 0.2
  type: float
  description: 单票最大权重，单位：小数。含义：单只股票占组合权重上限，典型取值0.05-0.20，默认0.12，理由：分散风险，避免单票过度集中。
  reason: 降低单票权重至10%减少个股风险，控制回撤
- name: rsi_overbought
  default: 80
  range:
  - 70
  - 95
  type: int
  description: RSI超买出场阈值，单位：数值。含义：RSI超过此值触发超买出场，典型取值70-90，默认75，理由：短期过热信号，及时止盈。
  reason: 提高至80减少过早出场，让利润奔跑，提升盈亏比
- name: atr_threshold
  default: 0.08
  range:
  - 0.02
  - 0.15
  type: float
  description: ATR波动率过滤阈值，单位：小数。含义：要求ATR/收盘价大于该阈值，典型取值0.01-0.03，默认0.01，理由：过滤低波动无效突破，0.01表示要求波动率至少1%。
  reason: atr/close 25分位0.074，提高至0.08过滤低波股，提升胜率和平均收益
description: 基于多因子（均线趋势、ATR波动、量能、动量、RSI）过滤的中期波段策略。目标年化22%，胜率52%，盈亏比2.9，夏普1.35，回撤12%。
universe: 沪深300
holding_period: 15-30个交易日
rebalance_freq: 每5个交易日强制再平衡
---

