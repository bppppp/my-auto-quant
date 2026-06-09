---
name: donchian_breakout_vol_rsi_ma
targets:
  annual_return: 0.25
  win_rate: 0.45
  profit_loss_ratio: 3.5
  sharpe: 1.3
  max_drawdown: -0.18
  description: 基于Donchian通道突破+成交量放大+趋势与RSI过滤，配合多级止损的中周期波段策略。目标年化25%，胜率45%，盈亏比3.5，夏普1.3，最大回撤18%。
test_universe:
- HS300
factors:
- name: donchian_high_20
  description: 20日最高价，Donchian通道上轨，突破关键阻力
  calculation: max(high, 20)
- name: donchian_low_20
  description: 20日最低价，Donchian通道下轨，跌破关键支撑
  calculation: min(low, 20)
- name: ma_20
  description: 20日简单移动平均线，衡量短期趋势
  calculation: mean(close, 20)
- name: ma_60
  description: 60日简单移动平均线，衡量中期趋势
  calculation: mean(close, 60)
- name: atr_14
  description: 14日平均真实波幅，衡量市场波动程度
  calculation: atr(high, low, close, 14)
- name: volume_ratio_20
  description: 当日成交量与20日均量之比，衡量放量程度
  calculation: volume / mean(volume, 20)
- name: rsi_14
  description: 14日相对强弱指标，量化短期超买超卖状态
  calculation: 100 - 100 / (1 + mean(gain, 14) / mean(loss, 14))
entry_signals:
- name: breakout_entry
  weight: 0.5
  factors:
  - donchian_high_20
  - volume_ratio_20
  direction: positive
  trigger: close > donchian_high_20 AND volume_ratio_20 > {vol_breakout_threshold}
  logic: AND
- name: trend_entry
  weight: 0.3
  factors:
  - ma_20
  - ma_60
  direction: positive
  trigger: ma_20 > ma_60 AND close > ma_20
  logic: AND
- name: rsi_entry
  weight: 0.2
  factors:
  - rsi_14
  direction: positive
  trigger: rsi_14 > {rsi_entry_low} AND rsi_14 < {rsi_entry_high}
  logic: AND
exit_signals:
- name: fixed_stop_loss
  weight: 0.3
  factors: []
  direction: negative
  trigger: current_price < entry_price * (1 - {fixed_stop_loss_pct})
  logic: 单因子
- name: trailing_stop
  weight: 0.2
  factors: []
  direction: negative
  trigger: current_price < highest_close_since_entry * (1 - {trail_stop_pct})
  logic: 单因子
- name: volatility_stop
  weight: 0.2
  factors:
  - atr_14
  direction: negative
  trigger: current_price < highest_close_since_entry - {atr_stop_multiplier} * atr_14
  logic: 单因子
- name: trend_reversal_exit
  weight: 0.15
  factors:
  - donchian_low_20
  direction: negative
  trigger: close < donchian_low_20
  logic: 单因子
- name: overbought_reduce
  weight: 0.1
  factors:
  - rsi_14
  direction: negative
  trigger: rsi_14 > {rsi_overbought} AND pnl_pct > {partial_profit_pct}
  logic: AND
- name: time_stop
  weight: 0.05
  factors: []
  direction: negative
  trigger: holding_days >= {max_holding_days}
  logic: 单因子
position_weights:
  max_single_weight: 0.1
  max_industry_concentration: 0.25
  target_holdings: 10
  max_turnover_per_rebalance: 0.5
  rebalance_freq_days: 5
params:
- name: rsi_entry_low
  default: 42
  range:
  - 25
  - 60
  type: int
  description: RSI入场下限，避免在极度超卖时入场。单位：数值。典型取值30-50，默认40确保短期动量已从低位回升，减少接飞刀风险。
  reason: 下修至42，扩大入场机会，捕捉RSI回暖个股，提升胜率。
