# Subject 总规范

> **本文件**定义策略测试系统的**总规范**：输入数据格式、字段归属规则、测试模块边界、行情数据契约、A 股规则、运行模式、输出格式。
>
> **配套文档**：
> - [`subject_structure.md`](./subject_structure.md) —— 代码架构、公共 vs 私有判定、`_original.md` → 代码的翻译规则、LLM 工作流
> - [`PARTS_SUMMARY.md`](./PARTS_SUMMARY.md) —— 现有公共部分清单（factors / conditions / position state / backtest 基础设施），append-only
>
> **LLM 读取顺序**：先读 `subject.md`（本文件）→ `subject_structure.md` → `PARTS_SUMMARY.md` → 目标策略 `<name>_original.md`。

---

## 1. 策略 spec 格式（YAML frontmatter + Markdown body）

策略 spec 文件统一为 **YAML frontmatter + Markdown body** 格式。LLM 通过 `subject/parser/strategy_md.py` 的 `parse_strategy_spec(path) -> dict` 工具解析（**属于公共工具**，详见 `PARTS_SUMMARY.md`）。

### 1.1 frontmatter 必填段

| 段 | 用途 | LLM 是否消费 |
|---|---|---|
| `factors` | 因子声明（每个含 name / description / calculation） | ✅ description + name 用于检索公共因子 |
| `entry_signals` | 入场信号列表（每个含 name / weight / factors / direction / trigger / logic） | ✅ name + weight 是运行时数据；其余字段是**文档参考**（LLM 翻译 `strategy.py` 时理解意图，**不严格 1:1 翻译 trigger 字符串**） |
| `exit_signals` | 出场信号列表（结构同 entry_signals） | ✅ 同上 |
| `params` | 可调参数（每个含 name / default / range / type / description） | ✅ 全部字段运行时使用 |
| `position_weights` | 冗余历史段，**字段在 `params` 段都有副本** | ❌ 忽略（见 `subject_structure.md` §4.7） |
| `targets` / `test_universe` | 目标收益 / 测试股票池（回测期望指标） | ⚪ 报告用 |

> **触发器（trigger）字段的处理**：spec 里的 `trigger` 字符串（`close > donchian_high_20 AND volume_ratio_20 > {vol_breakout_threshold}`）是**给人类 + LLM 阅读的文档参考**，**不是** runner 的执行指令。runner 不知道也不解析 trigger 字符串——所有判断逻辑在 `<strategy>/generated/strategy.py` 里**手写**。LLM 翻译 strategy.py 时把 trigger 字符串当作**意图参考**翻译成 Python if-else 代码；runner 只调用 `entry_score` / `should_exit` 拿结果，**不读 spec 任何字段**。
>
> **顶层元数据字段**（frontmatter 末尾、`---` 闭合前的 `description` / `universe` / `holding_period` / `rebalance_freq`）：仅供人工阅读，**LLM 不消费**。如需 LLM 读取这些信息，应迁移到 `params` 段或 `strategy_narrative` 中。

### 1.2 body 必填节

| 节 | 用途 |
|---|---|
| `## 策略业务逻辑叙事` | 策略特定规则（入场信号数 / 出场优先级 / 牛熊处理等）**不在 frontmatter 里**的语义信息 |

### 1.3 spec 结构骨架（不含具体策略内容）

> **本文件不含任何具体策略的因子 / 信号 / 参数定义**。完整规范示例见任一 `<strategy>/<name>_original.md`（如 `donchian_breakout_vol_rsi_ma/donchian_breakout_vol_rsi_ma_original.md` / `ma_cross_atr_volume/ma_cross_atr_volume_original.md` / `multi_factor_trend_swing/multi_factor_trend_swing_original.md`）。
>
> spec 中因子名 / trigger 用**英文简称**（`close` / `high` / `low` / `volume`），DataFrame 用**中文全名**（`收盘价` / `最高价` 等），详见 `subject_structure.md` §4.2.1-§4.2.5。
>
> 字段含义已在 §1.1 表格列出，下方骨架示例**只展示结构**，不重复注释字段含义。

