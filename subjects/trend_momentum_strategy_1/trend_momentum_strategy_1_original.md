---
name: trend_momentum_strategy_1
targets:
  annual_return: 0.25
  win_rate: 0.48
  profit_loss_ratio: 3.2
  sharpe: 1.5
  max_drawdown: -0.18
  description: 多指标共振趋势策略，期望25%年化，胜率48%，盈亏比3.2，夏普1.5，最大回撤18%。
factors:
- name: ma_5
  description: 5日简单移动均线
  calculation: mean(close, 5)
- name: ma_20
  description: 20日简单移动均线
  calculation: mean(close, 20)
- name: ma_60
  description: 60日简单移动均线
  calculation: mean(close, 60)
- name: atr_14
  description: 14日平均真实波幅
  calculation: atr(high, low, close, 14)
- name: rsi_14
  description: 14日相对强弱指标
  calculation: 100 - 100 / (1 + mean(gain, 14) / mean(loss, 14))
- name: macd_line
  description: MACD快线（DIF）
  calculation: ema(close, 12) - ema(close, 26)
- name: macd_signal
  description: MACD慢线（DEA）
  calculation: ema(macd_line, 9)
- name: volume_ratio_20
  description: 20日成交量比率
  calculation: volume / mean(volume, 20)
- name: max_close_since_entry
  description: 持仓期间最高收盘价
  calculation: max(close, from_entry_to_now)
entry_signals:
- name: trend_momentum_entry
  weight: 1.0
  factors:
  - ma_5
  - ma_20
  - ma_60
  - macd_line
  - macd_signal
  - rsi_14
  - atr_14
  - volume_ratio_20
  direction: positive
  trigger: ma_5 > ma_20 AND ma_20 > ma_60 AND macd_line > macd_signal AND rsi_14 >
    {rsi_low} AND rsi_14 < {rsi_high} AND atr_14 / close > {atr_min} AND volume_ratio_20
    > {vol_min}
  logic: AND
exit_signals:
- name: trend_reversal
  weight: 0.3
  factors:
  - ma_5
  - ma_20
  direction: negative
  trigger: ma_5 < ma_20
  logic: AND
- name: fixed_stop
  weight: 0.25
  factors: []
  direction: negative
  trigger: current_price < entry_price * (1 - {fixed_stop_pct})
  logic: 单因子
- name: trailing_stop
  weight: 0.25
  factors:
  - max_close_since_entry
  direction: negative
  trigger: current_price < max_close_since_entry * (1 - {trailing_stop_pct})
  logic: 单因子
- name: time_stop
  weight: 0.1
  factors: []
  direction: negative
  trigger: holding_days >= {max_holding_days}
  logic: 单因子
- name: rsi_overbought_stop
  weight: 0.1
  factors:
  - rsi_14
  direction: negative
  trigger: rsi_14 > {rsi_overbought}
  logic: 单因子
position_weights:
  max_single_stock_weight: 0.1
  max_industry_concentration: 0.3
  target_holdings: 8
  max_turnover_per_rebalance: 0.5
  rebalance_freq_days: 5
params:
- name: rsi_low
  default: 40
  range:
  - 30
  - 50
  type: float
  description: RSI入场低阈值。RSI需高于此值以避免超卖陷阱，常设40。典型取值35-45。默认40，保证入场时有一定动能。
- name: rsi_high
  default: 70
  range:
  - 60
  - 80
  type: float
  description: RSI入场高阈值。RSI需低于此值以防止追高，常设70。典型取值65-75。默认70，避免在超买区进场。
- name: atr_min
  default: 0.02
  range:
  - 0.005
  - 0.05
  type: float
  description: 最小波动率阈值。ATR/收盘价需大于此值，确保股票波动足够，过滤横盘。单位小数。典型0.01-0.03。默认0.02。
- name: vol_min
  default: 1.5
  range:
  - 1.0
  - 3.0
  type: float
  description: 成交量放大倍数。当日成交量与20日均量之比需大于此值，确认资金介入。单位倍。典型1.2-2.0。默认1.5。
