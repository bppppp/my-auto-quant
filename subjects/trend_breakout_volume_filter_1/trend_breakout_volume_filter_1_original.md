---
name: trend_breakout_volume_filter_1
targets:
  annual_return: 0.25
  win_rate: 0.5
  profit_loss_ratio: 3.2
  sharpe: 1.4
  max_drawdown: -0.15
  description: 策略目标：年化25%，胜率50%，盈亏比3.2，夏普1.4，最大回撤-15%。基于趋势多空头排列、RSI非超买、突破前高、成交量放大和波动率过滤，结合严格止损止盈。
factors:
- name: ma_short
  description: 短期均线，反映近{N}日短期趋势
  calculation: mean(close, {ma_short_window})
- name: ma_mid
  description: 中期均线，反映近{N}日中期趋势方向
  calculation: mean(close, {ma_mid_window})
- name: ma_long
  description: 长期均线，反映近{N}日长期趋势背景
  calculation: mean(close, {ma_long_window})
- name: rsi
  description: 相对强弱指标，衡量多空力量对比
  calculation: 100 - 100 / (1 + mean(gain, {rsi_period}) / mean(loss, {rsi_period}))
- name: donchian_high
  description: N日最高价，用于突破确认
  calculation: max(close, {donchian_window})
- name: atr
  description: 平均真实波幅，衡量波动性
  calculation: atr(close, {atr_period})
- name: volume_ratio
  description: 量比，当日成交量与{N}日均量的比值
  calculation: volume / mean(volume, {volume_window})
- name: highest_close_since_entry
  description: 持仓期间最高收盘价，用于移动止损
  calculation: max(close_since_entry)
entry_signals:
- name: trend_breakout
  weight: 0.6
  factors:
  - ma_short
  - ma_mid
  - ma_long
  - rsi
  - donchian_high
  - atr
  direction: positive
  trigger: ma_short > ma_mid AND ma_mid > ma_long AND rsi > {rsi_entry_threshold}
    AND rsi < {rsi_overbought} AND close > donchian_high AND atr / close > {atr_min_threshold}
  logic: AND
- name: volume_confirm
  weight: 0.4
  factors:
  - volume_ratio
  direction: positive
  trigger: volume_ratio > {volume_breakout_ratio}
  logic: 单因子
exit_signals:
- name: fixed_stop
  weight: 0.35
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
- name: profit_take
  weight: 0.25
  factors: []
  direction: negative
  trigger: current_price > entry_price * (1 + {profit_take_pct})
  logic: 单因子
- name: time_stop
  weight: 0.1
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
- name: ma_short_window
  default: 10
  range:
  - 5
  - 20
  type: int
  description: 短期均线计算窗口（单位：交易日）。典型取值5、10、20。默认10基于A股短期波动节奏，捕捉近两周趋势。
- name: ma_mid_window
  default: 30
  range:
  - 20
  - 60
  type: int
  description: 中期均线计算窗口（单位：交易日）。典型取值20、30、60。默认30代表一个半月趋势，过滤短期噪音。
- name: ma_long_window
  default: 60
  range:
  - 40
  - 120
  type: int
  description: 长期均线计算窗口（单位：交易日）。典型取值60、120。默认60识别季线级别趋势方向。
- name: rsi_period
  default: 14
  range:
  - 5
  - 30
  type: int
  description: RSI计算周期（单位：交易日）。典型取值7、14、21。默认14为经典参数，反应中期多空力量均衡性。
- name: rsi_entry_threshold
  default: 40
  range:
  - 30
  - 50
  type: float
  description: RSI入场下限（0-100数值）。典型取值40。默认40确保买入时价格未处于严重超卖，但也不过高追入，留有上行空间。
- name: rsi_overbought
  default: 70
  range:
  - 60
  - 80
  type: float
  description: RSI超买上限（0-100数值）。典型取值70。默认70避免在超买区域入场，防止短期回调风险。
- name: volume_window
  default: 20
  range:
  - 10
  - 40
  type: int
  description: 成交量均值计算窗口（单位：交易日）。典型取值10、20。默认20反映近一个月的平均交易量水平。
