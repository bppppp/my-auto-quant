# autoRun 质量评估精炼设计

> **Date**: 2026-06-08
> **Author**: Claude (brainstorming session)
> **Status**: Draft (pending user spec review)
> **Scope**: 3 个文件的轻量改造,提高 generate 模式一次过 90% 概率

---

## 1. 背景与目标

### 1.1 现状问题

`autoRun/pipeline.py` 跑全流程时,Stage A (`strategies/strategies.py generate`) 通过率极低:
- 5 次重试经常全失败 → 抛 RuntimeError → `mark_failed` → 当个策略被丢弃
- `result/` 目录产出量极低

### 1.2 根因(经代码探索确认)

经源码级探索,3 个文件存在以下问题导致 LLM 难以达到 90% 门槛:

**A. `strategies/agents/prompts/generate.md` (22.6 KB) 内部矛盾 3 处**

| 矛盾 | 位置 1 | 位置 2 |
|---|---|---|
| `strategy_narrative` 字符数 | L4 "≥ 800 字符" | `_build_user_prompt` L103 "≥ 1500 字符" |
| `strategy_narrative` 节数 | L36 #4 "必含 4 节" | L155 JSON 例子"6 节" |
| 硬规则分散 | L36-43 速查表 | L386-411 关键禁止 + L415-441 末尾速查(同一规则说 3 遍) |

**B. `strategies/agents/prompts/quality_eval.md` (9.6 KB) 评分偏严**

- 6 维共列 30+ 项"扣分项"——LLM 倾向"找茬"式评分
- `hard_evaluation` 空壳输出(LLM 必须输出无意义字段)
- "维度数从 7 → 6"历史包袱(LLM 困惑)
- 无评分校准参考(LLM 评分全凭"理解",波动大)

**C. `strategies/agents/generate.py` `_format_quality_eval_feedback` 反馈无效**

- 阈值口径不一致: L188 "85%" vs L203 "90%"
- 6 维分数按维度原序排(LLM 难以找最弱)
- issues 按 severity 分类(LLM 难以对应到维度)
- 无"下次怎么改"的具体指导(LLM 第 2 次重试大概率还是老问题)
- 无失败递增机制(LLM 失败 5 次都按相同思路重生成)

### 1.3 目标

| 目标 | 方向 |
|---|---|
| 提高 spec 质量(让 90% 更容易达成) | ✅ 核心 |
| 保持 90% 门槛 | ✅ 不动(用户硬约束) |
| 保持 pipeline 架构 | ✅ 不动(用户硬约束) |
| 不增加输入窗口大小 | ✅ 用户关键约束(生成时间敏感) |
| 只改 prompt + LLM 调用方式 | ✅ 改造范围(用户硬约束) |
| 消除 prompt 内部矛盾 | ✅ 新增 |
| 让 retry 反馈"具体到可执行" | ✅ 新增 |

### 1.4 预期收益

| 指标 | 当前(假设) | 预期 |
|---|---|---|
| 一次过 90% 概率 | ~20% | ≥ 40% |
| 平均生成尝试次数 | 3-5 次 | 1-2 次 |
| `generate.md` + `quality_eval.md` 总输入 | 32.2 KB | ~27 KB(-16%) |
| 单次生成时间 | 长 | 短(输入少 16%) |
| 重试时 LLM 改进方向 | 不确定(模式坍缩) | 有具体"下次怎么改"指导 |

---

## 2. 设计原则

### 2.1 核心原则:**压缩冗余,不压缩规则**

> 用户反馈: "generate.md 大小的减少会导致生成内容不容易过硬校验码"

回应: 修订后的设计严格遵守:
- ✅ **可压缩**: 同一规则说 3 遍 → 1 遍;冗长 JSON 示例(13 params) → 6 params;详细扣分清单(30+ 项) → 评估 hint 表(6 行)
- ❌ **不可压缩**: 22+1 硬校验每条至少 1 处明确提示;JSON 示例中演示硬校验的字段必须保留;关键禁止保留核心项

### 2.2 范围限定

| 文件 | 改动 |
|---|---|
| `strategies/agents/prompts/generate.md` | 7+1 条(§3) |
| `strategies/agents/prompts/quality_eval.md` | 6 条(§4) |
| `strategies/agents/quality_eval.py` | 1 条兼容处理(§5.3 配套) |
| `strategies/agents/generate.py` | 5 条(§5) |

**不改**: `autoRun/pipeline.py` / `scorer.py` / `state.py` / `subjects/` 任何文件 / `strategies/config.py` / 任何其他 agent 文件