- name: rebalance_freq_days
  default: 5
  range:
  - 1
  - 10
  type: int
  description: 再平衡频率，每隔该交易日数检查信号并调仓。单位：交易日。典型取值3-7，默认5天在及时跟进信号与减少操作噪音间取得平衡。
  reason: 维持5日，平衡信号响应与操作成本。
- name: rsi_overbought
  default: 70
  range:
  - 60
  - 85
  type: int
  description: RSI超买阈值，触发盈利减仓的条件之一。单位：数值。典型取值70-80，默认75略高于入场上限，减少过早止盈，保留头部利润。
  reason: 上调至70，提高减仓门槛，让利润充分发展。
- name: max_holding_days
  default: 35
  range:
  - 15
  - 60
  type: int
  description: 最大持仓交易日数，超时强制平仓。单位：交易日。典型取值15-40，默认25贴合中周期波段目标，防止被动转为长期套牢。
  reason: 延长至35天，允许盈利股充分运行，改善盈亏比。
- name: trail_stop_pct
  default: 0.1
  range:
  - 0.03
  - 0.15
  type: float
  description: 移动止损比例，从最高收盘价回撤该比例时触发。单位：小数。典型取值0.04-0.10，默认0.06适合10-30天波段，让利润充分发展但及时锁定。
  reason: 放宽至0.10，降低噪声触发，让趋势持仓更持久。
- name: reduce_position_floor
  default: 0.03
  range:
  - 0.01
  - 0.06
  type: float
  description: 减仓后个股最低持仓权重，避免在震荡中彻底清仓丢失头寸。单位：小数（总资产比）。典型取值0.02-0.05，默认0.03保留微小仓位跟踪信号。
  reason: 维持0.03底仓，保留信号跟踪。
- name: atr_stop_multiplier
  default: 2.8
  range:
  - 1.5
  - 4.0
  type: float
  description: ATR动态止损倍数，止损距离=该倍数×ATR。单位：倍数。典型取值1.5-3.0，默认2.0在过滤市场噪音与保护趋势利润之间平衡。
  reason: 上调至2.8，放宽波动止损，容纳合理回撤，减少过早离场。
- name: fixed_stop_loss_pct
  default: 0.11
  range:
  - 0.05
  - 0.2
  type: float
  description: 固定止损比例，单笔最大亏损限制。单位：小数（相对成本价）。典型取值0.05-0.10，默认0.08在容忍正常波动与保护本金间取得均衡。
  reason: 微收至0.11，进一步控制单笔极端亏损，防风险蔓延。
- name: target_holdings
  default: 10
  range:
  - 4
  - 15
  type: int
  description: 目标持仓股票数量，调仓时尽量维持。单位：只。典型取值6-12，默认8在分散与集中之间平衡，确保每只股票能获得足够权重。
  reason: 维持10只不变，平衡分散与收益潜力。
- name: max_single_weight
  default: 0.1
  range:
  - 0.03
  - 0.2
  type: float
  description: 单只股票最大持仓权重，控制组合集中度风险。单位：小数。典型取值0.05-0.15，默认0.10与目标持仓8只匹配，实现适度分散。
  reason: 上调至0.10，适度集中，增强强势股贡献。
- name: add_position_weight_threshold
  default: 0.6
  range:
  - 0.5
  - 1.0
  type: float
  description: 加仓信号综合得分阈值（入场信号权重和），超过该值可将个股仓位加至上限。单位：比例。典型取值0.6-0.9，默认0.7要求信号共振明显才加满。
  reason: 下调至0.6，放宽加仓条件，让高确信信号获更多仓位。
- name: vol_breakout_threshold
  default: 1.6
  range:
  - 1.0
  - 3.5
  type: float
  description: 成交量突破倍数阈值，决定入场时的量能要求。单位：倍数。典型取值1.2-2.0，A股有效突破通常放量1.5倍以上，默认1.5平衡信号数量与质量。
  reason: 调低至1.6，增加有效突破信号，提升入场机会。
