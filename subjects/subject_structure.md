# Subject 项目代码结构规范

> 本文档面向**无历史记忆的 LLM**，配合 `subject.md` 共同指导策略测试系统的生成。
> 阅读顺序：先读 `subject.md`（总规范）→ 本文件（代码架构 + 规则）→ `PARTS_SUMMARY.md`（现有公共部分清单）→ 目标策略的 `<name>_original.md`（策略 spec）。

---

## 1. 项目架构总览

```
subjects/
├── subject.md                        # 总规范（数据格式 / A 股规则 / 输出格式等）
├── subject_structure.md              # 本文件：代码架构与规则
├── PARTS_SUMMARY.md                  # 公共部分清单（append-only）
│
├── factors/                          # 公共因子库
├── conditions/                       # 公共条件原语
├── params/                           # 公共参数工具（仅元类型，不放具体值）
├── backtest/                         # 回测基础设施
├── cli/                              # 统一 CLI 入口
│
└── <strategy_name>/                  # 每个策略一个目录
    ├── <name>_original.md            # 策略 spec（YAML frontmatter）
    ├── generated/                    # 由 _original.md 翻译的策略私有代码
    │   └── strategy.py
    ├── strategiesParam/              # mode 1 输入：params 调参版本
    │   └── <name>_v<n>.md            # <n> 为正整数
    ├── strategiesWeight/             # mode 2 输入：weight 调参版本
    │   └── <test_name>_weight_v<n>.md   # <test_name> 用户自取
    ├── reportParams/                 # mode 1 输出
    │   └── report_v<n>.md
    └── reportWeight/                 # mode 2 输出
        └── report_signals_v<n>.md
```

---

## 2. 公共 vs 策略私有 判定规则

### 2.1 公共（放 `subject/`）

| 类别 | 内容 |
|---|---|
| 纯计算因子 | ma / atr / rsi / donchian / volume_ratio 等技术指标 |
| 通用条件原语 | 固定止损、移动止损、时间止损、ATR 止损、Donchian 突破、RSI 区间等"模板式判断" |
| 回测基础设施 | 数据加载、universe 过滤、A 股规则、交易费用、信号引擎、组合管理、指标计算、报告生成、CLI |
| 参数元类型 | `ParamDef` dataclass + `@register_param` 装饰器（**不放**具体参数值） |

### 2.2 策略私有（放 `<strategy>/`）

**`params` 段 / `entry_signals` / `exit_signals` 整段都是策略私有**——具体值 + 具体 signal 名字 + trigger 字符串 + weight 全部跟随 spec，不进公共库。公共库只放**元类型**（`ParamDef` dataclass + `@register_param` 装饰器）和**通用工具**（因子函数 + 条件原语）。

| 类别 | 内容 |
|---|---|
| spec `params` 整段 | 具体参数值（如 `vol_breakout_threshold=1.5`），随策略 spec 走 |
| spec `entry_signals` 整段 | 具体入场信号名（如 `breakout_entry`）+ trigger 字符串 + weight |
| spec `exit_signals` 整段 | 具体出场信号名（如 `trailing_stop`）+ trigger 字符串 + weight |
| 策略 entry 评分逻辑 | 哪些信号触发、加多少分（strategy.py 内手写） |
| 策略 exit 优先级链 | 出场信号的执行顺序（strategy.py 内手写） |
| 策略 position 调整逻辑（**判断部分**） | "score > 0.7 → 加仓" 等**触发条件**在 strategy.py 内手写（基于 `params["add_position_weight_threshold"]` 等） |
| 加仓/减仓的**执行部分** | portfolio.py 负责：按目标 weight 与当前 weight 计算仓位差 + 应用 5 个仓位约束 + 费用计算 |
| 业务描述 | `strategy_narrative`（spec 的 Markdown body） |

### 2.3 公共库渐进生长规则

> **核心约束**：不同策略可能用**同名变量但语义不同**（如 `mom_60` 在 A 策略可能是 60 日收益率，在 B 策略可能是 60 日价格动量）。
> 因此公共库的**检索必须按 description 语义匹配，不按 name 字面匹配**（详见 §9.2 步骤 1）。
> "通用"的判定也按语义：即使新策略叫一个新名字，**只要语义上别的策略可能用，就走公共**。

- 新策略出现新的"通用"因子 / 条件时，**先在策略私有代码中实现**
- 判断"未来其他策略是否可能复用"（按语义判定，不是按 name）：
  - **是** → 提升到 `subject/factors/` 或 `subject/conditions/`，**同步在 `PARTS_SUMMARY.md` 追加一行**（完整签名 + 中英描述 + 适用场景 + 示例 + Introduced by）
  - **否** → 保留在 `<strategy>/generated/` 私有实现
- 公共部分的具体代码实现可以修改（bug fix），但**函数签名必须保持兼容**
- `PARTS_SUMMARY.md` 是 append-only：只能追加新行，不能修改 / 删除现有行（详见该文件顶部声明）

---

## 3. 策略目录文件命名约定

| 文件类别 | 命名格式 | 说明 |
|---|---|---|
| 规范 | `<name>_original.md` | 策略 spec，YAML frontmatter 格式 |
| 策略代码 | `generated/strategy.py` | 由 `_original.md` 翻译的策略私有代码 |
| params 版本 | `strategiesParam/<name>_v<n>.md` | `<n>` 为正整数，自动挑选最大值 |
| weight 版本 | `strategiesWeight/<test_name>_weight_v<n>.md` | `<test_name>` 由用户自取（不能含 `_weight_v` 子串） |
| mode 1 报告 | `reportParams/report_v<n>.md` | MD 格式 |
| mode 2 报告 | `reportWeight/report_signals_v<n>.md` | MD 格式 |

---

## 4. `_original.md` → `generated/strategy.py`（LLM 手写 + runner 机制层）

### 4.0 核心架构：策略私有 vs runner 公共

**所有"策略逻辑"在 `<strategy>/generated/strategy.py` 里手写**——LLM 读 spec 后**直接写 Python 代码**（无模板，无 IR，无 runner 解析 trigger）。

**runner 只做"机制"**——runner 不知道 spec 的 entry_signals / exit_signals 是什么，也不知道哪些因子存在。runner 只负责：
- 在每个 bar 调用 `strategy.compute_factors` / `entry_score` / `should_exit`
- 按 `(code, score)` 列表选 top N
- 处理 A 股规则 / 费用 / 仓位约束
- 收集 trigger 日志、计算 7 项指标、写报告

**trigger 字符串的角色**（spec.frontmatter.entry_signals[].trigger / exit_signals[].trigger）：
- **保留在 spec**（人类可读 + LLM 翻译 strategy.py 时的**意图参考**）
- **runner 不解析** trigger
- **LLM 不严格 1:1 翻译** trigger 到 Python 代码——LLM 看 trigger 理解意图后，**手写 if-else**，可以按 narrative 补充额外的判断、合并条件、调整顺序

### 4.1 `generated/strategy.py` 的固定结构

```python
# 1. imports（按需从 PARTS_SUMMARY.md 查公共函数名）
from subject.factors import ma, atr, rsi, donchian_high, donchian_low, volume_ratio, mom
from subject.conditions import check_fixed_stop, check_trailing_stop, check_atr_stop, check_time_stop, check_channel_break, check_rsi_in_range, check_rsi_above, check_volume_ratio_above


# 2. Strategy 类
class Strategy:
    # 3. factor 计算：返回 {factor_name: Series} 字典
    def compute_factors(self, df, params):
        ...

    # 4. entry 评分：返回 Σ(weight)（float）
    #    weights 形如 {"entry": {"ma_golden_cross": 0.5, ...}, "exit": {...}}
    def entry_score(self, factors, params, weights):
        ...

    # 5. exit 判断：按 weight 降序检查，返回触发的信号名（str）或 None
    #    weights 由调用方按 mode 1 / mode 2 不同来源传入
    def should_exit(self, position, factors, params, weights):
        ...

    # 6. 获取触发入场的信号名列表（供 runner 记录事件用）
    #    返回 entry_signals 中触发条件的信号名列表
    #    注意：此方法的触发条件必须与 entry_score 中的条件保持一致
    def get_triggered_signals(self, factors, params, weights):
        triggered = []
        # 根据 entry_signals 中的条件判断每个信号是否触发
        # 示例：
        #   if factors["ma_5"].iloc[-1] > factors["ma_20"].iloc[-1]:
        #       triggered.append("ma_golden_cross")
        #   if factors["atr_14"].iloc[-1] > factors["atr_14_prev"].iloc[-1]:
        #       triggered.append("atr_expand")
        return triggered
```