```yaml
---
name: <strategy_name>
targets:
  annual_return: <目标年化>
  win_rate: <目标胜率>
  profit_loss_ratio: <目标盈亏比>
  sharpe: <目标夏普>
  max_drawdown: <目标最大回撤>
  description: <目标描述>
test_universe:
- <universe_name>          # 如 HS300
factors:
- name: <factor_1>
  description: <中文描述>
  calculation: <计算公式，伪代码>
entry_signals:
- name: <signal_name>
  weight: <0-1 之间的小数>          # 通过 weights 参数注入，禁止硬编码（§4.9）
  factors: [<factor_1>, ...]
  direction: <positive | negative>
  trigger: <类 Python 表达式，可含 {param_name}>
  logic: <AND | OR | 单因子 | ...>
exit_signals:
  ...
position_weights:                  # 冗余历史段，**整体忽略**（§4.7）
  <key>: <value>
params:
- name: <param_name>
  default: <value>
  range: [<min>, <max>]
  type: <float | int>
  description: <中文描述>
---

## 策略业务逻辑叙事

### 1. 策略思路 / edge 来源
<策略特有的入场逻辑来源说明>

### 2. 市场环境假设
<A 股市场环境假设>

### 3. 牛 / 熊 / 震荡 3 环境处理（**所有阈值 param 化**）
<三环境的参数调整方案>

### 4. 多信号逻辑关系
- **入场时机**: <信号触发条件>
- **出场优先级**: <出场信号顺序>

### 5. 风险机制
- **涨跌停挤不出场**: <规则>
- **早期数据 NaN 处理**（**A 股硬约束**）：
  - 上市未满 N 日 → 该股票该日不参与信号计算
  - 长期停牌 → 复牌当日不立即入场
  - 涨跌停日 → 出场信号被吞
  - 新股 / 退市 → 默认跳过
```

> **关于 `position_weights` 段**：保留在 spec 中仅为向后兼容，**测试模块整体忽略该段**，所有可调字段以 `params` 段同名条目为准。详见 `subject_structure.md` §4.7。
>
> **关于 `position_state` 字段**：spec 的 `entry_signals[].trigger` / `exit_signals[].trigger` 字符串中可能引用 `current_price` / `entry_price` / `highest_close_since_entry` / `holding_days` / `pnl_pct` —— 这些是 position state 字段，**不属于 factors 段**，翻译为 `position["<name>"]` 访问（详见 `subject_structure.md` §4.5 强制规则 + `PARTS_SUMMARY.md` §2.5）。

---

## 2. 测试模块边界（read-only 原则）

> **核心原则**：**测试模块对策略内容只读不写。策略的任何修改不由测试模块执行。**

### 2.1 测试模块**可以**做的事

| 行为 | 写入位置 | 是否修改策略内容 |
|---|---|---|
| 读 `_original.md` 解析 spec | — | ❌ 否 |
| 读 `strategiesParam/<name>_v<n>.md` 取 params | — | ❌ 否 |
| 读 `strategiesWeight/<strategy_name>_weight_v<n>.md` 取 weights（test name = 策略名, 见 §3.7） | — | ❌ 否 |
| 读行情数据 | — | ❌ 否 |
| **首次** 生成 `<strategy>/generated/strategy.py`（从 `_original.md` 翻译） | `<strategy>/generated/` | ❌ 否（新增文件，不动 spec） |
| **首次** 创建 `strategiesParam/<name>_v1.md`（baseline，从 `_original.md` 复制） | `<strategy>/strategiesParam/` | ❌ 否（复制 _original.md，原文件未动） |
| 跑回测并**写入**报告 | `reportParams/` / `reportWeight/` | ❌ 否（报告是产出物，不是策略内容） |
| 追加公共条目 | `PARTS_SUMMARY.md` / `subject/` | ❌ 否（公共库是基础设施，不是策略内容） |

### 2.2 测试模块**不可**做的事

| 行为 | 原因 |
|---|---|
| 修改 `_original.md` | 策略定义不可变 |
| 修改 `strategiesParam/<name>_v<n>.md`（任何 n） | params 调参是外部模块的工作 |
| 修改 `strategiesWeight/<strategy_name>_weight_v<n>.md`（任何 n） | weight 调权是外部模块的工作 |
| 创建 `strategiesParam/<name>_v<n+1>.md` | v2+ 由外部调参模块创建 |
| 创建 `strategiesWeight/<strategy_name>_weight_v<n+1>.md` | weight v2+ 由外部调权模块创建 |
| 重新生成 `strategy.py`（因 params/weight 变了） | strategy.py 与版本/权重解耦，只在 `_original.md` 变了才重新生成 |
| 直接改 `strategy.py` 中的 weight / param 数值 | 数值来源于 spec 文件，代码内禁止硬编码（详见 `subject_structure.md` §4.9） |

### 2.3 LLM 发现 spec 问题时怎么办

如果 LLM 在生成 `strategy.py` 过程中发现 spec 存在问题：
- **不要**直接修改 spec 文件
- **不要**在生成的 `strategy.py` 中绕过问题
- **应当**：在 CLI 输出或一份"spec 审查报告"中列出所有问题，**让用户决定**如何修复
- LLM 的修复动作只限"`strategy.py` 内部消化问题"（如 §4.5 强制规则把 `highest_close_since_entry` 识别为 position state 而非 factor 函数生成）

