---
name: trend_atr_volume_strategy_1
targets:
  annual_return: 0.25
  win_rate: 0.5
  profit_loss_ratio: 3.2
  sharpe: 1.3
  max_drawdown: -0.18
  description: 双均线趋势+波动扩张+量能确认，预期年化25%，胜率50%，盈亏比3.2，夏普1.3，最大回撤18%。
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
  description: 当日成交量/20日均量
  calculation: volume / mean(volume, 20)
- name: highest_close_20
  description: 20日内最高收盘价（移动止损基准）
  calculation: max(close, 20)
entry_signals:
- name: ma_trend_up
  weight: 0.4
  factors:
  - ma_10
  - ma_30
  direction: positive
  trigger: ma_10 > ma_30
  logic: 单因子
- name: volatility_expand
  weight: 0.3
  factors:
  - atr_14
  direction: positive
  trigger: atr_14 / close > {atr_min_threshold}
  logic: 单因子
- name: volume_confirm
  weight: 0.3
  factors:
  - volume_ratio_20
  direction: positive
  trigger: volume_ratio_20 > {volume_breakout_ratio}
  logic: 单因子
exit_signals:
- name: fixed_stop_loss
  weight: 0.5
  factors: []
  direction: negative
  trigger: current_price < entry_price * (1 - {fixed_stop_pct})
  logic: 单因子
- name: trailing_stop
  weight: 0.3
  factors:
  - highest_close_20
  direction: negative
  trigger: current_price < highest_close_20 * (1 - {trailing_stop_pct})
  logic: 单因子
- name: time_stop
  weight: 0.2
  factors: []
  direction: negative
  trigger: holding_days >= {max_holding_days}
  logic: 单因子
position_weights:
  max_single_weight: 0.1
  max_industry_concentration: 0.3
  target_holdings: 10
  max_turnover_per_rebalance: 0.5
  rebalance_freq_days: 5
params:
- name: atr_min_threshold
  default: 0.015
  range:
  - 0.005
  - 0.05
  type: float
  description: ATR波动率最小阈值，单位为小数比例（ATR/收盘价），要求波动率超过此值才入场。典型取值0.01-0.02，默认0.015基于沪深300历史波动率中位数，既能过滤低波动无效信号，又不至于门槛过高而错过机会。
- name: volume_breakout_ratio
  default: 1.5
  range:
  - 1.0
  - 3.0
  type: float
  description: 成交量放大倍数阈值，要求当日成交量超过20日均量的倍数。典型取值1.3-2.0，默认1.5表示需要中等程度的放量确认，避免无量虚涨。
- name: entry_score_threshold
  default: 0.7
  range:
  - 0.5
  - 1.0
  type: float
  description: 入场综合得分阈值，三个入场信号加权总分达到此值才开仓。典型取值0.6-0.8，默认0.7要求至少两个高权重信号（0.4+0.3=0.7）同时触发，平衡信号严格性与机会数量。
- name: fixed_stop_pct
  default: 0.08
  range:
  - 0.05
  - 0.2
  type: float
  description: 固定止损比例，单位为小数，当股价较入场价下跌超过此比例时无条件止损。典型取值0.05-0.10，默认8%覆盖A股中周期正常波动，避免被洗出。
- name: trailing_stop_pct
  default: 0.06
  range:
  - 0.02
  - 0.15
  type: float
  description: 移动止损回撤比例，当股价从20日高点回撤超过此比例时止盈出场。典型取值0.03-0.10，默认6%旨在保护浮盈的同时让利润适度奔跑。
- name: max_holding_days
  default: 30
  range:
  - 10
  - 60
  type: int
  description: 最大持仓天数，超过此交易日数则强制平仓出场。典型取值20-40天，默认30天对应中周期波段时长，防止长期持股转化为被动投资。
- name: rebalance_freq_days
  default: 5
  range:
  - 1
  - 20
  type: int
  description: 调仓间隔天数，每过此天数扫描信号并调整持仓。典型取值3-10天，默认5天减少交易频率，降低手续费和滑点影响。
- name: max_single_weight
  default: 0.1
  range:
  - 0.03
  - 0.25
  type: float
  description: 单只股票最大持仓权重，控制集中度风险。典型取值0.05-0.15，默认10%避免单一黑天鹅对组合造成过大冲击。
- name: max_industry_concentration
  default: 0.3
  range:
  - 0.1
  - 0.5
  type: float
  description: 单一行业最大持仓集中度，控制行业系统性风险。典型取值0.20-0.40，默认30%适度分散，降低政策或行业利空影响。
- name: target_holdings
  default: 10
  range:
  - 5
  - 30
  type: int
  description: 目标持仓股票数量，策略同时持有的最大股票数。典型取值5-20只，默认10只平衡集中度与分散效果。
- name: max_turnover_per_rebalance
  default: 0.5
  range:
  - 0.2
  - 0.8
  type: float
  description: 单次再平衡最大换手率，限制每次调仓的成本和延迟。典型取值0.30-0.60，默认50%允许灵活调整同时控制交易损耗。
description: 双均线趋势 + ATR波动扩张 + 量能确认的中周期波段策略，通过加权评分入场，多级止损出场。
holding_period: 15-30 个交易日
rebalance_freq: 每 5 个交易日再平衡
test_universe:
- HS300
universe: 沪深 300
---