### 4.2 LLM 翻译 spec → strategy.py 的规则

LLM 读 spec 写 strategy.py 时，按以下规则**手写** 4 个方法（含新增的 `get_triggered_signals`）。

#### 4.2.1 spec → DataFrame 列名映射

策略 spec 用**英文简称**，data_loader 返回的 DataFrame 用**中文全名**。LLM 翻译时按此映射：

| spec 中写法 | DataFrame 列名 |
|---|---|
| `close` | `df["收盘价"]` |
| `high` | `df["最高价"]` |
| `low` | `df["最低价"]` |
| `open` | `df["开盘价"]` |
| `volume` | `df["成交量（股）"]` |
| `prev_close` | `df["前收盘价"]` |

#### 4.2.2 factor 命名 → 公共函数调用

策略 spec 的 `factors[i].name` 命名遵循 `<base>_<period>` 模式（除 `highest_close_since_entry` 等状态字段外）：

| spec 名 | strategy.py 写法（公共函数调用） |
|---|---|
| `ma_5` / `ma_20` / `ma_60` | `factors["ma_5"] = ma(df["收盘价"], 5)` |
| `atr_14` | `factors["atr_14"] = atr(df["最高价"], df["最低价"], df["收盘价"], 14)` |
| `donchian_high_20` | `factors["donchian_high_20"] = donchian_high(df["最高价"], 20)` |
| `donchian_low_20` | `factors["donchian_low_20"] = donchian_low(df["最低价"], 20)` |
| `rsi_14` | `factors["rsi_14"] = rsi(df["收盘价"], 14)` |
| `volume_ratio_20` | `factors["volume_ratio_20"] = volume_ratio(df["成交量（股）"], 20)` |
| `mom_60`（**N 日动量**） | `factors["mom_60"] = mom(df["收盘价"], 60)`，公式 `close / close.shift(N) - 1` |

LLM 通过 `_` 分隔取 `base` 部分查 `PARTS_SUMMARY.md` §1 找到公共函数，按上表组装调用。

公共条件原语**默认形态**：接受**已算好的 Series** + 参数，返回 bool Series。例如 `check_rsi_in_range(rsi_series, low, high)`——rsi 由 strategy.py 先在 `compute_factors` 里算好，condition 函数不感知 period。

> **粒度变体（可选）**：如需"按 period 写死"的 condition（如 `check_rsi_14_in_range`），可单独定义。两种形态并存，公共库不需要"枚举所有 period"。

#### 4.2.3 `<factor>_prev` 后缀

`X_prev` 表示 `X` 的**前一根 K 线**值。LLM 翻译为：
```python
factors["atr_14_prev"] = factors["atr_14"].shift(1)
```

#### 4.2.4 trigger 中缺失标识符的处理

spec 的 entry_signals[].trigger / exit_signals[].trigger 字符串中可能用到 spec.factors 列表**外**的标识符。LLM 翻译 strategy.py 时按性质分两类处理：

**A 类：数据列（raw data）** —— 在 `compute_factors` 中加入 factors dict：
| 标识符 | factors dict 写法 |
|---|---|
| `close` | `factors["close"] = df["收盘价"]` |
| `high` | `factors["high"] = df["最高价"]` |
| `low` | `factors["low"] = df["最低价"]` |
| `open` | `factors["open"] = df["开盘价"]` |
| `volume` | `factors["volume"] = df["成交量（股）"]` |

**B 类：持仓状态字段（position state）** —— 在 `should_exit` 中通过 `position["<name>"]` 访问（**这 5 个字段永远不写进 spec.factors**，详见 §4.5）：

| spec 中写法 | position 字段 |
|---|---|
| `current_price` | `position["current_price"]` |
| `entry_price` | `position["entry_price"]` |
| `highest_close_since_entry` | `position["highest"]` |
| `holding_days` | `position["holding_days"]` |
| `pnl_pct` | `position["pnl_pct"]` |

**判定捷径**：如果标识符在 `PARTS_SUMMARY.md` §2.5 表格中 → B 类；否则 → A 类（数据列）。

#### 4.2.5 中文描述反推（fallback 规则）

当 §4.2.1 标准映射无法唯一确定列名时（如 `volume` 可能映射到 `成交量（股）` / `成交额（元）` / `量比`），LLM 应读 `factors[i].description` 或 `params[i].description` 的中文描述，按语义匹配。

**示例**：
- `volume_ratio_20` 的 description 是 "当日成交量 / 20 日均量"
- LLM 按 "成交量" 匹配 → `volume` → `df["成交量（股）"]`
- 计算：`df["成交量（股）"] / df["成交量（股）"].rolling(20).mean()`

**反推优先级**：
1. §4.2.1 标准映射
2. 不在标准表 → 按 `description` 中文语义匹配
3. 仍有歧义 → 报 warning 让用户人工确认

#### 4.2.6 trigger 字符串 → Python 代码

LLM 把 spec 的 `entry_signals[].trigger` / `exit_signals[].trigger` 字符串当作**意图参考**，翻译为 strategy.py 里的手写 if-else：

| trigger 写法 | strategy.py 写法 |
|---|---|
| `close > donchian_high_20` | `factors["close"] > factors["donchian_high_20"]` |
| `volume_ratio_20 > {vol_breakout_threshold}` | `factors["volume_ratio_20"] > params["vol_breakout_threshold"]` |
| `rsi_14 > {rsi_entry_low} AND rsi_14 < {rsi_entry_high}` | `(factors["rsi_14"] > params["rsi_entry_low"]) & (factors["rsi_14"] < params["rsi_entry_high"])`（**或**调用 `check_rsi_in_range(factors["rsi_14"], params["rsi_entry_low"], params["rsi_entry_high"])`） |
| `current_price < entry_price * (1 - {fixed_stop_pct})` | `position["current_price"] < position["entry_price"] * (1 - params["fixed_stop_pct"])`（**或**调用 `check_fixed_stop(position["current_price"], position["entry_price"], params["fixed_stop_pct"])`） |
| `X AND Y` | `(X) & (Y)`（Series 之间用 `&`，不是 `and`） |
| `X / close > {thr}` | `factors["X"] / factors["close"] > params["thr"]`（按 §4.2.4 在 factors dict 中加 `close`） |

**LLM 翻译的自由度**：
- 简单判断：直接用 Series 比较内联
- 复杂判断：调用 `subject/conditions/` 里的公共函数（**推荐**）
- 可以在 trigger 翻译之上**补充** narrative 里的语义（如"至少 2 个信号同时触发"——这在 trigger 字符串里没有，需要 LLM 读 narrative 后加额外判断）
- **不允许**写死 weight 数值（必须用 `entry_weights["<signal_name>"]`）

### 4.3 entry_score 实现规范

```python
def entry_score(self, factors, params, weights):
    score = 0.0
    entry_weights = weights["entry"]   # 形如 {"ma_golden_cross": 0.5, ...}
    # 按 spec.entry_signals 列表顺序遍历（顺序写死，不动态生成）
    # 简单判断直接用 Series 比较
    if factors["close"] > factors["donchian_high_20"]:
        score += entry_weights["breakout_entry"]   # weight 通过 weights 参数读
    # 复杂判断调公共 condition
    if check_rsi_in_range(factors["rsi_14"], params["rsi_entry_low"], params["rsi_entry_high"]).iloc[-1]:
        score += entry_weights["rsi_entry"]
    return score
```