### 2.4 版本与代码的解耦

- `strategy.py` 一份代码适用所有 v1 / v2 / v3 / ... + 所有 weight 版本
- 不同版本之间的差异**全部**由 runner 读取对应的 .md 文件后注入函数参数实现
- 这意味着 `_original.md` 改了才需要重新生成 `strategy.py`；只改 params / weight 不需要重新生成

### 2.5 `strategiesParam/<name>_v1.md` 复制语义

`strategiesParam/<name>_v1.md` = 从 `_original.md` 的 **frontmatter 完整复制**，**不含** Markdown body。

| 段 | 复制？ | 备注 |
|---|---|---|
| `name` | ✅ | |
| `targets` | ✅ | |
| `test_universe` | ✅ | |
| `factors` | ✅ | |
| `entry_signals` | ✅ | weights 也复制（baseline 默认） |
| `exit_signals` | ✅ | weights 也复制 |
| `position_weights` | ✅ | 保留段名（向后兼容，但 runner 不读，见 `subject_structure.md` §4.7） |
| `params` | ✅ | `default` / `range` / `type` / `description` 全部复制 |
| Markdown body | ❌ | v1.md 不需要 narrative——narrative 是 LLM 翻译 strategy.py 用的参考，不是 runner 输入 |

v2+ 由外部调参模块**只修改** `params[i].default` 后另存为 v2.md，其他段不动。

---

## 3. 测试数据格式（回测用行情数据）

> 来源：`D:\project\quant\my-quant3\data\README.md`

### 3.0 数据源总览

行情数据放在 **2 个目录**，按"读取视角"区分。本项目**没有** `--data-mode` 这类 CLI 公共参数，**数据源由运行模式硬绑定**（详见 §5）：

| 数据源 | 视角 | 文件数 | 覆盖年份 | 硬绑定 |
|---|---|---|---|---|
| `data-by-stock/` | 时间序列（单股全历史） | 5841 | 上市日 ~ 2026-05-14 | **params 模式** |
| `data-by-day/` | 横截面（每天全市场） | ~2267 | 2018 ~ 2026 | **weight 模式** |

> **重要正交关系**：
> - **数据源**（`data-by-stock` / `data-by-day`）↔ **运行模式**（params / weight）**硬绑定**，不可配置
> - **测试集**（spec.frontmatter.`test_universe`，如 `HS300`）↔ **数据源** **完全正交**
>   - 同一 spec 的 `test_universe` 在不同 mode 下含义不变（都是"测哪批股票"）
>   - params 模式按 test_universe 逐股做时间序列回测；weight 模式按 test_universe 在每日横截面中做选股

### 3.1 `data-by-stock/`（时间序列视角）

- **路径**：`data/data-by-stock/`
- **命名格式**：`{XXXXXX}_金玥数据.csv`（6 位纯数字代码）
- **文件数**：5841
- **覆盖日期**：每只股票从其上市日 ~ 2026-05-14（**最长约 26 年**，如 `000001` 平安银行自 2000-01-04 起）
- **单文件大小**：~1.6 MB（活跃股）/ 几十 KB（冷门股，如 `000003` 仅 ~99 KB）
- **每文件记录数**：每只股票的全部历史日线
- **数据形态注意**：
  - 包含北交所股票（`92` / `83` 开头），需按代码前缀过滤
  - 早期均线字段为空：上市未满 250 日的股票，前 250 日的 `120日线` / `250日线` 等为 NaN
  - 早期涨幅字段为空：上市未满 N 日的 `3日涨幅%` / `6日涨幅%` 等滚动涨幅字段为空
  - 退市股仍保留在目录中（`退市时间` 有值），按 `退市时间` 过滤
  - 停牌日：`成交量=0`、`收盘价=前收盘价`

### 3.2 `data-by-day/`（横截面视角）

- **路径**：`data/data-by-day/{YYYY}/`（**按年份分目录**，**不**是扁平）
- **文件命名**：`{YYYY-MM-DD}_金玥数据.csv`
- **覆盖年份**：2018 ~ 2026（9 个年份目录，~8.4 年）
- **每年文件数**：~243
- **总文件数**：~2267
- **单文件大小**：~1.5 ~ 1.6 MB
- **每文件记录数**：~4000-5000 行（覆盖全 A 当日所有股票）
- **数据形态注意**：
  - 完整覆盖 8+ 年牛熊周期：2018 熊末 / 2019-2020 牛 + 疫情 / 2021 牛尾 / 2022 熊 / 2023-2024 震荡 / 2025 反弹 / 2026-Q1 续涨
  - glob **必须**两层 `*/*` 模式：`data-by-day/*/*_金玥数据.csv`（**不**能只 glob 一层 `data-by-day/*`）
  - 路径构造：`data/data-by-day/{year}/{date}_金玥数据.csv`
  - 早期均线 / 涨幅 NaN：上市未满 N 日的股票当日记录中相应字段为空
  - 停牌日：同上