- name: fixed_stop_pct
  default: 0.08
  range:
  - 0.03
  - 0.15
  type: float
  description: 固定止损比例。当亏损超过此比例时强制平仓。单位小数。典型5%-10%。默认8%，平衡风险与容忍度。
- name: trailing_stop_pct
  default: 0.05
  range:
  - 0.02
  - 0.1
  type: float
  description: 移动止损回撤比例。从持仓最高点回落超过此比例时平仓，保护盈利。单位小数。典型3%-7%。默认5%。
- name: max_holding_days
  default: 30
  range:
  - 10
  - 60
  type: int
  description: 最大持仓天数。超过此天数将强制平仓，防止持仓过久。单位交易日。典型20-40。默认30，中周期合适。
- name: rsi_overbought
  default: 80
  range:
  - 70
  - 90
  type: float
  description: RSI超买出场阈值。当RSI高于此值时视为超买，触发止盈。单位数值。典型75-85。默认80。
- name: max_single_stock_weight
  default: 0.1
  range:
  - 0.03
  - 0.2
  type: float
  description: 单只股票最大持仓权重。控制单票集中度风险。单位小数。典型5%-15%。默认10%。
- name: max_industry_concentration
  default: 0.3
  range:
  - 0.1
  - 0.5
  type: float
  description: 单一行业最大持仓集中度上限。单位小数。典型20%-40%。默认30%。
- name: target_holdings
  default: 8
  range:
  - 5
  - 15
  type: int
  description: 目标持仓数量。组合持有股票只数，平衡分散与收益。单位只。典型5-12。默认8只。
- name: max_turnover_per_rebalance
  default: 0.5
  range:
  - 0.2
  - 0.8
  type: float
  description: 单次调仓最大换手率约束。控制换手成本。单位小数。典型0.3-0.6。默认0.5。
- name: rebalance_freq_days
  default: 5
  range:
  - 2
  - 10
  type: int
  description: 再平衡周期。每隔多少个交易日进行调仓。单位交易日。典型3-7。默认5。
- name: add_position_profit_threshold
  default: 0.1
  range:
  - 0.05
  - 0.2
  type: float
  description: 加仓盈利阈值。如果持仓盈利超过此值且信号持续，可增加仓位。单位小数。典型8%-15%。默认10%。
- name: reduce_position_risk_threshold
  default: 0.04
  range:
  - 0.02
  - 0.08
  type: float
  description: 减仓风险阈值。当ATR/收盘价超过此值时，风险上升，减仓一半。单位小数。典型0.03-0.06。默认0.04。
description: 多指标共振趋势策略：趋势排列+动量确认+波动过滤+量能验证+RSI区间优化
universe: 沪深300
holding_period: 10-30个交易日
rebalance_freq: 每5个交易日再平衡
test_universe:
- HS300
---

## 策略业务逻辑叙事

### 1. 策略思路 / edge 来源（含市场环境假设）
本策略立足于A股市场存在的中期趋势延续效应，捕捉由资金流入、事件驱动或基本面改善引发的持续性波段行情。核心edge在于多重技术指标的协同验证：均线排列确认趋势方向，MACD评估动量强度，ATR过滤低波动横盘，成交量放大确保资金参与，RSI区间避免极端超买或超卖陷阱。五个维度形成共振时，虚假突破的概率显著降低，从而获得较高的盈亏比。
市场环境假设：策略默认运行于非极端震荡环境；在明确的趋势市中（无论涨跌），均线排列和动量指标能有效筛选出具有延续性的个股。策略不依赖单一因子，而是通过多条件AND逻辑自然适应市场结构变化——当市场转入震荡或下跌时，信号自动稀疏，达到防御效果。

