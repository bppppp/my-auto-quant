# my-quant3 — 策略生成系统

> **写于 2026-06-04**（最终版，9 轮迭代完成）。
> 本文件是 my-quant3 策略生成子系统的**完整项目 spec**——可直接据此实现。
> **核心数据**：42 个设计决策（A1–N4 + O1–O5；G4 模式 2/3 审计字段、O1–O5 收益门槛后期补充）+ 15 个核心设计原则 + **23 项校验（22 硬 + 1 软；按模式分类）**：模式 1 跑全 22 硬 + 1 软 / 模式 2 跑 **4 项** params 相关（`#13` description 长度检查仅模式 1）/ 模式 3 跑 9 项 signals 相关，**模式 2 / 3 无软校验**）+ 6 维 quality_eval 评估（**仅模式 1**）+ 模式 2 / 3 **不可改字段前后对比**（G2 / G3 扩展，**核心硬规则**）。
> **配套 spec**（单独 .md，后续提供）：backtest 代码生成器要求。
> **迭代历史**：4 轮（v1 → v4）+ 5 轮（R1 → R5，O1–O5 + #23 + data_implementability）= 9 轮渐进完善。

---

## 目录

1. [项目概述](#1-项目概述)
2. [15 个核心设计原则（P1–P15）](#2-15-个核心设计原则p1p15)
3. [42 个设计决策（详细）](#3-42-个设计决策详细)
4. [系统架构](#4-系统架构)
5. [模式 1：generate](#5-模式-1generate-详细设计)
6. [模式 2：optimize](#6-模式-2optimize-详细设计)
7. [模式 3：factor_weights](#7-模式-3factor_weights-详细设计)
8. [数据契约](#8-数据契约)
9. [质量评估（quality_eval）](#9-质量评估quality_eval)
10. [CLI 接口](#10-cli-接口)
11. [文件结构](#11-文件结构)
12. [配置](#12-配置)
13. [实现要点](#13-实现要点)
14. [失败处理](#14-失败处理)
15. [实现细节（决策未覆盖部分）](#15-实现细节决策未覆盖部分)
16. [核心设计原则速查](#16-核心设计原则速查)
17. [backtest 代码生成器要求（占位）](#17-backtest-代码生成器要求占位)

---

## 1. 项目概述

### 1.1 项目目标

为 A 股市场提供一个 **LLM 驱动的中周期波段策略生成与迭代系统**：

- **输入**：业务目标 + 数据契约
- **核心能力**：
  1. LLM 按目标生成新策略
  2. LLM 根据回测报告迭代调优策略
  3. LLM 调整策略的因子权重
- **输出**：可回测、可调优、可追溯的策略 `.md` 文件
- **目标用户**：量化研究员（具备基本编程能力 + LLM 协作能力）

### 1.2 核心域

| 项 | 规格 |
|---|---|
| 持仓周期 | 中周期（典型 2 周 – 2 个月） |
| 信号源 | **纯量价**（不含基本面、消息面） |
| **测试集** | 沪深 300 / 中证 1000 / 科创 50 / 创业板 50——每个策略从 4 个中**选 1 个或多个**作为测试集（**M1**） |
| **市场周期覆盖** | **必须能穿越牛熊**（**P13 / N1**）——回测期 ≥ 5 年 + 至少 1 轮完整牛熊周期；策略设计须考虑牛 / 熊 / 震荡 3 种环境的差异化处理 |
| 数据载体 | 日 K 线；信号与成交价同为日线收盘价 |
| 范围外 | 短 / 超短 / 长线、北交所、融券、跨市场、基本面驱动 |

### 1.3 关键约束

- **A 股硬约束**（**回测层职责**——**不**在策略 .md 中明文）：
  - T+1 交割；最小买入 100 股
  - 涨跌停：主板 ±10% / 创业·科创 ±20% / ST ±5%
  - 停牌日不成交；新股 / 退市 / 一字板默认跳过
  - 费用：买入佣金万 2.5（最低 5 元）+ 沪市过户费万 0.1；卖出加印花税万 10
  - 涨跌停挤不出场不静默、不算反事实收益
  - **由 backtest 代码生成器在生成回测代码时强制兑现**（详见后续**单独 .md** —— backtest 代码生成器 spec，本文件**不**含）
- **穿越牛熊**（**P13 / N1**）：
  - 回测期 ≥ 5 年 + 至少 1 轮完整牛熊周期（数据 2018-2026 覆盖 1.5 轮）
  - 策略设计须在 `strategy_narrative` 第 3 节明文说明牛 / 熊 / 震荡 3 种环境的差异化处理
  - 熊市必须有风控机制（降低仓位 / 收紧止损 / 切换因子权重）
- **不在本系统范围**：实盘下单代码、**回测代码生成**（由外部回测器按**单独 .md spec** 实现，**后续提供**）、数据采集

---

## 2. 15 个核心设计原则（P1–P15）

> 这些原则都有具体的设计决策（A1–N4 + O1–O5）做支撑。

| # | 原则 | 关键决策 |
|---|---|---|
| **P1** | **首版策略必须有明确业务目标**——LLM 按"同类型策略前 90%"自定目标，**写入 frontmatter 的 `targets` 字段**方便对照回测分析 | A1 / A2 / A3 |
| **P2** | **所有数值阈值必须 param 化**——入场、出场、档位细节全部暴露，不留硬编码 | B1 / B2 / B3 / B4 |
| **P3** | **参数取值范围必须足够宽**——调优空间 ≥ 3 倍经验合理值，靠 prompt 引导不卡硬数值 | C1 / C2 / C3 |
| **P4** | **新策略必须过 quality_eval**——1 次过，失败重生成整篇，反馈不留痕在 .md | D1 / D2 / D3 / K1 / K2 |
| **P5** | **模式 2 / 3 必须明确支持单次与监听**——互斥子命令组，默认单次 | E1 / E2 |
| **P6** | **报告权重按"最新主导"**——最多 5 份，隐式分配，不写死具体数字 | F1 / J1 / J2 |
| **P7** | **报告 token 分配差异化**——最新完整 + 其它精简，节省上下文 | F2 |
| **P8** | **模式 2 / 3 数据流精简同构**——LLM 只返新参数，本地 merge + 局部校验 | G1 / G2 / G4 |
| **P9** | **保留原始版本快照**——生成时同时写 `original.md`，建议不改 | H1 / H2 / H3 |
| **P10** | **factors 是"词汇"，signals 是"规则"**——factors 列表锁死（v1 后不增不删），**weight 在 entry_signals / exit_signals 上**（不在 factors 上）；weight 含义 = 该信号在多信号同发时的优先级，**不要求总和 = 1.0** | G3 |
| **P11** | **模式 3 bootstrap 严格走 signals track**——只读 `strategiesWeight/<name>_weight_v<N>.md`，**不 fallback 到 main track**（找不到直接报错）；`--from-original` 强制用顶层 original.md | I1 |
| **P12** | **测试集可单选 / 多选 + 参数描述详细 + 入口注释完备**——4 个 universe 选 1~N 个、param 描述清晰、所有调用指令写在入口文件顶部 | M1 / B4 / M2 |
| **P13** | **策略必须能穿越牛熊**——5+ 年回测覆盖至少 1 轮完整牛熊周期（数据：2018-2026 = 1.5 轮）；设计须考虑牛 / 熊 / 震荡 3 种环境的差异化处理；`strategy_narrative` 第 3 节必须明文说明。**注**：3 环境处理是**设计层面**说明（策略本身稳健），**不**要求实时市场状态识别 | A3 / N1 / N2 / N3 |
| **P14** | **入场 / 出场信号必须结构化**——`entry_signals` / `exit_signals` 列表中**逐条**含**信号名 / 命中因子 / 触发条件 / 因子逻辑**；多信号关系在 `strategy_narrative` 第 4 节说明，不能模糊描述 | N4 |
| **P15** | **期望年化收益必须 > 20%**——`targets.annual_return` 严格 > 0.20；且年化收益 / 回撤绝对值 ≥ 1.0（风险预算约束）；**win_rate × profit_loss_ratio ≥ 1.5**（数学自洽下界）；exit_signals 类别缺失需在 `strategy_narrative` 第 5 节明文说明（O5）；高夏普 + 低回撤 + 高收益 = 内部自洽；**因子 / trigger / param 全部可用本地 38 字段实现**（data_implementability） | O1 / O2 / O3 / O4 / O5 |

---

## 3. 42 个设计决策（详细）

> 决策编号按字母顺序排列（A → O），方便检索。每节首行标注对应原则编号。

### 3.1 盈利目标（P1）

| 编号 | 决策 |
|---|---|
| **A1** | 目标由 **LLM 根据策略类型自己定**；**至少是同类型策略的前 90%**（按历史回测排序） |
| **A2** | 目标**写入 .md frontmatter 的 `targets` 字段**——**方便回测后对照实际结果分析**。包含 5 项量化指标（年化收益 / 胜率 / 盈亏比 / 夏普 / 最大回撤）+ 文字说明 |
| **A3** | Phase 2 gate 5 项硬要求（5 年 / 夏普 > 1 / 回撤 < 15% / 牛熊一致 / 换手合理）作为 generate prompt 的**最低标准**写明，LLM 自定目标**可超过** |

### 3.2 可调整性（P2）

| 编号 | 决策 |
|---|---|
| **B1** | 参数数量按**"主动出场条件都暴露"定性判断**，**不卡数量**（不强制 ≥ N 个） |
| **B2** | **所有可调优的数值阈值**都**必须 param 化**——**硬规则**，违反则 quality_eval 不通过。具体覆盖范围：①入场阈值 ②出场阈值 ③调仓频率 ④加仓 / 减仓阈值 ⑤**风控识别阈值**（止损 / 止盈 / 时间止损等的数值判定，**不**包括"市场状态识别"） ⑥仓位调整系数 ⑦行业暴露上限 ⑧position_weights 块里的字段。**禁止在 body 任何位置写硬编码数字**（除非该数字是数学常量如 100 / 1000 股转换，或 system 隐含默认值）。**注意**：**不强制**要求"熊市 / 震荡市临时调整值"——市场状态判断无可靠依据（详见 N1 备注），策略应**设计层面**考虑穿越牛熊，而非依赖实时 regime detection |
| **B3** | **全部暴露**（包括档位细节），可调整性最大化，**不留任何硬编码数值** |
| **B4** | **每个 param 必须有详细 description**——描述必须含 4 要素（**含义 / 单位 / 典型取值 / 选默认值的理由**），**不能模糊**。quality_eval 检查这一项，模糊则不通过；硬校验 description 长度 ≥ 30 字符 |

### 3.3 取值范围（P3）

| 编号 | 决策 |
|---|---|
| **C1** | LLM 自己定宽度，prompt 引导"**调优空间 ≥ 3 倍经验合理值**"，不卡硬数值 |
| **C2** | **不加 range 相关硬校验**——靠 prompt 引导：**①**"range 宽度应足够宽"（C1 对应）**②**"default 应大致在 range 内"（C2 对应）。**模式 2 不做软检查**——LLM 自律，prompt 引导 |
| **C3** | **新策略按新规则**，旧策略（my-quant2 残留的 v1-v9）**保持原状，不迁移** |

### 3.4 新策略评估 + 硬校验（P4）

| 编号 | 决策 |
|---|---|
| **D1** | **新增独立 `quality_eval.py`**——独立 LLM 调用，独立评分；**包含原 self_eval 的所有检查项**；**仅模式 1 使用** |
| **D2** | 评估不通过 → **加反馈让 LLM 重生成**——但**反馈不能出现在修改后的 .md**（仅在 user_prompt 引导） |
| **D3** | 评估结果**只写日志**，**不进 .md frontmatter**（不污染产物） |
| **D4** | **硬校验按模式分类**（详见 §8.4）——模式 1 = **22 硬 + 1 软** 全跑（`#12` 软检查仅模式 1）；模式 2 = **4 项** params 相关（`#13` description 长度检查仅模式 1）+ G1/G2（含**不可改字段前后对比**：`name` / `type` / **`description`** 与 latest 一致）；模式 3 = 9 项 signals 相关 + G3（含**不可改字段前后对比**：`factors` 列表 + `entry_signals` / `exit_signals` 5 字段与 latest 一致）；**模式 2 / 3 不跑 LLM 评估**（硬失败 → 反馈 + 重生成，最多 5 次） |

### 3.5 入口设计（P5）

| 编号 | 决策 |
|---|---|
| **E1** | **互斥子命令组**：`optimize once <name>` / `optimize watch <name>`（factor_weights 同理） |
| **E2** | **默认单次触发**（`optimize <name>` 等价 `optimize once <name>`）——更轻量，避免误启动监听 |

### 3.6 报告权重（P6 / P7）

| 编号 | 决策 |
|---|---|
| **F1** | **不写死数字**（不写"6:1:1:1:1"），LLM 隐式处理"最新主导、其它辅助"（与"不写死方向"原则一致） |
| **F2** | **最新 1 份报告给完整内容** + **其它 4 份只给 §0 frontmatter + §1 关键指标 + §2 出场归因**（砍 §3 硬约束 + §4 修改意见）——**总 token 约 30%** |

### 3.7 参数合并 + factors 锁死 + 调优审计字段（P8 / P10）

| 编号 | 决策 |
|---|---|
| **G1** | **param 数量 1:1 覆盖**（仅模式 2）——LLM 必须返回**所有现有 param**（漏掉 → 报错），多给 → 丢弃（防 LLM 自由发挥）。LLM 返回**完整 param 列表** `[{name, default, range, type, description, ...}]`（**覆盖式**），本地按 `name` 匹配 merge |
| **G2** | **param 不可改字段前后对比**（仅模式 2）——除 `default` / `range` / `reason` 外的 param 字段（`name` / `type` / **`description`**）必须与 latest **完全一致**（字符串相等）。**任何不一致 → 硬失败 + 重生成**。`description` 锁死后，模式 2 不可改 description（含 B4 4 要素），LLM 必须原样复制 |
| **G3** | **factors 列表锁死**（仅模式 3）——v1 生成后**不增不删**，仅作"计算词汇表"——**不带 weight，不带 direction**。**G3 进一步要求**（**不可改字段前后对比**）：①factors 每个因子的 `name` / `description` / `calculation` 必须与 latest **完全一致** + 数量 1:1 ②`entry_signals` / `exit_signals` 每条 signal 的 `name` / `factors`（引用列表）/ `direction` / `trigger` / `logic` 5 字段必须与 latest **完全一致**（`weight` 是**唯一**可改的字段）。**任何不一致 → 硬失败 + 重生成**。**重要**：`factors` 列表**不进入 LLM 输出**——由代码从 latest 整体继承；LLM 仅输出 `entry_signals` + `exit_signals`（**仅 2 个顶层 key**）。weight 含义：①entry_signals 多信号同发时按 weight 比例决定排名 ②exit_signals 多信号同发时按 weight 比例排序触发优先级链。**不要求 weight 总和 = 1.0**，仅需满足比例关系（非负数）。每个 signal 自身就是一个组合（factor logic 写在 signal 内，AND / OR / 序列 / 单因子） |
| **G4** | **新增 `reason` 字段**（**仅模式 2 / 3 使用**）——LLM 在 param 列表的每个条目下挂一个 `reason` 字段（≤ 80 字符），说明本轮调优针对该 param 的具体理由。**审计 + 报告回放用**，**不写入 .md frontmatter**（避免污染产物）。**LLM 自由填写**——缺失不触发任何检查 / 报告标注 |

### 3.8 原始快照（P9）

| 编号 | 决策 |
|---|---|
| **H1** | 文件命名：`<name>_original.md`（与 `<name>_v1.md` 同目录） |
| **H2** | **建议不改**（人工约束，靠文档 + 代码注释提醒；不做技术锁） |
| **H3** | **不新增** `find_seed_md()`，重启时**人工指定** original 文件路径（`--from-original` flag） |

### 3.9 引导源（P11）

| 编号 | 决策 |
|---|---|
| **I1** | 模式 3 bootstrap **严格从 signals track 引导**——只读 `strategiesWeight/<name>_weight_v<N>.md`；**不 fallback 到 main track**（找不到直接 `FileNotFoundError`）。`--from-original` 强制用顶层 `<name>_original.md` |

### 3.10 报告数量（P6 配套）

| 编号 | 决策 |
|---|---|
| **J1** | **最多 5 份，不足没事**——按实际有的份数顺位分配（少一份则少一个 1× 权重，6× 主权不变） |
| **J2** | 超过 5 份时**只取最近 5 份**（按 `_v(\d+)` 数字倒序） |

### 3.11 评估协同（P4 配套）

| 编号 | 决策 |
|---|---|
| **K1** | **两层合并**——`validate_md_structure`（硬校验，机器判）→ `quality_eval`（业务质量评估，LLM） |
| **K2** | **`quality_eval` 1 次过**——评估失败**不重试**，**直接重生成整篇**（节省 18-54s） |

### 3.12 range 业务意义（P3 配套）

| 编号 | 决策 |
|---|---|
| **L1** | **不强制业务意义下限**——LLM 自由定范围，可能出现 `range=[0, 1]` 这种宽范围 |

### 3.13 测试集配置 + 入口注释（P12）

| 编号 | 决策 |
|---|---|
| **M1** | **测试集配置化**——每个策略在 frontmatter 声明 `test_universe: list`，从 4 个 universe（`hs300` / `csi1000` / `star50` / `cyb50`）中**选 1~4 个**作为测试集。默认 `["hs300"]`（单选）。**模式 2 / 3 不可改**（设计选择） |
| **M2** | **入口文件顶部注释**——`strategies.py` 顶部 docstring 包含**所有模式调用指令**（generate / optimize once\|watch / factor_weights once\|watch / list），每条带**简短说明**。便于首次使用者直接复制粘贴运行（见 §10.1） |

### 3.14 穿越牛熊（P13）

| 编号 | 决策 |
|---|---|
| **N1** | **策略必须能穿越牛熊**——`strategy_narrative` 第 3 节必须明文说明牛 / 熊 / 震荡 3 种环境的差异化处理（含入场 / 出场 / 仓位调整）。**注**：3 环境处理是**设计层面**的说明（策略**本身**在 3 种环境下都稳健），**不**要求实时市场状态识别。**实时判断市场是牛/熊/震荡** 没有可靠依据（任何启发式都有滞后 + 误判），强行要求会导致策略过度复杂 |
| **N2** | **回测期 ≥ 5 年 + 至少 1 轮完整牛熊周期**——数据层支持（`data-by-day/` 2018-2026 = 1.5 轮）；Phase 1 / Phase 2 默认时间范围 `2018-01-02 ~ 2026-05-14`（数据源实际范围） |
| **N3** | **牛熊不一致 → quality_eval 不通过**——LLM 评估时检查 `strategy_narrative` 第 3 节是否含 3 种环境处理说明；缺一即不通过，反馈 + 重生成 |

### 3.15 入场 / 出场信号结构化（P14）

| 编号 | 决策 |
|---|---|
| **N4** | **`entry_signals` / `exit_signals` 列表中每条**必须按统一格式含 6 字段：①`name`（含 `weight`）②`factors` ③`direction` ④`trigger`（伪代码）⑤`logic`（AND / OR / 序列 / 单因子）。**禁止**用一段话笼统描述入场 / 出场；多信号逻辑关系放 `strategy_narrative` 第 4 节说明 |

### 3.16 期望收益率门槛 + 止损分类（**O 系列**）

| 编号 | 决策 |
|---|---|
| **O1** | **期望年化收益率必须 > 20%**——`targets.annual_return` 必须严格 > 0.20（不含等于）。硬规则：硬校验 #21 检查 `targets.annual_return > 0.20`，违反则不通过 |
| **O2** | **期望收益必须内部自洽**——`targets.sharpe / targets.max_drawdown` 关系应合理（高收益 + 高回撤 = 矛盾；高夏普 + 低收益 = 不可能），quality_eval 软判断 |
| **O3** | **风险预算约束**——`targets.annual_return / abs(targets.max_drawdown)` 应 ≥ 1.0（收益回撤比），即年化收益至少等于回撤绝对值，否则视为"高风险低收益" |
| **O4** | **数学自洽性（soft check）**——`win_rate × profit_loss_ratio` 应 ≥ 1.5（即"期望单笔收益 / 风险" 比至少 1.5），作为 LLM 设定收益目标的合理下界。quality_eval 软判断；< 1.0 视为不自洽，1.0-1.5 视为激进，≥ 1.5 视为合理 |
| **O5** | **`exit_signals` 类别缺失需明文说明**——若策略未包含 ②移动止损（trailing stop，基于 `highest_close_since_entry` 等动态变量），**必须**用 ③通道反向止损（基于固定支撑/阻力位）替代，并在 `strategy_narrative` 第 5 节**显式说明**业务理由（如"均值回归策略无浮盈保护需求"）；第 6 节说明与其他策略差异时不重复此说明 |

---

## 4. 系统架构

### 4.1 整体架构（三层）

```
┌──────────────────────────────────────────────────────────────┐
│ 第一层：CLI 入口                                              │
│   strategies.py  (optimize / factor_weights 子命令组)         │
├──────────────────────────────────────────────────────────────┤
│ 第二层：3 模式 LLM 智能体                                     │
│   generate ─┐   quality_eval (业务质量评估，**仅模式 1**)     │
│   optimize ─┼─→ base_agent (硬校验 + 共享工具)              │
│   factor_  ─┘   watcher (watchdog + debounce)                 │
├──────────────────────────────────────────────────────────────┤
│ 第三层：策略实例                                              │
│   subject/<name>/                                            │
│     strategy/  (v<N>.md, original.md, weight_v<N>.md)        │
│     reports/   (report_v*.md, report_signals_v*.md)          │
│     backtest/  (外部回测器，按 .md 契约生成代码)              │
└──────────────────────────────────────────────────────────────┘
```

### 4.2 三大模式

| 模式 | 入口 | 核心能力 | 输出 |
|---|---|---|---|
| **模式 1: generate** | `strategies.py generate` | LLM 按业务目标生成新策略 | `<name>_v1.md` + `<name>_original.md` |
| **模式 2: optimize** | `strategies.py optimize once\|watch <name>` | 调 Part A 参数 | `<name>_v<N+1>.md` |
| **模式 3: factor_weights** | `strategies.py factor_weights once\|watch <name>` | 调 Part B 因子权重 | `<name>_weight_v<N+1>.md` |

### 4.3 两阶段开发（业务域）

| 阶段 | 优化对象 | 数据视角 | 主评估指标 |
|---|---|---|---|
| Phase 1 | Layer 1 信号规则 | per-stock, time-dim | 单股胜率 / 盈亏比 / 单股收益 |
| Phase 2 | Layer 2 / 3 仓位参数 | cross-section, per-day | 组合夏普 / 最大回撤 / 换手率 |

> **本系统（strategies）只负责策略 .md 的生成与调优**；**回测由外部回测器**（`subject/<name>/backtest/`）按 .md 契约实现。

---

## 5. 模式 1：generate 详细设计

### 5.1 工作流

```
┌─────────────────────────────────────────────────────────────┐
│ 启动 generate                                                │
└────────────────────────────┬────────────────────────────────┘
                             ↓
         ┌───────────────────────────────────┐
         │ 1) LLM 生成（think 模式, T=0.3）    │
         │    输入：业务目标 + 数据契约         │
         │    输入：策略域 + A 股硬约束        │
         │    输出：完整 .md (json)            │
         │    - frontmatter 7 区块 + 元信息    │
         │    - body 单字段 strategy_narrative   │
         │    - factors 列表（锁死，不带 weight）│
         │    - entry_signals / exit_signals   │
         │      各自带 weight（比例关系）      │
         │    - params 全部数值阈值 param 化   │
         └────────────────┬──────────────────┘
                          ↓
         ┌───────────────────────────────────┐
         │ 2) validate_md_structure (硬校验) │
         │    **22 项硬校验 + 1 项软检查（#12）** │
         │    （详见 §8.4，模式 1 跑全部）     │
         │    - frontmatter YAML 可解析       │
         │    - targets 5 项数值键齐全        │
         │    - test_universe 1~4 合法值      │
         │    - factors / entry_signals /     │
         │      exit_signals / position_      │
         │      weights / params 非空        │
         │    - signals weight 非负数值      │
         │      (G3 比例关系)                │
         │    - factors 引用一致性            │
         │    - range 是 2 元素 [min, max]    │
         │    - default in range（软）       │
         │    - params description ≥ 30 字符  │
         │    - A6 至少 3 类止损止盈          │
         │    - narrative 无硬编码数字（B2 完整）│
         │    - signals[].factors 与 trigger 一致│
         │    - position_weights 字段在 params│
         │      列表里有 B4 完整表达          │
         │    - narrative 引用 param 语义单义性│
         │    - factors 列表无孤立因子        │
         │    - trigger 公式无硬编码数字      │
         │    - factors description +         │
         │      calculation 字段非空          │
         │    - targets.annual_return > 0.20  │
         │    - 收益回撤比 ≥ 1.0             │
         │    失败 → 反馈 + 重生成（最多 5 次）│
         └────────────────┬──────────────────┘
                          ↓
         ┌───────────────────────────────────┐
         │ 3) quality_eval (LLM, 1 次过)     │
         │    - 业务目标达成度                │
         │    - 穿越牛熊（narrative 含 3 环境）│
         │    - 参数可调整性（B2 完整覆盖）  │
         │    - 逻辑自洽（权重合理 + 多信号）│
         │    - 数据可实现性（hard gate）    │
         │    （**结构完整性不入 soft**，由 22 硬校验覆盖） │
         │    失败 → 反馈 + 重生成（不写入）  │
         └────────────────┬──────────────────┘
                          ↓
         ┌───────────────────────────────────┐
         │ 4) 写盘                           │
         │    - <name>_v1.md                 │
         │    - <name>_original.md  (副本)   │
         └───────────────────────────────────┘
```

### 5.2 重试与失败

- 最大重试：5 次（默认，可配）
- 每次重试：把上次的失败原因（硬校验 / quality_eval）加入 user_prompt
- 反馈规则：反馈仅在 prompt 里引导，**不写入 .md**
- 5 次失败：抛异常退出，不写任何文件

### 5.3 产物

- `<name>_v1.md` —— 模式 2 / 3 迭代起点
- `<name>_original.md` —— 不可变原始快照（建议不改，H2）

---

## 6. 模式 2：optimize 详细设计

### 6.1 入口

```bash
# 单次触发（默认）
python strategies.py optimize <name>
python strategies.py optimize once <name>

# 持续监听
python strategies.py optimize watch <name>

# 重启时从原始版本引导（可选）
python strategies.py optimize once <name> --from-original
```

### 6.2 单次触发数据流（once）

```
┌─────────────────────────────────────────────────────────────┐
│ 1) 读 latest .md                                            │
│    - 默认：<name>_v<N>.md（最大版本号）                      │
│    - 重启：--from-original → <name>_original.md             │
└────────────────────────────┬────────────────────────────────┘
                             ↓
┌─────────────────────────────────────────────────────────────┐
│ 2) 读 5 份回测报告                                          │
│    - glob report_v*.md                                      │
│    - 取最近 5 份（J2）                                      │
│    - 不足 5 份：按实际数量（J1）                             │
│                                                             │
│    token 分配（F2）：                                        │
│    - 最新 1 份：完整内容                                    │
│    - 其它 4 份：仅 §0 + §1 + §2                            │
└────────────────────────────┬────────────────────────────────┘
                             ↓
┌─────────────────────────────────────────────────────────────┐
│ 3) LLM 调优（3+1 think 策略, per-round）                    │
│    - 输入：.md 全文 + 5 份报告（隐式"最新主导"）            │
│    - 输出：完整 param 列表 G1（覆盖式）                     │
│    - 约束：只动 Part A 参数值，不增不删不改方向             │
└────────────────────────────┬────────────────────────────────┘
                             ↓
┌─────────────────────────────────────────────────────────────┐
│ 4) 本地 merge + **params 硬校验**（4 项硬 + G1/G2）       │
│    - 按 name 匹配新 param                                   │
│    - 漏掉 → 报错（G1）                                     │
│    - 多给 → 丢弃（G1）                                     │
│    - 不可改字段前后对比（G2 扩展）——name + type 必须与 latest 完全一致 │
│    - 模式 2 专属校验（G1 / G2 + §8.4 C / E 组子集）       │
│    - 失败 → 反馈 + 重生成（最多 5 次）                      │
│    - **模式 2 不跑 LLM 评估**（quality_eval 仅模式 1）     │
│    - **不校验 signals / factors / targets / 章节**（继承）│
│    - **模式 2 无软校验**——LLM 自律 + prompt 引导           │
└────────────────────────────┬────────────────────────────────┘
                             ↓
┌─────────────────────────────────────────────────────────────┐
│ 5) 写盘 → <name>_v<N+1>.md                                 │
└─────────────────────────────────────────────────────────────┘
```

### 6.3 持续监听（watch）

- 先跑一次 `once`
- watchdog 监听 `subject/<name>/reports/report_v*.md` 新增
- debounce 5s 触发再跑 `once`
- 串行处理
- 最大监听次数 20（默认，可配）
- Ctrl+C 退出

### 6.4 报告读取规则

| 项 | 规则 |
|---|---|
| glob 模式 | `report_v*.md`（不递归） |
| 排序 | 按 `_v(\d+)` 数字倒序（最新 → 最旧） |
| 数量上限 | 5 份（J2） |
| 不足处理 | 顺位分配 6:1:1:1:1（J1） |
| 权重显式 | **不写死数字**给 LLM（F1） |
| token 分配 | 最新完整 + 其它 4 份精简（F2） |

### 6.5 调优对象边界（**硬规则**）

| 字段 | 模式 2 是否可改 | 说明 |
|---|---|---|
| `params[].default` | ✅ | **核心调优对象** |
| `params[].range` | ✅ | 可放宽/收窄 |
| `params[].reason`（仅审计）| ✅ | **不进入 .md**（不进 frontmatter）|
| `params[].name` | ❌ | narrative 引用 key，改名 = 旧 narrative 失效（**G2 前后对比**——见 §6.7）|
| `params[].type` | ❌ | 类型变更需 backtest 配合（**G2 前后对比**——见 §6.7）|
| `params[].description` | ❌ | **与 latest 完全一致**（**G2 前后对比**——见 §6.7；LLM 不改 description，原样复制；B4 4 要素由模式 1 保证，模式 2 不可改）|
| `params` 数量 | ❌ | **不增不删**（G1 硬规则）|
| `targets` | ❌ | v1 锁定，模式 2/3 不可改（参考"目标 vs 实际"对比是观察项） |
| `test_universe` | ❌ | M1 锁定 |
| `factors` 列表 | ❌ | G3 锁死（计算词汇表）|
| `entry_signals` 结构 | ❌ | G3 锁死；调 signal **权重**是模式 3 的事 |
| `exit_signals` 结构 | ❌ | 同上 |
| `position_weights` 结构 | ❌ | 5 字段结构锁死；对应 param 的 default 改了 → position_weights 显示值自动跟随 |
| `strategy_narrative` 字段 | ❌ | 整体继承，不重写 |

### 6.6 关键禁止（**LLM 业务层硬规则**）

| 禁止项 | 理由 |
|---|---|
| ❌ 改名（`params[].name` 与现有不一致） | body 失效（**G2 前后对比**）|
| ❌ 改 `type`（float ↔ int 切换） | backtest 端不支持（**G2 前后对比**）|
| ❌ 改 `description` | **G2 前后对比**——与 latest 必须完全一致 |
| ❌ 增删 param | G1 硬规则（缺/多都失败） |
| ❌ 改 `targets` | v1 锁定 |
| ❌ 改 `test_universe` | M1 锁定 |
| ❌ 改 `factors` 列表 | G3 锁死 |
| ❌ 改 `entry_signals` / `exit_signals` 结构 | G3 锁死 |
| ❌ 改 `entry_signals[].weight` / `exit_signals[].weight` | 模式 3 专属，模式 2 不可碰 |
| ❌ 改 `position_weights` 字段结构 | 5 字段结构锁死 |
| ❌ 重写 `strategy_narrative` | 整体继承 |
| ❌ `range` 不是 2 元素 [min, max] | 硬校验 |
| ❌ 一次改所有 param | 失去归因能力 |
| ❌ 改 `name` 语义方向（同一 param 用于不同业务含义） | 违反 **param 语义单义** |
| ❌ 自由发挥加新字段到 frontmatter | 模式 2 仅输出 params 列表 |

---

### 6.7 不可改字段前后对比（**G2 硬规则扩展**）

> **核心目的**：在本地 merge 之后，逐字段对比 LLM 返回的 `params` 与 latest .md 中的 `params` ——**除 LLM 显式声明的"可改字段"外，其余字段必须完全一致**。这是"**锁死"对 LLM 的硬约束**——prompt 引导 + 硬校验兜底。

**对比表**（mode 2 调优对象 vs 不可改字段）：

| param 字段 | 模式 2 是否可改 | G2 前后对比要求 |
|---|---|---|
| `name` | ❌ 不可改 | **必须与 latest 完全一致**（字符串相等）|
| `type` | ❌ 不可改 | **必须与 latest 完全一致**（字符串相等）|
| `description` | ❌ 不可改 | **必须与 latest 完全一致**（字符串相等）——LLM 不改 description，**原样复制** |
| `default` | ✅ 可改 | 不参与对比（LLM 的输出值）|
| `range` | ✅ 可改 | 不参与对比（LLM 的输出值）|
| `reason`（仅本轮审计用）| ✅ 可改 | **不进入 .md**（不进 frontmatter，prompt 引导即可）|

**执行流程**：

```
1) 本地按 name merge 后，得到 merged_params: list[dict]
2) 遍历每个 param：
   - 取 latest[i] 和 merged[i] 对应 param（按 name 1:1）
   - 对比 name 字段：latest.name == merged.name？
     - 不一致 → 硬失败（违反 G2 字符串匹配）
   - 对比 type 字段：latest.type == merged.type？
     - 不一致 → 硬失败（违反 G2 类型不变）
   - 对比 description 字段：latest.description == merged.description？
     - 不一致 → 硬失败（违反 G2 description 锁死——LLM 不改 description，原样复制）
3) 任意一个不一致 → 整轮重生成（反馈："param {name} 的 {field} 字段被修改，违反 G2 锁死"）
```

**反馈格式**（加入 user_prompt）：

```markdown
## ⚠️ 硬校验失败（G2 不可改字段前后对比）

违反规则：param `stop_loss_pct` 的 `description` 字段被修改。
- latest.description: `止损比例阈值（单位：小数，0.10 = 10%）。...`
- 你的输出.description: `止损比例阈值（单位：小数，0.12 = 12%）。...`
- 期望：保持与 latest **完全一致**（**G2 锁死**——LLM 不改 description，原样复制 latest）

请重新输出完整 params 列表（覆盖式），保持 `description` 字段不变。
```

**与 G1 的关系**：

| 检查项 | 关注点 | 失败处理 |
|---|---|---|
| **G1** | param **数量** 1:1 覆盖（缺/多）| 缺 → 报错 + 重试；多 → 丢弃 |
| **G2 扩展** | 每个 param 的**不可改字段**前后一致 | 任意不一致 → 报错 + 重试 |

> **G1 检查"有没有"，G2 扩展检查"对不对"**——两者配合形成"param 字段完整 + 锁死"的双重保障。

---

## 7. 模式 3：factor_weights 详细设计

### 7.1 与模式 2 的对称

| 维度 | 模式 2 (optimize) | 模式 3 (factor_weights) |
|---|---|---|
| 调优对象 | **Part A 参数值** | **Part B 信号权重** |
| 入口 | `optimize once\|watch <name>` | `factor_weights once\|watch <name>` |
| 引导源 | main track 最大版本 | **signals track 严格** → `original`(`--from-original` 时) ；**不 fallback 到 main track**（I1） |
| 输出文件 | `<name>_v<N+1>.md` | `<name>_weight_v<N+1>.md` |
| 监听文件 | `report_v*.md` | `report_signals_v*.md` |
| LLM 输出 | 完整 param 列表 | 完整 entry_signals + exit_signals 列表 |
| 强约束 | 只动 Part A，不增不删 | factors 列表锁死（G3），方向 param 化 |

### 7.2 数据流

```
读 latest <name>_weight_v<N>.md（signals track 严格，不 fallback）
  ↓ (无 weight 文件时直接 FileNotFoundError；--from-original 强制走 original)
  ↓
读 5 份 report_signals_v*.md（同 F2 分配）
  ↓
LLM 调权重（3+1 think）
  - 输出：完整 entry_signals + exit_signals 列表
         （每个 signal 含 name / weight / factors / direction / trigger / logic）
  - **factors 列表由代码从 latest 整体继承，LLM 不输出**
  - 约束：factors 列表不变 / signal 5 字段不变 / direction param 化 / weight 比例关系（不要求总和=1.0）
  ↓
本地 merge + **signals 硬校验**（9 项硬 + G3）
  - 模式 3 专属校验：G3（不可改字段前后对比——factors + signal 5 字段与 latest 完全一致）
  - §8.4 B 组：#4 / #5 / #6 / #7 / #8
  - §8.4 E 组：#16 / #20 / #23 / #24
  - 失败 → 反馈 + 重生成（最多 5 次）
  - **不校验 params / targets / 章节**（继承）
  - **模式 3 不跑 LLM 评估**（quality_eval 仅模式 1）
  ↓
写盘 → <name>_weight_v<N+1>.md
```

### 7.3 调优对象边界（**硬规则**）

| 字段 | 模式 3 是否可改 | 说明 |
|---|---|---|
| `entry_signals[].weight` | ✅ | **核心调优对象**（**唯一可改字段**）|
| `exit_signals[].weight` | ✅ | **核心调优对象**（**唯一可改字段**）|
| `entry_signals[].name` | ❌ | 改名 = `strategy_narrative` 章节（body 7 节）失效 |
| `entry_signals[].factors`（引用列表）| ❌ | 5 字段锁死 |
| `entry_signals[].direction` | ❌ | **调权重不改 direction**（改方向走 param 化）|
| `entry_signals[].trigger` | ❌ | 5 字段锁死 |
| `entry_signals[].logic` | ❌ | 5 字段锁死 |
| `exit_signals` 5 字段（`name` / `factors` / `direction` / `trigger` / `logic`）| ❌ | 同上 |
| `entry_signals` / `exit_signals` 数量 | ❌ | **不增不删**（G3 硬规则）|
| `factors` 列表（`name` / `description` / `calculation`）| ❌ | G3 锁死（计算词汇表）—— **LLM 不输出 factors**，由代码从 latest 整体继承 |
| `factors` 数量 | ❌ | **不增不删**（G3 硬规则）|
| `params` 列表 | ❌ | Part A，模式 2 的事 |
| `targets` | ❌ | v1 锁定 |
| `test_universe` | ❌ | M1 锁定 |
| `position_weights` 字段 | ❌ | 5 字段结构锁死 |
| `strategy_narrative` 字段（即 body）| ❌ | 整体继承 |

> **核心要点**（与 `factor_weights.md` 对齐）：
> - **LLM 仅输出 2 个顶层 key**：`entry_signals` + `exit_signals`（**覆盖式**，按 `name` merge）
> - **factors 列表不进入 LLM 输出**——由代码从 latest 整体继承；LLM 不传、不改、不输出
> - **`weight` 是 LLM 唯一被允许改变的字段**——其它所有字段硬校验兜底（详见 §7.5）

### 7.4 关键禁止（**LLM 业务层硬规则**）

| 禁止项 | 理由 |
|---|---|
| ❌ 在 JSON 输出中添加 `factors` 顶层 key | factors 列表由代码整体继承 |
| ❌ 改 `entry_signals` / `exit_signals` 数量 | G3 锁死（不增不删）|
| ❌ 改 5 字段（name / factors / direction / trigger / logic）中的任何一个 | 5 字段锁死——原样复制 latest |
| ❌ `entry_signals[].weight` / `exit_signals[].weight` 为负数 | #8 硬校验 |
| ❌ 一次改所有 weight | 失去归因能力 |
| ❌ 改 weight 为"语义反转"（如把 long signal weight 改为 0 来"禁用"）| 违反 G3 weight 比例关系 |
| ❌ 改 `factors` 列表（增删 + 改 name/description/calculation）| G3 锁死（计算词汇表）|
| ❌ 自由发挥加新字段到 frontmatter | 模式 3 仅输出 signals 列表 |

### 7.5 不可改字段前后对比（**G3 硬规则扩展**）

> **核心目的**：在本地 merge 之后，对 LLM 的输出和最终 .md 进行两类对比——**LLM 侧检查**（signals 5 字段，LLM 可控）和**代码侧检查**（factors 继承正确性，防御性兜底）。两类性质不同，**失败处理也不同**。

#### A. 对比表（mode 3 调优对象 vs 不可改字段）

| 字段 | 模式 3 是否可改 | G3 前后对比要求 | **检查侧** |
|---|---|---|---|
| `entry_signals[].weight` / `exit_signals[].weight` | ✅ 可改 | 不参与对比（LLM 的输出值）| — |
| `entry_signals[].name` / `exit_signals[].name` | ❌ 不可改 | **必须与 latest 完全一致**（字符串相等）| **LLM 侧**（LLM 输出）|
| `entry_signals[].factors`（引用列表）/ `exit_signals[].factors` | ❌ 不可改 | **必须与 latest 完全一致**（list 元素逐一对比）| **LLM 侧**（LLM 输出）|
| `entry_signals[].direction` / `exit_signals[].direction` | ❌ 不可改 | **必须与 latest 完全一致**（字符串相等）| **LLM 侧**（LLM 输出）|
| `entry_signals[].trigger` / `exit_signals[].trigger` | ❌ 不可改 | **必须与 latest 完全一致**（字符串相等）| **LLM 侧**（LLM 输出）|
| `entry_signals[].logic` / `exit_signals[].logic` | ❌ 不可改 | **必须与 latest 完全一致**（字符串相等）| **LLM 侧**（LLM 输出）|
| `entry_signals` / `exit_signals` 数量 | ❌ 不可改 | 必须 == latest 数量（**不增不删**）| **LLM 侧** |
| `factors[].name` | ❌ 不可改 | **必须与 latest 完全一致**（字符串相等）| **代码侧**（factors 不进入 LLM 输出，由代码从 latest 整体继承）|
| `factors[].description` | ❌ 不可改 | **必须与 latest 完全一致**（字符串相等）| **代码侧**（同上）|
| `factors[].calculation` | ❌ 不可改 | **必须与 latest 完全一致**（字符串相等）| **代码侧**（同上）|
| `factors` 数量 | ❌ 不可改 | 必须 == latest 数量（**不增不删**）| **代码侧**（继承 latest，理论上必一致）|

#### B. 执行流程（**LLM 侧 vs 代码侧**）

```
【LLM 侧检查】—— LLM 输出的 entry_signals / exit_signals
1) LLM 返回 merged_signals: {entry_signals, exit_signals}（**仅 2 个顶层 key**）
2) 遍历每条 signal：
   - 取 latest[i] 和 merged[i] 对应 signal（按 name 1:1）
   - 对比 5 字段：name / factors / direction / trigger / logic
   - 任意字段与 latest 不一致 → 硬失败 → 反馈 + LLM 重生成

【代码侧检查】—— 最终 .md 的 factors（**防御性兜底**）
3) 代码从 latest 整体继承 factors 到新 .md（**LLM 不参与**）
4) 检查新 .md 的 factors：
   - 数量对比：len(latest.factors) == len(new_md.factors)？
   - 逐个 factor 对比：latest[j] 和 new_md[j]（按 name 1:1）的 name / description / calculation
   - 任意不一致 → 硬失败 → **代码 bug，非 LLM 错误**（理论上不会发生）
```

> **重要区分**：
> - **LLM 侧失败** = LLM 改了不该改的字段 → 反馈 + LLM 重生成（最多 5 次）
> - **代码侧失败** = factors 继承出错（防御性）→ 理论上不会发生；如发生则是代码 bug，需要修 merge 逻辑

#### C. 反馈格式（LLM 侧失败）

```markdown
## ⚠️ 硬校验失败（G3 不可改字段前后对比）

违反规则：entry_signal `momentum_breakout` 的 `direction` 字段被修改。
- latest.direction: `long`
- 你的输出.direction: `short`
- 期望：保持与 latest 完全一致（**调权重不改 direction**；改方向的方式是 param 化）

请重新输出完整 entry_signals + exit_signals 列表（**仅 2 个顶层 key**，不含 factors），保持 5 字段不变。
```

#### D. G3 数量锁死 + 字段锁死（双重保障）

| 检查项 | 关注点 | 范围 | 失败处理 |
|---|---|---|---|
| **G3 数量锁死** | `entry_signals` / `exit_signals` **数量** 与 latest 一致 | LLM 侧 | 缺/多 → 反馈 + LLM 重试 |
| **G3 信号字段锁死** | 每个 signal 的 5 字段（`name` / `factors` / `direction` / `trigger` / `logic`）前后一致 | LLM 侧 | 任意不一致 → 反馈 + LLM 重试 |
| **G3 factors 锁死** | `factors` 列表的 3 字段（`name` / `description` / `calculation`）前后一致 | **代码侧**（防御性）| 不一致 → 代码 bug，**不重试** |

> **G3 数量锁死检查"数量有没有变"**，**G3 字段锁死检查"内容有没有变"**——两者配合形成"结构完整 + 内容锁死"的双重保障。

---

---

## 8. 数据契约

### 8.1 策略 .md 文件结构

```
<name>_<version>.md
│
├── YAML Frontmatter (7 区块 + 元信息，结构固定)
│   ├── targets: {...}             # 业务目标（A2 必填）
│   ├── test_universe: [...]       # 测试集（M1 必填）
│   ├── factors: [...]             # 锁死，仅"计算词汇表"，不带 weight / direction
│   ├── entry_signals: [...]       # 入场信号，weight 标在这里（G3）
│   ├── exit_signals: [...]        # 出场信号，weight 标在这里（G3）
│   ├── position_weights: {...}    # 仓位参数
│   ├── params: [...]              # 所有数值阈值 param 化
│   └── 元信息: {description, universe, holding_period, rebalance_freq}
│
└── Body (1 字段：`strategy_narrative`，≥ 1500 字符业务逻辑叙事)
    └── ## 策略业务逻辑叙事（含 6 节：思路 / 环境 / 3 环境处理 / 多信号关系 / 风险机制 / 差异化）
```

### 8.2 Frontmatter 规范

#### `targets`（**A2 必填**）

```yaml
targets:
  annual_return: 0.15            # 年化收益目标（小数，0.15 = 15%）
  win_rate: 0.50                 # 胜率目标（小数）
  profit_loss_ratio: 1.8         # 盈亏比目标
  sharpe: 1.2                    # 夏普目标
  max_drawdown: -0.12            # 最大回撤目标（负数）
  description: |
    动量策略，参考同类型前 90% 水平设定。
    锚点：年化 15% / 胜率 50% / 盈亏比 1.8 / 夏普 1.2 / 回撤 12% 以下。
```

- **5 项数值必填**：`annual_return` / `win_rate` / `profit_loss_ratio` / `sharpe` / `max_drawdown`
- `description` 可选（业务锚点说明）
- **写入 .md 的目的**（A2）：**回测后对照实际结果分析**——报告 §1 应包含"目标 vs 实际"对比
- **模式 2 / 3 不可改**（设计选择，非调优对象）
- LLM 自定原则：参考"同类型策略前 90%"水平（A1）

#### `test_universe`（**M1 必填**）

```yaml
test_universe: [hs300]            # list，从 4 个中选 1~4 个
# 合法值：hs300 / csi1000 / star50 / cyb50
# 默认：[hs300]；模式 2 / 3 不可改
```

#### `factors` 列表（必填，**仅"计算词汇表"**）

```yaml
factors:
  - name: return_20d
    description: 20 日收益率因子，衡量近期股价走势强度
    calculation: "close / close_20d_ago - 1"
  - name: rsi_14d
    description: 14 日相对强弱指数
    calculation: "rsi(close, 14)"
  - name: vol_ratio
    description: 量比
    calculation: "volume / mean(volume, 20)"
```

**约束**（G3）：
- **不带 weight**，**不带 direction**
- 列表 v1 后**锁死**（不增不删）
- 方向调整通过 param 化实现

**每因子必含 3 字段**（**硬规则 #24**）：
- `name`：唯一标识，snake_case
- `description`：业务含义
- `calculation`：**计算规则伪代码**——backtest 端据此实现因子计算

#### `entry_signals` 列表（必填，**weight 标在这里**）

```yaml
entry_signals:
  - name: trend_confirm
    weight: 0.40                  # 比例关系（不要求总和=1.0）
    factors: [return_20d]         # 引用 factors 列表（可空[]，但不能引用 param）
    direction: positive           # 该信号对 factors 的方向（positive / negative）
    trigger: "return_20d > 0.05"  # 触发条件伪代码
    logic: AND                    # 因子逻辑（AND / OR / 序列 / 单因子）
  - name: volume_breakout
    weight: 0.30
    factors: [vol_ratio]
    direction: positive
    trigger: "vol_ratio > 2.0"
    logic: 单因子
  - name: rsi_moderate
    weight: 0.30
    factors: [rsi_14d]
    direction: positive
    trigger: "40 < rsi_14d < 70"
    logic: 单因子
```

**`factors` 字段语义**（修复 v1 漏洞）：
- **该信号直接依赖的因子**列表
- **可空 `[]`**：当信号仅依赖 param（如时间止损）
- **若非空**：所有元素**必须**在 `factors` 列表中存在
- **禁止**：把 param 名塞进 `factors` 列表（param 不属于计算词汇表）

#### `exit_signals` 列表（必填，**weight 标在这里**）

```yaml
exit_signals:
  - name: fast_stop
    weight: 0.40                  # 比例关系（不要求总和=1.0）
    factors: [return_5d]
    direction: negative
    trigger: "return_5d < -0.03"  # 5 日内亏 3% 触发
    logic: 单因子
  - name: trend_break
    weight: 0.30
    factors: [rsi_14d]
    direction: negative
    trigger: "rsi_14d < {rsi_exit_threshold}"
    logic: 单因子
  - name: take_profit
    weight: 0.30
    factors: [return_from_entry]
    direction: positive
    trigger: "return_from_entry > {take_profit_pct}"
    logic: 单因子
  - name: time_stop
    weight: 0.20
    factors: []                   # 仅依赖 param（max_holding_days），factors 留空
    direction: negative
    trigger: "holding_days >= {max_holding_days}"
    logic: 单因子
```

#### weight 校验规则（**G3 兑现**）

- **不要求** `Σ entry_signals[].weight = 1.0`
- **不要求** `Σ exit_signals[].weight = 1.0`
- weight 只需满足**比例关系**（非负数，比例决定优先级）
- **`factors` 不带 weight**（仅作"计算词汇"）
- 需要排序时：现场计算 `priority_i = weight_i / Σ(weights)`

#### `trigger` 公式变量（**无白名单限制**）

trigger 公式可使用**任何变量名**，包括但不限于：
- `factors` 列表中的因子名
- `params` 列表中的 param（用 `{param_name}` 引用）
- K 线系统变量：`close` / `open` / `high` / `low` / `volume` / `amount`
- 持仓系统变量：`current_price` / `entry_price` / `holding_days`
- 持仓过程变量：`highest_close_since_entry` / `lowest_close_since_entry` / `drawdown_from_peak` / `pnl_pct`
- **技术分析常见变量**（**自由使用**）：
  - 滞后值：`<factor>_prev` / `<factor>_lag_N`
  - 差值：`<a> - <b>` / `<a>_diff`
  - 比率：`<a> / <b>` / `<a>_ratio`
  - 变化率：`<a>_change_<N>d` / `<a>_pct_change_<N>d`
  - 滚动统计：`mean_5d` / `std_5d` / `max_5d` / `min_5d`

**原则**：backtest 端负责实现 LLM 使用的变量；LLM 专注于策略业务逻辑。**白名单**过去限制了策略多样性，**已移除**——信任 LLM 的设计选择。

**唯一限制**：
- ❌ 禁止引用 `position_weights` 块里的字段名（如 `target_holdings` 不应直接出现在 trigger，应通过 `{param_name}` 引用）
- ❌ 禁止引用 `meta` 信息（`universe` / `holding_period` 等）

#### `position_weights`（必填，至少 1 字段，**修复 v2 漏洞**）

```yaml
position_weights:
  max_single_weight: 0.10
  max_industry_concentration: 0.25
  target_holdings: 6
  max_turnover_per_rebalance: 0.50
```

**`position_weights` 与 `params` 关系**（B2 兑现）：
- position_weights 提供**结构化仓位参数概览**（阅读友好）
- **同一字段必须**也在 `params` 列表里出现，**带 B4 description + range + default**
- 例：`position_weights.target_holdings: 6` 必须**同时**在 `params` 里有 `name: target_holdings / default: 6 / range: [...] / description: "..."`
- **硬校验**（§8.4 #18）：position_weights 字段必须在 params 列表里能找到同名 param
- **禁止**：position_weights 块里的字段**仅**在此处出现而 params 列表里没有（该字段不可调优）

#### `params` 列表（必填，**所有数值阈值；B4 每个必须有详细 description**）

```yaml
params:
  - name: stop_loss_pct
    default: 0.10
    range: [0.05, 0.20]           # 必须是 2 元素 [min, max]
    type: float
    description: |
      止损比例阈值，相对于入场价最大容忍亏损（单位：小数，0.10 = 10%）。
      典型取值：0.05（紧止损，保护本金）/ 0.10（中等）/ 0.20（宽止损，给趋势更多空间）。
      默认值 0.10：基于趋势策略历史回测，中等止损在胜率与盈亏比间取较优平衡。
```

#### 元信息（可选）

- `description`：策略一句话描述
- `universe`：股票池说明
- `holding_period`：持仓周期
- `rebalance_freq`：调仓频率

### 8.3 Body 单字段：`strategy_narrative`（业务逻辑叙事）

**核心原则**：frontmatter 是机器可读的结构化字段，`strategy_narrative` 是人可读的策略设计说明——承载"业务智慧"。

| # | 必含节 | 内容 | 来源 frontmatter |
|---|---|---|---|
| 1 | **策略思路 / edge 来源** | 策略核心 edge、市场为何有效 | 无（前文不存） |
| 2 | **市场环境假设** | 策略适用 / 不适用的市场条件 | 无 |
| 3 | **牛 / 熊 / 震荡 3 环境处理**（**N1 必含**，quality_eval 强校验） | 3 环境差异化处理（**所有阈值 param 化**） | 部分（`bear_*` params） |
| 4 | **多信号逻辑关系** | 入场时机（任一/全部/按序）+ 出场优先级 | 无 |
| 5 | **风险机制** | 熊市风控 + 涨跌停挤不出场 + 优先级链 | 无 |
| 6 | **与其他策略区别** | 3 行以内差异化定位（**不写对比表格**） | 无 |

**字段约束**：
- **类型**：单 string 字段
- **字符数**：**≥ 1500 字符**（约 600 tokens）
- **不重复 frontmatter**：因子定义 / 信号规则 / 参数列表 / 仓位上限**不要在 narrative 重复**
- **不写目标数字**：annual_return / win_rate 等数字在 `targets` 字段
- **所有阈值 param 化**：引用的数字必须用 `{param_name}`

**示例骨架**：

```markdown
## 策略业务逻辑叙事

### 1. 策略思路 / edge 来源
本策略基于 A 股...的延续效应，捕捉中周期...的特定模式。

### 2. 市场环境假设
- A 股存在...特征
- ...

### 3. 牛 / 熊 / 震荡 3 环境处理（**所有阈值 param 化**）
- **牛市**: 满仓运行，让趋势充分发展
- **熊市**: 固定止损 + 仓位折算 + 收紧门槛
- **震荡市**: 时间止损 + 信号稀疏 + 调仓延长

### 4. 多信号逻辑关系
- **入场时机**: 至少 2 个信号同时触发；sum(weight) 决定排名
- **出场优先级**: 固定止损 → 移动止损 → 时间止损

### 5. 风险机制
- **熊市识别**: 沪深 300 20 日跌幅 < `{bear_drawdown_threshold}`
- **涨跌停挤不出场**: 当日涨跌停时所有出场信号被吞，报告 §2 记录"信号被吞次数"

### 6. 与其他策略区别
本策略区别于...（3 行以内）
```

### 8.4 硬校验（validate_md_structure）

> **22 项硬校验 + 1 项软检查（#12）+ 1 项已废除（#17）**——按"适用模式"分组如下：

| 模式 | 硬校验数 | 软检查 | 总数 |
|---|---|---|---|
| **模式 1 (generate)** | **22 项**（基础 + signals + params + narrative + 因子 + 收益） | 1 项（#12）| **23 项** |
| **模式 2 (optimize)** | **4 项**（仅 params 相关——`#13` description 长度检查仅模式 1）| **0 项**（**软校验已移除**）| 4 项 |
| **模式 3 (factor_weights)** | **9 项**（仅 signals / factors 相关） | 0 项 | 9 项 |

> **模式 2 / 3 不可改字段前后对比**（G2 / G3 扩展，**核心硬规则**）：
> - **G1**（**仅模式 2**）：param 数量 1:1 覆盖（缺/多都失败——缺报错，多丢弃）
> - **G2 扩展**（**仅模式 2**）：**param 不可改字段前后对比**（**LLM 侧**）——`name` + `type` + **`description`** 字段必须与 latest **完全一致**（字符串相等）
> - **G3 扩展**（**仅模式 3**）：分两类检查
>   - **G3 信号字段锁死**（**LLM 侧**）：`entry_signals` / `exit_signals` 5 字段（`name` / `factors` / `direction` / `trigger` / `logic`）与 latest 一致 + 数量 1:1
>   - **G3 factors 锁死**（**代码侧 / 防御性**）：`factors` 列表 3 字段（`name` / `description` / `calculation`）与 latest 一致 + 数量 1:1——`factors` 列表**不进入 LLM 输出**，由代码从 latest 整体继承；理论上必一致，如不一致则是代码 bug
>
> **执行位置**：本地 merge 之后、validate_md_structure 末尾。**失败处理**：
> - LLM 侧失败（信号 5 字段）→ 反馈 + LLM 重生成（最多 5 次）
> - 代码侧失败（factors 继承）→ **不重试**，是代码 bug
>
> 详见 §6.7（mode 2）、§7.5（mode 3）。

**A. 基础结构（4 项，模式 1）**

| # | 检查项 | 适用模式 | 失败处理 |
|---|---|---|---|
| 1 | frontmatter 存在 + YAML 可解析 | 模式 1 | 失败 → 反馈 + 重生成 |
| 2 | **`targets` 存在 + 5 项数值键齐全**（annual_return / win_rate / profit_loss_ratio / sharpe / max_drawdown）+ 数值类型合法 | 模式 1 | 同上 |
| 3 | **`test_universe` 存在 + 是 list + 元素全部合法**（`hs300` / `csi1000` / `star50` / `cyb50`）+ 数量 1~4 | 模式 1 | 同上 |
| 9 | `position_weights` 至少 1 字段 | 模式 1 | 同上 |

**B. signals 结构 + 权重（5 项，模式 1 / 3）**

| # | 检查项 | 适用模式 | 失败处理 |
|---|---|---|---|
| 4 | **`factors` 列表非空**（仅"计算词汇表"，不带 weight / direction） | 模式 1 / 3 | 失败 → 反馈 + 重生成 |
| 5 | **`entry_signals` 列表非空** + 每项含 `name` / `weight` / `factors` / `direction` / `trigger` / `logic` | 模式 1 / 3 | 同上 |
| 6 | **`exit_signals` 列表非空** + 每项含 `name` / `weight` / `factors` / `direction` / `trigger` / `logic` | 模式 1 / 3 | 同上 |
| 7 | `entry_signals[].factors` / `exit_signals[].factors` 引用的因子名**必须**在 `factors` 列表中存在（factors 字段可空 `[]`，但**禁止**引用 param 名） | 模式 1 / 3 | 同上 |
| 8 | **`entry_signals[].weight` / `exit_signals[].weight` 是非负数值**（**G3 比例关系**——不要求总和=1.0） | 模式 1 / 3 | 同上 |

**C. params 列表（4 项，模式 1 / 2）**

| # | 检查项 | 适用模式 | 失败处理 |
|---|---|---|---|
| 10 | `params` 列表非空 | 模式 1 / 2 | 失败 → 反馈 + 重生成 |
| 11 | `params[].range` 是 2 元素 [min, max] | 模式 1 / 2 | 同上 |
| 12 | `params[].default` 在 range 闭区间内 | **模式 1** | **软检查**（**不失败**）：超出 → 报告标注（**模式 2 已移除软校验**，不再检查） |
| 13 | **`params[].description` 非空 + 长度 ≥ 30 字符**（**B4 防模糊**） | **模式 1** | 失败 → 反馈 + 重生成 |

**D. strategy_narrative 字段（2 项，模式 1）**

| # | 检查项 | 适用模式 | 失败处理 |
|---|---|---|---|
| 14 | `strategy_narrative` 字段存在 + 字符数 ≥ 1500 | 模式 1 | 失败 → 反馈 + 重生成 |
| 15 | `strategy_narrative` 含 6 节（思路 / 环境 / 3 环境处理 / 多信号关系 / 风险机制 / 差异化） | 模式 1 | 同上 |

> **注**：以下 2 项早期被编为硬校验 #16 / #17，**已移至 quality_eval 软检查**（详见 §9.2），**不**计入 22 硬：
> - `exit_signals` 含 ≥ 3 类止损止盈（①固定止损 ②移动止损 ③时间止损 / 止盈）
> - `strategy_narrative` 中无硬编码数字（除数学常量 0/1/100/1000）——**B2 扩展**

**E. 信号引用一致性 + 因子完整性（6 项）**

| # | 检查项 | 适用模式 | 失败处理 |
|---|---|---|---|
| 16 | **`signals[].factors` 引用的因子必须**在 trigger 公式中作为独立 token 出现**（factors 可空 `[]`，但若非空则所有元素**必须**作为独立标识符出现在 trigger 字符串中）——**严格解析**（不是子字符串匹配） | 模式 1 / 3 | 失败 → 反馈 + 重生成 |
| 18 | **`position_weights` 块的字段必须**在 `params` 列表里有完整 B4 表达**（带 description / range / default）——否则该字段不可调优 | 模式 1 / 2 | 同上 |
| 19 | **同一 `param` 在 `strategy_narrative` 中引用必须语义一致**（**修复漏洞 11**）——param 的 `description` 定义其唯一语义，narrative 中任何 `{param_name}` 引用必须符合该语义。**禁止**把 `add_position_weight_threshold` 当作"减仓下限"等跨语义复用 | 模式 1 / 2 | 同上 |
| 20 | **`factors` 列表里的每个因子必须被至少一个 signal 的 trigger 公式引用**（**修复漏洞 12**）——孤立因子（未被引用）= 死代码。允许 trigger 中"白名单系统变量"独立存在 | 模式 1 / 3 | 同上 |
| 23 | **`trigger` 公式中除数学常量（0, 1, 100, 1000）外无其他硬编码数字**（**修复 R3 漏洞**）——每个数字阈值必须以 `{param_name}` 形式引用。包括：区间两端（`40 < rsi_14 < 70` 中的 40 和 70）、阈值（`X > 5` 中的 5）、倍数（`X * 2` 中的 2，**但 2 视为数学常量 OK**） | 模式 1 / 3 | 同上 |
| 24 | **每个因子必含 3 字段**（`name` / `description` / `calculation`）——`calculation` 是计算规则伪代码，backtest 端据此实现。**description 非空 + calculation 非空**（**修复 v5 漏洞**） | 模式 1 / 3 | 同上 |

**F. 收益门槛 + 风险预算（2 项，模式 1）**

| # | 检查项 | 适用模式 | 失败处理 |
|---|---|---|---|
| 21 | **`targets.annual_return > 0.20`**（**O1 硬规则**）——期望年化收益率必须 > 20%，否则不通过 | 模式 1 | 失败 → 反馈 + 重生成 |
| 22 | **`targets.annual_return / abs(targets.max_drawdown) ≥ 1.0`**（**O3 风险预算**）——年化收益至少等于回撤绝对值，否则视为"高风险低收益" | 模式 1 | 同上 |

**G. 已废除**

| # | 检查项 | 状态 |
|---|---|---|
| ~~17~~ | ~~trigger 公式的变量必须在白名单内~~ | **已废除**（白名单限制策略多样性，移除） |

**按模式校验范围汇总**：

| 模式 | 校验项 | 来源 | 失败处理 |
|---|---|---|---|
| **模式 1 (generate)** | #1 / #2 / #3 / #4 / #5 / #6 / #7 / #8 / #9 / #10 / #11 / #12 (软) / #13 / #14 / #15 / #16 / #18 / #19 / #20 / #21 / #22 / #23 / #24 = **22 硬 + 1 软** | §8.4 A-F 组 | 硬失败 → 反馈 + 重生成（最多 5 次）；软 #12 → 报告标注 |
| **模式 2 (optimize)** | #10 / #11 / #18 / #19 + G1 / G2 = **4 硬 + 2 模式 2 专属**（**软校验已移除**；`#13` description 长度检查仅模式 1）| §8.4 C / E + G1/G2 | 硬失败 → 反馈 + 重生成（最多 5 次） |
| **模式 3 (factor_weights)** | #4 / #5 / #6 / #7 / #8 / #16 / #20 / #23 / #24 + G3 = **9 硬 + 1 模式 3 专属** | §8.4 B / E + G3 | 硬失败 → 反馈 + 重生成（最多 5 次） |

**G1 / G2 / G3 不可改字段前后对比（关键）**：

| 模式 | 范围 | 不可改字段 | 检查侧 | 失败处理 |
|---|---|---|---|---|
| **模式 2 (G2 扩展)** | `params[]` | `name` + `type` + `description` | **LLM 侧** | 任意字段与 latest 不一致 → 反馈 + LLM 重生成 |
| **模式 3 (G3 信号)** | `entry_signals[]` / `exit_signals[]` | `name` + `factors`（引用列表）+ `direction` + `trigger` + `logic`（含数量 1:1）| **LLM 侧** | 任意字段与 latest 不一致 → 反馈 + LLM 重生成 |
| **模式 3 (G3 factors)** | `factors[]` | `name` + `description` + `calculation`（含数量 1:1）| **代码侧**（防御性）| 理论上不会失败；如失败 = 代码 bug，**不重试** |

> **G1 / G2 / G3 是"锁死"对 LLM 的硬约束**——LLM 输出必须满足这些字段的前后一致，否则视为"破坏锁死"，硬失败。详见 §6.7（mode 2）、§7.5（mode 3）。

---

## 9. 质量评估（quality_eval）

### 9.1 两层评估（**仅模式 1 完整使用**）

| 层 | 名称 | 形式 | 重试 | 失败处理 | 适用范围 |
|---|---|---|---|---|---|
| **1** | `validate_md_structure` | 机器硬校验（**按模式分类**）| 不重试 | 直接失败，触发 LLM 重生成 | 模式 1（22 硬 + 1 软）/ 模式 2（4 项 params）/ 模式 3（9 项 signals） |
| **2** | `quality_eval` | LLM 业务评估 | **1 次过**（K2） | **不重试**，反馈 → LLM 重生成整篇 | **仅模式 1** |

> 模式 2 / 3 **不跑 quality_eval**——硬失败直接反馈 + 重生成；业务质量由下一轮回测报告验证。

### 9.2 quality_eval 检查项

- **业务目标达成度**：策略设计是否能实现 LLM 自定的前 90% 目标（参考 `targets` 字段的 5 项数值）
- **目标合理性**（**O 系列**）：targets 5 项数值是否内部一致（夏普高 + 回撤大 = 矛盾）、是否过于激进、**annual_return > 20%（O1）**、**收益 / 回撤比 ≥ 1.0（O3）**、**win_rate × profit_loss_ratio ≥ 1.5（O4 数学自洽 soft check）**
- **exit_signals 类别完整性**（**O5**）：若策略无 ②移动止损（trailing stop），是否用 ③通道反向止损替代，并在 `strategy_narrative` 第 5 节**明文说明**理由
- **穿越牛熊**（**N3**）：
  - `strategy_narrative` 第 3 节是否含 3 种环境处理说明（牛 / 熊 / 震荡）
  - 熊市风控机制是否存在（降低仓位 / 收紧止损 / 切换因子权重，至少 1 项）
  - 缺失 → 不通过，反馈 + 重生成
- **参数可调整性**（**B2 完整 8 项**）：
  - 入场 / 出场 / 调仓频率 / 加仓减仓 / **风控识别** / 仓位调整 / 行业暴露 / position_weights 字段 全部 param 化
  - 档位细节是否全部暴露（B3）
  - range 宽度是否 ≥ 3 倍经验合理值（C1 软判断）
  - **每个 param 的 description 是否详细**（**B4**）：含 4 要素之一（含义 / 单位 / 典型取值 / 默认值理由）才算合格
  - **`strategy_narrative` 中无硬编码数字**（除数学常量 0/1/100/1000）
  - **不强制**要求"熊市/震荡市临时调整值"（市场状态判断无可靠依据，详见 N1 备注）
- **结构完整性**（**不入 soft 评估**——其内容由 22 项硬校验覆盖：#1 / #2 / #3 / #9 / #14 / #15 / #16 / #19 / #20 / #24，详见 §8.4；此处仅作交叉引用）：
  - frontmatter **7 区块 + 元信息**齐全（**targets** / **test_universe** / factors / **entry_signals** / **exit_signals** / position_weights / params / 元信息）— #1 / #2 / #3 / #9
  - `strategy_narrative` 字段存在 + ≥ 1500 字符 + 含 6 节 — #14 / #15
  - `test_universe` 字段存在（M1）— #3
  - **entry_signals / exit_signals 必须按 N4 结构化**（每条信号含：name / weight / factors / direction / trigger / logic）— #5 / #6
  - **exit_signals 包含至少 3 类止损止盈**（含移动止损）— **O5 / quality_eval 软判断**（非硬校验 #16）
- **逻辑自洽**：
  - 入场 / 出场规则互相不矛盾
  - 止损止盈优先级清晰（在 `strategy_narrative` 第 4 节说明）
  - **entry_signals / exit_signals 权重合理**（G3）：每条 signal 的 weight 必须有"为什么是这个值"的业务理由（**不要求总和=1.0**，只要比例合理）
  - **多信号关系明确**（N4）：入场时机（OR / AND / 序列）、出场优先级链
  - **signals[].factors 与 trigger 一致**（硬校验 #16）：引用的因子必须实际在 trigger 中作为独立 token 使用
  - **factors 列表无孤立因子**（硬校验 #20）：每个因子必须被至少一个 signal 的 trigger 引用
  - **同一 param 语义单义性**（硬校验 #19）：`strategy_narrative` 中 `{param_name}` 引用必须符合 param.description 语义，不允许跨语义复用
- **数据可实现性**（**hard gate**）：
  - 因子 / 触发条件 / 仓位 / 参数**全部能用本地 38 字段 + 持仓过程变量实现**（**data/README.md §7.1**）
  - 因子窗口 N ≤ 250（最长均线周期）
  - 早期数据 NaN 处理**已明确**（上市未满 N 日 / 涨跌停 / 停牌）
  - **不可实现** = error 级问题 → `passed: false`，建议重生成

**6 维评估体系**（与 `quality_eval.md` 一致——**`structural_completeness` 不入软评估**，其内容已由 22 硬校验覆盖，重复评估无意义；维度数 7 维 → 6 维）：
1. business_goal_alignment（业务目标达成度）
2. target_consistency（目标合理性 + O 系列）
3. bull_bear_adaptability（穿越牛熊 + N3）
4. parameter_tunability（参数可调整性 + B2 完整 8 项）
5. logical_self_consistency（逻辑自洽 + 硬校验 #16 / #19 / #20 / #23）
6. **data_implementability（数据可实现性，hard gate）**

**数据可实现性 - 详细检查项**：
- **因子可实现性**：factors[].calculation 描述的算法能用基础字段 + 持仓过程变量计算；N 日窗口 ≤ 250
- **trigger 可实现性**：trigger 公式中每个变量可归类为（因子 / param / 系统变量 / 数学常量 0, 1, 100, 1000）
- **position_weights 可实现性**：5 字段全部在 params 列表中有 B4 表达
- **params 可实现性**：所有 param 都是 backtest 端的合法操作对象
- **数据完整性处理**：早期数据 NaN / 涨跌停 / 停牌 处理方式**已明确**

**当前 spec 未使用的字段**（引用 = error）：`所属行业` / `滚动市盈率` / `市净率` / `滚动市销率` / `总市值` / `是否融资融券` —— 这些字段**当前 spec 未使用**，引用会被 LLM 拒绝（避免无意义复杂度）

### 9.3 失败反馈格式

- 反馈加在 `user_prompt` 的最后（"上次评估未通过：{原因}，请修正"）
- **反馈不写入 .md frontmatter 或 body**（D2）
- 反馈内容可被 LLM 自由解读，但硬校验的 22 项 + 1 软（模式 1 全跑，**模式 2 / 3 仅跑其子集**）**不能违反**（#17 已废除，#12 已改为软检查，#24 新增）
- **数据可实现性**反馈策略：因子 / trigger / param 不可实现时，给出**具体字段**和**推荐替代字段**

### 9.4 报告目标对比（**A2 兑现**）

回测报告 §1 必须包含**目标 vs 实际**对比表：

| 指标 | 目标（targets） | 实际 | 差距 | 评价 |
|---|---|---|---|---|
| annual_return | 15% | 1.86% | -13.14% | ❌ 未达 |
| win_rate | 50% | 57.69% | +7.69% | ✅ 超过 |
| profit_loss_ratio | 1.8 | 1.32 | -0.48 | ❌ 未达 |
| sharpe | 1.2 | — | — | （Phase 2 才计算）|
| max_drawdown | -12% | — | — | （Phase 2 才计算）|

**评价规则**：实际 vs 目标 = ✅ 超过 / ❌ 未达 / ➖ 持平

---

## 10. CLI 接口

### 10.1 入口文件顶部注释（**M2 强制**）

`strategies.py` 顶部 docstring **必须**包含以下完整注释块（**所有模式调用指令**），便于首次使用者直接复制粘贴：

```python
"""
my-quant3 策略生成系统 — CLI 入口

============================================================
=== 模式 1: 生成新策略 ===
============================================================
python strategies.py generate
# 行为：LLM 按业务目标（前 90% 锚点）生成新策略
# 产出：subject/<name>/strategy/<name>_v1.md + <name>_original.md

============================================================
=== 模式 2: Part A 参数调优 ===
============================================================
python strategies.py optimize <name>                # 默认 = once（单次触发）
python strategies.py optimize once <name>           # 显式单次触发
python strategies.py optimize watch <name>          # 持续监听（Ctrl+C 退出）

# 重启时从原始版本引导（可选）
python strategies.py optimize once <name> --from-original

============================================================
=== 模式 3: Part B 因子权重调优 ===
============================================================
python strategies.py factor_weights <name>          # 默认 = once
python strategies.py factor_weights once <name>     # 显式单次
python strategies.py factor_weights watch <name>    # 持续监听

============================================================
=== 工具命令 ===
============================================================
python strategies.py list                           # 列出 subject/ 下所有策略
"""
```

### 10.2 命令汇总

```bash
# 模式 1：生成新策略
python strategies.py generate

# 模式 2：参数调优
python strategies.py optimize <name>                # 默认 = once
python strategies.py optimize once <name>           # 单次触发
python strategies.py optimize watch <name>          # 持续监听

# 模式 3：因子权重调优
python strategies.py factor_weights <name>          # 默认 = once
python strategies.py factor_weights once <name>     # 单次触发
python strategies.py factor_weights watch <name>    # 持续监听

# 重启（从原始版本引导）
python strategies.py optimize once <name> --from-original
python strategies.py factor_weights once <name> --from-original

# 列表
python strategies.py list
```

### 10.3 行为约定

| 命令 | 行为 |
|---|---|
| `optimize <name>` | 等价 `optimize once <name>`（E2 默认） |
| `optimize once <name>` | 跑一次调优即退出 |
| `optimize watch <name>` | 跑一次后进入 watchdog 监听，Ctrl+C 退出 |
| `optimize <name> --from-original` | 从 `<name>_original.md` 启动，写新版本为 `_v2.md`（§15.2） |
| `factor_weights <name>` | 同 `optimize` 模式 |
| `generate` | 跑一次生成，成功打印策略名；失败抛异常 |

---

## 11. 文件结构

```
D:\project\quant\my-quant3\
├── strategies.md                # 本文件
├── config.py                    # LLM 配置（base_url / model / api_key）
├── .env                         # 本地密钥（不提交）
├── strategies.py                # CLI 入口（顶部 docstring 含所有调用指令，M2）
├── data/
│   └── config.py                # 4 个独立 universe list（M1）
│                                 #   HS300 / CSI1000 / STAR50 / CYB50
│                                 #   + load_universe(name: str) 支持多选
├── src/
│   ├── config.py                # LLMSettings + RuntimeSettings
│   └── agents/
│       ├── base_agent.py        # 共享工具
│       │   - 路径工具
│       │   - .md 读写
│       │   - 报告查找（5 份 + F2 分配）
│       │   - LLM 构建（build_llm + thinking 控制）
│       │   - JSON 解析（parse_strategy_json）
│       │   - 硬校验（validate_md_structure）
│       │   - 提示加载
│       │   - 自动起名校验
│       │
│       ├── generate.py          # 模式 1
│       ├── optimize.py          # 模式 2（once / watch）
│       ├── factor_weights.py    # 模式 3（once / watch）
│       ├── quality_eval.py      # 业务质量评估
│       ├── watcher.py           # watchdog + debounce
│       │
│       └── prompts/
│           ├── generate.md
│           ├── optimize.md
│           ├── factor_weights.md
│           └── quality_eval.md
│
└── subject/                     # 模式 1 生成的策略实例
    └── <auto_name>/
        ├── strategy/
        │   ├── <name>_v1.md           # 模式 1 产物
        │   ├── <name>_original.md     # 不可变原始快照
        │   ├── <name>_v<N>.md         # 模式 2 调优产物
        │   └── <name>_weight_v<N>.md  # 模式 3 调优产物
        ├── reports/                   # 回测报告（外部回测器写入）
        └── backtest/                  # 外部回测器（按 .md 契约生成代码）
```

---

## 12. 配置

### 12.1 LLM 配置（`config.py`）

| 字段 | 默认 | 说明 |
|---|---|---|
| `LLM_BASE_URL` | OpenAI 兼容端点 | 由环境变量覆盖 |
| `LLM_MODEL` | 默认模型 | 由环境变量覆盖 |
| `LLM_API_KEY` | 从 `.env` 读 | 必填 |
| `temperature` | 0.7（generate 用 0.3） | 调高创造性，调低稳定性 |
| `max_tokens` | 32768 | 留余量装策略 narrative |
| `timeout` | 180s | 防 hang |

### 12.2 运行时配置（`src/config.py: RuntimeSettings`）

| 字段 | 默认 | 说明 |
|---|---|---|
| `self_eval_max_retries` | 5 | LLM 调优时的最大重试次数 |
| `debounce_seconds` | 5.0 | watch 模式去抖时间 |
| `watch_create_only` | True | 仅 created 事件触发 |
| `max_listen_iterations` | 20 | 监听回调最大次数 |
| `max_reports_reference` | 5 | 调优时参考的最近报告数（J2） |

### 12.3 环境变量

```bash
# 必填
LLM_API_KEY=<key>

# LLM 配置覆盖
LLM_BASE_URL=<url>
LLM_MODEL=<model>

# 运行时覆盖
SELF_EVAL_MAX_RETRIES=5
DEBOUNCE_SECONDS=5
MAX_LISTEN_ITERATIONS=20
MAX_REPORTS_REFERENCE=5
```

---

## 13. 实现要点

### 13.1 模式 1 generate 关键实现

- **think 模式**：模式 1 持续使用 think（深度生成，不追求速度）
- **temperature=0.3**：让 JSON 结构稳定
- **5 次重试**：硬校验 / quality_eval 失败时带反馈重试
- **写盘两文件**：`<name>_v1.md` + `<name>_original.md`

### 13.2 模式 2 / 3 关键实现

- **3+1 think 策略**：每 4 轮一个周期，前 3 轮 non-think（快速试错），第 4 轮 think（深度调优）
- **per-round 不是 per-attempt**：一轮内的所有 attempt 用同一个 LLM 实例
- **LLM 输出格式**（**与 factor_weights.md 对齐**）：
  - **模式 2**：完整 `params` 列表（覆盖式）
  - **模式 3**：完整 `entry_signals` + `exit_signals` 列表（覆盖式）——**仅 2 个顶层 key**；`factors` 列表**不进入 LLM 输出**，由代码从 latest 整体继承
- **本地 merge**：按 `name` 匹配，漏掉报错，多给丢弃
- **按模式分类硬校验**（**重要**）：
  - **模式 2** 跑 **4 项硬校验 + 2 项 G1/G2 专属**——只关注 params 字段（详见 §8.4 C / E 组子集 + G2 不可改字段前后对比）；`#13` description 长度检查仅模式 1；**无软校验**（已移除）
  - **模式 3** 跑 **9 项硬校验 + 1 项 G3 专属**——只关注 factors / signals 字段（详见 §8.4 B / E 组子集 + G3 不可改字段前后对比）
  - **不**校验非调优对象（targets / test_universe / strategy_narrative——全部继承）
- **G1 / G2 / G3 不可改字段前后对比**（**本地 merge 末尾执行**）：
  - 模式 2：`params[].name` + `params[].type` + **`params[].description`** 与 latest 完全一致（详见 §6.7）——**description 已锁死**，模式 2 不可改
  - 模式 3：**分两类**：
    - **G3 信号字段锁死**（**LLM 侧**）：`entry_signals[]` / `exit_signals[]` 5 字段（`name` / `factors` / `direction` / `trigger` / `logic`）与 latest 完全一致 + 数量 1:1（详见 §7.5）
    - **G3 factors 锁死**（**代码侧 / 防御性**）：`factors` 列表 3 字段（`name` / `description` / `calculation`）与 latest 完全一致——`factors` 列表由代码从 latest 整体继承；理论上必一致，如不一致则是代码 bug（详见 §7.5）
- **不跑 LLM 评估**：模式 2 / 3 **无 quality_eval**——业务质量由下一轮回测报告验证

### 13.3 硬校验关键实现

- **早于 LLM 评估**（**仅模式 1**）：硬校验失败不调 quality_eval，省 6-18s
- **按模式分类**（详见 §8.4 末尾"按模式校验范围汇总"表）：
  - **模式 1** = **22 项硬校验 + 1 项软检查**（覆盖全部 23 项）
  - **模式 2** = 4 项硬校验 + G1/G2（**仅 params 相关**，**无软校验**；`#13` description 长度检查仅模式 1）
  - **模式 3** = 9 项硬校验 + G3（仅 factors / signals 相关）
- **失败处理统一**：硬失败 → 反馈 + 重生成（最多 5 次）
- **entry_signals[].weight** / **exit_signals[].weight** 是非负数值：**比例关系决定优先级**，**不要求总和=1.0**
- **factors 列表不带 weight**：仅作"计算词汇表"
- **比例转换**（如需）：`priority_i = weight_i / Σ(weights)`

### 13.4 quality_eval 关键实现

- **1 次过**：失败直接反馈 + 重生成，不重试
- **含原 self_eval 内容**：业务目标 / 可调整性（含 B4 描述详细度）/ 硬约束 / 逻辑自洽 / **数据可实现性**（data/README.md §7 字段映射对齐）——**不含结构完整性**（由 22 硬校验覆盖，详见 §9.2）
- **反馈格式**：失败原因加入 user_prompt，不写入 .md

### 13.5 test_universe 加载实现（**M1**）

```python
VALID_UNIVERSES = {"hs300", "csi1000", "star50", "cyb50"}

def load_test_universe(strategy_md_path: Path) -> list[str]:
    """从 .md frontmatter 读 test_universe，校验后返回 list[str]。

    - 默认：["hs300"]
    - 校验：list 长度 1~4，元素全部 ∈ VALID_UNIVERSES
    - 模式 2 / 3 禁止修改（仅读取）
    """
    fm, _ = read_md(strategy_md_path)
    tu = fm.get("test_universe", ["hs300"])
    if not isinstance(tu, list) or not (1 <= len(tu) <= 4):
        raise ValueError(f"test_universe 必须是 1~4 个元素的 list，实际: {tu}")
    for u in tu:
        if u not in VALID_UNIVERSES:
            raise ValueError(f"test_universe 含非法值: {u!r}（须 ∈ {VALID_UNIVERSES}）")
    return tu
```

**数据层**：
- `data/config.py` 提供 4 个独立 universe list：
  ```python
  HS300 = [...]        # 沪深 300
  CSI1000 = [...]      # 中证 1000
  STAR50 = [...]       # 科创 50
  CYB50 = [...]        # 创业板 50
  ```
- `load_universe(name: str)` 支持 4 个取值 + `all`（去重合并）
- 多选时（如 `["hs300", "csi1000"]`）：取并集去重

### 13.6 5 份报告 + F2 分配

```python
def get_reports_for_tuning(strategy_name: str, max_reports: int = 5):
    reports = find_all_reports(strategy_name, limit=max_reports)  # 最近 5 份
    if not reports:
        return ""

    text_parts = []
    for i, r in enumerate(reports):
        if i == 0:
            # 最新 1 份：完整内容
            text_parts.append(f"## {r.name}\n{r.read_text()}")
        else:
            # 其它 4 份：仅 §0 + §1 + §2
            content = r.read_text()
            trimmed = extract_sections(content, sections=["§0", "§1", "§2"])
            text_parts.append(f"## {r.name}（精简）\n{trimmed}")
    return "\n\n".join(text_parts)
```

---

## 14. 失败处理

| 场景 | 处理 |
|---|---|
| LLM 调用失败 | 重试（最多 5 次） |
| JSON 解析失败 | 重试（带原始文本落盘 + 错误反馈） |
| 硬校验失败 | **反馈 + 重生成**（最多 5 次）——模式 1 / 2 / 3 **统一规则**，但**校验范围按模式分类**（详见 §8.4） |
| quality_eval 失败（**仅模式 1**） | **重生成整篇**（K2，不在 eval 内部重试） |
| 5 次重试全失败 | 抛异常退出（模式 1）/ 跳过本轮继续监听（模式 2 / 3） |
| 监听回调中 LLM 失败 | 写日志 + 不中断监听 + 跳过本轮 |

---

## 15. 实现细节（决策未覆盖部分）

> 以下 9 条是 42 个决策**没有明文规定**的实现细节，根据 my-quant2 工程经验和当前 spec 连贯性给出。

### 15.1 报告读取顺序

| 项 | 决策 |
|---|---|
| 排序键 | `_v(\d+)` 数字倒序（最新 → 最旧） |
| 截断 | 最多 5 份 |
| 实现 | `base_agent.find_all_reports(strategy_name, glob_pattern="report_v*.md", limit=5)` 返回值已排序 |

### 15.2 重启 CLI 形态

| 项 | 决策 |
|---|---|
| 入口 | 模式 2 / 3 的 `once` 子命令加 `--from-original` flag |
| 默认 | False（从 `find_latest_md()` 引导） |
| 用法 | `python strategies.py optimize <name> --from-original` |
| 行为 | True 时用 `<name>_original.md` 替代 `find_latest_md` 的结果，写新版本为 `_v2.md`（不覆盖 original） |

### 15.3 quality_eval 反馈 prompt 格式

反馈附加在 `user_prompt` 末尾，**不写入 .md**：

```markdown
## 上次 quality_eval 未通过（请修正后重生成）

### 失败类型
- 业务目标达成度 / 参数可调整性 / 穿越牛熊 / 逻辑自洽 / 数据可实现性

### 具体问题
- {失败项 1 描述}
- {失败项 2 描述}

### 修复方向
- {具体可执行的修复建议 1}
- {具体可执行的修复建议 2}
```

### 15.4 信号流契约

| 字段 | 类型 | 说明 |
|---|---|---|
| `date` | date | 交易日 |
| `code` | string(6) | 6 位纯数字，无交易所后缀 |
| `signal` | int8 | -1=卖出, 0=持有, +1=买入 |
| `price` | float64 | 触发价 = 当日收盘价 |
| `factors` | dict \| None | 触发时因子快照（`signal=0` 时为 None） |

**存储路径**：`data/signals/{strategy_name}/signals.parquet`
**格式**：dense（每天每只股票一行，含 signal=0 行）
**规模**：1300 股 × 1220 日 ≈ 160 万行

### 15.5 跨模式 2 / 3 信号命名一致性

| 项 | 决策 |
|---|---|
| 命名约束 | `extracted_params[].name` 与 .md 定义名**字符串完全一致** |
| factors 锁死的后果 | 模式 2 / 3 调优时**不能改名**（factors 锁死后该约束自动满足） |
| 强校验 | **不**做（避免 LLM 反复重试） |
| 兜底 | 报告 §2 归因 + 人工 review |

### 15.6 3+1 think 策略

```python
TUNE_CYCLE_ROUNDS = 4  # 4 轮一个周期

def should_use_thinking_round(round_no: int) -> bool:
    """(round_no - 1) % 4 == 3 为 True → think 模式"""
    return (round_no - 1) % TUNE_CYCLE_ROUNDS >= (TUNE_CYCLE_ROUNDS - 1)
```

| 轮次 | 模式 | 耗时（典型） |
|---|---|---|
| round 1, 2, 3 | non-think（快速试错）| 30-90s |
| round 4 | think（深度调优）| 60-180s |
| round 5, 6, 7 | non-think | 30-90s |
| round 8 | think | 60-180s |
| ... 循环 | | |

**关键规则**：
- **per-round**，不是 per-attempt
- 一轮内 5 次 attempt **共用同一个 LLM 实例**
- 模式 1（generate）持续 think
- 兼容无 think 块的 LLM（`parse_strategy_json` 第 1 步 `re.sub` 零次匹配跳过）

### 15.7 watchdog + debounce 配置

| 参数 | 默认 | 说明 |
|---|---|---|
| `debounce_seconds` | 5.0 | 5s 内无新事件才触发回调 |
| `watch_create_only` | True | 仅 created 事件触发（不响应 modified） |
| 处理方式 | 串行 | 短时间多份报告一份一份处理 |
| 模式 2 监听文件 | `report_v*.md` | glob 模式 |
| 模式 3 监听文件 | `report_signals_v*.md` | glob 模式 |
| 最大监听回调次数 | 20 | `max_listen_iterations` |
| 退出 | Ctrl+C | 写日志 + 不中断退出 |

### 15.8 原始快照"建议不改"实现

**不做技术锁**，靠以下三层防护：

1. **.md 顶部注释**：
   ```markdown
   <!-- ⚠️ This is the immutable original snapshot of <name>. Do not edit. -->
   <!-- 重启时通过 --from-original flag 显式引用本文件 -->
   ---
   ```
2. **`subject/<name>/README.md` 写明规则**：
   > original.md 是不可变原始快照，模式 2 / 3 不会自动改写。
3. **`base_agent.write_md` 防护**：
   检测到路径以 `_original.md` 结尾且文件已存在 → 抛异常（防误覆盖）
4. **LLM 调优**：
   `find_latest_md` 默认跳过 `_original.md`（只匹配 `*_v<N>.md`），必须用 `--from-original` 显式指定

### 15.9 factors 锁死后模式 1 的"可重生成"边界

| 项 | 决策 |
|---|---|
| "新策略" 定义 | **完全重新 generate**，LLM 重新起名 + 重新生成 factors 列表 |
| 同名重生成 | 抛异常退出（**不覆盖**已有 `subject/<name>/` 目录） |
| 同策略重生成路径 | 删 `subject/<name>/` 整个目录后重新 `generate` |
| 模式 2 / 3 | 严格遵守 factors 列表锁死（**不增不删**，方向 param 化） |
| factors 改名 | 不允许（factors 锁死） |
| 方向变更 | 通过 param 化实现（mode 2 / 3 不直接改 direction） |

> **设计意图**：factors 锁死保证 downstream 兼容性（同 factors → 同 backtest 代码结构）；方向 param 化保证调优空间（业务规则层面的"反转"由 param 控制）。

---

## 16. 核心设计原则速查

| 原则 | 一句话 |
|---|---|
| **目标导向** | 首版必须有明确业务目标（前 90% 锚点），**写入 .md 的 `targets` 字段** |
| **可调整性** | 所有数值阈值 param 化，range 足够宽，description 必须详细 |
| **数据流精简** | LLM 只返新参数，本地 merge + 局部校验 |
| **同构对称** | 模式 2 / 3 输入输出形态对称（一个调 params，一个调 weights） |
| **原始快照** | 生成时同步写 `original.md`，出问题可重启 |
| **factors 锁死** | v1 后 factors 列表不变，方向 param 化，weight 在 signals 上 |
| **两阶段开发** | Phase 1 信号规则 / Phase 2 仓位参数独立迭代 |
| **报告权重** | 最多 5 份，最新主导，隐式分配 |
| **评估分层** | **按模式分类硬校验**（模式 1 = **22 硬 + 1 软** 全 / 模式 2 = 4 项 params / 模式 3 = 9 项 signals）→ quality_eval（LLM, 1 次过，**仅模式 1**） |
| **入口明确** | `once\|watch` 互斥子命令，默认 `once` |
| **穿越牛熊** | A1 含牛 / 熊 / 震荡 3 环境处理，熊市必须风控 |
| **信号结构化** | A3 / A4 按 N4 格式逐条列信号 + 多信号关系 |
| **收益门槛** | 期望年化 > 20%，收益 / 回撤比 ≥ 1.0，胜率 × 盈亏比 ≥ 1.5，A6 类别缺失需说明 |

---

## 17. backtest 代码生成器要求（占位）

> **本节仅占位**。backtest 代码生成器的**详细 spec 在单独 .md**（**后续提供**）。
> 任何回测代码生成相关的设计决策都不在本文件。

简要交叉引用：

| 主题 | 本文件位置 | backtest spec 位置 |
|---|---|---|
| A 股硬约束（T+1 / 涨跌停 / 停牌 / 费用 / 复权） | §1.3 简述 | **单独 .md（后续）** |
| 信号流契约（5 字段 parquet） | §15.4 | （backtest spec 引用） |
| targets 5 项 vs 实际对比 | §9.4 | （回测器报告生成时兑现） |
