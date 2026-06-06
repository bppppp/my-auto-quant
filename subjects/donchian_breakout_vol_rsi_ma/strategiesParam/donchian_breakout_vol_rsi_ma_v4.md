---
name: donchian_breakout_vol_rsi_ma
targets:
  annual_return: 0.25
  win_rate: 0.45
  profit_loss_ratio: 3.5
  sharpe: 1.3
  max_drawdown: -0.18
  description: 基于Donchian通道突破+成交量放大+趋势与RSI过滤，配合多级止损的中周期波段策略。目标年化25%，胜率45%，盈亏比3.5，夏普1.3，最大回撤18%。
test_universe:
- hs300
factors:
- name: donchian_high_20
  description: 20日最高价，Donchian通道上轨，突破关键阻力
  calculation: max(high, 20)
- name: donchian_low_20
  description: 20日最低价，Donchian通道下轨，跌破关键支撑
  calculation: min(low, 20)
- name: ma_20
  description: 20日简单移动平均线，衡量短期趋势
  calculation: mean(close, 20)
- name: ma_60
  description: 60日简单移动平均线，衡量中期趋势
  calculation: mean(close, 60)
- name: atr_14
  description: 14日平均真实波幅，衡量市场波动程度
  calculation: atr(high, low, close, 14)
- name: volume_ratio_20
  description: 当日成交量与20日均量之比，衡量放量程度
  calculation: volume / mean(volume, 20)
- name: rsi_14
  description: 14日相对强弱指标，量化短期超买超卖状态
  calculation: 100 - 100 / (1 + mean(gain, 14) / mean(loss, 14))
entry_signals:
- name: breakout_entry
  weight: 0.5
  factors:
  - donchian_high_20
  - volume_ratio_20
  direction: positive
  trigger: close > donchian_high_20 AND volume_ratio_20 > {vol_breakout_threshold}
  logic: AND
- name: trend_entry
  weight: 0.3
  factors:
  - ma_20
  - ma_60
  direction: positive
  trigger: ma_20 > ma_60 AND close > ma_20
  logic: AND
- name: rsi_entry
  weight: 0.2
  factors:
  - rsi_14
  direction: positive
  trigger: rsi_14 > {rsi_entry_low} AND rsi_14 < {rsi_entry_high}
  logic: AND
exit_signals:
- name: fixed_stop_loss
  weight: 0.3
  factors: []
  direction: negative
  trigger: current_price < entry_price * (1 - {fixed_stop_loss_pct})
  logic: 单因子
- name: trailing_stop
  weight: 0.2
  factors: []
  direction: negative
  trigger: current_price < highest_close_since_entry * (1 - {trail_stop_pct})
  logic: 单因子
- name: volatility_stop
  weight: 0.2
  factors:
  - atr_14
  direction: negative
  trigger: current_price < highest_close_since_entry - {atr_stop_multiplier} * atr_14
  logic: 单因子
- name: trend_reversal_exit
  weight: 0.15
  factors:
  - donchian_low_20
  direction: negative
  trigger: close < donchian_low_20
  logic: 单因子
- name: overbought_reduce
  weight: 0.1
  factors:
  - rsi_14
  direction: negative
  trigger: rsi_14 > {rsi_overbought} AND pnl_pct > {partial_profit_pct}
  logic: AND
- name: time_stop
  weight: 0.05
  factors: []
  direction: negative
  trigger: holding_days >= {max_holding_days}
  logic: 单因子
position_weights:
  max_single_weight: 0.1
  max_industry_concentration: 0.3
  target_holdings: 8
  max_turnover_per_rebalance: 0.5
  rebalance_freq_days: 5
params:
- name: partial_profit_pct
  default: 0.15
  range:
  - 0.05
  - 0.3
  type: float
  description: 触发盈利减仓的最低累计收益率。单位：小数。典型取值0.10-0.25，默认0.15确保在已有可观利润后再执行减仓，避免微利卖出。
  reason: 最佳出场信号(均收+5870胜率100%)，保持
- name: rebalance_freq_days
  default: 5
  range:
  - 1
  - 10
  type: int
  description: 再平衡频率，每隔该交易日数检查信号并调仓。单位：交易日。典型取值3-7，默认5天在及时跟进信号与减少操作噪音间取得平衡。
  reason: 5日频率与波段匹配，不影响入场根因，保持
- name: rsi_entry_high
  default: 70
  range:
  - 50
  - 80
  type: int
  description: RSI入场上限，防止在严重超买时追高。单位：数值。典型取值60-80，默认70允许在较强趋势中入场，但规避极端过热状态。
  reason: v2试65仍0入场，恢复70；高值不抑制入场，保持
- name: atr_stop_multiplier
  default: 2.5
  range:
  - 1.5
  - 3.5
  type: float
  description: ATR动态止损倍数，止损距离=该倍数×ATR。单位：倍数。典型取值1.5-3.0，默认2.0在过滤市场噪音与保护趋势利润之间平衡。
  reason: vol_stop触发22598次(89%亏损)，放宽至2.5减频
