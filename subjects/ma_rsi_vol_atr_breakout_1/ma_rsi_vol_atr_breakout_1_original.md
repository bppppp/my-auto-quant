---
name: ma_rsi_vol_atr_breakout_1
targets:
  annual_return: 0.28
  win_rate: 0.48
  profit_loss_ratio: 3.2
  sharpe: 1.2
  max_drawdown: -0.18
  description: 双均线趋势+RSI动量过滤+成交量确认，ATR自适应止损与移动止盈搭配，期望年化28%，胜率48%，盈亏比3.2，夏普1.2，最大回撤18%。
factors:
- name: ma_10
  description: 10日简单移动平均线
  calculation: mean(close, 10)
- name: ma_30
  description: 30日简单移动平均线
  calculation: mean(close, 30)
- name: rsi_14
  description: 14日相对强弱指标
  calculation: 100 - 100 / (1 + mean(gain, 14) / mean(loss, 14))
- name: atr_14
  description: 14日平均真实波幅
  calculation: atr(high, low, close, 14)
- name: volume_ratio_20
  description: 量比（当日成交量/20日均量）
  calculation: volume / mean(volume, 20)
- name: highest_close_since_entry
  description: 入场后最高收盘价（用于移动止盈/止损）
  calculation: max(close_since_entry)
entry_signals:
- name: trend_momentum_confirm
  weight: 0.6
  factors:
  - ma_10
  - ma_30
  - rsi_14
  direction: positive
  trigger: ma_10 > ma_30 AND rsi_14 > {rsi_lower} AND rsi_14 < {rsi_upper}
  logic: AND
- name: volume_breakout
  weight: 0.4
  factors:
  - volume_ratio_20
  direction: positive
  trigger: volume_ratio_20 > {volume_breakout}
  logic: 单因子
exit_signals:
- name: atr_stop
  weight: 0.35
  factors:
  - atr_14
  direction: negative
  trigger: close < entry_price - {atr_stop_multiple} * atr_14
  logic: 单因子
- name: trailing_stop
  weight: 0.3
  factors:
  - highest_close_since_entry
  direction: negative
  trigger: close < highest_close_since_entry * (1 - {trailing_stop_pct})
  logic: 单因子
- name: ma_death_cross
  weight: 0.2
  factors:
  - ma_10
  - ma_30
  direction: negative
  trigger: ma_10 < ma_30
  logic: AND
- name: time_stop
  weight: 0.15
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
- name: rsi_lower
  default: 35
  range:
  - 20
  - 50
  type: int
  description: RSI下限阈值（单位：数值，0-100）。典型取值30-40，默认35，过滤超卖区但不过度严格，确保标的已有企稳迹象。
- name: rsi_upper
  default: 70
  range:
  - 50
  - 80
  type: int
  description: RSI上限阈值（单位：数值，0-100）。典型取值65-75，默认70，防止在极度超买区追高，降低回调风险。
- name: volume_breakout
  default: 1.5
  range:
  - 1.2
  - 3.0
  type: float
  description: 成交量突破倍数（单位：倍数）。典型取值1.3-2.0，默认1.5，要求当日量至少为20日均量的1.5倍，确认增量资金介入。
- name: atr_stop_multiple
  default: 2.0
  range:
  - 1.5
  - 4.0
  type: float
  description: ATR止损倍数（单位：倍数）。典型取值1.5-3.0，默认2.0，以入场价为基准向下2倍14日ATR设置初始止损，自适应波动率。
- name: trailing_stop_pct
  default: 0.06
  range:
  - 0.03
  - 0.12
  type: float
  description: 移动止损回撤比例（单位：小数）。典型取值0.05-0.10，默认0.06，即从入场后最高收盘价回撤6%时平仓，锁定部分浮盈。
- name: max_holding_days
  default: 30
  range:
  - 15
  - 60
  type: int
  description: 最大持仓天数（单位：交易日）。典型取值20-40，默认30，防止资金长期占用，保证中线波段的周转效率。
- name: max_single_weight
  default: 0.1
  range:
  - 0.05
  - 0.2
  type: float
  description: 单只股票最大仓位权重（单位：小数）。典型取值0.05-0.15，默认0.10，兼顾集中度收益与个股黑天鹅风险。
- name: max_industry_concentration
  default: 0.3
  range:
  - 0.2
  - 0.45
  type: float
  description: 单一行业最大集中度（单位：小数）。典型取值0.25-0.40，默认0.30，避免行业系统性风险导致净值大幅波动。
- name: target_holdings
  default: 8
  range:
  - 5
  - 15
  type: int
  description: 目标持仓数量（单位：只）。典型取值5-12，默认8，平衡资金利用率与组合分散效果，降低非系统性风险。
- name: max_turnover_per_rebalance
  default: 0.5
  range:
  - 0.3
  - 0.7
  type: float
  description: 单次调仓最大换手率（单位：小数）。典型取值0.30-0.60，默认0.50，控制交易成本与市场冲击，避免频繁换手。
