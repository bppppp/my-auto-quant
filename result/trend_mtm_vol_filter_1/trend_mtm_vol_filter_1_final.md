---
name: trend_mtm_vol_filter_1
targets:
  annual_return: 0.25
  win_rate: 0.45
  profit_loss_ratio: 3.5
  sharpe: 1.3
  max_drawdown: -0.2
  description: 期望年化25%，胜率45%，盈亏比3.5，夏普1.3，最大回撤20%。
factors:
- name: ma_20
  description: 20日简单移动平均线，反映中短期趋势。
  calculation: mean(close, 20)
- name: ma_60
  description: 60日简单移动平均线，反映中长期趋势。
  calculation: mean(close, 60)
- name: atr_14
  description: 14日平均真实波幅，衡量市场波动程度。
  calculation: atr(high, low, close, 14)
- name: rsi_14
  description: 14日相对强弱指标，衡量价格变动的速度和幅度。
  calculation: 100 - 100 / (1 + mean(gain, 14) / max(mean(loss, 14), 1e-10))
- name: volume_ratio_20
  description: 当日成交量与20日均量的比值，衡量交易活跃度。
  calculation: volume / mean(volume, 20)
- name: return_20d
  description: 20日滚动收益率，衡量近期价格动量。
  calculation: close / delay(close, 20) - 1
- name: highest_since_entry
  description: 自入场以来的最高收盘价，用于移动止损。
  calculation: max(close_since_entry)
- name: atr_14_prev
  description: 前一交易日的ATR14值，用于比较波动率变化。
  calculation: delay(atr_14, 1)
entry_signals:
- name: trend_momentum_filter
  weight: 0.4
  factors:
  - ma_20
  - ma_60
  - return_20d
  - volume_ratio_20
  direction: positive
  trigger: ma_20 > ma_60 AND return_20d > {min_return_20d} AND volume_ratio_20 > {vol_min}
  logic: AND
- name: rsi_filter
  weight: 0.1
  factors:
  - rsi_14
  direction: positive
  trigger: rsi_14 > {rsi_min} AND rsi_14 < {rsi_max}
  logic: AND
- name: volatility_expansion
  weight: 0.5
  factors:
  - atr_14
  - atr_14_prev
  direction: positive
  trigger: atr_14 > atr_14_prev AND atr_14 / close > {atr_min_pct}
  logic: AND
exit_signals:
- name: fixed_stop
  weight: 0.05
  factors: []
  direction: negative
  trigger: current_price < entry_price * (1 - {fixed_stop_pct})
  logic: 单因子
- name: trailing_stop
  weight: 0.5
  factors:
  - highest_since_entry
  direction: negative
  trigger: current_price < highest_since_entry * (1 - {trailing_stop_pct})
  logic: 单因子
- name: time_stop
  weight: 0.4
  factors: []
  direction: negative
  trigger: holding_days >= {max_holding_days}
  logic: 单因子
- name: trend_reverse
  weight: 0.05
  factors:
  - ma_20
  - ma_60
  - rsi_14
  direction: negative
  trigger: ma_20 < ma_60 AND rsi_14 < {rsi_weakness}
  logic: AND
position_weights:
  max_single_weight: 0.2
  max_industry_concentration: 0.4
  target_holdings: 10
  max_turnover_per_rebalance: 0.7
  rebalance_freq_days: 5
params:
- name: max_industry_concentration
  default: 0.4
  range:
  - 0.1
  - 0.5
  type: float
  description: 单一行业最大总仓位权重（小数），防止行业风险。典型取值0.20~0.40，默认0.30允许适度集中。
  reason: 上调至0.40，适度行业集中，匹配高集中度策略。
- name: min_return_20d
  default: 0.02
  range:
  - 0.0
  - 0.2
  type: float
  description: 20日滚动收益率最小阈值（小数），要求股票在过去20个交易日至少实现该涨幅才考虑入场。典型取值0.02~0.05，默认0.02用于过滤下跌趋势。
  reason: 降至0.02，放宽20日动量要求，扩大选股机会。
- name: entry_score_threshold
  default: 0.6
  range:
  - 0.5
  - 1.0
  type: float
  description: 入场信号加权得分阈值（小数），必须达到此分数才开仓。典型取值0.5~0.7，默认0.6至少需要两个信号触发。
  reason: 维持0.6，保证充足交易次数，配套其他参数放量提收益。