- name: max_turnover_per_rebalance
  default: 0.5
  range:
  - 0.2
  - 0.8
  type: float
  description: 单次再平衡最大换手率，控制交易成本和冲击。单位：小数。典型取值0.30-0.70，默认0.50允许灵活调整但避免过度频繁换股。
  reason: 维持0.5不变，控制交易成本。
- name: max_industry_concentration
  default: 0.25
  range:
  - 0.15
  - 0.5
  type: float
  description: 行业暴露上限，限制同一行业总权重。单位：小数。典型取值0.20-0.40，默认0.30防止行业系统性风险过度集中，保障组合稳健。
  reason: 维持0.25，严控行业风险，预防系统性回撤。
- name: partial_profit_pct
  default: 0.15
  range:
  - 0.05
  - 0.3
  type: float
  description: 触发盈利减仓的最低累计收益率。单位：小数。典型取值0.10-0.25，默认0.15确保在已有可观利润后再执行减仓，避免微利卖出。
  reason: 回升至0.15，确保可观盈利后再减仓，提升单笔利润。
- name: reduce_position_weight_threshold
  default: 0.38
  range:
  - 0.15
  - 0.55
  type: float
  description: 减仓信号综合得分阈值（出场信号权重和），超过该值将个股仓位降至下限。单位：比例。典型取值0.2-0.4，默认0.3在趋势转弱时适度降仓。
  reason: 微升至0.38，延缓减仓，保留趋势仓位，提升潜在收益。
- name: rsi_entry_high
  default: 70
  range:
  - 50
  - 80
  type: int
  description: RSI入场上限，防止在严重超买时追高。单位：数值。典型取值60-80，默认70允许在较强趋势中入场，但规避极端过热状态。
  reason: 上调至70，放宽入场区间，捕捉强势动量个股。
description: 基于Donchian通道突破+成交量放大+趋势与RSI过滤，配合多级止损的中周期波段策略。
universe: 沪深 300
holding_period: 10-30 个交易日
rebalance_freq: 每 5 个交易日强制再平衡
---

## 策略业务逻辑叙事

### 1. 策略思路 / edge 来源
本策略捕捉A股市场中‘趋势延续+突破效应’带来的中期收益。核心逻辑：股价突破20日最高价（Donchian上轨）往往是一轮中级行情的起点，配合成交量放大（{vol_breakout_threshold}）能过滤假突破。同时，利用20/60日均线交叉确认中期趋势方向，避免逆势操作；RSI（14日）反映短期动量，限制在{ rsi_entry_low }至{ rsi_entry_high }之间入场，可规避极端超买超卖带来的反转风险。Edge来源：A股因散户主导、信息逐步扩散，趋势一旦形成常有惯性；突破关键阻力后追涨资金涌入，加之成交量验证，提供确定性较强的波段机会。策略设计为10-30天持仓，通过多级止损保护资本，跨牛熊稳健运行。

### 2. 市场环境假设
策略在存在明显趋势的市场（单边上涨或下跌）中表现最佳，能有效捕捉方向性波动；在宽幅震荡市中，趋势过滤和RSI限制会减少无效入场，但可能产生少量小亏，依靠固定止损和时间止损控制。不适用环境：极端低波动、连续窄幅横盘且无成交量放大，此时突破多为假信号；市场流动性枯竭或政策干预导致的硬拐点，策略滞后性可能带来较大回撤，但ATR动态止损能部分缓解。