### 3.3 共同 Schema（38 列，2 种数据源完全一致）

**标识/元信息（4）**：`日期` (string `YYYY-MM-DD`) / `代码` (string 6 位纯数字) / `名称` (string, 含全角空格) / `所属行业` (string)

**行情（6）**：`开盘价` / `最高价` / `最低价` / `收盘价`（元）/ `前收盘价`（元）/ `振幅%`

**成交（4）**：`成交量（股）` / `成交额（元）` / `换手率`（%）/ `量比`（倍）

**涨跌相关（6）**：`涨幅%` / `3日涨幅%` / `6日涨幅%` / `10日涨幅%` / `25日涨幅%` / `是否涨停`（`是`/`否`）

**股本/市值（4）**：`总股本（股）` / `流通股本（股）` / `总市值（元）` / `流通市值（元）`

**估值（3）**：`滚动市盈率` / `市净率` / `滚动市销率`

**均线（7）**：`5日线` / `10日线` / `20日线` / `30日线` / `60日线` / `120日线` / `250日线`（元，简单移动平均）

**状态（4）**：`是否ST`（`是`/`否`）/ `是否融资融券`（`是`/`否`/空）/ `上市时间`（`YYYY-MM-DD`）/ `退市时间`（未退市为 `-`）

### 3.4 字段 → 模块映射（LLM 必读，2 种数据源通用）

| 字段 | 类型 | 模块 | 用途 | 必用？ |
|---|---|---|---|---|
| `日期` | Timestamp | `data_loader` | 时间索引 / 范围过滤 | ✅ |
| `代码` | str(6) | `data_loader` | 股票标识 / universe 过滤 / 北交所过滤 | ✅ |
| `名称` | str | `portfolio`（日志） | 显示/日志（已去全角空格） | ⚪ |
| `所属行业` | str | `portfolio` | 行业集中度约束（数据源，`enforce_industry_concentration` 读取） | ⚪ |
| `开盘价` | float | `factors` | 入场/出场参考价 | ✅ |
| `最高价` | float | `factors` / `portfolio` | 通道突破因子 / 止损触发价 | ✅ |
| `最低价` | float | `factors` / `portfolio` | 通道跌破因子 / 止损触发价 | ✅ |
| `收盘价` | float | `factors` / `portfolio` | **信号触发价 = 当日收盘价** | ✅ |
| `前收盘价` | float | `portfolio` | 涨跌停判断基准价 | ✅ |
| `振幅%` | float | `factors` | 波动率因子 | ⚪ |
| `成交量（股）` | int | `factors` / `portfolio` | 量能因子 / 流动性过滤 | ✅ |
| `成交额（元）` | int | `factors` / `portfolio` | 量能因子 / 最小成交额过滤 | ✅ |
| `换手率` | float | `factors` / `portfolio` | 流动性因子 / 换手率过滤 | ✅ |
| `量比` | float | `factors` | 量能放大因子 | ⚪ |
| `涨幅%` | float | `portfolio` | 当日涨跌停判断 | ✅ |
| `3日涨幅%` | float | `factors` | 短期动量因子 | ⚪ |
| `6日涨幅%` | float | `factors` | 短期动量因子 | ⚪ |
| `10日涨幅%` | float | `factors` | 中期动量因子 | ⚪ |
| `25日涨幅%` | float | `factors` | 中期动量因子 | ⚪ |
| `是否涨停` | bool | `portfolio` | 涨跌停判断 / 一字板跳过 | ✅ |
| `总股本（股）` | int | `portfolio` | 流通市值计算 | ⚪ |
| `流通股本（股）` | int | `portfolio` | 流通市值计算 / 最小可投资规模 | ✅ |
| `总市值（元）` | int | — | 当前 spec 未使用 | ❌ |
| `流通市值（元）` | int | `portfolio` | 最小可投资规模过滤 | ✅ |
| `滚动市盈率` / `市净率` / `滚动市销率` | float | — | 当前 spec 未使用 | ❌ |
| `5日线` / `10日线` / `20日线` / `30日线` / `60日线` / `120日线` / `250日线` | float | `factors` | 均线因子 | ✅ |
| `是否ST` | bool | `data_loader` | ST 过滤 | ✅ |
| `是否融资融券` | bool | — | 当前 spec 未使用 | ❌ |
| `上市时间` | date | `portfolio` | 新股过滤（跳过上市未满 N 日） | ✅ |
| `退市时间` | date | `data_loader` | 退市过滤 | ✅ |