---

## 3. `generate.md` 改动清单 (7+1 条)

### 3.1 统一 `strategy_narrative` 字符数(消除核心矛盾)

| 文件:行 | 当前 | 改为 |
|---|---|---|
| `generate.md` L4 | "≥ 800 字符" | "≥ 1200 字符(中位值,既不严也不松)" |
| `generate.md` L337 | "≥ 800 字符(约 320 tokens,节省约 50%)" | "≥ 1200 字符" |
| `generate.py` `_build_user_prompt` L103 | "≥ 1500 字符,含 6 节" | "≥ 1200 字符,含 5 节" |

**理由**: 用户已确认 800/1500 矛盾是 LLM 困惑源头。1200 是中位值。

### 3.2 统一 `strategy_narrative` 节数(消除第 2 个核心矛盾)

| 文件:行 | 当前 | 改为 |
|---|---|---|
| `generate.md` L36 #4 | "必含 4 节" | "必含 5 节" |
| `generate.md` L155 JSON 例子 | 6 节 | 5 节(合并"市场环境假设"入"策略思路") |
| `generate.md` L398-400 关键禁止 | "缺 4 节中任一节" | "缺 5 节中任一节" |
| `generate.md` L427 末尾速查 | "4 节" | "5 节" |
| `generate.py` `_build_user_prompt` L103 | "含 6 节" | "含 5 节" |

**5 节最终定义**:
1. 策略思路 / edge 来源(含市场环境假设)
2. 牛 / 熊 / 震荡 3 环境处理(所有阈值 param 化)
3. 多信号逻辑关系(入场时机 + 出场优先级)
4. 风险机制(与竞品差异 + 核心风控)
5. 早期数据 NaN 处理(上市未满 N 日 / 停牌 / 涨跌停 / 一字板 4 类)

### 3.3 合并硬规则表 + 22+1 硬校验全覆盖验证

**改动**: L36-43 速查表(主表) + L386-411 关键禁止(并入主表) + L415-441 末尾速查(精简)。

**22+1 硬校验全覆盖验证**(每条 ≥1 处提示):

| 硬校验 | 改后位置 |
|---|---|
| #1 顶层 4 字段 | L36 速查表 |
| #2-#10 frontmatter 7 块 | L36 + JSON 例 |
| #3 test_universe 合法值 | L36 速查表 |
| #4-#8 narrative 长度/节 | L36 + JSON 例 |
| #9/#20 孤立因子 | L36 |
| #10/#11 params 8 字段 | L36 + L279-300 |
| #12 position_weights 5 字段 | L36 + L273-277 |
| #13 description 4 要素 | L36 + L294-300 |
| #14-#15 narrative 长度/节 | L36 + JSON 例 |
| #16 factors↔trigger | L36 + L266 |
| #18 position_weights↔params | L273-277 |
| #19 `{param_name}` | L36 + L431-436 |
| #21-#22 targets 数学 | L36 + L162-176 |
| #23 trigger 硬编码 | L36 + L269-271 |
| #24 factors 3 字段 | L36 + L249-257 |

**关键禁止**: 26 条 → 12 条,每条映射具体硬校验(见 §3.7)。

### 3.4 `data_implementability` 高分指南前置

| 当前位置 | 新位置 | 理由 |
|---|---|---|
| L221-242 | L80-110 区域(紧跟硬规则速查表) | `data_implementability` 是 hard gate(< 6 即 fail),LLM 越早看到这维度的"高分特征",生成时越有意识 |

### 3.5 精简 JSON 示例(保留所有演示硬校验的字段)

| 字段 | 操作 | 理由 |
|---|---|---|
| `position_weights` 块 | ✅ **保留** | 硬校验 #12 #18 演示必需 |
| `description` / `universe` / `holding_period` / `rebalance_freq` | ✅ **保留** | 硬校验 #1 要求,JSON 例演示 |
| params 列表 13 → 6 | **精简** | 演示 description 4 要素 + B2 8 项覆盖即可(每类至少 1 个) |
| `### 5.` NaN 处理节 | ✅ **保留** | 硬校验 #15 要求 5 节齐全 |

**实际节省**: ~300 字符(JSON 例只稍微瘦身)。

### 3.6 trigger 变量白名单压缩(L302-318)

**改为 1 张 4 行表**:

| 类别 | 示例 | 是否需 `{}` 包裹 |
|---|---|---|
| 因子名 | `ma_20` / `atr_14` | ❌ 裸名 |
| param 名 | `atr_min_threshold` | ✅ `{name}` |
| K 线系统变量 | `close` / `volume` / `holding_days` | ❌ 裸名 |
| 数学常量 | `0` / `1` / `100` / `1000` | ❌ 字面值 |

**节省**: ~400 字符。

### 3.7 关键禁止压缩: 26 ❌ → 12 ❌(每条映射硬校验)

| 改后 ❌(12 条) | 覆盖硬校验 |
|---|---|
| 1. 数值不达标: annual_return ≤ 0.20 / 回撤比 < 1.0 / win_rate×盈亏比 < 1.0 | #21, #22 |
| 2. 字符数不达标: narrative < 1200 / 缺 5 节中任一节 | #14, #15 |
| 3. 因子问题: 孤立因子 / 缺 calculation / 缺 3 字段 / 窗口 > 250 / 引用未声明变量 | #9, #16, #20, #24 |
| 4. param 问题: 跨语义复用 / range 非 2 元素 / default 出 range / 描述 < 30 字符 | #10, #11, #13 |
| 5. trigger 硬编码数字(除 0/1/100/1000 外) | #23 |
| 6. position_weights 5 字段缺一 / 与 params 不对应 | #12, #18 |
| 7. `{param_name}` 引用未声明 param | #19 |
| 8. 顶层 4 字段缺一 | #1 |
| 9. frontmatter 6 块缺一 | #2-#10 |
| 10. test_universe 元素不在白名单 | #3 |
| 11. signals 字段不完整 / weight 硬编码 / factors 与 trigger 不一致 | #4-#8 |
| 12. A6 少于 3 类止损止盈 | (策略性,非硬校验) |

**节省**: ~600 字符。

### 3.8 (额外)优化 `description` 字段示例

| 位置 | 当前 | 改为 |
|---|---|---|
| L150 | "双均线交叉 + ATR 波动率扩张 + 量能确认 + 移动止损" | "双均线交叉 + ATR 波动率扩张 + 量能确认" |

**理由**: 与 narrative 第 4 节"风险机制"区分;`description` 只放策略简述,不放风控。

### 3.9 §3 净效果

| 指标 | 改前 | 改后 |
|---|---|---|
| 大小 | 22.6 KB / 442 行 | ~19.5 KB / ~380 行(-14%) |
| 内部矛盾 | 3 处 | 0 处 |
| 22+1 硬校验提示 | 每条 ≥3 处 | 每条 ≥1 处(主表 + 详细描述) |
| JSON 示例完整度 | 演示所有硬校验 | 演示所有硬校验(只瘦 params 13→6) |
| ❌ 关键禁止 | 26 条 | 12 条(每条映射硬校验) |

---

## 4. `quality_eval.md` 改动清单 (6 条)

### 4.1 删除"硬指标 23 项详细列表"(L81-92)

| 当前 | 改为 |
|---|---|
| 11 行表格,逐条列出 23 项硬校验 | 1 行: "23 项硬校验已由 `validate_md_structure` 完成,LLM **不重复评估**,只关注下文的 6 维软指标" |

**保留**: L222 关键禁止第 2 条"不重复硬校验"。

**节省**: ~700 字符。

### 4.2 删除 `hard_evaluation` 空壳(L48-53 + L73)

| 当前 | 改为 |
|---|---|
| 输出格式含 `"hard_evaluation": {"validate_md_structure": {"all_passed": true, "note": "..."}}` | 删除整个 `hard_evaluation` 字段 |

**配套**: `quality_eval.py` 解析时给 `hard_evaluation` 默认值 `{}`(向后兼容,见 §5.6)。

**节省**: ~300 字符。

### 4.3 删除"维度数从 7 → 6"历史包袱(L98-99)

| 当前 | 改为 |
|---|---|
| "维度数从 7 维 → 6 维:structural_completeness 已废除..." | 删除,直接说"6 维软指标" |

**保留**: 6 维列表本身。

**节省**: ~200 字符。

### 4.4 6 维"扣分项"详细列表 → 1 张"评分 hint"表

**当前**: 6 维共 30+ 项"❌ 扣 X 分"。
**改为**: 1 张 6 行 hint 表,每行 维度 / 核心评估点 / 加分方向。

**新表内容**:

