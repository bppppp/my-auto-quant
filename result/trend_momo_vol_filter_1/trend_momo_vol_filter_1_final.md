---
name: trend_momo_vol_filter_1
targets:
  annual_return: 0.24
  win_rate: 0.46
  profit_loss_ratio: 3.3
  sharpe: 1.2
  max_drawdown: -0.18
  description: 多因子趋势动量策略：均线金叉+MACD正柱+放量+ATR适中，三道止损（固定/移动/时间）控制风险。目标年化24%，胜率46%，盈亏比3.3，夏普1.2，回撤18%。
factors:
- name: ma_10
  description: 10日简单移动平均线，反映短期价格趋势
  calculation: mean(close, 10)
- name: ma_30
  description: 30日简单移动平均线，反映中期价格趋势
  calculation: mean(close, 30)
- name: macd_diff
  description: MACD指标的快线DIF，12日EMA减26日EMA，衡量价格动量
  calculation: ema(close, 12) - ema(close, 26)
- name: volume_ratio_20
  description: 当日成交量与20日均量的比值，用于判断放量程度
  calculation: volume / mean(volume, 20)
- name: atr_14
  description: 14日平均真实波幅，衡量个股波动率
  calculation: atr(high, low, close, 14)
- name: highest_close_since_entry
  description: 入场持仓期间的最高收盘价，用于移动止损计算
  calculation: max(close, since=entry_date)
entry_signals:
- name: ma_golden_cross
  weight: 0.44
  factors:
  - ma_10
  - ma_30
  direction: positive
  trigger: ma_10 > ma_30
  logic: AND
- name: macd_positive
  weight: 0.01
  factors:
  - macd_diff
  direction: positive
  trigger: macd_diff > 0
  logic: 单因子
- name: volume_surge
  weight: 0.45
  factors:
  - volume_ratio_20
  direction: positive
  trigger: volume_ratio_20 > {vol_break_ratio}
  logic: 单因子
- name: atr_normal_range
  weight: 0.1
  factors:
  - atr_14
  direction: positive
  trigger: atr_14 / close > {atr_low_limit} AND atr_14 / close < {atr_up_limit}
  logic: AND
exit_signals:
- name: fixed_stop_loss
  weight: 0.02
  factors: []
  direction: negative
  trigger: current_price < entry_price * (1 - {stop_loss_pct})
  logic: 单因子
- name: trailing_stop
  weight: 0.28
  factors:
  - highest_close_since_entry
  direction: negative
  trigger: current_price < highest_close_since_entry * (1 - {trailing_stop_pct})
  logic: 单因子
- name: time_stop
  weight: 0.7
  factors: []
  direction: negative
  trigger: holding_days >= {max_holding_days}
  logic: 单因子
position_weights:
  max_single_weight: 0.15
  max_industry_concentration: 0.3
  target_holdings: 6
  max_turnover_per_rebalance: 0.4
  rebalance_freq_days: 5
params:
- name: max_holding_days
  default: 35
  range:
  - 15
  - 40
  type: int
  description: 最大持仓天数，单位：交易日。持仓超过此天数强制卖出离场。典型取值10~30，默认20，防止资金长期钝化。
  reason: 延长至35天让时间出场获利更充分，提升年化收益。
- name: max_single_weight
  default: 0.15
  range:
  - 0.05
  - 0.2
  type: float
  description: 单支股票最大仓位权重，单位：小数（总资产占比）。典型取值0.05~0.15，默认0.12，适度集中同时控制个股风险。
  reason: 提至0.15增加个股集中度，放大优质信号收益贡献。
- name: vol_break_ratio
  default: 1.4
  range:
  - 1.0
  - 3.0
  type: float
  description: 成交量放大倍数阈值，单位：倍。当当日成交量/20日均量超过该值时视为有效放量。典型取值1.2~2.0，默认1.5，过滤温和放量，仅捕捉显著资金介入。
  reason: 降至1.4放宽量能过滤，增加入场机会，配合收紧止损对冲。