图例：✅ **必用**（漏用 → 自检不通过）/ ⚪ **可选**（按策略 .md 决定）/ ❌ **当前未用**（不得自行添加）

### 3.5 读取约定（`data_loader.py` 必做的 5 项处理，2 种数据源通用）

1. `代码` 补后缀：6 位 → `xxx.SZ` / `xxx.SH`（`60xxxx` / `68xxxx` → SH；`00xxxx` / `30xxxx` / `20xxxx` → SZ；`92xxxx` / `83xxxx` → BJ）
2. `名称` 去全角空格：`万  科Ａ` → `万科A`（`re.sub(r"\s+", "", str(name))`）
3. `退市时间` `-` → `NaT`：`pd.to_datetime(退市时间, errors="coerce")`
4. `日期` → `pd.Timestamp`：`pd.to_datetime(日期)`
5. `是否ST` / `是否涨停` / `是否融资融券` → `bool`：`{"是": True, "否": False, "": False}`

### 3.6 2 种数据源读取入口差异

| 维度 | `data-by-stock/` | `data-by-day/` |
|---|---|---|
| 入口函数 | `load_stock(code: str) → DataFrame` | `load_day(date: str) → DataFrame` |
| 输入参数 | 6 位股票代码 | `YYYY-MM-DD` 日期 |
| 文件定位 | `data/data-by-stock/{code}_金玥数据.csv` | `data/data-by-day/{YYYY}/{date}_金玥数据.csv` |
| 返回结构 | 单股时间序列（按 `日期` 排序） | 单日横截面（全 A ~4000-5000 行） |
| 跨年拼接 | 单文件已含全历史，无需拼接 | 跨日循环，逐日读取后按 `代码` 对齐 |
| universe 过滤 | 由调用方提供 `code` 列表 | 通常在每日内再做 universe 过滤（按 `代码` 前缀） |

### 3.7 `strategiesWeight/` 文件命名规则

**`strategiesWeight/<strategy_name>_weight_v<n>.md`**

- **test name = 策略名**：本项目不存在"多 test 场景"概念，每个策略只有一份当前 weight 文件
- 文件前缀**必须**等于 `<strategy_name>`（runner 用 `f"{weight_test}_weight_v"` 找文件）
- 版本号 `v<n>`：`<n>` 为正整数，新调优产物递增（v1 → v2 → v3）
- **反例**（**不允许**）：`baseline_weight_v1.md` / `experiment1_weight_v1.md`（test name 必须是策略名）

**示例**（3 个策略当前产物）：

```
subjects/ma_cross_atr_volume/strategiesWeight/ma_cross_atr_volume_weight_v1.md
subjects/donchian_breakout_vol_rsi_ma/strategiesWeight/donchian_breakout_vol_rsi_ma_weight_v1.md
subjects/multi_factor_trend_swing/strategiesWeight/multi_factor_trend_swing_weight_v1.md
```

**runner 默认行为**：`BacktestRunner.weight_test` 为 None 时**默认 = strategy_name**，无需调用方传 `--weight-test`：

```python
self.weight_test = weight_test if weight_test else strategy_name
```

CLI 层（`subject/cli/main.py`）：`--weight-test` 改为**可选**（default None），去掉早期"weight 模式必填"硬约束。详细规范见 `subject_structure.md` §4.12。

**报告输出命名（连带影响）**：
- single：`report_signals_v<n>.md`
- monitor：`report_signals_v<n>_<YYYY-MM-DD>.md`

### 3.8 执行日志（log 文件）

每次回测自动在 `subjects/<strategy>/log/` 下生成日志文件，**同时**输出到 console：

- **文件路径**：`subjects/<strategy_name>/log/backtest_YYYY-MM-DD_HHMMSS.log`
- **格式**：`YYYY-MM-DD HH:MM:SS [LEVEL] message`
- **输出**：双 handler (FileHandler 永久保存 + StreamHandler 实时打印)
- **创建时机**：`BacktestRunner.__init__` 末尾（跑回测前就创建好）

**日志内容**：