### 2. 牛 / 熊 / 震荡 3 环境处理
策略未内置显式的市场状态识别模型，而是通过参数化的阈值和多重过滤，在不同环境中表现出自适应行为：
- **牛市环境**：均线系统呈多头排列，大部分股票符合趋势条件，信号充足；策略以目标仓位满仓运行，移动止损（{trailing_stop_pct}）能够充分保护利润，让盈利奔跑。此时入场信号频繁，但成交量阈值（{vol_min}）和波动率阈值（{atr_min}）可过滤掉无量空涨的弱势股。
- **熊市环境**：均线空头排列，满足ma_5 > ma_20 > ma_60的个股锐减，信号极度稀少，策略天然处于轻仓或空仓状态，回撤可控。即使个别逆势品种触发入场，严格的固定止损（{fixed_stop_pct}）和收紧的波动要求也限制了单笔损失。此外，减仓阈值（{reduce_position_risk_threshold}）在波动急剧放大时进一步降低仓位，形成双重保护。
- **震荡环境**：均线反复缠绕，频繁出现虚假金叉。策略依靠ATR过滤（{atr_min}）和量能确认（{vol_min}）来削减无势震荡中的噪音信号；同时时间止损（{max_holding_days}）及时清除长期无方向波动的持仓，避免资金被无效占用。加仓阈值（{add_position_profit_threshold}）则确保只在已盈利且趋势维持的情况下才扩大暴露，避免在震荡中过度交易。
通过上述设计，策略在牛市中进攻锐利，在熊市中防守稳健，在震荡市中控制损耗，实现全周期相对稳定的风险收益特征。

### 3. 多信号逻辑关系
- **入场决策**：采用单一入口但为复合条件的“trend_momentum_entry”信号，逻辑为AND——即所有8个因子条件必须同时满足才会开仓。这种严格的共振要求确保了高胜率，尽管牺牲了部分交易频率。无其他辅助信号，避免了信号冲突或权重分配的主观性。
- **出场优先级**：共定义5个出场信号，按其权重和业务重要性排序执行：固定止损（权重0.25，保护本金安全）> 移动止损（权重0.25，保护浮盈）> 趋势反转（权重0.30，但作为趋势信号往往晚于止损触发，实际优先级让位于损失控制）> RSI超买止盈（权重0.10）> 时间止损（权重0.10）。系统在每根K线按此顺序依次检查，一旦某个信号触发立即平仓，不再评估后续信号，从而形成清晰的保护链。

### 4. 风险机制
- **与同类策略的差异**：大多数纯趋势策略仅依赖双均线或MACD，常在震荡市中反复止损；本策略通过融入ATR、量能和RSI区间过滤，显著降低了假突破率，并通过三层止损（固定、移动、时间）实现了全天候风控。
- **核心风控要点**：
  1) 组合层面：单票上限{max_single_stock_weight}、行业上限{max_industry_concentration}、目标持仓数{target_holdings}和再平衡频率{rebalance_freq_days}共同控制集中度风险和调仓冲击。
  2) 极端行情：如遇涨跌停无法执行出场，系统自动延期至下一可交易日，并在日志中记录信号被吞情况（由backtest框架实现）。
  3) 风险管理动态调整：当ATR/close突破{reduce_position_risk_threshold}时，减仓一半以应对波动激增；当持仓盈利超过{add_position_profit_threshold}且信号保持时，允许适度加仓以放大盈利。
- **特殊场景简化说明**：策略在设计上假设流动性充足，未专门针对ST股、新股首日等极端情况做特殊处理，这些标的将由投研池事先剔除。涨跌停造成的执行延迟属于市场固有风险，通过时间止损和固定止损可部分缓释。

### 5. NaN 处理
- **上市未满N日**：对于窗口期较长的因子（如ma_60、atr_14等），新股或次新股的早期数据不足会导致因子计算为NaN。系统对该部分股票当日不参与信号计算，但不从交易所剔除；待其上市交易日满足相应窗口后自动纳入。
- **长期停牌**：停牌期间因子值停止更新或出现缺失，策略停用该股信号。复牌当日由于均线等指标可能失真（跳空影响），需等复牌后N日（window期）数据回填充分后方可重新参与，防止错误入场。
- **涨跌停**：涨停时，入场信号正常评估（开盘判断），但若封单牢固可能实际无法买入，系统视作未成交；跌停时，出场信号被吞，延后次日处理。一字板（不含开板）视为极端涨跌停，直接跳过。
- **退市/ST风险**：虽然不作为因子，但系统可结合基础信息过滤，默认跳过这些标的，不纳入回测池，避免非正常交易带来的噪声。