| 维度 | 核心评估点 | 加分方向 |
|---|---|---|
| business_goal_alignment | 策略思路↔目标是否一致 | 给出明确 edge 来源 + 入出场规则匹配策略类型 |
| target_consistency | 5 项数值内部自洽 | win_rate×盈亏比 ≥ 1.5 视为合理 |
| bull_bear_adaptability | narrative 第 2 节含 3 环境处理 | 设计层面考虑(非实时识别)+ 阈值全部 param 化 |
| parameter_tunability | B2 8 项覆盖 + description 4 要素 | 给出每个 param 的典型取值 + 默认值理由 |
| logical_self_consistency | 入场/出场不矛盾 + 止损优先级 | 给出 weight 业务理由 + 多信号关系明确 |
| data_implementability | 因子可由基础字段计算 + calculation 清晰 | 用标准技术指标名 + trigger 变量可归类(因子/param/系统变量/常量) |

**关键变化**: 从"找茬式扣分"改为"加分式评估"——LLM 拿到 spec 时,先看"加分方向"再判断分数。

**节省**: ~1500 字符。**保留**: 6 维全部评估点(信息量等价)。

### 4.5 新增"评分校准"段

**新增内容**(L98 附近):
> **评分校准**: 6 维独立评分,8 分为常规优秀(占多数),9-10 分需明确理由(如"采用标准 ma_N + atr_N + volume_ratio 组合,calculation 字段全部为标准公式,trigger 变量归类清晰"),< 6 分需指出具体字段/段落。**避免全维度 9-10 分**——若全维度 9+ 应反思是否过于宽松。

**目的**: 让 LLM 评分有"基线参考",不靠 LLM 的"主观感觉"。

**+250 字符**(净增长,因 §4.1-§4.4 总体 -2700,所以净结果仍为 -2450 字符)。

### 4.6 关键禁止压缩: 11 ❌ → 6 ❌

| 当前(11 条) | 改为(6 条) |
|---|---|
| 修改策略 / 重复硬校验 / 评分主观 / issue 模糊 / 推荐实时市场识别 / 业务目标激进 = 硬错 / description 模糊 = 硬错 / 跨维度重复扣分 | 1. 不修改策略 2. 不重复硬校验 3. 评分有具体理由(不主观) 4. issue 描述具体到字段/段落 5. 不推荐"实时市场状态识别" 6. 不跨维度重复扣分 |

**节省**: ~400 字符。**保留**: 核心禁止项。

### 4.7 §4 净效果

| 指标 | 改前 | 改后 |
|---|---|---|
| 大小 | 9.6 KB / 231 行 | ~7.5 KB / ~180 行(-22%) |
| 6 维评估点 | 完整(每维 4-7 项) | 完整(改"加分方向"表,信息量等价) |
| Hard gate 规则 | 明确 | 明确(不变) |
| 评分校准 | 无 | 新增 1 段 |
| 关键禁止 | 11 条 | 6 条 |
| `hard_evaluation` 空壳 | 输出 | 删除(代码端兼容) |

---

## 5. `generate.py` 改动清单 (5 条 + 1 条 `quality_eval.py` 兼容)

### 5.1 修复 85% / 90% 口径不一致

| 位置 | 当前 | 改为 |
|---|---|---|
| `_format_quality_eval_feedback` L188 | "修复后总分需达到 51/60(85%)才算通过" | "修复后总分需达到 54/60(90%,见 `strategies/agents/quality_eval.py` `_PASS_THRESHOLD`)才算通过" |

**配套**: 从 `quality_eval._PASS_THRESHOLD` 引用,避免硬编码(若该常量未来变化)。

**风险**: 0(纯 bug 修正)。

### 5.2 6 维分数表按 gap 降序(L156-162)

**改动**:
```python
# 改前
for dim, content in soft.items():
    ...
# 改后
sorted_dims = sorted(
    soft.items(),
    key=lambda kv: -(10 - float(kv[1].get("score", 0))),
)
for dim, content in sorted_dims:
    ...
```

**风险**: 0(只影响展示,不影响评分)。

### 5.3 issues 按维度归类(不是按 severity)

| 当前 | 改为 |
|---|---|
| `issues_by_sev = {error:[], warning:[], info:[]}` | `issues_by_dim = {dim_name: [issue, ...]}` |
| L165-182 按 severity 分类 | 在 §5.2 循环里,直接展示该维度的 issues |

**风险**: 0(重新组织,信息量不变)。

### 5.4 (核心)加"下次怎么改"的可执行指导

**思路**: 6 维各定义 1 段"低分修复模板",根据 LLM 实际给的分数,匹配并注入到反馈中。

**6 维修复模板**:

| 维度 | 修复模板(注入到 feedback) |
|---|---|
| business_goal_alignment | "重新审视 targets.annual_return 与策略类型的关系: 趋势跟随策略年化 > 25% 较激进,均值回归策略 < 15% 较合理" |
| target_consistency | "重算 win_rate × profit_loss_ratio: 若 < 1.5,提高盈亏比或胜率;高夏普必须配高收益;高胜率可降盈亏比" |
| bull_bear_adaptability | "narrative 第 2 节须**明文**写 3 环境差异化处理(牛/熊/震荡),每环境 2-3 行,所有阈值用 `{param_name}`,**不**做实时市场识别" |
| parameter_tunability | "B2 8 项检查: 入场/出场/调仓/加仓/减仓/风控/仓位调整/position_weights 字段;description 4 要素: 含义+单位+典型取值+默认值理由" |
| logical_self_consistency | "narrative 第 3 节须明确**出场优先级**(固定止损>移动止损>时间止损),每个 signal weight 给业务理由" |
| data_implementability | "factors[].calculation 必须用标准公式(`mean(x, N)`/`atr(h,l,c, N)`/`100 - 100/(1+...)`),禁止 `market_sentiment` / `news_score` 等不可计算变量" |

**实现**:
- 在 `_format_quality_eval_feedback` 末尾追加"### 修复模板(按当前最弱维度)"段
- 6 个模板硬编码为 1 个 dict
- 选取 gap 最大的维度,注入对应模板

**+~600 字符**(反馈 user_prompt 增长,系统 prompt 不变)。

**风险**: 低(模板是通用指引,不绑死 LLM 输出)。

### 5.5 加"失败次数递增"机制

| 当前 | 改为 |
|---|---|
| 每次 retry feedback 形式一致 | 第 3 次及以上失败时,在 feedback 头部加红字: "⚠️ 已失败 N 次。请**大幅修改策略类型/因子选择/出入场逻辑**,不要在原 spec 上做小调整。" |

**实现**:
- `_run_generate_once` 把 `attempt` 传给 `_format_quality_eval_feedback`
- 函数签名加可选参数 `attempt: int = 1`(默认 1,保持向后兼容)
- 当 `attempt >= 3` 时,在 feedback 顶部插入警告

**风险**: 低(机制是"提醒",不强制 LLM)。

### 5.6 配套: `quality_eval.py` 兼容处理(因 §4.2 删除 `hard_evaluation` 字段)

`strategies/agents/quality_eval.py` 中:
- L170 解析 LLM 返回 JSON 后,只关心 `soft_evaluation` / `passed` / `summary` / `hard_pass_recommendation`
- `hard_evaluation` 在代码里只被 **读取**(可能用于日志),不参与评分
- 修改: 在 `_judge_hard_gates` 前后,**给 `hard_evaluation` 设默认值 `{}`**,LLM 不输出也不会 KeyError

**风险**: 0(纯向后兼容)。

### 5.7 §5 净效果

| 指标 | 改前 | 改后 |
|---|---|---|
| 反馈"知道分低但不知怎么改" | 通用建议(3 条) | 每 weak 维 1 段具体修复模板 |
| 反馈"按维度归类" | 按 severity | 按维度(LLM 易对应修改点) |
| 反馈"按 gap 排序" | 维度原序 | gap 降序(LLM 一眼看到最弱) |
| 阈值口径 | 85% / 90% 不一致 | 统一 90% |
| 失败递增 | 每次一样 | 第 3 次起给"换思路"提醒 |
| 函数签名兼容 | n/a | 保持不变(attempt 是新加可选参数) |

---

## 6. 验证方案

### 6.1 阶段 1: 静态验证(改完立即跑,~10 分钟)

| 检查项 | 命令 | 预期 |
|---|---|---|
| 文件大小 | `wc -c strategies/agents/prompts/generate.md quality_eval.md` | generate.md ≤ 19.5 KB, quality_eval.md ≤ 7.5 KB |
| 22+1 硬校验覆盖 | 人工对照 §3.3 验证表 | 每条硬校验 ≥1 处明确提示 |
| Python 语法 | `python -c "from strategies.agents import generate, quality_eval"` | 无 import 错误 |
| `_format_quality_eval_feedback` 签名 | 检查 `attempt` 参数 | 默认值 1,向后兼容 |
| `hard_evaluation` 兼容 | 跑 1 次 generate,确认无 KeyError | 通过 |

### 6.2 阶段 2: 单 spec 端到端(~30-60 分钟)