**强制规则**：
- weight **不可**写死为 Python 字面量（如 `score += 0.5`），必须通过 `entry_weights["<signal_name>"]` 读取
- if 的**顺序**由 strategy.py 写死（按 spec.entry_signals 顺序），**不动态生成**
- runner **不参与** entry_score 的实现

### 4.4 should_exit 实现规范

```python
def should_exit(self, position, factors, params, weights):
    exit_weights = weights["exit"]   # 形如 {"ma_death_cross": 0.30, "trailing_stop": 0.30, ...}
    # 按 exit_weights 降序排序，weight 高的信号先检查（先触发者先 return）
    for signal_name in sorted(exit_weights, key=exit_weights.get, reverse=True):
        if signal_name == "ma_death_cross":
            if factors["ma_5"].iloc[-1] < factors["ma_20"].iloc[-1]:
                return "ma_death_cross"
        elif signal_name == "trailing_stop":
            if check_trailing_stop(
                pd.Series([position["current_price"]]),
                pd.Series([position["highest"]]),
                params["trailing_stop_pct"]
            ).iloc[-1]:
                return "trailing_stop"
        # ... 其他 exit signal 手写 if-else
    return None
```

**强制规则**：
- 排序键**不可**写死，必须由 `exit_weights` 动态生成（`sorted(exit_weights, key=exit_weights.get, reverse=True)`）
- 每个 exit signal 的判断**手写**——LLM 看 trigger 字符串理解意图后写 if-else
- 推荐调 `subject/conditions/` 里的公共函数（避免重复实现）
- runner **不参与** should_exit 的实现

### 4.5 position 字段约定

`should_exit` 接收的 `position` dict 包含（**与 `PARTS_SUMMARY.md` §2.5 完全对齐**）：

| 字段 | 类型 | 含义 | spec 中常见别名 |
|---|---|---|---|
| `current_price` | float | 当前价（最新 K 线收盘价） | `current_price` |
| `entry_price` | float | 入场价（含费用调整） | `entry_price` |
| `highest` | float | 入场后最高收盘价 | `highest_close_since_entry`、`highest` |
| `holding_days` | int | 持仓天数 | `holding_days` |
| `pnl_pct` | float | 累计盈亏比例（小数），公式 `(current_price - entry_price) / entry_price` | `pnl_pct` |

> **强制规则**：这 5 个字段**永不写进** `spec.factors`。如果 spec 把 `highest_close_since_entry` 错误地放在 `factors` 列表中，LLM 应**识别为 position state 字段**并归入 position 访问（不生成 factor 函数）。判定依据：`PARTS_SUMMARY.md` §2.5 表格中的字段。

### 4.6 完整示例（donchian 策略的 `breakout_entry` + `trailing_stop`）

`_original.md` 片段：
```yaml
entry_signals:
- name: breakout_entry
  weight: 0.5
  factors: [donchian_high_20, volume_ratio_20]
  trigger: "close > donchian_high_20 AND volume_ratio_20 > {vol_breakout_threshold}"
  logic: AND
exit_signals:
- name: trailing_stop
  weight: 0.3
  factors: [highest_close_since_entry]
  trigger: "current_price < highest_close_since_entry * (1 - {trail_stop_pct})"
  logic: 单因子
```

`generated/strategy.py`：
```python
from subject.factors import donchian_high, volume_ratio
from subject.conditions import check_trailing_stop
import pandas as pd


class Strategy:
    def compute_factors(self, df, params):
        return {
            "close": df["收盘价"],  # trigger 中用到但不在 spec.factors 列表（按 §4.2.4 A 类）
            "donchian_high_20": donchian_high(df["最高价"], 20),
            "volume_ratio_20": volume_ratio(df["成交量（股）"], 20),
            # ... 其他 spec.factors 中的因子
        }

    def entry_score(self, factors, params, weights):
        score = 0.0
        entry_weights = weights["entry"]   # 形如 {"breakout_entry": 0.5, ...}
        # breakout_entry（按 spec entry_signals 顺序）
        if (factors["close"] > factors["donchian_high_20"]).iloc[-1] \
                and (factors["volume_ratio_20"] > params["vol_breakout_threshold"]).iloc[-1]:
            score += entry_weights["breakout_entry"]
        return score

    def should_exit(self, position, factors, params, weights):
        # 按 exit_weights 降序
        for sig in sorted(weights["exit"], key=weights["exit"].get, reverse=True):
            if sig == "trailing_stop":
                # 调公共 condition（推荐），也可用内联
                fired = check_trailing_stop(
                    pd.Series([position["current_price"]]),
                    pd.Series([position["highest"]]),
                    params["trail_stop_pct"],
                )
                if bool(fired.iloc[0]):
                    return "trailing_stop"
        return None
```

### 4.6.1 runner 与 strategy.py 的接口

runner 调用 strategy.py 的 3 个方法时**只传数据 + 参数 + 权重**，**不传 spec 任何字段**：

```python
# runner 伪代码
strategy = Strategy()
for bar in market_bars:
    factors = strategy.compute_factors(bar.df, params)
    score = strategy.entry_score(factors, params, weights)  # 单只股票一个 float
    if score > 0:
        # 把 (code, score) 加入候选列表
        candidates.append((bar.code, score))
# runner 按 score 降序选 top N
target = sorted(candidates, key=lambda x: x[1], reverse=True)[:N]
# 出场时
exit_name = strategy.should_exit(position, factors, params, weights)
if exit_name is not None:
    # 触发退出
    ...
```

runner 不知道 spec 有哪些 entry / exit 信号，也不知道 trigger 长什么样。

### 4.7 `position_weights` 段：**测试模块整体忽略**

> 当前所有策略 spec 中 `position_weights` 段（`max_single_weight` / `max_industry_concentration` / `target_holdings` / `max_turnover_per_rebalance`）的字段**在 `params` 段都有完整副本**（带 `default` / `range` / `type` / `description`）。`position_weights` 段是**冗余的历史遗留**，所有可调字段以 `params` 段为准。

**规则**：
- 测试模块**不读** `position_weights` 段，所有可调字段从 `params[i].default` 取
- LLM 生成 `strategy.py` 时**不引用** `position_weights` 段
- runner 在调仓/仓位约束时直接读 `params["<name>"]`
- 段名保持兼容（不强制重命名），但行为上等同"无操作"

**LLM 处理流程**：
1. 解析 spec 时**跳过** `position_weights` 段
2. 所有结构性约束（单票上限 / 行业集中度 / 目标持仓数 / 换手上限）从 `params` 段同名字段读
3. 不在 `strategy.py` 中引用 `position_weights` 这个 dict

### 4.8 `max_industry_concentration` 的数据来源

`max_industry_concentration` 约束（从 `params["max_industry_concentration"]` 读）**可以直接使用数据中的 `所属行业` 列**（详见 `subject.md` §1 / `data/README.md` §7.1，38 列 schema 之一）。

`所属行业` **不放入 factors dict**（它是 portfolio 层的元数据，不参与策略逻辑判断）。正确做法：

```python
# 在 portfolio.py 的 load_industry_map 中（从 data_loader 读每日横截面构造 industry_map）：
def load_industry_map(universe_codes: list[str], date: str) -> dict[str, str]:
    """从 data_loader.load_day(date) 读全市场横截面，过滤 universe，构造 {code: industry_name}"""
    df = data_loader.load_day(date)
    sub = df[df["代码"].isin(universe_codes)]
    return dict(zip(sub["代码"], sub["所属行业"]))

# 在 portfolio.py 的 enforce_industry_concentration 中：
def enforce_industry_concentration(weights, industry_map, max_pct):
    # weights: {code: weight} 字典
    # industry_map: {code: industry_name} 字典
    # max_pct: 来自 params["max_industry_concentration"]
    ...
```

当前 3 个策略 spec 中**未使用** `max_industry_concentration` 字段（不参与行业过滤），但 `enforce_industry_concentration` 函数仍应在 `subject/backtest/portfolio.py` 中实现，以备未来需要。

