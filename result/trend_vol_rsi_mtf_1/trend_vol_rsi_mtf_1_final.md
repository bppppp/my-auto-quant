---
name: trend_vol_rsi_mtf_1
targets:
  annual_return: 0.23
  win_rate: 0.5
  profit_loss_ratio: 3.0
  sharpe: 1.35
  max_drawdown: -0.16
  description: 期望年化23%，胜率50%，盈亏比3.0，夏普1.35，最大回撤16%。收益回撤比>=1.44，胜率*盈亏比=1.5，满足数学自洽与硬规则。
factors:
- name: ma_10
  description: 10日简单移动平均线
  calculation: mean(close, 10)
- name: ma_30
  description: 30日简单移动平均线
  calculation: mean(close, 30)
- name: atr_14
  description: 14日平均真实波幅
  calculation: atr(high, low, close, 14)
- name: volume_ratio_20
  description: 当日成交量与20日均量之比
  calculation: volume / mean(volume, 20)
- name: rsi_14
  description: 14日相对强弱指数
  calculation: 100 - 100 / (1 + mean(gain, 14) / mean(loss, 14))
- name: max_close_20
  description: 20日最高收盘价
  calculation: max(close, 20)
entry_signals:
- name: trend_up
  weight: 0.2
  factors:
  - ma_10
  - ma_30
  direction: positive
  trigger: ma_10 > ma_30
  logic: AND
- name: volume_surge
  weight: 0.7
  factors:
  - volume_ratio_20
  direction: positive
  trigger: volume_ratio_20 > {volume_threshold}
  logic: 单因子
- name: rsi_strength
  weight: 0.1
  factors:
  - rsi_14
  direction: positive
  trigger: rsi_14 > {rsi_threshold}
  logic: 单因子
exit_signals:
- name: fixed_stop
  weight: 0.0001
  factors: []
  direction: negative
  trigger: current_price < entry_price * (1 - {fixed_stop_pct})
  logic: 单因子
- name: atr_trailing_stop
  weight: 0.001
  factors:
  - atr_14
  direction: negative
  trigger: current_price < entry_price - {atr_stop_mult} * atr_14
  logic: 单因子
- name: trailing_stop
  weight: 0.001
  factors:
  - max_close_20
  direction: negative
  trigger: current_price < max_close_20 * (1 - {trailing_stop_pct})
  logic: 单因子
- name: take_profit
  weight: 0.9
  factors: []
  direction: negative
  trigger: current_price > entry_price * (1 + {profit_target_pct})
  logic: 单因子
- name: time_stop
  weight: 0.85
  factors: []
  direction: negative
  trigger: holding_days >= {max_holding_days}
  logic: 单因子
- name: trend_reverse
  weight: 0.01
  factors:
  - ma_10
  - ma_30
  direction: negative
  trigger: ma_10 < ma_30
  logic: AND
position_weights:
  max_single_weight: 0.12
  max_industry_concentration: 0.22
  target_holdings: 10
  max_turnover_per_rebalance: 0.4
  rebalance_freq_days: 5
params:
- name: rebalance_freq_days
  default: 5
  range:
  - 3
  - 10
  type: int
  description: 再平衡周期（交易日）。每隔多少天检查信号并调整仓位。典型取值3-7天，默认5天匹配波段操作节奏，避免每日频繁调仓。
  reason: 5日再平衡节奏适当，无调整依据。
- name: max_single_weight
  default: 0.12
  range:
  - 0.04
  - 0.15
  type: float
  description: 单只股票最大仓位权重（占总资金比例）。控制个股集中度风险。典型取值5%-10%，默认8%平衡集中与分散。
  reason: 回撤近限，维持12%平衡风控与收益。
- name: atr_stop_mult
  default: 3.2
  range:
  - 1.2
  - 4.0
  type: float
  description: ATR动态止损倍数。止损距离 = ATR * 倍数，低于入场价减该值即止损。典型取值1.5-2.5，默认2.0使止损线位于正常波动边界之外。
  reason: ATR触发次数稳定，维持3.2避免过度放宽。
