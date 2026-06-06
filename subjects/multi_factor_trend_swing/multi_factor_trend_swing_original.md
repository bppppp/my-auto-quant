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
  max_single_weight: 0.12
  max_industry_concentration: 0.3
  target_holdings: 10
  max_turnover_per_rebalance: 0.4
  rebalance_freq_days: 5
params:
- name: atr_threshold
  default: 0.01
  range:
  - 0.005
  - 0.03
  type: float
  description: ATR波动率过滤阈值，单位：小数。含义：要求ATR/收盘价大于该阈值，典型取值0.01-0.03，默认0.01，理由：过滤低波动无效突破，0.01表示要求波动率至少1%。
- name: vol_threshold
  default: 1.3
  range:
  - 1.0
  - 2.5
  type: float
  description: 量能放大倍数阈值，单位：倍数。含义：当日成交量/20日均量须大于该值，典型取值1.0-2.5，默认1.3，理由：1.3倍均量确认资金介入。
- name: mom_threshold
  default: 0.05
  range:
  - 0.0
  - 0.2
  type: float
  description: 60日动量最低阈值，单位：小数。含义：过去60日涨幅须超过该值，典型取值0.0-0.2，默认0.05，理由：确保中期上升趋势存在。
- name: rsi_upper
  default: 70
  range:
  - 60
  - 85
  type: int
  description: RSI入场上限，单位：数值。含义：入场时RSI须低于此值，典型取值60-85，默认70，理由：避免在超买区域追高。
- name: fixed_stop_pct
  default: 0.08
  range:
  - 0.03
  - 0.2
  type: float
  description: 固定止损比例，单位：小数。含义：股价较入场价下跌超过该比例则止损，典型取值0.03-0.20，默认0.08，理由：平衡最大损失容忍度与正常波动。
- name: trailing_stop_pct
  default: 0.05
  range:
  - 0.02
  - 0.15
  type: float
  description: 移动止损比例，单位：小数。含义：从持仓最高价回落超过该比例则止盈/止损，典型取值0.02-0.15，默认0.05，理由：保护浮盈同时避免过早离场。
- name: max_holding_days
  default: 30
  range:
  - 10
  - 60
  type: int
  description: 最大持仓天数，单位：交易日。含义：持仓达到该天数后强制出场，典型取值10-60，默认30，理由：约1.5个月，符合中周期波段特征。
- name: rsi_overbought
  default: 75
  range:
  - 70
  - 90
  type: int
  description: RSI超买出场阈值，单位：数值。含义：RSI超过此值触发超买出场，典型取值70-90，默认75，理由：短期过热信号，及时止盈。
- name: max_single_weight
  default: 0.12
  range:
  - 0.05
  - 0.2
  type: float
  description: 单票最大权重，单位：小数。含义：单只股票占组合权重上限，典型取值0.05-0.20，默认0.12，理由：分散风险，避免单票过度集中。
- name: max_industry_concentration
  default: 0.3
  range:
  - 0.2
  - 0.5
  type: float
  description: 行业集中度上限，单位：小数。含义：单一行业权重占比上限，典型取值0.20-0.50，默认0.30，理由：控制行业风险暴露。
- name: target_holdings
  default: 10
  range:
  - 5
  - 20
  type: int
  description: 目标持仓数量，单位：只。含义：组合中持有的股票数量目标，典型取值5-20，默认10，理由：平衡分散度与持仓集中度，便于管理。
- name: max_turnover_per_rebalance
  default: 0.4
  range:
  - 0.2
  - 0.8
  type: float
  description: 单次再平衡最大换手率，单位：小数。含义：再平衡时买入卖出合计占组合的比例上限，典型取值0.20-0.80，默认0.40，理由：控制交易成本和冲击。
- name: rebalance_freq_days
  default: 5
  range:
  - 1
  - 10
  type: int
  description: 再平衡频率，单位：交易日。含义：每隔多少交易日进行一次组合再平衡，典型取值1-10，默认5，理由：每周再平衡，平衡时效性与交易成本。
description: 基于多因子（均线趋势、ATR波动、量能、动量、RSI）过滤的中期波段策略。目标年化22%，胜率52%，盈亏比2.9，夏普1.35，回撤12%。
universe: 沪深300
holding_period: 15-30个交易日
rebalance_freq: 每5个交易日强制再平衡
---

## 策略业务逻辑叙事

### 1. 策略思路 / edge来源
本策略专注于A股沪深300成分股的中期波段机会，核心edge源于多维度信号过滤带来的高胜率和高盈亏比。A股市场由于投资者结构、政策驱动等因素，中级趋势一旦形成，往往延续数周甚至数月，存在明显的趋势惯性。策略通过均线多头排列识别趋势方向，结合ATR波动率扩张和成交量放大确认突破有效性，利用中期动量过滤假突破，同时以RSI超买过滤防止追高。多信号共振大幅降低了假信号概率，严格的止损体系（固定止损、移动止损、时间止损）则控制了下行风险，从而实现较高的收益回撤比。