| 阶段 | 等级 | 内容 |
|---|---|---|
| 启动 | INFO | 模式 / test name / 日期范围 / 初始资金 / test_universe / max_stocks / 实际 universe 数 |
| params 模式逐股 | INFO | `[i/N] code: N bars (date1 ~ date2)` |
| params 模式逐股 | INFO | `[i/N] code: entries=X, exits=Y, swallowed=Z` |
| params 模式逐股 | WARN | `[i/N] code - data not found` / `too few bars` |
| params 模式逐股 | ERROR | `[i/N] code - backtest failed` (含 stack trace) |
| weight 模式按日 | INFO | `[day i/N] date - processing`（约 20 次均匀进度）|
| weight 模式调仓 | INFO | `[date] rebalance #N: top M = codes...` |
| weight 模式 industry | WARN | `[date] industry_concentration failed: ...` |
| weight 模式跳日 | WARN | `[date] data file not found, skip` |
| 跑完 | INFO | `=== Run summary ===` 块: 处理/跳过数 / rebalance 数 / 交易数 / wall time / log 文件路径 |

**典型输出**（params 模式截取）：

```
2026-06-05 22:00:00 [INFO] === Log file: .../ma_cross_atr_volume/log/backtest_2026-06-05_220000.log ===
2026-06-05 22:00:00 [INFO] === BacktestRunner init ===
2026-06-05 22:00:00 [INFO] mode: params
2026-06-05 22:00:00 [INFO] test_universe: spec.test_universe (默认 HS300)
2026-06-05 22:00:00 [INFO] actual universe size: 5
2026-06-05 22:00:00 [INFO] === params mode: processing 5 stocks ===
2026-06-05 22:00:01 [INFO] [1/5] 000001.SZ: 1250 bars (2018-01-02 ~ 2026-05-14)
2026-06-05 22:00:03 [INFO] [1/5] 000001.SZ: entries=3, exits=2, swallowed=1
2026-06-05 22:00:03 [INFO] [5/5] 000005.SZ: 1100 bars (2018-01-02 ~ 2026-05-14)
2026-06-05 22:00:05 [INFO] === Run summary ===
2026-06-05 22:00:05 [INFO] stocks processed: 5/5
2026-06-05 22:00:05 [INFO] trades: 18 (wins: 10, losses: 8)
2026-06-05 22:00:05 [INFO] wall time: 0:00:05.123
2026-06-05 22:00:05 [INFO] log file: .../ma_cross_atr_volume/log/backtest_2026-06-05_220000.log
```

**实现入口**：`subject/backtest/log_utils.py::setup_backtest_logger(strategy_name, subjects_dir)` 返回 `(logger, log_file_path)`，被 `BacktestRunner.__init__` 调用。

---

## 4. A 股规则硬约束

> 回测**必须**兑现以下 A 股交易规则，由 backtest 代码生成器在生成回测代码时**强制兑现**。

### 4.1 交割与数量

- **T+1 交割**：当日买入次日方可卖出
- **最小买入 100 股**：买入数量必须是 100 的整数倍

### 4.2 涨跌停

| 板块 | 涨跌幅限制 |
|---|---|
| 主板（沪深） | ±10% |
| 创业板 / 科创板 | ±20% |
| ST 股票 | ±5% |

### 4.3 特殊状态

- **停牌日不成交**：成交量=0、收盘价=前收盘价
- **新股 / 退市 / 一字板默认跳过**：不参与回测

### 4.4 交易费用

| 费用项 | 费率 | 备注 |
|---|---|---|
| 买入佣金 | 万 2.5 | 最低 5 元 |
| 沪市过户费 | 万 0.1 | 仅沪市收取 |
| 卖出印花税 | 万 10 | 卖出时加收 |

---

## 5. 运行模式

**2 种模式 × 2 种调用方式**：

| 模式 | 调用方式 | 数据源（**硬绑定**） | 输入 | 调参对象 | 输出 |
|---|---|---|---|---|---|
| **params 模式** | single | `data-by-stock/`（时间序列） | `strategiesParam/<name>_v<n>.md`（自动挑最大 n） | `frontmatter.params` | `<strategy>/reportParams/report_v<n>.md` |
| **params 模式** | monitor | `data-by-stock/`（时间序列） | 同上 | 同上 | `<strategy>/reportParams/report_v<n>_<YYYY-MM-DD>.md`（多份带日期戳） |
| **weight 模式** | single | `data-by-day/`（横截面） | `strategiesWeight/<strategy_name>_weight_v<n>.md`（test name = 策略名, `--weight-test` 可覆盖） | `frontmatter.entry_signals[].weight` / `exit_signals[].weight` | `<strategy>/reportWeight/report_signals_v<n>.md` |
| **weight 模式** | monitor | `data-by-day/`（横截面） | 同上 | 同上 | `<strategy>/reportWeight/report_signals_v<n>_<YYYY-MM-DD>.md` |

> **数据源硬绑定规则**：params 模式**自动**用 `data-by-stock/`（按 spec.frontmatter.`test_universe` 逐股回测），weight 模式**自动**用 `data-by-day/`（按 spec.frontmatter.`test_universe` 每日横截面选股）。**不通过 CLI 或 spec 字段控制**。
>
> **与 `test_universe` 的正交关系**：`test_universe`（spec 字段）只决定**测哪批股票**，与数据源读取方式无关。同一 spec 的 `test_universe` 在两种 mode 下含义一致，runner 各自按 mode 加载数据。

