---
name: dma_breakout_vol_rsi_1
targets:
  annual_return: 0.26
  win_rate: 0.45
  profit_loss_ratio: 3.5
  sharpe: 1.5
  max_drawdown: -0.2
  description: 预期年化收益26%，胜率45%，盈亏比3.5，夏普1.5，最大回撤-20%。通过多重信号过滤和分层止损实现收益风险平衡。
factors:
- name: ma_5
  description: 5日简单移动平均线，反映短期价格趋势
  calculation: mean(close, 5)
- name: ma_20
  description: 20日简单移动平均线，代表中期趋势方向
  calculation: mean(close, 20)
- name: high_20
  description: 过去20个交易日的最高收盘价，用于突破确认和移动止损参考
  calculation: max(close, 20)
- name: rsi_14
  description: 14日相对强弱指数，衡量超买超卖状态
  calculation: 100 - 100 / (1 + mean(gain, 14) / mean(loss, 14))，其中gain=max(close-close_prev,0)，loss=max(close_prev-close,0)
- name: vol_ratio
  description: 当日成交量与20日均量之比，反映成交活跃度
  calculation: volume / mean(volume, 20)
- name: atr_14
  description: 14日平均真实波幅，衡量价格波动性
  calculation: atr(high, low, close, 14)
entry_signals:
- name: ma_trend_bull
  weight: 0.3
  factors:
  - ma_5
  - ma_20
  direction: positive
  trigger: ma_5 > ma_20 AND close > ma_20
  logic: AND
- name: price_breakout
  weight: 0.25
  factors:
  - high_20
  direction: positive
  trigger: close > high_20
  logic: 单因子
- name: volume_surge
  weight: 0.15
  factors:
  - vol_ratio
  direction: positive
  trigger: vol_ratio > {vol_breakout_ratio}
  logic: 单因子
- name: rsi_healthy
  weight: 0.15
  factors:
  - rsi_14
  direction: positive
  trigger: rsi_14 > {rsi_min} AND rsi_14 < {rsi_max}
  logic: AND
- name: volatility_active
  weight: 0.15
  factors:
  - atr_14
  direction: positive
  trigger: atr_14 / close > {min_atr_ratio}
  logic: 单因子
exit_signals:
- name: ma_trend_bear
  weight: 0.3
  factors:
  - ma_5
  - ma_20
  direction: negative
  trigger: ma_5 < ma_20
  logic: AND
- name: trailing_stop
  weight: 0.25
  factors:
  - high_20
  direction: negative
  trigger: current_price < high_20 * (1 - {trail_stop_pct})
  logic: 单因子
- name: fixed_stop
  weight: 0.25
  factors: []
  direction: negative
  trigger: current_price < entry_price * (1 - {fixed_stop_pct})
  logic: 单因子
- name: time_stop
  weight: 0.2
  factors: []
  direction: negative
  trigger: holding_days >= {max_hold_days}
  logic: 单因子
position_weights:
  max_single_weight: 0.1
  max_industry_concentration: 0.3
  target_holdings: 10
  max_turnover_per_rebalance: 0.4
  rebalance_freq_days: 5
params:
- name: vol_breakout_ratio
  default: 1.5
  range:
  - 1.0
  - 3.0
  type: float
  description: 成交量放大倍数阈值。单位：倍数。典型取值1.2-2.0，默认1.5表示要求当日成交量至少为20日均量的1.5倍，用于确认资金参与。
- name: rsi_min
  default: 30
  range:
  - 20
  - 50
  type: int
  description: RSI下界阈值。单位：数值（0-100）。典型取值25-40，默认30，确保入场时非严重超卖，避免弱势股。
- name: rsi_max
  default: 70
  range:
  - 60
  - 80
  type: int
  description: RSI上界阈值。单位：数值（0-100）。典型取值65-75，默认70，避免在RSI超买时追高，控制入场成本。
- name: min_atr_ratio
  default: 0.015
  range:
  - 0.005
  - 0.05
  type: float
  description: 最小波动率阈值。单位：小数（相对于价格）。典型取值0.008-0.03，默认0.015表示要求ATR至少占价格的1.5%，过滤交投清淡的股票。
- name: trail_stop_pct
  default: 0.06
  range:
  - 0.02
  - 0.15
  type: float
  description: 移动止损回落比例。单位：小数（百分比）。典型取值0.03-0.10，默认0.06即从20日高点回落6%时止损，保护浮盈。
- name: fixed_stop_pct
  default: 0.08
  range:
  - 0.05
  - 0.2
  type: float
  description: 固定止损比例。单位：小数（百分比）。典型取值0.05-0.15，默认0.08即从入场价下跌8%无条件止损，控制单笔最大亏损。
- name: max_hold_days
  default: 30
  range:
  - 15
  - 60
  type: int
  description: 最大持有交易日数。单位：天。典型取值15-45，默认30，持有超过该天数未触发其他出场则强制平仓，防止资金占用过久。
- name: max_single_weight
  default: 0.1
  range:
  - 0.03
  - 0.2
  type: float
  description: 单只股票最大仓位占比。单位：小数（占组合比例）。典型取值0.05-0.15，默认0.10，限制个股权重以分散风险。
- name: max_industry_concentration
  default: 0.3
  range:
  - 0.1
  - 0.5
  type: float
  description: 行业最大集中度。单位：小数（占组合比例）。典型取值0.20-0.40，默认0.30，防止单一行业过度暴露。
