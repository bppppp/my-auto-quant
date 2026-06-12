---
name: trend_breakout_atr_rsi
name: trend_breakout_atr_rsi
targets:
  annual_return: 0.25
  win_rate: 0.47
  profit_loss_ratio: 3.3
  sharpe: 1.35
  max_drawdown: -0.18
  description: 双均线趋势+ATR波动扩张+量能确认+RSI过滤，期望年化25%、胜率47%、盈亏比3.3、夏普1.35、最大回撤18%。
factors:
- name: ma_10
  description: 10日简单移动平均线，反映短期趋势
  calculation: mean(close, 10)
- name: ma_50
  description: 50日简单移动平均线，反映中期趋势
  calculation: mean(close, 50)
- name: atr_14
  description: 14日平均真实波幅，衡量波动率
  calculation: atr(high, low, close, 14)
- name: volume_ratio_20
  description: 当日成交量与20日均量之比，衡量量能爆发
  calculation: volume / mean(volume, 20)
- name: rsi_14
  description: 14日相对强弱指标，识别超买超卖
  calculation: 100 - 100 / (1 + mean(gain, 14) / mean(loss, 14))
- name: highest_close_since_entry
  description: 入场后最高收盘价，用于移动止损
  calculation: rolling_max(close, days_since_entry)
entry_signals:
- name: ma_trend
  weight: 0.35
  factors:
  - ma_10
  - ma_50
  direction: positive
  trigger: ma_10 > ma_50
  logic: AND
- name: atr_expand
  weight: 0.25
  factors:
  - atr_14
  direction: positive
  trigger: atr_14 / close > {atr_threshold_pct}
  logic: 单因子
- name: volume_confirm
  weight: 0.25
  factors:
  - volume_ratio_20
  direction: positive
  trigger: volume_ratio_20 > {volume_breakout_ratio}
  logic: 单因子
- name: rsi_filter
  weight: 0.15
  factors:
  - rsi_14
  direction: positive
  trigger: rsi_14 < {rsi_overbought}
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
  factors:
  - highest_close_since_entry
  direction: negative
  trigger: current_price < highest_close_since_entry * (1 - {trailing_stop_pct})
  logic: 单因子
- name: time_stop
  weight: 0.2
  factors: []
  direction: negative
  trigger: holding_days >= {max_holding_days}
  logic: 单因子
- name: ma_death_cross
  weight: 0.2
  factors:
  - ma_10
  - ma_50
  direction: negative
  trigger: ma_10 < ma_50
  logic: AND
position_weights:
  max_single_weight: 0.1
  max_industry_concentration: 0.3
  target_holdings: 8
  max_turnover_per_rebalance: 0.5
  rebalance_freq_days: 5
params:
- name: atr_threshold_pct
  default: 0.015
  range:
  - 0.005
  - 0.05
  type: float
  description: ATR波动率最小阈值（单位：小数）。含义：要求当日ATR/收盘价大于该值，确保波动扩张。典型取值：0.01~0.03。默认0.015适合中度活跃市场，避免低波无趋势品种。
- name: volume_breakout_ratio
  default: 1.5
  range:
  - 1.0
  - 3.0
  type: float
  description: 成交量突破倍数（单位：倍数）。含义：当日成交量需超过20日均量的该倍数才视为放量。典型取值：1.3~2.0。默认1.5平衡确认强度与信号频率。
- name: rsi_overbought
  default: 70
  range:
  - 60
  - 85
  type: float
  description: RSI超买阈值（单位：0-100）。含义：RSI低于该值时允许入场，避免在极度超买区域追高。典型取值：65~80。默认70为经典超买线。
- name: fixed_stop_pct
  default: 0.07
  range:
  - 0.03
  - 0.15
  type: float
  description: 固定止损比例（单位：小数）。含义：现价低于入场价的该比例则无条件止损。典型取值：0.05~0.10。默认0.07控制单笔最大亏损在合理范围。
- name: trailing_stop_pct
  default: 0.05
  range:
  - 0.02
  - 0.12
  type: float
  description: 移动止损回撤比例（单位：小数）。含义：现价低于持仓期间最高收盘价的该比例则止盈出场。典型取值：0.03~0.08。默认0.05保护浮盈并让趋势充分发展。
- name: max_holding_days
  default: 30
  range:
  - 10
  - 60
  type: int
  description: 最大持仓天数（单位：交易日）。含义：持仓超过该天数则强制卖出，避免资金长期沉淀。典型取值：15~45。默认30天适应中周期波段节奏。
- name: max_single_weight
  default: 0.1
  range:
  - 0.03
  - 0.2
  type: float
  description: 单票最大权重（单位：小数）。含义：单个股票占组合的最大仓位比例。典型取值：0.05~0.15。默认0.10分散风险，避免个股黑天鹅冲击。
- name: max_industry_concentration
  default: 0.3
  range:
  - 0.1
  - 0.5
  type: float
  description: 行业集中度上限（单位：小数）。含义：同一行业持仓总权重不得超过该值。典型取值：0.20~0.40。默认0.30防止行业系统性风险过度暴露。
- name: target_holdings
  default: 8
  range:
  - 3
  - 20
  type: int
  description: 目标持仓只数（单位：只）。含义：组合理想持股数量上限。典型取值：5~15。默认8只平衡集中度与分散度，与单票权重配合。
- name: max_turnover_per_rebalance
  default: 0.5
  range:
  - 0.2
  - 1.0
  type: float
  description: 再平衡最大换手率（单位：小数）。含义：每次调仓允许的佣金成本上限，控制换手率。典型取值：0.30~0.70。默认0.50保障策略响应速度与成本可控。