## 策略业务逻辑叙事

### 1. 策略思路 / edge 来源（含市场环境假设）
本策略基于A股市场中周期趋势惯性效应，通过多条件过滤捕捉确定性较高的波段行情。核心假设是：一旦趋势形成，在均线、波动和量能三个维度上会呈现协同特征，这种协同状态的延续性能带来可观的超额收益。A股市场散户参与度高，容易出现非理性趋势，而本策略利用10/30日双均线交叉判断方向，结合ATR扩张确认潜在空间，量能放大验证资金意图，三重过滤显著提高胜率。在牛市环境下，趋势延续性强，策略满仓运行；在熊市和震荡市，由于入场条件严格，自然保持空仓或极低仓位，实现被动风控。

### 2. 牛 / 熊 / 震荡 3 环境处理（所有阈值 param 化）
- **牛市环境**：市场整体向上，均线系统呈现多头排列，ma_10持续高于ma_30，入场信号频繁触发。此时策略维持满仓，移动止损（{trailing_stop_pct}=6%）有效跟随趋势，让利润充分发展。可通过适当降低{entry_score_threshold}（如至0.5）或降低{volume_breakout_ratio}扩大捕捉面，但避免过度激进。
- **熊市环境**：均线空头排列，ma_10在ma_30下方，入场第一条件即不满足，策略自然空仓。即使市场出现短暂反弹，固定止损（{fixed_stop_pct}=8%）可硬性限制任何意外亏损。设计上，熊市下参数{fixed_stop_pct}可调紧如5%，但默认值已较保守。
- **震荡环境**：价格区间窄幅震荡，ATR较低，难以超过{atr_min_threshold}，成交量也常萎缩，入场信号难以同时达到阈值{entry_score_threshold}，策略保持空仓或低仓。时间止损{max_holding_days}避免了持仓在震荡中无意义拖长。所有环境参数均可通过回测优化调整为特定时段更优值，无需实时识别市场状态。

### 3. 多信号逻辑关系
- **入场时机**：采用加权评分制，而非简单AND/OR逻辑。三个独立入场信号各自根据trigger判断，触发则贡献其权重分：ma_trend_up权重0.4（作为核心趋势判断，提供基本方向），volatility_expand权重0.3（波动扩张意味着潜在获利空间，是必要的风险补偿确认），volume_confirm权重0.3（量能确认资金跟进，避免无量虚涨）。每日计算总分，当总分达到{entry_score_threshold}（默认0.7）时，触发实际买入。该机制要求至少两个高权重信号同时成立（0.4+0.3=0.7），既保证信号质量又保持一定灵活性。
- **出场优先级**：与入场不同，出场采用硬性的优先级链机制，而非加权评分。固定止损（weight 0.5）优先级最高，一旦触发立即平仓，防止亏损扩大；移动止损（weight 0.3）优先级第二，基于20日高点动态回撤{trailing_stop_pct}止盈，用于保护已有浮盈；时间止损（weight 0.2）优先级最低，在持仓天数超过{max_holding_days}时强制出场，避免变为被动长持。权重在此表示各信号在策略设计中的重要性排序，而实际执行严格按优先级顺序：系统先检查固定止损，若未触发则检查移动止损，最后检查时间止损。这种安排确保了资本保护永远优先于利润保护。

### 4. 风险机制
相较于普通的均线交叉策略，本策略引入波动与量能双重确认，大幅减少了震荡市中的无效交易和假突破带来的亏损。核心风控包括：（1）固定止损{fixed_stop_pct}硬性控制单笔最大损失，无论任何情况均执行；（2）移动止损{trailing_stop_pct}在盈利后动态上移止盈点，防止盈利大幅回吐；（3）时间止损{max_holding_days}切断长期持仓的不确定性。组合层面，{max_single_weight}、{max_industry_concentration}、{target_holdings}等参数严格控制个股和行业集中度，避免单一事件冲击。对于A股特有的涨跌停和停牌情况，runner层已内置处理机制（如涨跌停日出场信号被吞，次日重试），策略本身专注于信号生成，不介入流动性执行细节。

### 5. NaN 处理（A 股硬约束）
- **上市未满N日**：由于因子窗口（如ma_30需30个交易日，atr_14需14个交易日），新上市股票在数据不足时对应因子值为NaN。这些股票在该日被排除出信号计算，但保留在候选池中，待数据累积足够后自动纳入。
- **长期停牌**：停牌期间无交易数据，因子无法更新。复牌首日因短期价格可能异常且数据断层，策略规定复牌后需重新积累至少10个交易日数据（或因子所需最大窗口的一半）后方可重新参与信号评估，期间标记为不可交易。
- **涨跌停板**：买入信号在开盘时基于前一日收盘价计算，若股价开盘即涨停，买入信号虽可触发但无法成交；卖出信号若在跌停价无法成交，系统会记录并在下一交易日继续尝试。策略设计上不因这些微观成交问题而改变信号逻辑，默认由backtest引擎模拟成交与否。
- **一字板**：新股上市初期的连续一字板或重大事件导致的一字板，由于无法成交且波动异常，策略将其视为非正常交易状态，直接跳过，不生成任何买卖信号。