- name: volume_breakout_ratio
  default: 1.5
  range:
  - 1.2
  - 3.0
  type: float
  description: 成交量放大倍数（单位：倍）。典型取值1.5、2.0。默认1.5表示放量50%以上视为资金介入，过滤地量伪信号。
- name: atr_period
  default: 14
  range:
  - 10
  - 30
  type: int
  description: ATR计算周期（单位：交易日）。典型取值14。用于衡量市场波动率，辅助出场调整及波动率过滤。
- name: atr_min_threshold
  default: 0.02
  range:
  - 0.005
  - 0.05
  type: float
  description: ATR/收盘价最低阈值（单位：小数）。典型取值0.01-0.03。默认0.02确保市场有足够波动性时才开仓，避免死寂行情频繁损耗。
- name: donchian_window
  default: 20
  range:
  - 10
  - 40
  type: int
  description: 唐奇安通道突破窗口（单位：交易日）。典型取值20。默认20代表一个月高点，有效突破确认趋势。
- name: fixed_stop_pct
  default: 0.07
  range:
  - 0.03
  - 0.15
  type: float
  description: 固定止损比例（单位：小数值，相对入场价）。典型取值0.05-0.10。默认0.07基于A股个股波动率，控制单笔最大亏损在7%。
- name: trailing_stop_pct
  default: 0.05
  range:
  - 0.02
  - 0.1
  type: float
  description: 移动止损回撤比例（单位：小数值，相对持仓期间最高价）。典型取值0.05。默认5%平衡利润保护和避免被正常波动震出。
- name: profit_take_pct
  default: 0.2
  range:
  - 0.1
  - 0.4
  type: float
  description: 目标止盈比例（单位：小数值，相对入场价）。典型取值0.15-0.30。默认20%捕捉中波段盈利空间。
- name: max_holding_days
  default: 30
  range:
  - 10
  - 60
  type: int
  description: 最大持仓天数（单位：交易日）。典型取值20-40。默认30天防止持仓陷入长期震荡，释放资金机会。
- name: max_single_weight
  default: 0.1
  range:
  - 0.03
  - 0.2
  type: float
  description: 单支股票最大仓位占比（单位：小数）。已在position_weights中定义，此处提供调优范围。默认10%确保组合分散。
- name: max_industry_concentration
  default: 0.3
  range:
  - 0.1
  - 0.5
  type: float
  description: 单一行业最大配置比例（单位：小数）。已在position_weights中定义。默认30%控制行业风险。
- name: target_holdings
  default: 8
  range:
  - 5
  - 15
  type: int
  description: 目标持仓数量（单位：支）。已在position_weights中定义。默认8平衡跟踪效率和分散度。
- name: max_turnover_per_rebalance
  default: 0.5
  range:
  - 0.2
  - 0.8
  type: float
  description: 每次再平衡最大换手比例（单位：小数）。已在position_weights中定义。默认50%限制交易频率和冲击成本。
- name: rebalance_freq_days
  default: 5
  range:
  - 3
  - 10
  type: int
  description: 再平衡间隔天数（单位：交易日）。已在position_weights中定义。默认5天在一周内调整，及时跟踪信号变化。
description: 趋势突破+量能过滤中周期波段策略，基于多均线多头、RSI、唐奇安突破和成交量放大，配合固定/移动/目标/时间四重出场。
universe: 沪深300
holding_period: 15-30个交易日
rebalance_freq: 每5个交易日强制再平衡
test_universe:
- HS300
---

## 策略业务逻辑叙事

### 1. 策略思路 / edge 来源（含市场环境假设）
本策略基于A股市场中存在的趋势延续效应和成交量放大预示主力资金介入的规律，捕捉个股由震荡转为上升趋势并伴随放量的早期阶段。通过短、中、长期均线（{ma_short_window}、{ma_mid_window}、{ma_long_window}日）多头排列确认趋势方向，RSI（{rsi_period}日）确保价格不过分超买且仍有上行空间，股价突破{do chian_window}日高点作为突破确认，成交量相对{volume_window}日均量放大至{volume_breakout_ratio}倍以上验证资金参与度。同时，要求市场具备基础波动率（ATR/收盘价>{atr_min_threshold}），避免在低迷行情中频繁无效开仓。市场环境假设：A股市场中短期趋势一旦形成，在资金推动下常持续15-30个交易日，中周期波段机会较多，因而策略聚焦于捕捉此类机会，期望在中期获得稳健超额收益。