**v2+ 版本**：params 模式由外部调参模块创建；weight 模式由外部调权模块创建（**测试模块不参与**，详见 §2.2）。

**完整定义**（输入/输出/算法/CLI/调用方边界）见 `subject_structure.md` §6。

### 5.1 monitor 调用方式

`single` 跑一次生成报告即退出；`monitor` 按 `--interval <N>d` 周期自动循环跑，每次生成**带日期戳的报告**（避免覆盖历史），并在报告里写 `monitor_meta` 跟踪运行状态。

- **CLI**：
  - `python -m subject.cli run --strategy <name> --mode params`（默认 single）
  - `python -m subject.cli run --strategy <name> --mode params --monitor --interval 1d`（monitor，每 1 天跑一次）
  - `python -m subject.cli run --strategy <name> --mode weight --weight-test <strategy_name> --monitor --interval 7d`（`--weight-test` 默认 = 策略名, 一般无需传）

- **报告命名**：
  - single：`report_v<n>.md` / `report_signals_v<n>.md`
  - monitor：`report_v<n>_<YYYY-MM-DD>.md` / `report_signals_v<n>_<YYYY-MM-DD>.md`（同一 `<n>` 多份，按日期排序）

- **monitor_meta 字段**（仅 monitor 报告）：

  | 字段 | 含义 |
  |---|---|
  | start_date | 监控启动日期（首次跑的时间） |
  | end_date | 最新一次跑的时间 |
  | run_count | 累计跑次数 |
  | trigger_count | 累计入场信号触发次数 |
  | last_update | 最新一次报告的生成时间 |

- **何时用 monitor**：跟踪策略在版本迭代中的稳定性、对比相邻日期的指标变化。
- **何时用 single**：单次调参 / 调权验证。

### 5.2 熊市识别阈值来源

`bear_market.py` 用的熊市识别阈值（沪深 300 20 日跌幅阈值）**优先从 `spec.params["bear_drawdown_threshold"]` 读**；如果 spec 没有这个字段，使用公共默认值 -0.10（即 -10%）。

- 策略可自定义（params 段添加 `bear_drawdown_threshold` 字段）
- 不自定义也能跑（公共默认值兜底）
- 当前 3 个策略中只有 `ma_cross_atr_volume` 显式声明（默认 -0.10，与公共默认一致）
- `multi_factor_trend_swing` 和 `donchian_breakout_vol_rsi_ma` 未声明，走公共默认

### 5.3 策略执行配置（CONFIG 最高优先级）

`generated/strategy.py` 顶部**必须**定义一个 `StrategyConfig` dataclass 和一个 `CONFIG` 实例，作为代码层**最高优先级**的运行配置（覆盖 CLI 参数和 spec 默认值）：

```python
from dataclasses import dataclass
from typing import Optional

@dataclass
class StrategyConfig:
    test_universe: Optional[list[str]] = None   # 自定义股票代码列表 (带后缀, 如 ["000001.SZ"])
    start_date: Optional[str] = None            # "YYYY-MM-DD", None = 不限
    end_date: Optional[str] = None              # "YYYY-MM-DD", None = 不限
    limit: Optional[int] = None                 # 限制测试股票数 (取前 N), None = 不限

CONFIG = StrategyConfig(
    test_universe=None,   # 例如: ["000001.SZ", "600000.SH", "000333.SZ"] (快速 debug 用)
    start_date=None,      # 例如: "2024-01-01"
    end_date=None,        # 例如: "2024-12-31"
    limit=None,           # 例如: 10 (调试时建议 5-10, 全跑慢)
)
```

**优先级链**（高→低）：

```
CONFIG (代码中)  >  CLI 参数  >  spec 默认值 (test_universe: HS300)
```

**CONFIG 4 字段与 runner 参数的对应**：

| CONFIG 字段 | 透传给 `subject.cli.main` | runner 接收 |
|---|---|---|
| `test_universe` | `--test-universe <逗号分隔>` | `BacktestRunner.test_universe_override` |
| `start_date` | `--start-date <YYYY-MM-DD>` | `BacktestRunner.start_date` |
| `end_date` | `--end-date <YYYY-MM-DD>` | `BacktestRunner.end_date` |
| `limit` | `--max-stocks <int>` | `BacktestRunner.max_stocks` |

**CLI 层对应参数**（`subject/cli/main.py`，供人工或外部脚本通过命令行传）：

