# Public Parts Summary（append-only）

> 本文件由所有策略的公共部分汇总而成。
> **只能追加新行，不能修改/删除现有行。** 违反此约束会破坏其他依赖这些公共部分的策略。
> 配合 `subject_structure.md` §9 的"LLM 读取顺序"使用：LLM 需先读本文件判断"现有公共函数是否满足新策略需求"。

## 0. 检索与判定规则

LLM 翻译 spec 到 `generated/strategy.py` 时，按以下 3 个**检索对象**做语义匹配（**不按 name 字面匹配**，不同策略可能用同名变量但语义不同，详见 `subject_structure.md` §2.3 / §9.2 步骤 1）：

| 检索对象 | 检索位置（PARTS_SUMMARY） | 命中后动作 |
|---|---|---|
| ① spec `factors[]` 的 `description` 字段 | §1 公共因子 | import 公共函数，按 §4.2.2 命名约定调用 |
| ② spec `entry_signals` / `exit_signals` 的 `trigger` 字符串的判断意图（如 "RSI 在 40-70 区间"） | §2 公共条件原语 | strategy.py 内**调**该公共 condition |
| ③ spec `entry_signals` / `exit_signals` 列表项的 `factors` 字段引用的因子名 | §1 公共因子（同 ①） | 同 ① |

- 检索命中 → 直接复用，import 公共函数即可。
- 检索 ①/③ 未命中但按语义判定为公共 → 生成新因子函数 + **同步在本文件 §1 追加完整条目**。
- 检索 ② 未命中 → strategy.py 内手写 if-else，**不抽公共**（trigger 翻译是 strategy.py 内部逻辑，runner 不感知）。
- 写入规则详见末尾 §6。

---

## 1. Factors（公共因子）

### `ma`
- **Signature**：`ma(series: pd.Series, period: int) -> pd.Series`
- **Description**：简单移动平均线（SMA）。计算 `series` 在 `period` 个交易日内的算术平均值。**series 不限于 close** —— 任何 pd.Series 都可以（如成交量 `df["成交量（股）"]`、换手率等），用法相同。
- **Returns**：Series，长度与 `series` 一致；前 `period-1` 行为 NaN。
- **Use cases**：趋势判断（ma 上升=上升趋势）、均线交叉（金叉/死叉）、动态支撑阻力位、量能均线（量比基准）。
- **适用场景**：所有需要"序列平滑"的策略（趋势跟踪、均值回归、动量、量价配合等）。
- **Example**：
  - 价格均线：`ma_20 = ma(df["close"], 20)` — 计算 20 日简单移动平均
  - 量能均线：`vol_ma_20 = ma(df["成交量（股）"], 20)` — 计算 20 日均量（量能确认 / 量比基准）
- **Common params**：`period` 常用 5 / 10 / 20 / 60 / 120 / 250。
- **Edge cases**：上市未满 `period` 日的股票，前 `period-1` 行返回 NaN（由调用方决定是否过滤）。
- **Introduced by**：ma_cross_atr_volume, donchian_breakout_vol_rsi_ma

### `atr`
- **Signature**：`atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series`
- **Description**：14 日平均真实波幅（Average True Range）。True Range = `max(high-low, |high-prev_close|, |low-prev_close|)`，再求 `period` 日均值。
- **Returns**：Series；前 `period` 行为 NaN（因需要 period 个 TR 才能求均值）。
- **Use cases**：波动率度量、动态止损（ATR × 倍数）、仓位调整（波动大→仓位小）。
- **适用场景**：所有需要"波动率自适应"的策略（动态止损、突破过滤、仓控）。
- **Example**：`atr_14 = atr(df["high"], df["low"], df["close"], 14)`。
- **Common params**：`period` 常用 14（默认）/ 10 / 20。
- **依赖**：`close` 在内部需要 `shift(1)` 取前收；调用方需保证 `close` 列存在。
- **Introduced by**：ma_cross_atr_volume, donchian_breakout_vol_rsi_ma