### 2. 牛/熊/震荡 3 环境处理
策略并未显式地进行市场状态分类，而是通过入场条件间接实现环境适应：当市场处于熊市或震荡时，多数个股难以形成ma_short > ma_mid > ma_long的多头排列，且成交量萎缩，trend_breakout和volume_confirm两个信号同时触发的概率极低，策略因此自动减少或停止开仓，持有现金等价物。当市场转牛时，上述条件广泛满足，策略积极入场。出场规则方面，固定止损（{fixed_stop_pct}）在任何环境下优先触发，保护资本；移动止损（{trailing_stop_pct}）和止盈（{profit_take_pct}）在趋势行情中帮助锁定利润；时间止损（{max_holding_days}）防止在长时间震荡中消耗机会成本。所有阈值均已参数化，可通过回测调优以适应不同市场波动特征，确保策略整体穿越牛熊，无需人为判断牛熊切换时点。

### 3. 多信号逻辑关系
入场逻辑：两个入场信号trend_breakout（权重0.6）和volume_confirm（权重0.4）必须同时满足（逻辑AND），缺一不可。前者综合了多均线多头、RSI非超买、价格突破前高及波动率过滤，确保趋势质量；后者独立要求成交量放大，避免无量空涨的陷阱。权重反映两者在决策中的相对重要性，趋势形态权重稍高于量能确认。出场优先级：所有出场信号按权重降序依次检查，即固定止损（0.35）→ 移动止损（0.30）→ 目标止盈（0.25）→ 时间止损（0.10）。固定止损拥有最高优先级，因为本金保护是交易第一要义；移动止损次之，防止已有盈利大幅回吐；目标止盈在达到预定收益时积极主动兑现；时间止损作为最后的退出机制，强制了结长时间未达预期的持仓。每个信号的weight值即为其业务优先级的量化表达。

### 4. 风险机制
与简单均线交叉策略相比，本策略融合了成交量确认、RSI超买过滤和波动率要求，显著降低了高频震荡市中虚假信号带来的反复止损。核心风险控制设计：1)固定止损优先于任何其他出场信号，确保单笔损失不超过总资本的{max_single_weight}×{fixed_stop_pct}≈0.7%，极端行情下最大组合层面回撤仍然可控；2)组合层面通过max_single_weight（{max_single_weight}）和max_industry_concentration（{max_industry_concentration}）分散个股和行业风险；3)再平衡频率{rebalance_freq_days}天及最高换手率{max_turnover_per_rebalance}控制交易成本和市场冲击；4)涨跌停、停牌等极端场景由运行框架提供处理，信号被吞等情况自动记录。整体上策略追求在控制最大回撤的前提下实现较高的年化收益。

### 5. NaN 处理
严格遵循A股数据特点：1)上市未满计算窗口（如{ma_long_window}日）的个股，相应因子值为NaN，对应日不参与信号计算，但股票保留在候选池中，待上市时间满足最短窗口后自动纳入评估；2)长期停牌导致价格停滞，停牌期间因子无法更新，出场信号可能无法执行（由运行环境处理），复牌后需等待因子窗口回填（最长{ma_long_window}个交易日）再生成有效入场信号；3)涨跌停日：若已持仓，出场信号因涨跌停无法成交而被吞没（由runner记录并报告）；若未持仓，入场信号正常计算，但实际执行中涨停无法买入的情况由交易模拟层根据市场规则处理；4)一字板（连续涨跌停）及退市股票直接跳过，不纳入回测池，避免流动性陷阱。以上处理确保了策略在真实A股数据条件下的可回测性和稳健性。