### 4.9 `weights` 参数传递规则

> **核心约束**：weight 在策略代码中**不可硬编码为 Python 字面量**，必须由调用方按运行模式动态传入。否则 mode 2 调权时无法生效。

**`weights` 数据结构**（**调用方构造**，不是 runner——runner 不读 spec）：
```python
weights = {
    "entry": {
        "<signal_name_1>": 0.50,   # 来自 frontmatter.entry_signals[i].weight
        "<signal_name_2>": 0.25,
        ...
    },
    "exit": {
        "<signal_name_1>": 0.30,   # 来自 frontmatter.exit_signals[i].weight
        "<signal_name_2>": 0.30,
        ...
    },
}
```

**weight 来源**（由 CLI / 外部 orchestrator 在调用 strategy.py 前构造）：

| 运行模式 | entry weight 来源 | exit weight 来源 |
|---|---|---|
| **Mode 1（params 调参）** | `_original.md` 的 `frontmatter.entry_signals[i].weight` | `_original.md` 的 `frontmatter.exit_signals[i].weight` |
| **Mode 2（weight 调权）** | `strategiesWeight/<test_name>_weight_v<n>.md` 的 `entry_signals[i].weight` | `strategiesWeight/<test_name>_weight_v<n>.md` 的 `exit_signals[i].weight` |

**LLM 翻译 entry_score / should_exit 时的强制规则**：
- ❌ 错误：`score += 0.5`（硬编码）
- ❌ 错误：`score += frontmatter["entry_signals"][0]["weight"]`（直接读 spec）
- ✅ 正确：`score += entry_weights["<signal_name>"]`（通过 weights 参数）

**为什么必须用 dict 而不是 list**：
- `entry_weights["<signal_name>"]` 让 LLM 生成的代码不依赖 entry_signals 在 spec 中的顺序，调权重时信号顺序变化不影响代码
- `should_exit` 的排序由 `sorted(exit_weights, key=exit_weights.get, reverse=True)` 动态生成，新增 / 删除 exit signal 时无需改排序逻辑

**Signal name 必须严格一致**：weights dict 的 key 必须与 `frontmatter.entry_signals[i].name` / `exit_signals[i].name` 完全一致（区分大小写），否则 KeyError。LLM 翻译时按 spec 严格复制。

### 4.10 strategy.py 与 runner 的边界：时间范围 + limit

> **核心契约**：strategy.py **不感知**时间范围 / 股票数限制, 这些**完全由 runner 处理**。strategy 只接收**已经过滤好的 df** 和按 spec 算好的 params / weights, 不知道也不需要知道 "我在跑哪段时间 / 多少只股票"。

#### 4.10.1 runner 处理, strategy 无需感知

| 关注点 | runner 处理 | strategy.py 看不到 |
|---|---|---|
| 时间范围 (start_date / end_date) | `_run_params`: `df = df[df["日期"] >= pd.Timestamp(start)]` 后再传 strategy<br>`_run_weight` / `_enumerate_trading_dates`: 按日期 skip | strategy 收到的 df 已经是过滤后的 |
| 股票数限制 (max_stocks) | `self.universe = self.universe[:max_stocks]`, 只在选出的 universe 上调 strategy | strategy 不知道 universe 总共有多少 |
| 单只股票最少 K 线 (min_bars) | `if len(df) < min_bars: continue` (跳过该股票) | strategy 不知道 "够不够长" 的判断 |
| 数据源 (by_stock / by_day) | `mode` 决定 | strategy 不知道数据源, 只看到 1 个 df |

#### 4.10.2 strategy 需要时间信息时怎么办

**唯一可用的时间入口是 ``df["日期"]``** (params 模式: 多行 df, 可访问最早/最晚日期; weight 模式: 1 行 df, 只有当前日期).

```python
# 策略 A: 拿当前 bar 的日期
current_date = df.iloc[-1]["日期"]   # pd.Timestamp

# 策略 B: 拿 df 总长度 (跑了多少 bar)
n_bars = len(df)

# 策略 C: 拿最早/最晚日期 (params 模式)
if len(df) > 0:
    date_range_start = df.iloc[0]["日期"]
    date_range_end = df.iloc[-1]["日期"]
```

> **不允许**strategy.py 自己读 ``self.start_date`` / ``self.max_stocks`` —— strategy 类没有这些属性, runner 也不传.
> 如果策略需要"自适应" (如: 数据少时放宽阈值), 只能通过 ``params`` 字典传 (e.g. ``params["min_bars_required"]``).

#### 4.10.3 LLM 翻译 strategy.py 的边界规则

1. **不写日期过滤代码** —— runner 已经过滤过, strategy 再过滤会重复
2. **不写 universe 限制代码** —— runner 限定, strategy 不知道也不需要
3. **不写 "数据不够就跳过" 逻辑** —— runner 跳过, strategy 收到的 df 总是够长的 (>= min_bars)
4. **如果 spec narrative 提到 "按时间调整参数"** —— 通过 ``params`` 字典传 (e.g. ``params["bear_drawdown_threshold"]``), 不通过代码内的 if/else
5. **如果 spec 提到 "不同 universe size 用不同策略"** —— 这是策略的逻辑, 可以通过 ``len(df)`` 推断 (params 模式) 或写在 strategy.py 内 (weight 模式)

#### 4.10.4 完整示例 (params 模式 + 时间范围)

调用方:
```bash
python -m subject.cli run --strategy ma_cross_atr_volume --mode params \
    --start-date 2024-01-01 --end-date 2024-03-31 --max-stocks 5
```

runner 内部:
```python
# runner._run_params 主循环
for code in self.universe:                # 已经限制为 5 只
    df = load_stock(code)
    df = df[df["日期"] >= pd.Timestamp("2024-01-01")]   # ← 时间过滤
    df = df[df["日期"] <= pd.Timestamp("2024-03-31")]
    if len(df) < self.min_bars: continue   # ← 跳过不足的
    # ... 调用 strategy
    factors = strategy.compute_factors(df, params)   # df 已经是过滤后的
    score = strategy.entry_score(factors, params, weights)
```

strategy.py 内部 (无需修改):
```python
class Strategy:
    def compute_factors(self, df, params):
        # 直接算因子, 不需要管 df 是从哪段时间来的
        return {"ma_5": ma(df["收盘价"], 5), ...}
    
    def entry_score(self, factors, params, weights):
        # 拿 factors 算分数, 不需要知道时间
        score = 0.0
        if factors["ma_5"].iloc[-1] > factors["ma_20"].iloc[-1]:
            score += weights["entry"]["ma_golden_cross"]
        return score
```

#### 4.10.5 何时需要扩展 strategy.py 接口

如果未来出现以下需求, 才需要扩展 strategy.py 接口 (3 → 4 个方法):

- 策略需要知道 "当前跑的是回测还是实盘" (实盘: 单根 K 线触发, 回测: 多根 K 线扫描)
- 策略需要根据 universe size 动态调整参数 (e.g. 10 只股票时严苛, 100 只时宽松)
- 策略需要在调仓日做特殊处理 (调仓日 vs 普通日)

**当前不需要**, 因为 3 个 spec 都没有这些需求. 如果将来需要, 在 strategy.py 加一个 ``on_context(ctx)`` 钩子, runner 在调用前注入 ctx (含 time_range / max_stocks / mode).

---

### 4.11 策略文件级规范（generated/strategy.py 必含）

每个 `generated/strategy.py` **同时也是策略的执行入口**，除了 `class Strategy`（含 3 方法，§4.1）外，**必须**还包含以下 3 段：

#### 4.11.1 顶部 `# command` 注释块

- **位置**：文件最顶部（第 1 行起）
- **格式**：与 §8 调试模式注释块一致（`# key: value`）
- **必含字段**：`strategy` / `mode` 选项 / `run` 选项（single vs monitor）/ 至少 6 个 `# command` 行
- **示例**：