### `rsi`
- **Signature**：`rsi(close: pd.Series, period: int = 14) -> pd.Series`
- **Description**：14 日相对强弱指标（Relative Strength Index）。公式：`100 - 100 / (1 + mean(gain, period) / mean(loss, period))`，其中 gain = `max(close_diff, 0)`，loss = `max(-close_diff, 0)`。
- **Returns**：Series，范围 0-100；前 `period` 行为 NaN。
- **Use cases**：超买超卖判断（>70 超买、<30 超卖）、动量过滤、入场区间限制。
- **适用场景**：所有需要"动量过滤"的策略（避免在极端超买超卖位置入场）。
- **Example**：`rsi_14 = rsi(df["close"], 14)`。
- **Common params**：`period` 常用 14（默认）/ 6 / 12 / 24。
- **典型阈值**：`rsi_entry_low=40, rsi_entry_high=70`（入场区间）；`rsi_overbought=75`（超买减仓）。
- **Introduced by**：donchian_breakout_vol_rsi_ma

### `donchian_high`
- **Signature**：`donchian_high(high: pd.Series, period: int) -> pd.Series`
- **Description**：N 日最高价（Donchian 通道上轨）。计算 `high` 在 `period` 个交易日内的最大值。
- **Returns**：Series；前 `period-1` 行为 NaN。
- **Use cases**：突破策略入场（突破 N 日高点即买入信号）、阻力位识别。
- **适用场景**：所有需要"突破关键阻力"判定的策略（趋势启动、波段操作）。
- **Example**：`donchian_high_20 = donchian_high(df["high"], 20)`。
- **Common params**：`period` 常用 20 / 50 / 55 / 100。
- **Introduced by**：donchian_breakout_vol_rsi_ma

### `donchian_low`
- **Signature**：`donchian_low(low: pd.Series, period: int) -> pd.Series`
- **Description**：N 日最低价（Donchian 通道下轨）。计算 `low` 在 `period` 个交易日内的最小值。
- **Returns**：Series；前 `period-1` 行为 NaN。
- **Use cases**：跌破策略出场（跌破 N 日低点即卖出信号）、支撑位识别。
- **适用场景**：所有需要"跌破关键支撑"判定的策略（趋势反转、止损辅助）。
- **Example**：`donchian_low_20 = donchian_low(df["low"], 20)`。
- **Common params**：`period` 常用 20 / 50 / 55 / 100。
- **Introduced by**：donchian_breakout_vol_rsi_ma

### `volume_ratio`
- **Signature**：`volume_ratio(volume: pd.Series, period: int = 20) -> pd.Series`
- **Description**：当日成交量 / period 日均量。衡量当日成交相对历史均量的放大倍数。
- **Returns**：Series，范围通常 0-5（极端放量可达 10+）；前 `period-1` 行为 NaN。
- **Use cases**：量能确认（突破需放量配合）、突破有效性过滤。
- **适用场景**：所有需要"量价配合"判定的策略（突破策略、动量策略）。
- **Example**：`volume_ratio_20 = volume_ratio(df["成交量（股）"], 20)`。
- **Common params**：`period` 常用 20（默认）/ 5 / 10。
- **典型阈值**：`volume_ratio > 1.3` 表示温和放量；`> 1.5` 表示明显放量；`> 2.0` 表示强势放量。
- **Edge cases**：停牌日 `volume=0`，返回 0；新股上市初期 volume 数据可能异常。
- **Introduced by**：ma_cross_atr_volume, donchian_breakout_vol_rsi_ma

### `mom`
- **Signature**：`mom(close: pd.Series, period: int) -> pd.Series`
- **Description**：N 日动量（Momentum）。公式 `close / close.shift(period) - 1`，即当日收盘价相对 N 日前收盘价的相对收益。
- **Returns**：Series；前 `period` 行为 NaN（因 `shift(N)` 产生空值）。
- **Use cases**：中期动量过滤（确认趋势已启动）、相对强度排序、轮动策略。
- **适用场景**：所有需要"中期动量确认"的策略（趋势跟踪、动量轮动）。
- **Example**：`mom_60 = mom(df["收盘价"], 60)` — 60 日动量（`close / close.shift(60) - 1`）。
- **Common params**：`period` 常用 20 / 60 / 120 / 250。
- **典型阈值**：>0 表示中期上涨；>0.05（5%）表示明显上升趋势；<-0.10 表示明显下跌。
- **Edge cases**：上市未满 `period` 日的股票，前 `period` 行为 NaN。
- **Introduced by**：multi_factor_trend_swing

---

## 2. Conditions（公共条件原语）