- name: rsi_min
  default: 50
  range:
  - 35
  - 70
  type: int
  description: RSI指标下限（0-100整数），用于确保市场处于中等以上动量。典型取值50~60，默认50避免超卖区域。
  reason: 下调至50，放宽动量要求，匹配中位数，扩大入场范围。
- name: max_single_weight
  default: 0.2
  range:
  - 0.03
  - 0.2
  type: float
  description: 单一股票最大仓位权重（小数），控制集中风险。典型取值0.05~0.15，默认0.10适应中等分散度。
  reason: 调至上限0.20，重仓高信念股，提升收益弹性。
- name: fixed_stop_pct
  default: 0.12
  range:
  - 0.03
  - 0.2
  type: float
  description: 固定止损比例（小数），以入场价为基准的最大亏损容忍度。典型取值0.08~0.15，默认0.10平衡风险与容错。
  reason: 收紧至0.12，降低单笔亏损（avg-8291），提升盈亏比。
- name: rsi_max
  default: 80
  range:
  - 60
  - 90
  type: int
  description: RSI指标上限，防止在极度超买时入场。典型取值75~85，默认80过滤过热信号。
  reason: 维持80，过滤极端超买信号，不变。
- name: target_holdings
  default: 10
  range:
  - 5
  - 30
  type: int
  description: 目标持仓数量（只），组合期望持有的股票数量。典型取值8~15，默认10平衡分散与alpha。
  reason: 降至10只，集中资金于高概率标的，提升组合alpha。
- name: rsi_weakness
  default: 25
  range:
  - 25
  - 50
  type: int
  description: RSI弱势阈值（整数），当RSI跌破此值且均线死叉时确认趋势反转出场。典型取值35~45，默认40代表动量衰竭。
  reason: 维持25，trend_reverse出场2712次已大幅减少，有效。
- name: rebalance_freq_days
  default: 5
  range:
  - 1
  - 20
  type: int
  description: 再平衡频率（交易日），每隔多少天检查并调整持仓。典型取值3~10，默认5降低交易成本同时保持响应。
  reason: 维持5天，平衡调仓灵活性与交易成本。
- name: max_turnover_per_rebalance
  default: 0.7
  range:
  - 0.2
  - 1.0
  type: float
  description: 单次再平衡最大换手率（小数），限制交易成本。典型取值0.30~0.60，默认0.50灵活调仓。
  reason: 调至0.7，配合集中持仓，加速轮动捕捉机会。
- name: trailing_stop_pct
  default: 0.25
  range:
  - 0.03
  - 0.3
  type: float
  description: 移动止损回撤比例（小数），从最高收盘价回撤超过该比例时止盈/止损。典型取值0.03~0.08，默认0.05保护浮盈。
  reason: 微调至0.25，在保留趋势利润基础上降低回撤幅度。
- name: atr_min_pct
  default: 0.045
  range:
  - 0.005
  - 0.05
  type: float
  description: ATR相对价格的最小阈值（小数），要求波动率足够以提供利润空间。典型取值0.01~0.03，默认0.02确保活跃度。
  reason: 维持0.045，继续过滤低波伪信号，确保质素。
- name: vol_min
  default: 1.2
  range:
  - 1.0
  - 3.0
  type: float
  description: 成交量放大倍数阈值，要求当日成交量至少为该倍数乘以20日均量。典型取值1.2~2.0，默认1.2确认放量活跃。
  reason: 微调至1.2，放宽量能要求，增加入场机会。
- name: max_holding_days
  default: 250
  range:
  - 15
  - 250
  type: int
  description: 最大持仓天数（交易日），超期强制平仓以规避过夜风险。典型取值20~40，默认30匹配中周期波段。
  reason: 维持250天，time_stop贡献高收益，充分持仓。
description: 多因子趋势跟踪与波动率过滤的中周期波段策略，通过均线、动量、RSI和ATR复合信号择时，结合严格的止损和仓位管理，追求稳健超额收益。
universe: 沪深300及中证1000
holding_period: 10-30个交易日
rebalance_freq: 每5个交易日
test_universe:
- HS300
- CSI1000
---