```python
# strategy: ma_cross_atr_volume
# mode: params (默认) | weight | top300   ← positional, 第一参数
# run:   single (默认) | --monitor   ← single 跑一次退出 / --monitor 监听文件夹触发
# command: python strategy.py
# command: python strategy.py params
# command: python strategy.py weight
# command: python strategy.py top300
# command: python strategy.py top300 --rounds 5 --max-retries 3
# command: python strategy.py --monitor
# command: python strategy.py weight --monitor
# purpose: 策略回测执行入口 (本文件即调用自身 Strategy 类, 策略名隐含在文件路径)
# date: YYYY-MM-DD
```

#### 4.11.2 `StrategyConfig` 数据类（CONFIG 最高优先级）

文件**必须**定义一个 `StrategyConfig` dataclass 和一个 `CONFIG` 实例，作为代码层最高优先级的配置（覆盖 CLI 参数和 spec 默认值）：

```python
from dataclasses import dataclass
from typing import Optional

@dataclass
class StrategyConfig:
    """策略执行配置. 任何字段非 None 时, 覆盖对应 CLI 参数和 spec 默认值.

    **两套配置分离**:
    - params / weight 模式: test_universe / start_date / end_date / limit
    - top300 模式: top300_start_date / top300_end_date / top300_limit (时间范围和 limit 仅在 top300 模式生效)
    """
    # === params / weight 模式配置 ===
    test_universe: Optional[list[str]] = None   # 自定义股票代码列表 (带后缀, 如 ["000001.SZ", "600000.SH"])
    start_date: Optional[str] = None            # "YYYY-MM-DD", None = 不限
    end_date: Optional[str] = None              # "YYYY-MM-DD", None = 不限
    limit: Optional[int] = None                 # 限制测试股票数 (test_universe 取前 N), None = 不限

    # === top300 模式配置 (仅 top300 模式生效) ===
    top300_start_date: Optional[str] = None     # top300 模式时间范围: "YYYY-MM-DD", None = 默认 5 年
    top300_end_date: Optional[str] = None # top300 模式时间范围: "YYYY-MM-DD", None = 数据末日
    top300_limit: Optional[int] = None        # top300 模式每轮回测的 limit, None = 不限

# === 在这里配置 (None = 不覆盖) ===
CONFIG = StrategyConfig(
    # params / weight 模式
    test_universe=None, # None 时默认从 test_universe/top300.md 读取(存在时),否则用 HS300
    start_date=None,
    end_date=None,
    limit=None,
    # top300 模式
    top300_start_date=None,
    top300_end_date=None,
    top300_limit=None,
)
```

**优先级链**（高→低）：

```
CONFIG (代码中)  >  CLI 参数  >  spec 默认值
```

**CONFIG 生效时打印**（便于调试）：

```python
if eff_test_universe is not None or eff_limit is not None or CONFIG.start_date is not None or CONFIG.end_date is not None or args.weight_test:
    print(f"[CONFIG] test_universe={...} start={...} end={...} limit={...} weight_test={...}")
```

**CONFIG 字段与 runner 参数的对应**：

| CONFIG 字段 | 透传给 subject.cli.main | runner 接收 |
|---|---|---|
| `test_universe` | `--test-universe <逗号分隔>` | `BacktestRunner.test_universe_override` |
| `start_date` | `--start-date <YYYY-MM-DD>` | `BacktestRunner.start_date` |
| `end_date` | `--end-date <YYYY-MM-DD>` | `BacktestRunner.end_date` |
| `limit` | `--max-stocks <int>` | `BacktestRunner.max_stocks` |
| `top300_start_date` | 透传给 `run_top300_optimize()` 的 `start_date` | — |
| `top300_end_date` | 透传给 `run_top300_optimize()` 的 `end_date` | — |
| `top300_limit` | 透传给 `runner.backtest_all_stocks_summary()` 的 `min_bars` | — |

**top300 模式的测试集来源**：

```
1. test_universe/top300.md 存在 → 读取其中的股票列表
2. test_universe/top300.md 不存在 → fallback 到 HS300
```

> **注意**：`test_universe` 配置在 top300 模式下**不生效**（top300 模式强制遍历全部 5841 只股票）。`test_universe` 仅在 params / weight 模式下生效。

#### 4.11.3 末尾 `if __name__ == "__main__":` 块

`__main__` 块**必须**实现以下结构（直接复用即可，仅策略名 `ma_cross_atr_volume` 替换为对应策略）：

> ⚠️ **生成必读**：§4.11.3 的 `os.chdir(_HERE.parents[1])` 与 §4.11.4 的 `watch_dir` 必须保持**路径一致**——都基于**策略目录** `<name>/`，不能一个用 `parents[1]`，另一个用 `parents[2]`。详见 §4.11.5。

```python
if __name__ == "__main__":
    import argparse, os, re, sys, threading, time
    from pathlib import Path
    from watchdog.events import FileSystemEvent, FileSystemEventHandler
    from watchdog.observers import Observer

    # === 1. 路径注入 + 切到策略目录 ===
    # strategy.py 路径: subjects/<name>/generated/strategy.py
    # parents[0] = generated/, parents[1] = <name>/, parents[2] = subjects/
    _HERE = Path(__file__).resolve()
    _SUBJECTS_DIR = _HERE.parents[2]
    if str(_SUBJECTS_DIR) not in sys.path:
        sys.path.insert(0, str(_SUBJECTS_DIR))
    os.chdir(_HERE.parents[1])  # 切到 <name>/, 让 report 相对路径正确

    # === 2. argparse (mode positional + flags) ===
    parser = argparse.ArgumentParser(...)
    parser.add_argument("mode", nargs="?", default="params", choices=["params", "weight", "top300"])
    parser.add_argument("--monitor", action="store_true", help="watchdog 监听 strategiesParam/ 或 strategiesWeight/")
    parser.add_argument("--weight-test", default=None, help="weight 模式覆盖 test name (默认 = 策略名)")
    parser.add_argument("--start-date", default=None)
    parser.add_argument("--end-date", default=None)
    parser.add_argument("--capital", type=float, default=1_000_000)
    parser.add_argument("--output", default=None)
    parser.add_argument("--rounds", type=int, default=3, help="top300 模式: 调优轮数 (默认 3)")
    parser.add_argument("--max-retries", type=int, default=3, help="top300 模式: LLM 重试上限 (默认 3)")
    args = parser.parse_args()

    # === 3. run_once() 函数: 委托给 subject.cli.main ===
    def run_once() -> int:
        # CONFIG 覆盖 (最高优先级)
        eff_test_universe = CONFIG.test_universe
        eff_start_date = CONFIG.start_date if CONFIG.start_date is not None else args.start_date
        eff_end_date = CONFIG.end_date if CONFIG.end_date is not None else args.end_date
        eff_limit = CONFIG.limit
        eff_weight_test = args.weight_test if args.weight_test else "<strategy_name>"  # 默认 = 策略名

        from subject.cli.main import main
        cli_args = ["run", "--strategy", "<strategy_name>", "--mode", args.mode]
        cli_args += ["--weight-test", eff_weight_test]
        if eff_test_universe is not None:
            cli_args += ["--test-universe", ",".join(eff_test_universe)]
        if eff_limit is not None:
            cli_args += ["--max-stocks", str(eff_limit)]
        if eff_start_date:
            cli_args += ["--start-date", eff_start_date]
        if eff_end_date:
            cli_args += ["--end-date", eff_end_date]
        if args.capital != 1_000_000:
            cli_args += ["--capital", str(args.capital)]
        if args.output:
            cli_args += ["--output", args.output]
        return main(cli_args)

       # === 3.5. run_top300() 函数: 委托给 subject.cli.top300 ===
    def run_top300() -> int:
        from subject.cli.top300 import run_top300_optimize
        # CONFIG 覆盖 (最高优先级)
        eff_start_date = CONFIG.top300_start_date if CONFIG.top300_start_date is not None else args.start_date
        eff_end_date = CONFIG.top300_end_date if CONFIG.top300_end_date is not None else args.end_date
        eff_limit = CONFIG.top300_limit
        result = run_top300_optimize(
            name="<strategy_name>",
            rounds=args.rounds,
            max_retries=args.max_retries,
            start_date=eff_start_date,
            end_date=eff_end_date,
            limit=eff_limit,
        )
        if result is None:
            print("[ERROR] Top300 筛选失败")
            return 1
        print(f"[OK] Top300 测试集已写入: test_universe/top300.md")
        print(f"      最优轮: Round {result.best_round}, 平均年化收益率: {result.best_avg_return:+.2%}")
        return 0

    # === 4. single 模式: 跑一次退出 ===
    if not args.monitor:
        if args.mode == "top300":
            sys.exit(run_top300())
        sys.exit(run_once())

    # === 5. --monitor 模式: 用 watchdog 监听目录 (见 §4.11.4) ===
    ...
```