- name: max_industry_concentration
  default: 0.22
  range:
  - 0.15
  - 0.35
  type: float
  description: 单一行业最大总仓位权重。防范行业系统性风险。典型取值20%-30%，默认25%避免行业过度暴露。
  reason: 行业集中风控适当，维持。
- name: profit_target_pct
  default: 0.53
  range:
  - 0.1
  - 0.55
  type: float
  description: 止盈目标比例（入场价上涨百分比）。达到后自动止盈锁定利润。典型取值20%-30%，默认25%匹配A股中周期波段潜在涨幅。
  reason: 止盈平均盈利续升，微提至53%扩单笔收益。
- name: rsi_threshold
  default: 62
  range:
  - 30
  - 70
  type: float
  description: RSI动量阈值。要求RSI大于该值才入场，确保标的处于相对强势区。典型取值45-55，默认50代表中性偏强，避免过早介入弱势反弹。
  reason: 提高动量门槛至62，优化入场胜率和盈亏比。
- name: target_holdings
  default: 10
  range:
  - 6
  - 18
  type: int
  description: 目标持仓股票数量。组合分散程度，太少风险集中，太多稀释收益。典型取值8-15，默认10实现适度分散。
  reason: 持仓10只平衡分散与集中，维持。
- name: max_turnover_per_rebalance
  default: 0.4
  range:
  - 0.2
  - 0.6
  type: float
  description: 每次再平衡最大换手率。控制交易频率与成本。典型取值30%-50%，默认40%允许必要调整的同时抑制过度交易。
  reason: 当前换手率适中，无调整信号。
- name: trailing_stop_pct
  default: 0.42
  range:
  - 0.05
  - 0.45
  type: float
  description: 移动止损比例（从20日最高收盘价回撤百分比）。保护浮动利润，允许趋势发展。典型取值5%-8%，默认6%适配中周期波动幅度。
  reason: 触发极少，维持42%让利润充分奔跑。
- name: fixed_stop_pct
  default: 0.14
  range:
  - 0.04
  - 0.18
  type: float
  description: 固定止损比例（入场价下跌百分比）。控制单笔最大亏损，入场即设硬止损。典型取值5%-10%，默认8%在A股波段中提供适当保护而不轻易被震出。
  reason: 已放宽至14%，进一步放宽回撤风险增加，暂维持。
- name: volume_threshold
  default: 1.4
  range:
  - 1.0
  - 2.0
  type: float
  description: 成交量放大倍数阈值。控制入场时要求当日成交量至少是20日均量的多少倍。典型取值1.2-1.5，强势市场可降至1.0，弱势市场升至1.5。默认1.2平衡信号数量与质量，过滤缩量突破。
  reason: 量能胜率偏低，提升至1.4过滤弱量，提高信号质量。
- name: max_holding_days
  default: 99
  range:
  - 20
  - 100
  type: int
  description: 最大持仓天数（交易日）。超时强制平仓避免资金沉淀。典型取值20-30天，默认25天覆盖一般中周期行情时间窗口。
  reason: 时间止损胜率75%，延至99天捕大趋势。
description: 双均线趋势识别 + 成交量放大确认 + RSI动量过滤，配合三层止损与止盈的中周期波段策略。
universe: 沪深300
holding_period: 15-25个交易日
rebalance_freq: 每5个交易日再平衡
test_universe:
- HS300
---

## 策略业务逻辑叙事

### 1. 策略思路 / edge 来源（含市场环境假设）
本策略基于A股市场中强势股的趋势延续效应，捕捉15-25个交易日的中周期主升浪。核心假设：当股票处于10日均线上穿30日均线的多头排列时，伴随着成交量放大和RSI动量转强，后续一段行情大概率延续；同时利用多重动态止损保护本金与利润。市场环境假设：A股长期存在结构性的波段机会，个股受资金关注后易形成短期趋势，通过量价与动量共振筛选，能过滤掉大部分震荡或无量反弹的虚假信号。