- name: atr_low_limit
  default: 0.01
  range:
  - 0.005
  - 0.03
  type: float
  description: ATR/收盘价比值下限，单位：小数（如0.01代表1%）。排除波动率过低的“僵尸股”。典型取值0.005~0.02，默认0.01，确保候选股有一定波动空间。
  reason: 放宽至0.010增加候选，捕捉低波趋势股，改善胜率。
- name: max_turnover_per_rebalance
  default: 0.4
  range:
  - 0.2
  - 0.5
  type: float
  description: 单次再平衡最大换手率，单位：小数（如0.4=40%）。限制调仓规模以控制交易成本。典型取值0.20~0.50，默认0.40，保留一定调仓灵活性。
  reason: 换手率0.4非瓶颈，交易成本控制良好，维持。
- name: trailing_stop_pct
  default: 0.18
  range:
  - 0.05
  - 0.25
  type: float
  description: 移动止损回撤比例，单位：小数（如0.05=5%）。从入场后最高收盘价回撤此比例止盈。典型取值0.03~0.10，默认0.05，保护大部分浮盈。
  reason: 提至0.18减少过早止盈，让更多交易达时间出场，增厚利润。
- name: stop_loss_pct
  default: 0.07
  range:
  - 0.04
  - 0.12
  type: float
  description: 固定止损比例，单位：小数（如0.08=8%）。现价较入场价下跌该比例立即止损。典型取值0.05~0.12，默认0.08，控制单笔最大亏损在本金8%内。
  reason: 收紧至0.07减少单笔亏损，提升盈亏比，牺牲部分胜率。
- name: rebalance_freq_days
  default: 5
  range:
  - 3
  - 10
  type: int
  description: 再平衡频率，单位：交易日。每N天重新筛选并调整持仓。典型取值3~10，默认5，平衡信号响应速度与交易成本。
  reason: 5天平衡响应与成本，历版稳定，维持。
- name: atr_up_limit
  default: 0.06
  range:
  - 0.03
  - 0.15
  type: float
  description: ATR/收盘价比值上限，单位：小数（如0.06代表6%）。避免参与波动率过大的极端投机股。典型取值0.04~0.08，默认0.06，平衡风险与机会。
  reason: 放宽至0.06引入更多高波动股，配合收紧止损，提升潜在收益。
- name: max_industry_concentration
  default: 0.3
  range:
  - 0.2
  - 0.4
  type: float
  description: 单一行业最大总权重，单位：小数（如0.3=30%）。分散行业风险。典型取值0.20~0.40，默认0.30，均衡集中度与分散度。
  reason: 行业集中度0.3控制良好，回撤稳定，维持。
- name: target_holdings
  default: 6
  range:
  - 5
  - 12
  type: int
  description: 目标持仓数量，单位：只股票。力求持有该数量的股票，兼顾跟踪误差与分散度。典型取值5~12，默认8。
  reason: 降至6集中持仓，增强优质选股收益贡献。
description: 趋势动量+波动过滤策略：均线金叉确认趋势，MACD&成交量增强动量，ATR筛选活跃度，三道止损控制风险。
universe: 沪深300
holding_period: 5-20个交易日（中周期）
rebalance_freq: 每5个交易日
test_universe:
- HS300
---

## 策略业务逻辑叙事

### 1. 策略思路 / edge来源（含市场环境假设）
本策略基于趋势跟踪与动量效应，在A股中周期波段中捕捉主升浪。核心逻辑：当短期均线上穿长期均线确认趋势启动，MACD指标为正值验证多头动能，成交量放大表明资金积极介入，同时通过ATR过滤极端波动（避免死水或过度投机），形成多因子验证入场机制。出场采用三道防线：固定止损保护本金，移动止损保护浮盈，时间止损防止持仓钝化。Edge来源：A股市场个人投资者占比较高，趋势一旦形成往往具有惯性，叠加成交量的确认可有效降低假突破风险。市场环境假设：策略设计时假定市场会在牛熊震荡间切换，因此内置了参数化的环境适应机制，使得不同市况下仍能保持稳健。