#### 4.11.4 `--monitor` 行为（watchdog + debounce）

`--monitor` 用 `watchdog.observers.Observer` 监听对应目录，新增/修改匹配 pattern 的 `.md` 文件触发回测：

| 模式 | 监听目录 | 文件匹配 pattern |
|---|---|---|
| `python strategy.py --monitor` (params) | `strategiesParam/` | `.+_v\d+\.md$` |
| `python strategy.py weight --monitor` (weight) | `strategiesWeight/` | `.+_weight_v\d+\.md$` |
| `python strategy.py top300` (top300) | **不支持 monitor模式** | — |

> **注意**：`top300` 模式不支持 `--monitor`（因为三轮回测耗时较长，需要单独执行）。

**实现关键点**：

- `watchdog.observers.Observer`（非递归）
- `FileSystemEventHandler.on_created` + `on_modified` 都触发（防 LLM 写入被漏掉）
- `threading.Event` 在 watchdog 线程与主线程间传递事件
- **debounce 5 秒**（与 strategies 系统 `debounce_seconds` 默认一致）：5s 内若有新事件，重新计时
- 触发后调用 `run_once()` 跑一次回测
- `Ctrl+C`（KeyboardInterrupt）优雅停止 observer + join 线程后退出
- 每次触发都重新计算 weight 模式（若有 `--weight-test` 用它，否则 = 策略名）

#### 4.11.5 ⚠️ `os.chdir` 与 `watch_dir` 一致性规则（必读）

`__main__` 块的 `os.chdir` 与 `--monitor` 的 `watch_dir` 必须**锚定同一目录**，否则 monitor 模式会因路径解析错误而 `ERROR: monitor 模式需要 strategiesParam/ 目录, 不存在`。

**正确做法 A：两边都锚定策略目录 `<name>/`**（推荐，spec 模板默认）

```python
# §4.11.3 __main__ 顶部
os.chdir(_HERE.parents[1])  # chdir 到 <name>/

# §4.11.4 monitor 分支
watch_dir = Path("strategiesParam")       # 相对路径, 解析为 <name>/strategiesParam/  ✓
# 或显式绝对路径 (更稳健, 不依赖 cwd)
watch_dir = _HERE.parents[1] / "strategiesParam"
```

**错误做法 B：chdir 到 `subjects/` 根**（典型反例，2026-06-05 踩坑）

```python
# §4.11.3 __main__ 顶部
os.chdir(_HERE.parents[2])  # chdir 到 subjects/ 根 ← 错!

# §4.11.4 monitor 分支
watch_dir = Path("strategiesParam")       # 解析为 subjects/strategiesParam/  ✗ 不存在
```

**自检表**（生成/Review strategy.py 时检查）：

| 位置 | 锚点 | 必须等于 |
|---|---|---|
| §4.11.3 `os.chdir` | `_HERE.parents[?]` | `parents[1]` (策略目录) |
| §4.11.4 `watch_dir` | `Path(...)` 或 `_HERE.parents[?] / ...` | 同上, 或显式 `parents[1]` |
| §4.11.4 `weight` 模式 | `strategiesWeight/` | 同上 |

**修复命令**（已有策略踩坑时, 一行修复 chdir）：

```python
# 错误
os.chdir(_HERE.parents[2])
# 正确
os.chdir(_HERE.parents[1])
```

**关键代码片段**（参考完整实现）：

```python
DEBOUNCE_SECONDS = 5.0
trigger_event = threading.Event()

class _WatchHandler(FileSystemEventHandler):
    def _maybe_fire(self, path_str: str) -> None:
        if not path_str.endswith(".md"):
            return
        if watch_pattern.match(Path(path_str).name):
            trigger_event.set()
    def on_created(self, event):  # noqa
        if not event.is_directory: self._maybe_fire(event.src_path)
    def on_modified(self, event):  # noqa
        if not event.is_directory: self._maybe_fire(event.src_path)

observer = Observer()
observer.schedule(_WatchHandler(), str(watch_dir.resolve()), recursive=False)
observer.start()

try:
    while True:
        trigger_event.wait()  # 阻塞到首个事件
        trigger_event.clear()
        # debounce
        while True:
            fired_again = trigger_event.wait(timeout=DEBOUNCE_SECONDS)
            if fired_again:
                trigger_event.clear()
            else:
                break
        rc = run_once()
except KeyboardInterrupt:
    pass
finally:
    observer.stop()
    observer.join()
```

#### 4.11.5 模板可迁移性

新策略的 `strategy.py` 套用本节模板时，只需替换两处：

1. 顶部 `# strategy: <name>` 中的 `<name>`
2. `__main__` 块中两处 `"ma_cross_atr_volume"` 字符串 → `"<新策略名>"`
3. 顶部 `# command` 中的策略名描述

`Strategy` 类（3 方法）由 LLM 从 spec 翻译，**不受本节影响**（见 §4.2 翻译规则）。

---

### 4.12 文件命名规则（strategiesWeight/）

#### 4.12.1 weight 文件命名格式

**`strategiesWeight/<strategy_name>_weight_v<n>.md`**

- **test name = 策略名**：因为本项目不存在"多 test 场景"概念，每个策略只有一份当前 weight 文件
- 文件前缀**必须**等于 `<strategy_name>`（runner 用 `f"{weight_test}_weight_v"` 找文件）
- 版本号 `v<n>`：`<n>` 为正整数，新调优产物递增（如 `v1` → `v2` → `v3`）
- 示例：
  ```
  strategiesWeight/ma_cross_atr_volume_weight_v1.md
  strategiesWeight/ma_cross_atr_volume_weight_v2.md   ← 调优后
  strategiesWeight/donchian_breakout_vol_rsi_ma_weight_v1.md
  ```

**反例**（**不允许**的命名）：

```
strategiesWeight/baseline_weight_v1.md         ← test name 必须是策略名, 不是 baseline
strategiesWeight/experiment1_weight_v1.md      ← 不允许任意 test name
```

#### 4.12.2 runner 默认行为

`BacktestRunner` 在 `weight_test` 为 None（或空字符串）时**默认用 `strategy_name`**：

```python
self.weight_test = weight_test if weight_test else strategy_name
```

因此调用方：
- `python strategy.py weight`（不传 `--weight-test`）→ 自动用 `ma_cross_atr_volume` 找 `ma_cross_atr_volume_weight_v*.md`
- `python strategy.py weight --weight-test ma_cross_atr_volume`（显式传）→ 同上
- `python strategy.py weight --weight-test experimental`（覆盖）→ 找 `experimental_weight_v*.md`（仅在有实验性 weight 文件时使用）

**CLI 层**（`subject/cli/main.py`）：`--weight-test` 改为可选（default None），去掉"weight 模式必填"约束。

**早期硬约束移除**：旧的 `if mode == "weight" and not weight_test: raise ValueError(...)` 已删除。

#### 4.12.3 文件命名在生成 / 调优侧的对应