| 测试 | 操作 | 预期 |
|---|---|---|
| 真实 spec 走 generate | `python strategies/strategies.py generate --once` | 输出 1 个通过 90% 的 spec,记录 attempt 数和每次分数 |
| 失败 case 走 generate | 故意构造一个会 fail 的 spec,看 retry feedback | 第 2-3 次 attempt 应该明显提升 |
| 8 步 smoke | 跑 Stage B translator | strategy.py 翻译 + 8 步 smoke 通过 |

### 6.3 阶段 3: A/B 对比(2-3 天)

| 维度 | 旧版(master) | 新版(本设计) |
|---|---|---|
| 跑 N 次 generate,统计 | 一次过 90% 概率、平均 attempt 数、单次时间、token 用量 | 同左 |
| 关键指标 | (基线) | 目标: 一次过 ≥ 40%, 平均 attempt ≤ 2, 单次时间 ↓, token 用量 ↓ |
| 评估 | (基线) | 新版相对提升 |

**统计意义**: N ≥ 30 次 generate 调用,A/B 对比 p<0.05 为显著。

---

## 7. 回退预案

| 触发条件 | 行动 |
|---|---|
| 阶段 1 静态验证发现硬校验覆盖缺失 | 不合并,直接修补设计 |
| 阶段 2 单 spec 端到端失败 | `git revert` 还原全部 4 个文件(`generate.md` / `quality_eval.md` / `generate.py` / `quality_eval.py`) |
| 阶段 3 A/B 显著退化(一次过概率下降) | `git revert` 还原全部 4 个文件 |
| 阶段 3 A/B 持平 | 保留改动(至少节省 token) |
| 阶段 3 A/B 显著提升(一次过 ≥ +10%) | 合并 + 写 release notes |

**回退成本**: 4 个文件 `git revert`(`generate.md` / `quality_eval.md` / `generate.py` / `quality_eval.py`),预计 5 分钟。

---

## 8. 风险与缓解

| 风险 | 概率 | 影响 | 缓解 |
|---|---|---|---|
| LLM 仍达不到 90%(rubric 本身偏严) | 中 | 高 | 阶段 3 验证发现后,在 `_format_quality_eval_feedback` 中加"rubric hint"引导 LLM 评分稍宽松 |
| 压缩后 LLM 漏规则 | 低 | 中 | §3.3 修订表已严格保证 22+1 覆盖,阶段 1 静态验证再查一遍 |
| 修复模板过强(LLM 失去创意) | 低 | 中 | 模板是"指引",不绑死输出;LLM 仍可自由发挥 |
| 阈值口径修复引发连锁 | 极低 | 低 | grep 全文确认 `_PASS_THRESHOLD` 引用一致 |
| 失败递增机制误触发 | 极低 | 低 | 单元测试: 跑 5 次 fail,看第 3 次反馈是否含警告 |
| 阶段 3 A/B 跑不出来(N 太小) | 中 | 低 | 跑 50 次以上,或 1 周累计 |

---

## 9. 实施顺序(估时,writing-plans 阶段会细化)

| # | 任务 | 估时 | 依赖 |
|---|---|---|---|
| 1 | 改 `generate.md`(7+1 条) | 30 min | 无 |
| 2 | 改 `quality_eval.md`(6 条) | 20 min | 无 |
| 3 | 改 `quality_eval.py` 兼容 | 10 min | 无 |
| 4 | 改 `generate.py` `_format_quality_eval_feedback`(5 条) | 30 min | 3 |
| 5 | 静态验证(§6.1) | 10 min | 1-4 |
| 6 | 单 spec 端到端(§6.2) | 30-60 min | 5 |

**总估时**: ~2-3 小时(不含 A/B 阶段 3)。

---

## 10. 总结

**改 4 个文件、压缩 ~17% 输入窗口、消除 prompt 内部矛盾、加精准化 retry 反馈,预期一次过 90% 概率从 ~20% 提升到 ~40-50%,且回退成本 < 5 分钟。**

**关键设计原则**:
1. **压缩冗余,不压缩规则**——回应用户对硬校验覆盖的担忧
2. **从"找茬式扣分"改为"加分式评估"**——让 LLM 评分更平衡
3. **反馈"具体到可执行"**——6 维各 1 段修复模板
4. **失败递增机制**——第 3 次起给"换思路"提醒,避免模式坍缩

**严格不动**: 90% 门槛、pipeline 架构、6 维评分维度、22+1 硬校验。
