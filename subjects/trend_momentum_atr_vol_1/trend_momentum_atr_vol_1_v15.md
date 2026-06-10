---
name: trend_momentum_atr_vol_1
test_universe:
- HS300
targets:
  annual_return: 0.22
  win_rate: 0.45
  profit_loss_ratio: 3.5
  sharpe: 1.3
  max_drawdown: -0.15
  description: 双均线金叉+ATR波动率扩张+量能放大确认，打分制入场，三层止损出场，期望年化22%，胜率45%，盈亏比3.5，夏普1.3，回撤15%。
factors:
- name: ma_10
  description: 10日简单移动平均线，反映短期股价趋势
  calculation: mean(close, 10)
- name: ma_30
  description: 30日简单移动平均线，反映中期股价趋势
  calculation: mean(close, 30)
- name: atr_14
  description: 14日平均真实波幅，衡量市场波动率水平
  calculation: atr(high, low, close, 14)
- name: volume_ratio_20
  description: 当日成交量与20日均量的比率，反映成交活跃度
  calculation: volume / mean(volume, 20)
- name: highest_close_since_entry
  description: 入场以来最高收盘价，用于移动止损跟踪
  calculation: max(close_since_entry)
entry_signals:
- name: ma_golden_cross
  weight: 0.5
  factors:
  - ma_10
  - ma_30
  direction: positive
  trigger: ma_10 > ma_30
  logic: AND
- name: atr_expand
  weight: 0.25
  factors:
  - atr_14
  direction: positive
  trigger: atr_14 / close > {atr_threshold}
  logic: 单因子
- name: volume_confirm
  weight: 0.25
  factors:
  - volume_ratio_20
  direction: positive
  trigger: volume_ratio_20 > {vol_threshold}
  logic: 单因子
exit_signals:
- name: fixed_stop
  weight: 0.4
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
  weight: 0.1
  factors:
  - ma_10
  - ma_30
  direction: negative
  trigger: ma_10 < ma_30
  logic: AND
position_weights:
  max_single_weight: 0.2
  max_industry_concentration: 0.35
  target_holdings: 6
  max_turnover_per_rebalance: 0.6
  rebalance_freq_days: 10
params:
- name: atr_threshold
  default: 0.08
  range:
  - 0.02
  - 0.12
  type: float
  description: ATR波动率最低阈值（单位：小数）。含义：要求ATR/收盘价 > 该值，排除低波动震荡期。典型取值0.01-0.02，默认0.015基于A股中等波动率水平，在捕捉趋势时平衡信号频率。
  reason: v14 atr_expand触发近2万次偏多，提至0.08增强趋势确认。
- name: vol_threshold
  default: 2.8
  range:
  - 1.5
  - 3.5
  type: float
  description: 量能放大倍数最低阈值（单位：倍数）。含义：当日成交量 >= 该倍数 × 20日均量，确认资金参与度。典型取值1.2-2.0，默认1.3能有效捕捉温和放量，降低假突破。
  reason: v14 volume_confirm触发1.5万次仍偏高，提至2.8过滤弱量，强化信号。
- name: target_holdings
  default: 6
  range:
  - 5
  - 20
  type: int
  description: 目标持仓数量（单位：只）。含义：策略同时持有的股票数量目标，影响收益波动和交易成本。典型取值5-15，默认8兼顾分散化与持仓集中度。
  reason: v14收益低，减至6只集中持股，放大单票盈利贡献。
- name: max_holding_days
  default: 180
  range:
  - 20
  - 180
  type: int
  description: 最大持仓天数（单位：交易日）。含义：持仓超过此天数后强制平仓，防止资金在震荡中闲置。典型取值20-40，默认30匹配中周期波段目标。
  reason: v14 time_stop仅12次，延长让趋势充分发展，维持不变。
- name: max_industry_concentration
  default: 0.35
  range:
  - 0.1
  - 0.5
  type: float
  description: 单行业最大权重（单位：小数）。含义：同一行业股票总权重上限，降低板块系统性风险。典型取值0.20-0.40，默认0.30在行业集中与分散间平衡。
  reason: 行业集中度适中，回撤可控。