| 阶段 | 输出文件命名 |
|---|---|
| 模式 1 generate | 无 weight 文件（`strategiesWeight/` 不存在）|
| 模式 3 factor_weights 跑出第一份 | `strategiesWeight/<strategy_name>_weight_v1.md` |
| 模式 3 factor_weights 再次调优 | `strategiesWeight/<strategy_name>_weight_v2.md` |

strategies 系统生成 / 调优时**必须**使用 `<strategy_name>_weight_v<n>.md` 命名（见 `strategies.md` 模式 3 章节同步更新）。

---

### 4.13 runner 参数扩展（test_universe_override / max_stocks / start_date / end_date）

`BacktestRunner.__init__` 支持以下参数（**所有这些参数都受 CONFIG 最高优先级覆盖**，见 §4.11.2）：

| 参数 | 类型 | 默认 | 作用 |
|---|---|---|---|
| `start_date` | `str \| None` | None | 起始日期 `YYYY-MM-DD` (含)，过滤 `df["日期"] >= start` |
| `end_date` | `str \| None` | None | 结束日期 `YYYY-MM-DD` (含)，过滤 `df["日期"] <= end` |
| `max_stocks` | `int \| None` | None | 限制测试股票数（取 universe 前 N）|
| `test_universe_override` | `list[str] \| None` | None | 自定义股票代码列表，**覆盖** spec.test_universe 解析结果 |
| `min_bars` | `int` | 20 | params 模式单只股票至少需要的 K 线数 |

**CLI 层对应**（`subject/cli/main.py`）：

| CLI 参数 | 格式 | 透传到 runner |
|---|---|---|
| `--start-date` | `YYYY-MM-DD` | `start_date` |
| `--end-date` | `YYYY-MM-DD` | `end_date` |
| `--max-stocks` | `int` | `max_stocks` |
| `--test-universe` | `代码1,代码2,代码3` (逗号分隔, 带后缀) | `test_universe_override`（逗号拆 list）|

**universe 解析优先级**（`BacktestRunner.__init__` 内）：

```python
if self.test_universe_override is not None:
    self.universe = list(self.test_universe_override)   # 最高
else:
    self.universe = self._resolve_universe()             # 从 spec 解析 (hs300 → HS300_CODES)
if self.max_stocks is not None:
    self.universe = self.universe[: self.max_stocks]      # 最后截前 N
```

---

## 5. `subject/` 公共库结构

```
subject/
├── factors/                  # 公共因子（@register_factor 装饰器）
│   ├── registry.py           # 因子注册表
│   ├── moving_average.py     # ma(close, period) -> Series
│   ├── atr.py                # atr(high, low, close, period=14) -> Series
│   ├── rsi.py                # rsi(close, period=14) -> Series
│   ├── donchian.py           # donchian_high/low(high/low, period) -> Series
│   └── volume_ratio.py       # volume_ratio(volume, period=20) -> Series
│
├── conditions/               # 公共条件原语（@register_condition 装饰器）
│   ├── registry.py
│   ├── fixed_stop.py         # check_fixed_stop(price, entry, pct) -> bool
│   ├── trailing_stop.py      # check_trailing_stop(price, highest, pct) -> bool
│   ├── atr_stop.py           # check_atr_stop(price, highest, atr, mult) -> bool
│   ├── time_stop.py          # check_time_stop(holding_days, max) -> bool
│   ├── channel_break.py      # check_channel_break(close, channel_value, direction) -> bool
│   ├── rsi_in_range.py       # check_rsi_in_range(rsi, low, high) -> bool
│   ├── rsi_above.py          # check_rsi_above(rsi, threshold) -> bool
│   └── volume_ratio_above.py # check_volume_ratio_above(volume_ratio, threshold) -> bool
│
├── params/                   # ParamDef 工具类（不放具体值）
│   └── registry.py           # ParamDef dataclass + @register_param
│
├── parser/                   # 策略 spec 解析器
│   └── strategy_md.py        # parse_strategy_spec(path) -> dict
│
└── backtest/                 # 回测基础设施
    ├── data_loader/          # 2 种模式入口 + 5 项必做处理
    ├── universe/             # hs300 / 退市 / ST / 新股 / 停牌
    ├── a_share_rules.py      # T+1 / 涨跌停 / 一字板
    ├── fees.py               # 交易费用 3 项
    ├── signals.py            # 多信号 AND + Σ(weight) 排名 + 出场优先级
    ├── portfolio.py          # 调仓 / 仓位约束
    ├── bear_market.py        # 沪深 300 20 日跌幅识别
    ├── log_utils.py          # 双 handler logger (file + console, 见 subject.md §3.8)
    ├── runner.py             # BacktestRunner
    ├── metrics.py            # 7 项指标
    ├── stats/
    │   ├── signal_stats.py
    │   └── factor_value_stats.py
    └── reports/
        ├── params_mode.py    # params 模式报告（MD）
        └── weight_mode.py    # weight 模式报告（MD）
```

---

## 6. 运行模式

> **核心约束**（详见 `subject.md` "测试模块边界（read-only 原则）"）：测试模块对策略内容只读不写；v2+版本、weight v2+版本、strategy.py 重新生成等行为**均由外部模块或人工执行**；LLM 发现 spec 问题时报告用户而非自行修复。

### 6.1 Mode 1：params 调参模式

- **数据源（硬绑定）**：`data-by-stock/`（时间序列）
- **测试集**：spec.frontmatter.`test_universe`（如 `hs300`），按此 list 逐股回测
- **输入**：`strategiesParam/<name>_v<n>.md`（**自动挑选** `<n>` 最大的）
- **逻辑来源**：`<strategy>/generated/strategy.py`（**手写的 3 个方法**，参考 `_original.md` 的 factors / entry-exit 条件，`position_weights` 段忽略，见 §4.7）
- **参数来源**：version 文件中的 `params[i].default`
- **权重来源**：`_original.md` 中的 `entry_signals[].weight` / `exit_signals[].weight`（**CLI / 外部 orchestrator 构造**为 `weights={"entry": {...}, "exit": {...}}` 传入 strategy.py，详见 §4.9）
- **输出**：`reportParams/report_v<n>.md`（MD 格式）
- **后续**：外部调参模块读报告 → 决定调哪些 `default` → 写 `<name>_v<n+1>.md`

### 6.2 Mode 2：weight 调权模式

- **数据源（硬绑定）**：`data-by-day/`（横截面）
- **测试集**：spec.frontmatter.`test_universe`（如 `hs300`），按此 list 每日横截面选股
- **输入**：`strategiesWeight/<test_name>_weight_v<n>.md`（按 `--weight-test` 指定 test，按 `<n>` 自动挑选最大）
- **逻辑来源**：`<strategy>/generated/strategy.py`（与 Mode 1 同一份代码，**不需要重新生成**）
- **参数来源**：`strategiesParam/` 中 latest `<name>_v<n>.md` 的 `params[i].default`（fallback 到 `_original.md` 的 default）
- **权重来源**：weight 版本文件中的 `entry_signals[].weight` / `exit_signals[].weight`（**覆盖** `_original.md` 的默认 weight，CLI 构造方式同 §4.9）
- **输出**：`reportWeight/report_signals_v<n>.md`（MD 格式）
- **后续**：外部调权模块读报告 → 决定调哪些 weight → 写 `<test_name>_weight_v<n+1>.md`

> **数据源硬绑定**：本项目**不**提供 `--data-mode` CLI 参数。`data-by-stock` ↔ params、`data-by-day` ↔ weight 的映射在 runner 内部硬编码。详见 `subject.md §3.0 / §5`。
>
> **正交关系**：`test_universe`（spec 字段，决定"测哪批股票"）与数据源（mode 决定）**完全正交**。同一 spec 在两种 mode 下 `test_universe` 不变。

### 6.3 latest 版本自动挑选算法

- 扫对应文件夹下所有匹配模式的 `.md` 文件
- 解析出每个文件的版本号 `<n>`
- 取最大 `<n>` 对应的文件
- 若文件夹为空 → 报错（要求至少存在一个 baseline 版本）

### 6.4 CLI 调用