```bash
# CONFIG 全 None 时, CLI 参数生效
python strategy.py --start-date 2024-09-01 --end-date 2024-09-30

# CONFIG 非空时, 改 CONFIG 而不是传 CLI (CLI 无法覆盖 CONFIG)
```

**universe 解析顺序**（`BacktestRunner.__init__` 内）：

```python
if self.test_universe_override is not None:
    self.universe = list(self.test_universe_override)   # 最高
else:
    self.universe = self._resolve_universe()             # 从 spec 解析 (HS300 → HS300_CODES)
if self.max_stocks is not None:
    self.universe = self.universe[: self.max_stocks]      # 最后截前 N
```

**典型调试场景**：

```python
# 场景 1: 快速 debug —— 只跑 3 只股 + 1 个月
CONFIG = StrategyConfig(
    test_universe=["000001.SZ", "600519.SH", "000333.SZ"],
    start_date="2024-06-01",
    end_date="2024-06-30",
    limit=None,
)

# 场景 2: 完整 benchmark —— 跑 HS300 全部 + 2024 全年
CONFIG = StrategyConfig(
    test_universe=None,
    start_date="2024-01-01",
    end_date="2024-12-31",
    limit=None,
)

# 场景 3: 部分股票 + 长期 + 限数
CONFIG = StrategyConfig(
    test_universe=["600519.SH", "000858.SZ", "000333.SZ"],
    start_date="2020-01-01",
    end_date="2024-12-31",
    limit=3,
)
```

详细规范（CONFIG 在 `__main__` 块中的透传实现 / `__main__` 块结构 / `--monitor` 行为）见 `subject_structure.md` §4.11–§4.13。

---

## 6. 输出格式（.md 报告）

> **报告格式**：本项目所有回测报告统一为 **Markdown (.md) 格式**。
> 报告章节骨架见 `subject_structure.md` §7。

**2 个模式 = 2 份报告**，每份报告聚焦一个调参对象：
- **params 模式** → 调参对象：`frontmatter.params`（信号触发阈值 / 止损参数 / 加减仓阈值）
- **weight 模式** → 调参对象：`frontmatter.entry_signals[].weight` / `exit_signals[].weight`（信号权重）

**不互相对比**：每份报告观察**本次运行**的关键测试结果，独立给出调参依据。

### 6.1 params 模式报告内容

| 章节 | 内容 |
|---|---|
| 元信息 | strategy / version / date |
| **测试条件（新增）** | 中文名（测试集 / 实际测试股票数 / 测试起始日期 / 测试结束日期 / 股票数限制） \| 英文名（test_universe / universe_size / start_date / end_date / limit） \| 值 |
| Metrics（7 项，3 列展示） | 中文名（年化收益 / 年化收益率 / 年化收益额 / 胜率 / 盈亏比 / 夏普 / 最大回撤） \| 英文名（annual_return / avg_annual_return_rate / avg_annual_return_amount / win_rate / profit_loss_ratio / sharpe / max_drawdown） \| 值 |
| Signal Stats | 每信号 triggered / swallowed / skipped / win_count / win_rate / avg_return / median_holding_days |
| Factor Value Stats | 每因子 min / max / mean / std / p25 / p50 / p75 |
| monitor_meta（仅 monitor 调用） | start_date / end_date / trigger_count / last_update |

**调参依据**：
- 阈值在 p25 附近 → 偏严，触发过少，可考虑下调
- 阈值远低于 p25 → 过松，触发过多
- p75 接近因子上限 → 触发集中在高值区，阈值可能过严
- `swallowed_count` 占比高 → 涨跌停日出场信号被吞多，止损/止盈参数需调整
- `skipped_count` 占比高 → A 股硬约束触发频繁，相关过滤参数需调整

### 6.2 weight 模式报告内容

包含 params 模式的所有章节，外加：

| 章节 | 内容 |
|---|---|
| **测试条件（含 weight_test 行）** | 同 params 模式 + weight_test (= 策略名) |
| Weights Used | entry / exit 信号权重快照 |
| Signal Attribution | 每信号 return_share / win_share / loss_share / net_attribution |

**调权依据**：
- 高 `win_rate` + 高 `avg_return` → 强势信号，应增加权重
- 低 `win_rate` 或负 `avg_return` → 弱势信号，应降低权重
- `return_share` 高 + `win_share` 高 → 强势信号，应加权重
- `loss_share` 显著高于 `win_share` → 弱势信号，应降权重
- `net_attribution` < 0 → 净拖累，建议大幅降权或停用

### 6.3 全局配置

- `initial_capital` 默认 1,000,000 元，CLI 公共参数可覆盖
- 所有 7 项指标的具体公式与硬规则见 `subject_structure.md` §7