### 2. 牛 / 熊 / 震荡 3 环境处理（所有阈值 param 化）
策略设计层面考虑不同市场特征，通过可调参数适应而不依赖实时状态识别：
- **牛市**：趋势明确，可降低入场门槛（如调低 {volume_threshold} 至 1.0、{rsi_threshold} 至 45），同时提高盈利目标 {profit_target_pct} 至 0.30 以上，并适当放宽单票仓位上限 {max_single_weight}，让利润奔跑。
- **熊市**：系统性风险高，收紧所有风险敞口。提高入场阈值（{volume_threshold} 升至 1.5+、{rsi_threshold} 升至 55），降低 {max_single_weight}、{target_holdings}，缩短 {max_holding_days}，收紧止损幅度 {fixed_stop_pct} 和 {trailing_stop_pct}，以保全本金为首要目标。
- **震荡市**：趋势持续性差，采用更短的时间止损 {max_holding_days} 和更小的止盈目标 {profit_target_pct}，同时降低 {rebalance_freq_days} 以快速离场，减少持仓时间暴露；信号触发频率下降，仓位上限同步降低。
上述调整均通过优化对应参数实现，回测或实盘中可针对不同阶段进行参数分档配置。

### 3. 多信号逻辑关系
- **入场时机**：每天计算三个子信号的得分，按权重汇总形成个股入场强度。信号1（趋势）权重0.5，信号2（量能）0.25，信号3（动量）0.25，总分达到阈值或排名靠前者入选。这确保只有在短中期趋势向上、成交活跃且非超买区才建仓。
- **出场优先级**：出场信号按weight降序依次检核，任一触发立即执行全部平仓。优先级为：固定止损（本金保护，weight 0.30）> ATR动态止损（波动自适应，0.20）> 移动止损（利润保护，0.20）> 止盈（目标兑现，0.20）> 时间止损（防久拖，0.05）> 趋势反转（均线死叉，0.05）。这种层级确保先防亏损再保利润，最后再考虑趋势转弱。

### 4. 风险机制
与纯均线策略相比，本策略引入三层动态风控：ATR动态止损适应个股波动率，避免固定止损在低波股过宽、高波股过窄的问题；20日最高价移动止损在趋势行进中上移止损线，保护浮盈；固定止盈防收益坐过山车。核心风控要点：(1) 单票仓位硬上限 {max_single_weight} 与行业集中度上限 {max_industry_concentration} 双重分散非系统性风险；(2) 再平衡换手率上限 {max_turnover_per_rebalance} 约束交易频率，控制成本；(3) 所有止损止盈比例均param化，可针对市场状态快捷调整。特殊场景：涨跌停时无法成交，出场信号被吞，但下一交易日重新评估；策略假设流动性充裕，不设滑点模型。

### 5. NaN 处理（A 股硬约束）
1. **上市未满计算周期**：新股上市不足30日（ma_30计算窗口）导致对应因子为NaN，该股票在这些交易日不参与信号计算，待累积足够数据后自动纳入选股池，避免因子缺失产生错误信号。
2. **长期停牌**：停牌期间无行情数据，所有因子无法更新。复牌当日通常波动巨大且因子失真（如均线断层），因此复牌后至少等待 {rebalance_freq_days} 个交易日，待短期因子（ma_10、rsi_14等）充分回填后再参与信号评估。
3. **涨跌停**：主板±10%、创业板/科创板±20%、ST±5%。当日触及涨跌停板且封死至收盘，则所有出场信号视为被吞无法执行（入场信号在开盘判断，不受影响）。次日重新按开盘价判断。
4. **一字板**：开盘即涨停或跌停且无成交，当日视为无法交易，所有入场出场信号均无效，跳过该交易日，不产生任何持仓变动。