### `check_fixed_stop`
- **Signature**：`check_fixed_stop(current_price: float, entry_price: float, pct: float) -> bool`
- **Description**：固定止损。判断当前价是否跌破入场价的 `(1 - pct)`。
- **Returns**：`True` 表示触发止损。
- **Use cases**：硬性止损（单笔最大亏损限制）、熊市快速离场。
- **适用场景**：所有需要"无条件止损"的策略（作为第一道防线）。
- **Example**：`if check_fixed_stop(price, entry, 0.08): return "fixed_stop"` — 跌破入场价 8% 止损。
- **Typical `pct`**：0.05-0.10。
- **Introduced by**：ma_cross_atr_volume, donchian_breakout_vol_rsi_ma

### `check_trailing_stop`
- **Signature**：`check_trailing_stop(current_price: float, highest: float, pct: float) -> bool`
- **Description**：移动止损。判断当前价是否从入场后最高价回撤 `pct`。
- **Returns**：`True` 表示触发。
- **Use cases**：浮盈保护（让利润奔跑，但锁定已有浮盈）。
- **适用场景**：所有需要"跟踪止盈"的策略（中长期趋势、波段操作）。
- **Example**：`if check_trailing_stop(price, highest, 0.06): return "trailing_stop"`。
- **Typical `pct`**：0.04-0.10。
- **依赖**：调用方需维护 `highest`（入场后最高收盘价），由 `position` 传入。
- **Introduced by**：ma_cross_atr_volume, donchian_breakout_vol_rsi_ma

### `check_atr_stop`
- **Signature**：`check_atr_stop(current_price: float, highest: float, atr: float, multiplier: float) -> bool`
- **Description**：ATR 动态止损。判断当前价是否从最高价回撤 `multiplier * atr`。
- **Returns**：`True` 表示触发。
- **Use cases**：波动率自适应的止损（高波动时容忍更大回撤，低波动时收紧）。
- **适用场景**：所有需要"自适应止损"的策略（不同股票波动率差异大时尤其有用）。
- **Example**：`if check_atr_stop(price, highest, atr_14, 2.0): return "volatility_stop"` — 2 倍 ATR 止损。
- **Typical `multiplier`**：1.5-3.0。
- **依赖**：需要先计算 `atr`（从 `factors["atr_14"]` 取得）。
- **Introduced by**：donchian_breakout_vol_rsi_ma

### `check_time_stop`
- **Signature**：`check_time_stop(holding_days: int, max_days: int) -> bool`
- **Description**：时间止损。判断持仓天数是否超过 `max_days`。
- **Returns**：`True` 表示触发。
- **Use cases**：防止套牢（资金不应长期锁定在不动的仓位上）、震荡市强制平仓。
- **适用场景**：所有"中周期波段"策略（10-30 个交易日）。
- **Example**：`if check_time_stop(holding_days, 25): return "time_stop"`。
- **Typical `max_days`**：10-60。
- **Introduced by**：ma_cross_atr_volume, donchian_breakout_vol_rsi_ma

### `check_channel_break`
- **Signature**：`check_channel_break(close: float, channel_value: float, direction: str = "above") -> bool`
- **Description**：通道突破/跌破判断。
  - `direction="above"`：判断 `close > channel_value`（向上突破，如 Donchian 上轨）
  - `direction="below"`：判断 `close < channel_value`（向下突破，如 Donchian 下轨）
- **Returns**：`True` 表示突破/跌破。
- **Use cases**：突破策略入场（向上突破 N 日高点买入）、跌破策略出场（向下突破 N 日低点卖出）。
- **适用场景**：所有"通道突破/跌破"策略（趋势启动、波段入场/出场、趋势反转出场）。
- **Example**：
  - 入场：`if check_channel_break(close, donchian_high_20, "above"): score += entry_weights["<signal_name>"]`
  - 出场：`if check_channel_break(close, donchian_low_20, "below"): return "trend_reversal"`
- **依赖**：需要先计算 `donchian_high` 或 `donchian_low`（从 `factors[...]` 取得）。
- **Introduced by**：donchian_breakout_vol_rsi_ma

### `check_rsi_in_range`
- **Signature**：`check_rsi_in_range(rsi: float, low: float, high: float) -> bool`
- **Description**：RSI 区间判断。判断 RSI 是否在 `[low, high]` 区间内。
- **Returns**：`True` 表示在区间内。
- **Use cases**：入场过滤（避免在超买超卖时入场）。
- **适用场景**：所有需要"动量过滤"的策略。
- **Example**：`if check_rsi_in_range(rsi_14, 40, 70): score += 0.2` — RSI 在 40-70 之间才入场。
- **Typical 阈值**：入场区间 `[40, 70]`。
- **依赖**：需要先计算 `rsi`（从 `factors["rsi_14"]` 取得）。
- **Introduced by**：donchian_breakout_vol_rsi_ma