- name: target_holdings
  default: 10
  range:
  - 5
  - 20
  type: int
  description: 目标持股数量。单位：只。典型取值8-15，默认10，平衡组合的分散与集中度。
- name: max_turnover_per_rebalance
  default: 0.4
  range:
  - 0.2
  - 0.8
  type: float
  description: 单次调仓最大换手率。单位：小数（占组合比例）。典型取值0.30-0.60，默认0.40，控制交易成本和市场冲击。
- name: rebalance_freq_days
  default: 5
  range:
  - 1
  - 10
  type: int
  description: 调仓间隔交易日数。单位：天。典型取值3-10，默认5即每周调仓一次，减少过度交易。
description: 基于双均线多头趋势、价格突破20日高点、成交量放大、RSI过滤和波动率过滤的中周期波段策略。采用多重止损控制风险。
universe: 沪深300
holding_period: 15-30个交易日
rebalance_freq: 每5个交易日强制再平衡
test_universe:
- HS300
---

## 策略业务逻辑叙事

### 1. 策略思路 / edge 来源（含市场环境假设）
本策略捕捉A股市场中由趋势延续和动量效应驱动的中周期波段机会。核心假设为市场存在非完全有效，上升趋势一旦形成会持续数周。通过均线多头排列（ma_5 > ma_20且close > ma_20）确定趋势方向，价格突破20日高点（close > high_20）确认趋势强度，成交量放大（vol_ratio > {vol_breakout_ratio}）验证资金认可，RSI处于健康区间（{rsi_min} < rsi_14 < {rsi_max}）避免极端价位，波动率过滤（atr_14 / close > {min_atr_ratio}）确保交投活跃。多重信号共振显著降低单一指标的误判率，edge来源于对趋势质量的多维度评估。市场环境假设：沪深300成分股流动性好，机构参与度高，趋势信号可靠性较强；A股存在明显的板块轮动和动量效应，中周期波段策略能够捕捉到这些机会。

### 2. 牛 / 熊 / 震荡 3 环境处理（**所有阈值 param 化**）
- **牛市环境**：均线多头排列信号持续出现，入场机会增多，策略将保持较高仓位。在强烈的上升趋势中，固定止损和移动止损的默认值（{fixed_stop_pct}、{trail_stop_pct}）提供了适度的回调容忍，允许利润充分增长，不会被小幅波动轻易震出。
- **熊市环境**：严格的入场条件（需要均线多头和突破20日高点）在熊市中几乎不可能同时满足，因此策略将自动空仓或极轻仓，有效规避系统性下跌风险。即使偶有反弹引发的信号，固定止损（{fixed_stop_pct}）和时间止损（{max_hold_days}）也能快速截断亏损。
- **震荡市环境**：价格反复穿越均线和前期高点，容易产生假突破信号。本策略通过RSI过滤（{rsi_min}、{rsi_max}）排除超买/超卖区域的噪声，并结合成交量放大要求（{vol_breakout_ratio}）筛选出真正有资金推动的行情，同时时间止损（{max_hold_days}）及时了结陷入震荡的持仓，避免被长期消耗。整体设计使得策略在三种环境中均能自我调节，无需主观判断市场状态。

### 3. 多信号逻辑关系
- **入场时机**：采用严格的AND逻辑，要求5个维度的信号同时为真——均线趋势、价格突破、成交量、RSI健康、波动率活跃。每个信号拥有权重（总和1.0），实际入场需总分达到1.0，即全部满足。这种高门槛设计确保了高胜率（目标45%以上），但也牺牲了部分交易机会，适合追求高确定性的投资者。
- **出场时机**：采用OR逻辑，任意出场条件触发即平仓。出场优先级顺序为：固定止损（保护本金）> 移动止损（锁定浮盈）> 时间止损（防止僵持）> 均线死叉（趋势反转确认）。当多个信号同时触发时，系统按此优先级执行，确保最先响应最紧急的风险控制需求。例如，若持仓同时满足固定止损和均线死叉，将优先执行固定止损。

### 4. 风险机制
- 与普通双均线策略相比，本策略独特之处在于多重过滤和分层止损体系，有效降低了虚假突破和大幅回撤的风险。核心风控包括：单票最大仓位限制（{max_single_weight}）、行业集中度控制（{max_industry_concentration}）、调仓换手率限制（{max_turnover_per_rebalance}）以及定期再平衡（{rebalance_freq_days}）。固定止损和移动止损分别从本金和浮盈两个维度保护账户，时间止损防止无意义的资金占用。
- 特殊行情处理：涨跌停板可能导致出场信号延迟执行，回测引擎会记录此类事件并在可交易时执行；一字板视为不可交易状态，自动跳过；这些机制在运行端实现，确保策略在极端行情下的稳健性。

### 5. NaN 处理
- 上市未满20日（或因子计算所需回溯期）的股票，部分因子如ma_20、high_20、atr_14等为NaN，此类股票当日不参与信号计算，但保留在股票池中，待数据充足后自动纳入。
- 长期停牌日：无交易数据，跳过，不产生任何信号，防止基于陈旧数据的误判。
- 涨跌停日：入场信号正常评估（因可能以涨跌停价撮合），但若为开盘即封板且无成交量，则视为不可交易；出场信号若因涨跌停无法执行，将被记录并在后续交易日处理。
- 一字板（跳空涨跌停且无成交）：视为流动性缺失，当日不参与任何信号，避免滑点和无法成交的风险。
- 退市或ST证券：默认不纳入股票池，保障标的健康和可交易性。