- name: trailing_stop_pct
  default: 0.18
  range:
  - 0.05
  - 0.25
  type: float
  description: 移动止损回撤比例（单位：小数）。含义：从持仓最高点回落超过该比例时平仓止盈。典型取值0.03-0.08，默认0.05适合中周期趋势跟踪，保护浮盈。
  reason: v14移动止损仅138次，降至0.18早锁利润，减少死叉过早出场。
- name: fixed_stop_pct
  default: 0.14
  range:
  - 0.05
  - 0.25
  type: float
  description: 固定止损比例（单位：小数）。含义：持仓亏损超过该比例强制平仓。典型取值0.05-0.10，默认0.08在保护本金和避免频繁止损间取得平衡。
  reason: v14止损触发1261次亏损大，放宽至0.14给趋势空间，减少误杀。
- name: max_single_weight
  default: 0.2
  range:
  - 0.05
  - 0.2
  type: float
  description: 单只股票最大权重（单位：小数）。含义：组合中任一个股占比上限，控制个股特异性风险。典型取值0.05-0.15，默认0.10适用于中等分散度组合。
  reason: 集中持仓，权重上限充足。
- name: resume_trade_wait_days
  default: 5
  range:
  - 2
  - 15
  type: int
  description: 复牌后等待天数（单位：交易日）。含义：长期停牌后复牌，等待此天数让数据回填和因子稳定再参与信号。典型取值3-10，默认5避免数据跳空影响。
  reason: 复牌等待合理，无需调整。
- name: min_listing_days
  default: 60
  range:
  - 30
  - 120
  type: int
  description: 最低上市天数（单位：交易日）。含义：新股上市未满此天数则跳过，避免初期波动和因子NaN。典型取值40-90，默认60为次新股过滤标准。
  reason: 维持当前过滤标准，无异常影响。
- name: min_entry_score
  default: 0.8
  range:
  - 0.5
  - 0.9
  type: float
  description: 入场所需信号最低总分（单位：无）。含义：股票加权总分 >= 此值才可进入候选池。典型取值0.4-0.6，默认0.5要求至少一个核心信号或两个辅助信号，控制入场质量。
  reason: v14年化仅4.9%盈亏比1.4，提高至0.8要求三信号共振，提升质量。
- name: max_turnover_per_rebalance
  default: 0.6
  range:
  - 0.2
  - 0.8
  type: float
  description: 每次再平衡最大换手率（单位：小数）。含义：调仓时买卖总额占市值上限，控制交易成本和冲击。典型取值0.2-0.6，默认0.50允许适度调整。
  reason: 成本可控，维持。
- name: rebalance_freq_days
  default: 10
  range:
  - 3
  - 15
  type: int
  description: 调仓频率（单位：交易日）。含义：每隔多少交易日进行一次再平衡。典型取值3-10，默认5平衡反应速度与交易成本。
  reason: 平衡反应速度与成本，维持。
description: 双均线金叉+ATR波动率扩张+量能放大确认，打分制入场，三层止损出场的中周期波段策略。
universe: 沪深300
holding_period: 15-30个交易日
rebalance_freq: 每5个交易日
---

## 策略业务逻辑叙事

### 1. 策略思路 / edge 来源（含市场环境假设）
本策略基于 A 股市场存在显著的趋势延续效应——在散户交易占比高、涨停板制度等背景下，资金易形成追涨杀跌的正反馈，导致金叉后的行情往往具有惯性。策略采用 10 日与 30 日均线交叉作为基础趋势判断，同时引入 ATR 波动率扩张和成交量放大双重验证，以过滤震荡市中的假突破信号，捕捉中周期（15-30 日）主升浪。edge 来源于 A 股对强势突破的奖励机制：一旦股价带量突破且波动率放大，后续惯性推升的概率较高，而通过多层止损（固定、移动、时间）严格控制下行风险，实现正向期望收益。