### `check_rsi_above`
- **Signature**：`check_rsi_above(rsi: float, threshold: float) -> bool`
- **Description**：RSI 超买判断。判断 RSI 是否大于 `threshold`。
- **Returns**：`True` 表示超买。
- **Use cases**：盈利减仓（"已盈利 + RSI 超买"是典型的部分止盈触发）、超买出场。
- **适用场景**：所有需要"超买识别"的策略。
- **Example**：`if check_rsi_above(rsi_14, 75) and position["pnl_pct"] > 0.15: return "overbought_reduce"`。
- **Typical 阈值**：超买线 70-80。
- **依赖**：需要先计算 `rsi`。
- **Introduced by**：donchian_breakout_vol_rsi_ma

### `check_volume_ratio_above`
- **Signature**：`check_volume_ratio_above(volume_ratio: float, threshold: float) -> bool`
- **Description**：量能放大判断。判断 `volume_ratio` 是否大于 `threshold`。
- **Returns**：`True` 表示放量。
- **Use cases**：量能确认（突破需放量配合）、放量入场过滤。
- **适用场景**：所有需要"量价配合"判定的策略。
- **Example**：`if check_volume_ratio_above(volume_ratio_20, 1.5): score += entry_weights["<signal_name>"]` — 1.5 倍放量确认。
- **Typical 阈值**：温和 1.3、明显 1.5、强势 2.0。
- **依赖**：需要先计算 `volume_ratio`。
- **Introduced by**：donchian_breakout_vol_rsi_ma

---

## 2.5. Position State（持仓状态字段）

> 策略 spec 中的"因子"有些是**有状态的**（依赖持仓生命周期），不是从市场数据纯计算的。
> 这类"因子"在 LLM 翻译时应通过 `position[...]` 访问（详见 `subject_structure.md` §4.5），**不**通过 `factors[...]` 计算。

| spec 名 | position 字段 | 类型 | 描述 | 引入策略 |
|---|---|---|---|---|
| `highest_close_since_entry` | `position["highest"]` | float | 入场后最高收盘价。组合层每根 K 线更新：`highest = max(previous_highest, close)`。用于移动止损、ATR 止损。 | ma_cross_atr_volume |
| `holding_days` | `position["holding_days"]` | int | 持仓天数。组合层每根 K 线 +1。用于时间止损。 | ma_cross_atr_volume |
| `entry_price` | `position["entry_price"]` | float | 入场价（含费用调整）。开仓时记录。 | ma_cross_atr_volume |
| `current_price` | `position["current_price"]` | float | 当前价（最新 K 线收盘价）。 | ma_cross_atr_volume |
| `pnl_pct` | `position["pnl_pct"]` | float | 累计盈亏比例（小数），公式 `(current_price - entry_price) / entry_price`。 | ma_cross_atr_volume |

> **说明**：上表"引入策略"列记录**首个在 spec 中显式声明**该字段的策略。后续策略（donchian_breakout_vol_rsi_ma / multi_factor_trend_swing）通过 `position["<name>"]` **隐式使用**这些字段（详见 `subject_structure.md` §4.5 强制规则）。

---

## 3. Backtest Infrastructure（公共回测基础设施）

