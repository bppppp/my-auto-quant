---
name: donchian_adx_volume_entry_1
targets:
  annual_return: 0.25
  win_rate: 0.45
  profit_loss_ratio: 3.5
  sharpe: 1.25
  max_drawdown: -0.2
  description: 突破入场+趋势强度过滤+量能确认，出场按优先级风控。期望年化25%、胜率45%、盈亏比3.5、夏普1.25、回撤20%。
factors:
- name: hh_20
  description: 20日最高价，Donchian上轨
  calculation: max(high, 20)
- name: ll_10
  description: 10日最低价，短期支撑参考
  calculation: min(low, 10)
- name: adx_14
  description: 14日平均趋向指数，衡量趋势强度
  calculation: adx(high, low, close, 14)
- name: ma_20
  description: 20日简单移动平均线
  calculation: mean(close, 20)
- name: ma_60
  description: 60日简单移动平均线
  calculation: mean(close, 60)
- name: volume_ratio_20
  description: 当日成交量与20日均量的比值
  calculation: volume / mean(volume, 20)
- name: highest_close_since_entry
  description: 进场以来最高收盘价，用于移动止损
  calculation: max(close_since_entry)
entry_signals:
- name: breakout
  weight: 0.5
  factors:
  - hh_20
  direction: positive
  trigger: close > hh_20
  logic: 单因子
- name: trend_confirm
  weight: 0.3
  factors:
  - adx_14
  - ma_20
  - ma_60
  direction: positive
  trigger: adx_14 > {adx_threshold} AND ma_20 > ma_60
  logic: AND
- name: volume_confirm
  weight: 0.2
  factors:
  - volume_ratio_20
  direction: positive
  trigger: volume_ratio_20 > {volume_threshold}
  logic: 单因子
exit_signals:
- name: fixed_stop
  weight: 0.6
  factors: []
  direction: negative
  trigger: current_price < entry_price * (1 - {fixed_stop_pct})
  logic: 单因子
- name: trailing_stop
  weight: 0.5
  factors:
  - highest_close_since_entry
  direction: negative
  trigger: current_price < highest_close_since_entry * (1 - {trailing_stop_pct})
  logic: 单因子
- name: trend_reversal
  weight: 0.4
  factors:
  - ll_10
  direction: negative
  trigger: close < ll_10
  logic: 单因子
- name: time_stop
  weight: 0.3
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
- name: adx_threshold
  default: 25
  range:
  - 15
  - 40
  type: int
  description: 趋势强度最低要求（ADX值，无单位）。含义：ADX高于此值时才认为趋势有效。典型取值20-30。默认25为平衡点，过滤噪音同时不放过中等趋势。
- name: volume_threshold
  default: 1.5
  range:
  - 1.0
  - 3.0
  type: float
  description: 量能放大倍数（单位：倍）。要求当日成交量至少达到20日均量的该倍数。典型取值1.2-2.0。默认1.5可确认资金介入，且避免过度苛刻。
- name: entry_score_threshold
  default: 0.8
  range:
  - 0.5
  - 1.0
  type: float
  description: 入场信号总分阈值（无单位，0-1）。入场采用加权评分制，各信号触发时贡献对应weight，总分达到该阈值则入场。默认0.8要求至少突破信号（0.5）加上趋势或量能之一。
- name: fixed_stop_pct
  default: 0.1
  range:
  - 0.03
  - 0.25
  type: float
  description: 固定止损比例（单位：小数）。当股价相对入场价跌幅超过此比例时无条件止损。典型取值0.05-0.15。默认0.10平衡风险承受与波段容忍度。
- name: trailing_stop_pct
  default: 0.06
  range:
  - 0.02
  - 0.15
  type: float
  description: 移动止损回撤比例（单位：小数）。从持仓以来最高收盘价回撤超过此比例时触发止盈/止损。典型取值0.05-0.10。默认0.06保护浮盈同时允许正常波动。
- name: max_holding_days
  default: 30
  range:
  - 10
  - 60
  type: int
  description: 最大持仓天数（单位：交易日）。超过此天数仍未触发其他出场信号时强制平仓。典型取值15-45。默认30匹配中周期波段预期，防止资金长期套牢。
- name: max_single_weight
  default: 0.1
  range:
  - 0.03
  - 0.2
  type: float
  description: 单只股票最大仓位权重（单位：小数）。控制集中度风险。典型取值0.05-0.15。默认0.10在8只持仓下实现适度分散。
- name: max_industry_concentration
  default: 0.3
  range:
  - 0.2
  - 0.5
  type: float
  description: 单一行业最大仓位权重（单位：小数）。防止行业系统性风险。典型取值0.25-0.40。默认0.30在行业中性基础上保留选股超额空间。
- name: target_holdings
  default: 8
  range:
  - 5
  - 15
  type: int
  description: 目标持仓数量（单位：只）。策略同时持有的股票数量。典型取值5-12。默认8在分散与收益集中间取得平衡。
- name: max_turnover_per_rebalance
  default: 0.5
  range:
  - 0.3
  - 0.8
  type: float
  description: 单次再平衡最大换手率（单位：小数）。控制交易成本和冲击。典型取值0.30-0.60。默认0.50允许较大调仓但避免全进全出。