- name: rebalance_freq_days
  default: 5
  range:
  - 1
  - 10
  type: int
  description: 调仓频率（单位：交易日）。典型取值1-10，默认5，每5个交易日强制再平衡，保持组合纪律同时降低过度交易。
description: 双均线趋势+RSI动量+成交量确认，ATR自适应止损与移动止盈的中周期波段策略。
universe: 沪深300
holding_period: 15-30个交易日
rebalance_freq: 每5个交易日强制再平衡
test_universe:
- HS300
---

## 策略业务逻辑叙事

### 1. 策略思路 / edge 来源（含市场环境假设）
本策略捕捉A股中周期趋势的延续效应，核心假设是：当短期均线上穿长期均线形成“金叉”时，市场处于多头趋势初期或延续阶段，配合RSI处于非超买区间（{rsi_lower}~{rsi_upper}）排除过热追涨，同时要求成交量显著放大（量比>{volume_breakout}），确认机构资金或活跃资金参与。A股市场中，趋势一旦确立往往具有惯性，右侧交易者跟进可获取波段收益。
- 市场环境假设：适用于存在明显30~60度上升斜率的中期趋势行情。震荡市因缺乏方向性，信号密度降低，可通过调高阈值减少无效开仓；单边熊市则通过ATR止损与收紧条件保护本金。
- 优势来源：多维度信号共振（价格、动量、量能）提高胜率，自适应ATR止损动态匹配波动率，移动止盈锁定大部分利润，克服纯均线策略回撤过大的弱点。

### 2. 牛 / 熊 / 震荡 3 环境处理（所有阈值 param 化）
- **牛市环境**：默认参数即可运行，两信号全部成立时满仓入场。可选择性地上调{max_single_weight}至0.12~0.15，并配合上移{trailing_stop_pct}至0.08，让盈利充分发展。
- **熊市环境**：主动收紧入场条件，例如将{rsi_lower}提高至40、{rsi_upper}降低至60、{volume_breakout}提高至2.0，以提高信号质量；同时降低{max_single_weight}至0.06，减少暴露；缩短{max_holding_days}至20，加快止损止盈。这些调整全部通过参数组合完成。
- **震荡市环境**：信号稀疏，增加{rebalance_freq_days}至10，降低调仓频率；收紧{atr_stop_multiple}至1.5~1.8，减小止损缓冲；时间止损仍有效，避免资金被无效占用。所有阈值均为param，用户可根据市场特征灵活配置。

### 3. 多信号逻辑关系
- **入场时机**：两个入场信号必须同时满足（AND关系）。`trend_momentum_confirm`（权重0.6）负责趋势-动量检验，`volume_breakout`（权重0.4）负责量能确认。两者同时为真才生成买入信号，两个信号权重和决定组合内排序，但入场逻辑为刚性AND，不满足其一则不开仓。
- **出场优先级**：出场信号按权重降序遍历，一旦任一信号触发立即平仓，不等待其他信号。优先级链为：ATR止损（0.35，本金保护第一）→ 移动止损（0.30，浮盈保护）→ 均线死叉（0.20，趋势反转信号）→ 时间止损（0.15，防止无方向占用资金）。权重反映紧急程度，backtest框架据此顺序依次判断。

### 4. 风险机制
与普通双均线策略相比，本策略核心差异：（1）增加ATR自适应初始止损，止损距离随波动率动态调整，避免固定百分比止损在低波股中太宽、高波股中太窄的缺陷；（2）移动止损基于入场后最高收盘价回撤，保护已积累的浮盈；（3）多信号入场过滤显著降低假突破次数，尤其在震荡市中通过量能验证避免“毛刺”。
- **风控要点**：单票最大权重{max_single_weight}、行业集中度{max_industry_concentration}、目标持仓数{target_holdings}共同控制组合风险暴露；调仓换手率{max_turnover_per_rebalance}限制交易成本；时间止损防止长期套牢。
- **极端场景**：涨跌停或一字板时，所有出场信号均可能因无法成交而被吞，系统将在回测报告中记录“信号被吞次数”，以反映流动性风险，不影响其他信号逻辑。

### 5. NaN 处理（A 股硬约束）
- **上市未满 N 日**：所有因子（如ma_10、ma_30、rsi_14、atr_14）均依赖一定长度的窗口数据。上市不满30个交易日的股票，相关因子值为NaN，该股票当日不参与任何信号计算，直接跳过，待满窗口期后自动纳入。
- **停牌处理**：股票停牌期间无行情数据，所有因子无法更新，该股持续不产生信号。复牌后需重新累积至少N日（如30日）数据后才会重新参与计算，避免数据断层导致的错误信号。
- **涨跌停日**：若某日股票封涨/跌停板，入场或出场信号虽正常产生，但可能因流动性缺失无法成交。策略层不做特殊处理，由backtest执行层负责判定是否实际成交：若未成交，则信号被吞，不改变持仓状态，并在报告中标记。
- **一字板情况**：连续一字涨停或一字跌停视为涨跌停的极端情形，处理规则同上——信号产生但无法执行，且一字板期间股价不产生新的最高/最低记录，因此移动止损等信号不会错误触发。退市、ST等特殊状态默认全部跳过，不参与回测。