| 模块 | 路径 | 功能 |
|---|---|---|
| Data Loader | `subject/backtest/data_loader/` | 2 种数据源入口（`load_stock` 单股全历史 / `load_day` 单日横截面），统一执行 5 项必做处理（代码补后缀、名称去全角空格、退市时间 NaT、日期 Timestamp、bool 化）。**数据源由运行模式硬绑定**（params → `by_stock`，weight → `by_day`，详见 `subject.md §5`）。 |
| Universe | `subject/backtest/universe/` | 沪深 300 成分股加载与调入调出；过滤：北交所、退市、ST、新股；停牌日处理。 |
| A 股规则 | `subject/backtest/a_share_rules.py` | T+1 交割、最小买入 100 股、涨跌停限制（主板 ±10% / 创科 ±20% / ST ±5%）、一字板跳过。 |
| 交易费用 | `subject/backtest/fees.py` | 买入佣金万 2.5（最低 5 元）、沪市过户费万 0.1、卖出印花税万 10。 |
| 信号引擎 | `subject/backtest/signals.py` | 多信号 AND 合并、Σ(weight) 求和排名（入场）；出场优先级链（按 weight 降序）。 |
| 策略 spec 解析器 | `subject/parser/strategy_md.py` | `parse_strategy_spec(path) -> dict`：读 .md 文件，提取 `---` 包裹的 YAML frontmatter，校验必填键（factors / entry_signals / exit_signals / params），返回 dict。被 LLM 工作流第 0 步调用。 |
| 组合管理 | `subject/backtest/portfolio.py` | 调仓、加减仓 + 5 个仓位约束函数：`enforce_max_single_weight(weights, max)` / `enforce_industry_concentration(weights, industry_map, max)` / `rebalance_to_target_holdings(current, target, candidates)` / `enforce_max_turnover(current, target, max)` / `should_rebalance(last_date, current_date, freq_days)`。 |
| 熊市识别 | `subject/backtest/bear_market.py` | 沪深 300 20 日跌幅识别 + 仓位折算。 |
| Runner | `subject/backtest/runner.py` | `BacktestRunner` 主类，统一调度回测流程。**时间范围** (`start_date` / `end_date`) 和 **股票数限制** (`max_stocks`) 都在 runner 内部处理, strategy.py **不感知** (详见 `subject_structure.md` §4.10)。 |
| 指标 | `subject/backtest/metrics.py` | 7 项指标：年化收益、胜率、盈亏比、夏普、回撤、avg_annual_return_rate、avg_annual_return_amount。 |
| 信号统计 | `subject/backtest/stats/signal_stats.py` | 每信号 triggered / exits / swallowed / skipped / win_count / win_rate / avg_return / median_holding_days。 |
| 因子值统计 | `subject/backtest/stats/factor_value_stats.py` | 因子值分布：min / max / mean / std / p25 / p50 / p75。 |
| 报告（params） | `subject/backtest/reports/params_mode.py` | 生成 params 模式报告（MD 格式）。 |
| 报告（weight） | `subject/backtest/reports/weight_mode.py` | 生成 weight 模式报告（MD 格式，含 signal_attribution）。 |

---

## 4. Params（公共参数工具）

| 名称 | 位置 | 功能 |
|---|---|---|
| `ParamDef` | `subject/params/registry.py` | dataclass，定义参数元数据（name, default, range, type, description）。 |
| `@register_param` | `subject/params/registry.py` | 装饰器，用于将 ParamDef 注册到全局表。 |

**注意**：具体参数值（如 `vol_breakout_threshold=1.5`）**不放**在公共库，跟随策略 spec。

---

## 5. CLI 入口

| 名称 | 位置 | 功能 |
|---|---|---|
| `subject.cli` | `subject/cli/` | 统一 CLI 入口，支持 `--strategy`、`--mode`、`--weight-test` 等参数（详见 `subject_structure.md` §6.4）。 |

---

## 6. 写入规则

- ✅ **可做**：在对应章节末尾追加新行（新增 factor / condition / 模块）
- ✅ **可做**：修改公共部分的代码实现（bug fix），但**函数签名必须保持兼容**
- ❌ **不可做**：删除任何现有行
- ❌ **不可做**：修改现有函数签名
- ❌ **不可做**：重命名现有 public name
- ❌ **不可做**：修改现有行的"Introduced by"列（除非该策略不再使用 → 改为"已弃用"并写迁移说明）

### 6.1 写入示例

**新增 factor**：
```markdown
### `kdj`
- **Signature**：`kdj(high: pd.Series, low: pd.Series, close: pd.Series, n: int = 9) -> pd.DataFrame`
- **Description**：KDJ 随机指标。计算 K、D、J 三条线。
- **Returns**：DataFrame，包含 3 列（K, D, J）。
- **Use cases**：短期超买超卖、趋势反转。
- **Example**：`kdj_df = kdj(df["high"], df["low"], df["close"])`。
- **Introduced by**：<新策略名>
```

**新增 condition**：
```markdown
### `check_macd_golden_cross`
- **Signature**：`check_macd_golden_cross(macd: float, signal: float) -> bool`
- **Description**：MACD 金叉。判断 MACD 上穿 signal 线。
- **Returns**：`True` 表示金叉。
- **Use cases**：动量趋势确认、入场过滤。
- **Example**：`if check_macd_golden_cross(macd, signal): score += 0.3`。
- **Introduced by**：<新策略名>
```