- name: rebalance_freq_days
  default: 5
  range:
  - 1
  - 10
  type: int
  description: 再平衡频率（单位：交易日）。每隔该天数检查并执行调仓。典型取值3-7。默认5匹配周频调仓，平衡时效与成本。
description: 突破策略：价格突破20日高点入场，ADX确保趋势，量能确认，出场按优先级（固定>移动>趋势反转>时间）进行风控
universe: 沪深300
holding_period: 10-30个交易日
rebalance_freq: 每5个交易日强制再平衡
test_universe:
- HS300
---

## 策略业务逻辑叙事

### 1. 策略思路 / edge 来源（含市场环境假设）
本策略基于A股市场中“趋势延续”与“资金跟进”的短期动量效应，捕捉价格突破关键阻力位后形成的波段行情。核心假设：当股价向上突破20日高点（Donchian上轨）时，往往意味着新趋势的开启，配合ADX确认趋势强度、成交量放大验证资金参与，可过滤假突破。A股由于散户参与度高，突破后的正反馈较强，因此该信号在中周期（2-6周）内具备超额收益潜力。策略不依赖市场状态判别，而是通过入场评分制和参数化风控机制，使策略在趋势明显的牛熊环境下自动适应，在震荡市中减少无效交易。

### 2. 牛 / 熊 / 震荡 3 环境处理（所有阈值 param 化）
策略通过信号组合与参数设计实现对三种市场环境的自适应，无需人为判断牛熊。
- **牛市**：价格持续新高，突破信号频繁触发；ADX往往维持高位，量能活跃。策略将满仓运行，入场得分容易达到{entry_score_threshold}，回调较小，移动止损跟随上升，固定止损很少被触发。
- **熊市**：突破成功概率下降，假突破增多。ADX可能因急跌而偏高，但成交量放大阈值{volume_threshold}可过滤部分恐慌性放量。更关键的是出场端：固定止损{ fixed_stop_pct }和移动止损{ trailing_stop_pct }将快速截断亏损，仓位控制（单票最大权重{max_single_weight}）分散风险。同时，入场得分门槛{entry_score_threshold}可以适当调高，减少错误入场。
- **震荡市**：价格反复穿越均线，突破后易快速反转。此时ADX多处于低位，无法通过{adx_threshold}过滤；量能往往萎缩，突破信号得分难以达到{entry_score_threshold}，策略自动减少开仓。已持仓部分，时间止损{max_holding_days}可强制了结，避免长期纠缠。同时，再平衡频率{rebalance_freq_days}可适度延长，降低换手成本。所有调整均通过修改params数值实现，不改变策略骨架。

### 3. 多信号逻辑关系
- **入场时机**：采用加权评分制。三个入场信号分别代表突破力度、趋势背景、资金确认，各自权重0.5、0.3、0.2。交易时段内，系统计算所有已触发的入场信号得分之和，若达到{entry_score_threshold}则生成入场指令。得分制允许部分信号不满足（例如量能不配合但突破+趋势强仍可入场），也防止单一假突破信号导致过度交易。
- **出场优先级**：出场信号不采用评分制，而是按weight降序排列（固定止损0.6 > 移动止损0.5 > 趋势反转0.4 > 时间止损0.3），形成严格的风控链。运行时按此顺序逐一检查：一旦某一个信号的条件成立，立即执行卖出，不再检查后续信号。这种设计确保了本金保护（固定止损）永远优先于浮盈保护（移动止损），其次才是趋势反转和技术失效，时间止损作为最后防线兜底。权重数值直接定义了检查次序，绝不叠加。

### 4. 风险机制
本策略与单纯突破策略的差异在于：出场端构建了四层风控（固定、移动、反转、时间），而非单一移动止损。核心风控要点包括：a) 固定止损{ fixed_stop_pct }硬约束单笔最大损失；b) 移动止损保护极端反转造成的浮盈回吐；c) 跌破短期支撑（10日低点）及时离场，避免趋势逆转后硬扛；d) 时间止损防止资金沉淀；e) 仓位端通过{max_single_weight}、{max_industry_concentration}控制集中度。涨跌停特殊处理由执行层统一完成：当日触及涨跌停时，若需卖出则延至下一可交易日，期间暂停止损检查以防误判。

### 5. NaN 处理（A 股硬约束）
- **上市未满 N 日**：策略使用的均线最大窗口为60日（ma_60），所有窗口小于等于60日的因子在股票上市不满60个自然日时会出现NaN。回测中，该股票在该日不参与信号计算（即跳过），待数据满窗口后自动恢复。
- **长期停牌**：停牌期间无新数据，各因子沿用最后一根有效K线值，但可能失真。因此复牌当日不计入信号扫描，需等待N个交易日（等于最大因子窗口，即60日，但实践中取5日）数据回填后，再重新参与评分，防止基于停牌前价格产生错误交易。
- **涨跌停**：入场信号在开盘前判定，若当日开盘即涨跌停且未成交，则入场无效；若持仓中遇涨跌停，出场信号被暂时吞没，顺延至打开涨跌停后重新检查。此过程中，固定止损{ fixed_stop_pct }等累计计算，但执行被推迟，记录为“信号吞没次数”。
- **一字板**：一字涨跌停视为极端涨跌停，处理方式同上；若连续一字板导致无法出场，策略将在打开后立即按最新价格执行止损或趋势反转信号，不强行跳空成交。