```bash
# Mode 1（自动用 data-by-stock/，无需 --data-mode）
python -m subject.cli run --strategy <name> --mode params

# Mode 2（自动用 data-by-day/，需指定 weight test 名）
python -m subject.cli run --strategy <name> --mode weight --weight-test <test_name>
```

> **没有 `--data-mode` 参数**：数据源由 mode 硬绑定。`test_universe` 从 spec.frontmatter 读，不通过 CLI 传。

---

## 7. 输出格式（.md 报告）

**所有报告为 Markdown (.md) 格式**，不是 JSON。保存位置由 §6 规定。

### 7.1 params 模式报告骨架

```markdown
# Params Mode Report

**strategy**: <name>
**version**: v<n>
**date**: YYYY-MM-DD

## 测试条件（3 列：中文名 | 英文名 | 值）
| 中文名 | 英文名 | 值 |
|---|---|---|
| 测试集 | test_universe | spec.test_universe (300 只, 默认 hs300) |
| 实际测试股票数 | universe_size | 5 (受 limit=5 限制) |
| 测试起始日期 | start_date | 2024-01-01 |
| 测试结束日期 | end_date | 2024-12-31 |
| 股票数限制 | limit | 5 |

## Metrics（7 项，3 列：中文名 | 英文名 | 值）
| 中文名 | 英文名 | 值 |
|---|---|---|
| 年化收益 | annual_return | ... |
| 年化收益率 | avg_annual_return_rate | ... |
| 年化收益额 | avg_annual_return_amount | ... |
| 胜率 | win_rate | ... |
| 盈亏比 | profit_loss_ratio | ... |
| 夏普 | sharpe | ... |
| 最大回撤 | max_drawdown | ... |

## Signal Stats
| signal | triggered | swallowed | skipped | win_count | win_rate | avg_return | median_holding_days |
| ... |

## Factor Value Stats
| factor | min | max | mean | std | p25 | p50 | p75 |
| ... |
```

**测试条件字段说明**（来自 `BacktestRunner._build_test_conditions`）：

| 字段 | 来源 | 含义 |
|---|---|---|
| `test_universe` | `test_universe_override` 或 spec 解析 | 测试集来源描述（如"自定义 5 只"/"spec.test_universe (300 只, 默认 hs300)"）|
| `universe_size` | `len(self.universe)` | 实际跑的股票数（受 max_stocks 影响）|
| `start_date` | `self.start_date` | 测试起始日期 `YYYY-MM-DD`，None 时显示"不限" |
| `end_date` | `self.end_date` | 测试结束日期 `YYYY-MM-DD`，None 时显示"不限" |
| `limit` | `self.max_stocks` | 股票数限制，None 时显示"不限" |

### 7.2 weight 模式报告骨架（在 params 基础上多 `signal_attribution` 一节 + 测试条件含 `weight_test` 行）

```markdown
## 测试条件（weight 模式：多 weight_test 行）
| 中文名 | 英文名 | 值 |
|---|---|---|
| 测试集 | test_universe | ... |
| 实际测试股票数 | universe_size | ... |
| 测试起始日期 | start_date | ... |
| 测试结束日期 | end_date | ... |
| 股票数限制 | limit | ... |
| weight_test | weight_test | ma_cross_atr_volume   ← 等于策略名（§4.12） |

## Signal Attribution
| signal | return_share | win_share | loss_share | net_attribution |
| ... |
```

---

## 8. 调试模式注释规则

所有**调试模式脚本**（临时跑某个版本看效果、debug 等）必须在入口文件最上方用注释块标注：

```python
# debug_mode: <params_mode|weight_mode> / <single|monitor>
# strategy: <name>
# version: <v<n> | weight_<test_name>_v<n>>
# purpose: <调试目的>
# date: YYYY-MM-DD
```

CLI 模式下不直接生效（CLI 不是脚本）；仅适用于临时调试脚本。

---

## 9. LLM 读取顺序与决策流程

**目标**：一个无历史记忆的 LLM 拿到 `subject.md` + 某策略 spec 后，能直接生成该策略的测试系统。

### 9.1 读取顺序

```
1. subject.md                  ← 总规范（数据格式、A 股规则、运行模式、输出格式）
2. subject_structure.md        ← 本文件（代码架构、文件命名、生成规则）
3. PARTS_SUMMARY.md            ← ★ 现有公共部分清单（只读 + append）
4. <strategy_name>_original.md ← 本次要实现的策略 spec
```

### 9.2 决策流程

**步骤 0：读策略 spec**
- 调用 `parse_strategy_spec(<strategy>/<name>_original.md)` → 返回 `frontmatter` dict
- 后续步骤都基于该 dict 工作

**步骤 0a：读 strategy_narrative**
- 读 `<name>_original.md` 的 Markdown body 部分（含 `## 策略业务逻辑叙事`）
- 提取策略特定规则（如"至少 2 个入场信号触发"、"出场优先级"等）
- 这些规则**不在 frontmatter 里**，必须从 narrative 读
- LLM 翻译 `entry_score` / `should_exit` 时需参考 narrative 中的语义

**步骤 1：识别策略用到的公共部分（按语义检索）**
- **检索对象 1**：spec `frontmatter["factors"]` 列表的 `description` 字段 → 到 `PARTS_SUMMARY.md` §1 检索公共因子（不按 name 字面匹配，详见 §2.3）
  - 命中 → 复用（import 公共函数，按 §4.2.2 命名约定组装调用）
  - 未命中 → 进入步骤 2
- **检索对象 2**：spec `frontmatter["entry_signals"]` / `exit_signals` 的 `trigger` 字符串中的判断意图（如"RSI 在 40-70 区间"） → 到 `PARTS_SUMMARY.md` §2 检索公共条件
  - 命中 → strategy.py 翻译时**调**该公共 condition（如 `check_rsi_in_range`）
  - 未命中 → 策略私有（在 strategy.py 里手写 if-else，**不抽公共**，因为这是 strategy.py 内的逻辑）
- **检索对象 3**：spec `frontmatter["entry_signals"]` / `exit_signals` 列表项本身的 `factors` 字段引用的因子名 → 同检索对象 1（按 name → 公共因子映射）

**步骤 2：判断缺失的 factor / condition 是否应公共化**
- 完整判定流程与三路决策见 §2.3
- 简要：按语义判断"别的策略是否也可能用到" → 是 / 否 / 不确定，默认走公共

**步骤 3：实现 `generated/strategy.py`**
- 按 §4 规则翻译 `_original.md` 为 Python
- factor 调用 → import 自 `subject/factors/`
- condition 调用 → import 自 `subject/conditions/`
- entry / exit 逻辑 → 在 `class Strategy` 内手写
- 仓位约束 → 从 `params` 段同名条目读（如 `max_single_weight` / `max_industry_concentration` / `target_holdings` / `max_turnover_per_rebalance`），**不读** `position_weights` 段（见 §4.7）

**步骤 4：创建 baseline 版本**
- 复制 `_original.md` 到 `strategiesParam/<name>_v1.md`

**步骤 5：跑 mode 1 回测**
- CLI 自动挑 latest params 版本（v1）
- 输出 `reportParams/report_v1.md`

**步骤 6：（可选）调参循环**
- 外部模块读 report → 调 `default` → 写 `v2.md` → 跑 mode 1 → ...
- 不在本系统内

**步骤 7：（可选）weight 调权**
- 复制 latest params 版本到 `strategiesWeight/<test_name>_weight_v1.md`，修改 weights
- CLI 跑 mode 2 → 输出 weight 报告
- 外部模块调权 → 写 `_weight_v2.md` → 跑 mode 2 → ...

### 9.3 强制约束

- LLM **只能追加** `PARTS_SUMMARY.md` 的内容，**不能修改 / 删除** 现有行
- 修改 / 删除公共部分会破坏其他依赖这些部分的策略
- 公共部分的代码实现可以修改（如 bug fix），但**函数签名必须保持兼容**（不破坏现有调用方）