### 3. 牛 / 熊 / 震荡 3 环境处理（所有阈值 param 化）
- **牛市**：当大盘及个股站稳60日均线且突破信号频繁时，策略倾向满仓运行。此时移动止损参数{ trail_stop_pct }可适当放宽，ATR倍数{ atr_stop_multiplier }可设于范围上限，让趋势充分发展。加仓阈值{ add_position_weight_threshold }可降低，以便快速把仓位提升至上限{ max_single_weight }。目标持仓数{ target_holdings }可维持标准，通过高收益个股贡献利润。
- **熊市**：价格普遍运行在60日均线下方。策略通过严格的固定止损{ fixed_stop_loss_pct }（可调更紧）和ATR波动止损快速离场。入场时，要求更强的趋势确认（ma_20 > ma_60 且 close > ma_20 更严格），并提高成交量阈值{ vol_breakout_threshold }，减少弱反弹入场。减仓阈值{ reduce_position_weight_threshold }降低，仓位更易收缩至{ reduce_position_floor }。整体持仓权重因信号稀疏而自然低于牛市。
- **震荡市**：RSI高/低阈值{ rsi_entry_high }/{ rsi_entry_low }过滤大量噪音，时间止损{ max_holding_days }缩短（偏向范围下限），避免资金长时间锁定。信号综合得分难达加仓阈值{ add_position_weight_threshold }，多数情况仅以基础权重配置，目标持仓数{ target_holdings }可能无法满员，被动降低净暴露。出场信号中减仓机制更频繁触发，确保微利落袋。

### 4. 多信号逻辑关系
- **入场时机**：策略采用多信号共振模型。breakout_entry 是核心驱动（权重0.5），必须与 trend_entry（权重0.3）和/或 rsi_entry（权重0.2）同时满足，即至少两个入场信号触发，才会生成有效买入指令。实际操作中，综合得分 = Σ(触发信号的权重)，系统按得分排序，选择 top N 进入组合，N 由 { target_holdings } 动态确定。若信号不足，则降低持仓数量。
- **出场优先级**：固定止损 fixed_stop_loss 权重最高（0.30），为无条件第一道防线；其次 trailing_stop（0.20）和 volatility_stop（0.20）并列，锁定浮赢；趋势反转 exit trend_reversal_exit（0.15）在跌破下轨时离场；盈利减仓 overbought_reduce（0.10）仅在已盈利且 RSI 超买时生效；时间止损 time_stop（0.05）作为最后的强制退出。当多个出场信号同时触发时，按权重降序执行（如固定止损优先于时间止损）。

### 5. 风险机制
- **熊市风控**：除前述收紧参数外，通过降低单票最大权重 { max_single_weight } 和行业暴露 { max_industry_concentration }，分散系统性风险；调仓频率 { rebalance_freq_days } 可适度加快以快速响应。
- **涨跌停挤不出场**：若股票发生跌停，所有出场信号当日无效（被吞），策略不会虚假记录‘已止损’。系统跟踪‘被吞次数’，下一个交易日继续按原信号判断。涨停买入信号同样被吞，不强行排队，避免‘买到就是跌’的陷阱。
- **早期数据 NaN 处理（A股硬约束）**：
  1. 上市未满 N 日：如 ma_60 需要60个交易日历史，上市不足60日的股票，其 ma_60 等因子值为 NaN。策略规定：该股票当日不参与信号计算（不剔除出股票池），待满足数据长度后自动纳入。
  2. 长期停牌：停牌期间无成交，因子值停滞或为 NaN。复牌当日，由于近期数据缺失可能导致均线等指标失真，策略要求复牌后等待至少 5 个交易日数据回填，再将该股票重新纳入信号计算范围。
  3. 涨跌停日：涨停日入场信号仍然照常计算（依据开盘前数据），但实际能否成交取决于队列；跌停日所有出场信号被吞，不产生成交，避免在流动性枯竭时砸盘。策略日志记录此类事件。
  4. 一字板 / 退市：新股上市初期连续一字板，因子可能部分有效但无法买入，默认跳过；确定退市股票从候选池剔除，回测时不纳入，避免退市整理期的异常波动干扰。
- **优先级链**：出场信号按 weight 降序享有执行优先权：fixed_stop_loss > trailing_stop / volatility_stop > trend_reversal_exit > overbought_reduce > time_stop。同一优先级内，先触发先执行。

### 6. 与其他策略区别
本策略区别于单纯均线交叉策略，加入了 Donchian 突破和成交量确认，降低了横盘震荡中的假信号频率；不同于高频或日内策略，目标持仓 1-3 周，交易成本可控；与纯动量策略不同，融入 RSI 过滤和移动/ATR 止损，确保不追在极端位置，同时用时间止损防止持仓僵化。