- name: trail_stop_pct
  default: 0.08
  range:
  - 0.03
  - 0.18
  type: float
  description: 移动止损比例，从最高收盘价回撤该比例时触发。单位：小数。典型取值0.04-0.10，默认0.06适合10-30天波段，让利润充分发展但及时锁定。
  reason: v3触发6127次均亏-1903过深，收紧至0.08降均亏
- name: vol_breakout_threshold
  default: 0.4
  range:
  - 0.3
  - 1.5
  type: float
  description: 成交量突破倍数阈值，决定入场时的量能要求。单位：倍数。典型取值1.2-2.0，A股有效突破通常放量1.5倍以上，默认1.5平衡信号数量与质量。
  reason: 入场仍0，p25=0.70，降至0.4扩窗口
- name: max_industry_concentration
  default: 0.3
  range:
  - 0.15
  - 0.5
  type: float
  description: 行业暴露上限，限制同一行业总权重。单位：小数。典型取值0.20-0.40，默认0.30防止行业系统性风险过度集中，保障组合稳健。
  reason: 组合层参数，与入场/出场核心问题无关，保持
- name: target_holdings
  default: 8
  range:
  - 4
  - 15
  type: int
  description: 目标持仓股票数量，调仓时尽量维持。单位：只。典型取值6-12，默认8在分散与集中之间平衡，确保每只股票能获得足够权重。
  reason: 持仓数与max_single_weight=0.1匹配合理，保持
- name: rsi_overbought
  default: 75
  range:
  - 65
  - 85
  type: int
  description: RSI超买阈值，触发盈利减仓的条件之一。单位：数值。典型取值70-80，默认75略高于入场上限，减少过早止盈，保留头部利润。
  reason: 最佳出场信号(胜率100%均收+5870)，保持
- name: fixed_stop_loss_pct
  default: 0.1
  range:
  - 0.06
  - 0.2
  type: float
  description: 固定止损比例，单笔最大亏损限制。单位：小数（相对成本价）。典型取值0.05-0.10，默认0.08在容忍正常波动与保护本金间取得均衡。
  reason: v3触发746次均亏-4405过深，回退0.10降均亏
- name: add_position_weight_threshold
  default: 0.3
  range:
  - 0.2
  - 0.9
  type: float
  description: 加仓信号综合得分阈值（入场信号权重和），超过该值可将个股仓位加至上限。单位：比例。典型取值0.6-0.9，默认0.7要求信号共振明显才加满。
  reason: 入场仍0，趋势+rsi=0.5需0.3阈值即可解锁
- name: max_turnover_per_rebalance
  default: 0.5
  range:
  - 0.2
  - 0.8
  type: float
  description: 单次再平衡最大换手率，控制交易成本和冲击。单位：小数。典型取值0.30-0.70，默认0.50允许灵活调整但避免过度频繁换股。
  reason: 组合层参数，与入场恢复程度相关，保持
- name: rsi_entry_low
  default: 20
  range:
  - 15
  - 45
  type: int
  description: RSI入场下限，避免在极度超卖时入场。单位：数值。典型取值30-50，默认40确保短期动量已从低位回升，减少接飞刀风险。
  reason: 入场仍0，p25=37.9，降至20扩超卖窗口
- name: reduce_position_floor
  default: 0.03
  range:
  - 0.01
  - 0.06
  type: float
  description: 减仓后个股最低持仓权重，避免在震荡中彻底清仓丢失头寸。单位：小数（总资产比）。典型取值0.02-0.05，默认0.03保留微小仓位跟踪信号。
  reason: 分级减仓未启用，floor暂不生效，保持
- name: max_holding_days
  default: 25
  range:
  - 10
  - 60
  type: int
  description: 最大持仓交易日数，超时强制平仓。单位：交易日。典型取值15-40，默认25贴合中周期波段目标，防止被动转为长期套牢。
  reason: 触发16312次胜率84%(均收+1457)，良好保持
- name: reduce_position_weight_threshold
  default: 0.3
  range:
  - 0.1
  - 0.5
  type: float
  description: 减仓信号综合得分阈值（出场信号权重和），超过该值将个股仓位降至下限。单位：比例。典型取值0.2-0.4，默认0.3在趋势转弱时适度降仓。
  reason: 出场直接清仓未触发分级减仓，参数待验证，保持
- name: max_single_weight
  default: 0.1
  range:
  - 0.03
  - 0.2
  type: float
  description: 单只股票最大持仓权重，控制组合集中度风险。单位：小数。典型取值0.05-0.15，默认0.10与目标持仓8只匹配，实现适度分散。
  reason: 与target_holdings=8匹配，年化低不源于集中度问题
description: 基于Donchian通道突破+成交量放大+趋势与RSI过滤，配合多级止损的中周期波段策略。
universe: 沪深 300
holding_period: 10-30 个交易日
rebalance_freq: 每 5 个交易日强制再平衡
---