- name: rebalance_freq_days
  default: 5
  range:
  - 1
  - 20
  type: int
  description: 调仓频率（单位：交易日）。含义：每隔该天数强制再平衡仓位。典型取值：3~10。默认5天，适应中周期时间框架。
description: 双均线趋势跟踪 + ATR波动率扩张 + 成交量确认 + RSI超买过滤，辅以固定/移动/时间三重止损与死叉出场
universe: 沪深300
holding_period: 10-30 个交易日
rebalance_freq: 每 5 个交易日强制再平衡
test_universe:
- HS300
---

## 策略业务逻辑叙事

### 1. 策略思路 / edge 来源（含市场环境假设）
本策略基于双重趋势、波动率扩张、量能确认和情绪过滤四因子共振，捕捉A股中周期波段的主升浪。A股市场存在明显的中期动量效应和板块轮动特征，单因子趋势策略在震荡市中假信号频繁，回撤较大。通过添加ATR波动率扩张条件，仅参与波动率放大时段，规避缩量盘整；成交量确认确保有增量资金推动，提高突破有效性；RSI超买过滤避免在情绪高潮后追涨。edge来源于多因子交叉验证，将趋势跟踪的胜率与盈亏比同时提升。
市场环境假设：策略在中高流动性、中等波动度的环境下表现最优，但不依赖市场状态实时识别，而是通过参数暴露度设计使策略在牛市、熊市、震荡市中均有内在保护。

### 2. 牛 / 熊 / 震荡 3 环境处理（所有阈值 param 化）
- **牛市**：趋势延续性强，入场信号高频触发。本策略在牛市中通过维持标准参数（如{atr_threshold_pct}默认值0.015、{volume_breakout_ratio}1.5）即可捕捉大多数波段，同时移动止损{trailing_stop_pct}保持0.05让利润奔跑。持仓可趋向上限{max_holding_days}天，降低不必要的调仓。
- **熊市**：下跌趋势主导，反弹常为假信号。策略通过提高入场门槛——例如上调{volume_breakout_ratio}至2.0以上、收紧{atr_threshold_pct}至0.03，并缩短持仓周期{max_holding_days}至15天，同时将固定止损{fixed_stop_pct}降至0.05，以实现快速认错。这些阈值均可通过参数寻优在不同熊市阶段单独调整。
- **震荡市**：上下空间有限，趋势信号易反复。策略使用时间止损{max_holding_days}缩短至10~15天快速退出，并提高RSI过滤{ rsi_overbought }调低至65，减少在区间上沿入场。仓位管理上，可降低{target_holdings}至3~5只，控制总风险暴露。所有差异化处理均为参数调优预留，无需实时市场分类。

### 3. 多信号逻辑关系
- **入场时机**：采用加权评分制，要求至少一个趋势类信号（ma_trend）与一个确认类信号（atr_expand、volume_confirm、rsi_filter）同时生效。具体为：4个入场信号按权重（0.35,0.25,0.25,0.15）贡献评分，当加权总分超过0.5且趋势信号本身为真时生成买入指令。若仅有趋势信号而缺乏波动或量能支撑，则放弃入场，显著降低假突破风险。
- **出场优先级**：遍历出场信号时按固定止损 → 移动止损 → 时间止损 → 死叉离场的顺序执行，优先级最高者先触发，确保资金安全优先于利润保护。固定止损{fixed_stop_pct}为硬性风控，任何情况下触发即离场；移动止损{trailing_stop_pct}在浮盈后动态上移，保留大部分利润；时间止损{max_holding_days}防止长期占用资金；死叉离场作为趋势终结的确认，在未触发前三种止损时执行。

### 4. 风险机制
- **与竞品差异**：相比单纯双均线策略，本策略引入波动率、量能和RSI三重过滤，大幅降低在缩量窄幅震荡中的反复磨损，同时三重止损体系提供更精细的资金管理。相比纯动量策略，RSI过滤规避了高位追进的风险。
- **核心风控要点**：
  1. 固定止损控制单笔最大亏损不超过本金的{fixed_stop_pct}；
  2. 移动止损在盈利后逐步收紧，锁定收益；
  3. 时间止损避免“僵尸持仓”；
  4. 仓位管理：单票上限{max_single_weight}、行业集中度{max_industry_concentration}、目标持股数{target_holdings}共同作用，分散非系统性风险；
  5. 再平衡换手上限{max_turnover_per_rebalance}防止成本侵蚀利润；
  6. 特殊场景：涨跌停时所有出场信号可能无法执行（被吞），但系统会如实记录，不强制虚构成交；涨停板买入在默认规则下自动跳过，防止回测偏差。

### 5. NaN 处理（A 股硬约束）
本策略严格遵循A股市场硬约束，针对数据缺失情况设有4类处理规则：
- **上市未满N日**：若股票上市天数小于所需因子最大窗口（如ma_50需50天，atr_14需14天等），对应因子输出NaN，该股票当日不参与任何信号计算，但不从选股池剔除，待窗口满足后自动纳入。
- **长期停牌**：停牌期间成交量、价格均无变化，因子可能为NaN或滞值。策略在停牌日自动跳过该股票的信号更新，复牌后需待因子窗口重新填充（如ma_10需10个有效行情日）才重新参与评分，避免利用虚假信号。
- **涨跌停板**：当日触及涨跌停板时，所有出场信号（止损/止盈/死叉）可能无成交，系统记录“信号被吞”；入场信号若触及涨停板，默认无法买入，视为笔无效交易。回测中不假设能在板上成交，从而提供真实的模拟效果。
- **一字板（涨停/跌停至收盘）**：视为涨跌停板的极端情况，全天无任何成交机会，处理同涨跌停，跳过该日的所有入场或出场动作，确保回测与现实交易一致。
通过以上机制，策略在数据层面可安全落地，避免因A股特有制度导致的失真。