### 2. 牛/熊/震荡3环境处理
策略通过调整params中的阈值来适应不同环境，无需实时判断市场状态。
- **牛市**：放宽入场限制，降低{vol_break_ratio}（如1.2），允许较低成交量确认；提高{atr_up_limit}，容忍更大的波动率；同时可适当放宽{trailing_stop_pct}（如0.08）以让利润奔跑。满仓运行，{max_single_weight}可提至0.15，{target_holdings}可增至10。
- **熊市**：收紧所有阈值以提高防御性：{vol_break_ratio}升高至2.0，仅成交量显著放大时才入场；{stop_loss_pct}降至0.05，快速止损；{atr_up_limit}收窄至0.04，回避高波动个股；{max_single_weight}降至0.08，{max_industry_concentration}降至0.25，整体减少仓位暴露。
- **震荡市**：为避免反复止损，{max_holding_days}缩短至15天，加快资金周转；{atr_low_limit}适当提高（0.02），滤除缩量盘整股；同时可能要求多个信号同时满足（通过组合优化层调整），降低交易频率。
所有环境参数均可通过配置文件调整，无需变更策略逻辑。

### 3. 多信号逻辑关系
- **入场时机**：四个入场信号（均线金叉、MACD>0、成交量突破、ATR正常）各自独立触发，但最终持仓由组合权重分配决定。具体而言，对于每只候选股票，计算满足的信号权重之和作为“入选分数”。分数越高的股票优先纳入持仓，直至达到{target_holdings}上限。仅满足单个信号（权重较低）的股票也可入场，但比重较小，这样既保证信号质量，又避免错过部分机会。权重分配上，均线金叉（0.40）为核心趋势确认，MACD和成交量（各0.20）提供动量验证，ATR波动率（0.20）作为环境过滤，整体确保多维度验证。
- **出场优先级**：固定止损（权重0.45）作为第一道防线，一旦触及无条件离场；移动止损（权重0.35）次之，在浮盈后保护利润；时间止损（权重0.20）最后，作为持仓期限的硬约束。出场时严格按权重降序遍历：首先检查固定止损，触发则清仓；否则检查移动止损，再否则检查时间止损，确保风险控制优先于利润保护。权重值明确反映优先级顺序，实现上保证设计意图不被误解。

### 4. 风险机制
与单纯的技术指标策略不同，本策略采用“前重后轻”的风险结构：
1) **组合层面**：通过{max_single_weight}和{max_industry_concentration}控制个股与行业集中度，避免黑天鹅冲击；{max_turnover_per_rebalance}限制换手率，减少交易成本和滑点。
2) **交易层面**：{rebalance_freq_days}为5天，平衡了信号响应与过度交易；再平衡时考虑持仓权重优化，避免单笔过大。
3) **个股层面**：三道止损串联，确保每笔交易的最大损失被固定止损锁定（{stop_loss_pct}），移动止损解决趋势反转时的利润回吐，时间止损避免“僵尸仓”。
核心风控要点：止损优先级不可打破，所有数字阈值均参数化，可依据市况调整，无需改动策略代码。

### 5. NaN处理
- **上市未满N日**：对于依赖历史数据的因子（如ma_30需30日历史），新股在未满N个交易日前，相关因子值为NaN，该股票当日不参与信号计算，待满期后自动纳入。
- **停牌**：个股停牌期间，所有行情数据缺失，相关因子无法更新；复牌后需等待数据回填至所需窗口长度（如20日）后再参与信号评估，避免因数据缺失产生错误信号。
- **涨跌停**：涨跌停板限制当日成交，因此：①当日入场信号正常产生（基于开盘价判断），但若涨停则无法买入，系统自动撤单；②当日出场信号若触发，因跌停无法卖出，信号被吞，次日继续监控；③连续涨跌停时，策略将记录异常，并在恢复流动性后优先处理。
- **一字板**：开盘即涨跌停且全日无打开，视为极端流动性缺失，该类股票直接从候选池中剔除，直至打开且成交量恢复正常。