### 2. 牛 / 熊 / 震荡 3 环境处理
策略在设计层面考虑了三种市场环境的差异化应对，所有调整均通过修改 params 实现，而非实时判断牛熊：
- **牛市**：降低入场门槛（如 {min_entry_score} 从 0.5 调至 0.3），放宽量能和波动率阈值，提高单票最大权重 {max_single_weight} 至上限，延长最大持仓天数 {max_holding_days} 至 45 日，以充分享受趋势利润。
- **熊市**：大幅收紧条件，提高 {min_entry_score} 至 0.7 以上，降低 {max_single_weight} 至 0.06，缩小止损比例 {fixed_stop_pct} 和 {trailing_stop_pct}，缩短 {max_holding_days} 至 15 日，保护本金并快速止损。
- **震荡市**：延长再平衡周期 {rebalance_freq_days} 至 10 日以上，减少交易频率；进一步提高 {min_entry_score} 至 0.8，要求更多信号共振才入场；同时缩短时间止损，防止资金无效率占用。所有参数的动态调整可在回测框架中通过分段优化实现，使策略在不同风格市场中均能稳健运行。

### 3. 多信号逻辑关系
- **入场时机**：三个入场信号（均线金叉、ATR扩张、量能确认）独立计算，满足则获得对应权重（0.50/0.25/0.25）。每只股票的总得分为所有满足信号的权重之和。当总得分 >= {min_entry_score} 时，股票进入候选池；候选池按得分降序排列，选取前 {target_holdings} 只股票等权分配仓位，若候选数量不足则持有现金。此分数机制使得入场条件兼具灵活性与严格性，核心信号（金叉）权重最大，辅助信号可组合触发。
- **出场优先级**：出场按“固定止损（权重0.40） > 移动止损（0.30） > 时间止损（0.20） > 均线死叉（0.10）”的优先级链轮询。一旦高优先级信号触发，立即执行出场，不再检查后续信号。这样设计保证了本金保护优先于浮盈保护，浮盈保护优先于时间成本，最后才依赖趋势反转信号，避免单一死叉在震荡中频繁错误离场。

### 4. 风险机制
与单纯均线交叉策略相比，本策略的核心风控差异点在于：（1）波动率和量能双验证显著降低了震荡假突破时的无效入场；（2）三层止损体系覆盖了本金、浮盈、时间三个维度，任何一层触发即平仓，不依赖趋势反转；（3）权重限制通过 {max_single_weight} 和 {max_industry_concentration} 防止黑天鹅事件，{max_turnover_per_rebalance} 控制交易成本。特别地，对于涨跌停导致的无法成交情况，策略设计为：出场日若涨停封板，则标记“信号被吞”并顺延至下一可交易日卖出；入场日若一字板涨停无法买入，则跳过该股。此机制在回测中真实模拟 A 股实际交易约束。

### 5. NaN 处理
本策略严格遵循 A 股数据硬约束，对四种典型 NaN/异常场景做如下处理：
- **上市未满规定天数**：对上市交易日数少于 {min_listing_days} 的股票，其均线、ATR 等因子因历史数据不足产生 NaN，当日该股票不参与任何信号计算，也不进入候选池。
- **长期停牌**：股票连续停牌期间因子不更新，复牌后由于数据断层，系统需等待至少 {resume_trade_wait_days} 个交易日让因子重新稳定，在此期间该股票不参与信号计算，避免数据跳空引起错误。
- **涨跌停**：持仓股票若触及涨跌停且封板，出场信号可能因无流动性而无法执行，系统自动记录并延迟出场；未持仓股票若开盘即涨停/跌停且无法买入，当日入场信号跳过。
- **一字板**：对于开盘即涨停/跌停且全日未打开的股票，无论买卖方向均跳过该股票当日评估，防止虚假成交。此外，退市风险警示（ST）及退市整理期股票默认不纳入测试 universe，从而从源头规避非正常交易股票。