### 2. 市场环境假设
策略假设沪深300成分股存在可交易的中期趋势（2-6周），这些趋势通常由基本面变化、资金流动或政策催化驱动，流动性较好，冲击成本低。策略在趋势明显的牛熊市中表现优异，在纯粹无趋势的窄幅震荡市中，均线频繁交叉会导致信号质量下降。策略通过参数调整应对不同市况，无需实时判断市场状态。

### 3. 牛 / 熊 / 震荡 3 环境处理
策略设计具备在三种典型市场环境中的自适应能力，所有关键阈值均已参数化，用户可根据市场状况调整参数集，而非依赖实时识别：
- **牛市**：可放宽入场门槛（降低{atr_threshold}、{vol_threshold}，提高{mom_threshold}），延长持仓周期（提高{max_holding_days}），并放大移动止损空间（提高{trailing_stop_pct}），同时增加持仓数量（{target_holdings}）和单票权重（{max_single_weight}），以充分享受趋势发展。
- **熊市**：收紧风控，提高入场标准（提高{atr_threshold}、{vol_threshold}，降低{mom_threshold}），缩短持仓时间（降低{max_holding_days}），收紧止损（降低{fixed_stop_pct}、{trailing_stop_pct}），降低仓位（减少{target_holdings}和{max_single_weight}），以保住本金为主。
- **震荡市**：采用中性参数，{max_holding_days}适中，{trailing_stop_pct}较紧，通过较低{vol_threshold}和{rsi_upper}过滤频繁的假信号，降低换手频率（调整{rebalance_freq_days}），避免频繁交易损耗。

### 4. 多信号逻辑关系
入场采用多因子加权机制，各信号权重分配依据其逻辑重要性和历史经验：
- **趋势强度（trend_strength，0.35）**：均线多头排列是最稳定和可靠的中期趋势信号，赋予最高权重。
- **波动率扩张（atr_filter，0.20）**：波动率放大常伴随方向性突破，是有效的确认信号。
- **成交量确认（volume_confirm，0.15）**与**动量过滤（momentum_filter，0.15）**：量能验证资金介入，中期动量确保趋势已启动，二者共同巩固信号。
- **RSI过滤（rsi_filter，0.15）**：逆向指标，防止在超买区追高，提高入场后上涨空间。
出场优先级严格排序：固定止损（硬性损失控制）→ 移动止损（保护浮动利润）→ 趋势反转（均线死叉）→ RSI超买（短期过热）→ 时间止损（持仓周期过长）。同一时间触发多个信号时，按优先级执行，避免相互干扰。
- **加减仓**：本策略**不进行**加仓 / 减仓操作（spec.params 段无 `add_position_weight_threshold` / `reduce_position_weight_threshold` / `reduce_position_floor` 字段），仓位由 entry_score 排名 + `target_holdings` 决定，不做主动加减仓。

### 5. 风险机制
- **熊市风控**：通过调整参数实现整体收缩，已在第3节详述。当策略连续回撤达到外部风控线时，可整体暂停或降低仓位，但策略内部已通过固定止损确保单笔风险可控。
- **涨跌停挤不出场**：当出场信号触发日对应股票涨跌停无法交易时，该出场信号被吞，但系统会记录该事件，不将其视为已实现收益。下一交易日开盘后若条件仍满足则继续执行，杜绝虚假回测收益。
- **早期数据NaN处理（A股硬约束）**：
  - **上市未满N日**：因子计算窗口期（如ma_60需要60日）不足导致因子值为NaN时，该股票当日不参与入场信号计算，但不被剔除股票池，待满足窗口后自然纳入。
  - **长期停牌**：停牌期间行情不变，因子值停滞。复牌后需等待数据回填足够时长（至少达到因子最大窗口期，如60个交易日）后，才重新参与信号计算，避免失真数据。
  - **涨跌停日**：入场信号可正常基于开盘前数据判断并生效（允许在非涨跌停时买入）；但出场信号若当日涨跌停无法卖出则被吞，不产生实际成交。
  - **一字板 / 退市**：一字板股票默认跳过不参与交易；退市股票自动移除，不纳入回测。
- **优先级链**：出场按优先级顺序执行，确保损失控制优先于盈利保护，避免多个信号冲突时混乱。

### 6. 与其他策略区别
本策略区别于单纯的均线交叉或突破策略，通过融合多维度信号（趋势、波动、量能、动量、超买）显著降低噪音，提高信号质量；区别于长期趋势跟踪策略，专注于中周期（2-6周）波段，换手适中，适应A股T+1和涨跌停制度；区别于高频算法，不依赖日内数据，对滑点和流动性冲击不敏感，实盘可行性更高。