## 策略业务逻辑叙事

### 1. 策略思路 / edge 来源（含市场环境假设）
本策略基于A股中周期趋势延续效应，认为当价格处于上升趋势（均线多头排列）、动量增强（正收益率、RSI走强）且波动率扩张（ATR放大）时，后续有较大概率延续上涨。A股市场散户交易占比高、动量效应显著，通过多条件过滤可提高信号可靠性。假设市场在中低波动且成交量活跃时趋势信号更可靠，高波动/缩量环境中信号易失真，因此引入波动率和成交量确认，以此构建复合择时系统。

### 2. 牛 / 熊 / 震荡 3 环境处理（所有阈值 param 化）
- **牛市**：市场整体向上时，放宽部分条件，可通过降低入场得分阈值（{entry_score_threshold}降至0.4左右）和下调均线距离要求来实现满仓运行；但固定止损和移动止损仍然保留以防快速反转。
- **熊市**：收紧入场条件，提高{min_return_20d}至0.05以上，{vol_min}升至1.5，同时将{max_single_weight}下调至0.05，{fixed_stop_pct}收严至0.07，快速截断亏损并降低暴露。
- **震荡市**：缩短{max_holding_days}至15-20天，提高再平衡频率至3天，降低趋势假突破影响；RSI区间收窄（{rsi_min}提升至55，{rsi_max}降至75），捕捉短期均值回归机会；仓位保持中性偏低。
所有阈值调整均可通过修改params实现，确保策略在不同市场结构下保持稳健。

### 3. 多信号逻辑关系
- **入场时机**：三个入场信号（趋势动量、RSI动量、波动率扩张）独立评估，若满足其定义的条件则贡献相应权重（0.4/0.3/0.3）。加权总分 = Σ (weight_i × 触发状态) 须达到{entry_score_threshold}（默认0.6）方生成入场指令。该设计允许信号互补，例如某票趋势强但波动未放大仍可能凭借趋势和RSI信号得分0.7而入场，避免漏失机会。
- **出场优先级**：出场信号严格按固定止损 → 移动止损 → 时间止损 → 趋势反转的顺序检查。一旦高优先级信号触发即执行出场，之后不再评估。权重字段在此仅为记录信号重要性，不参与实时决策，以消除权重与优先级的逻辑冲突。固定止损保护本金，移动止损锁定浮盈，时间止损防止被动持仓，趋势反转确认方向变化。
- 所有信号阈值均已param化，方便用户根据品种特性或市场阶段调优。

### 4. 风险机制
- 相比简单均线交叉策略，本策略引入波动率（ATR）过滤，避免低波钝化时频繁开仓；成交量确认提升信号有效性，减少假突破。
- 核心风控节点：固定止损硬性控制单笔最大亏损；移动止损在盈利后动态上移，保护大部分利润；时间止损强制终止长期无方向持仓，避免资金沉淀。
- 仓位管理：通过{max_single_weight}、{max_industry_concentration}和{target_holdings}实现分散化，避免单票/单行业黑天鹅；{max_turnover_per_rebalance}限制调仓成本。
- 特殊行情场景下（如涨跌停无法出场），系统会记录“信号被吞次数”并在归因报告中单独列示，避免误判策略失效。

### 5. NaN 处理（A 股硬约束）
- **上市未满 N 日**：若股票上市交易日少于因子计算所需窗口（例如60日），则相关因子（如ma_60）会产生NaN。该股票在因子有效前不参与信号计算，但不剔除出股票池，待满足条件后自动纳入。
- **长期停牌**：停牌期间无行情数据，因子无法更新。复牌当日不立即入场，需等待至少5个交易日数据回填，确保技术指标稳定后再参与信号评估。
- **涨跌停**：涨停或跌停日，入场信号正常评估（因可能在早盘触发并成交），但出场信号若涉及卖出，在跌停时无法成交，将被记录并延至次日开盘后执行。连续跌停同理，直至开板。
- **一字板**：连续一字涨跌停视为极端流动性缺失，出场信号持续记录，直到开板成交为止；此类情况不计为策略失效。
- 对于ST股票（涨跌幅±5%）或创业板（±20%），策略统一按实际涨跌停幅度处理，涨跌停判断已内嵌在交易系统中；退市股票直接跳过。