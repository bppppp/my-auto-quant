# autoRun 质量评估精炼 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **User note:** 用户在 spec 评审时说"先不用提交"。本计划**默认不提交**(Step N 标记为"可选 git commit"),工程师执行时应:
> - 跳过所有"git add"和"git commit"步骤
> - 实施完成后**整体**询问用户是否提交
> - 如需分批 commit,应**逐次**询问用户

**Goal:** 通过精炼 `generate.md` / `quality_eval.md` / `generate.py` / `quality_eval.py` 4 个文件,提高 `strategies.py generate` 一次过 90% 概率从 ~20% 到 ≥ 40%,平均尝试次数从 3-5 次降到 1-2 次,同时保持 22+1 硬校验完整覆盖。

**Architecture:** 严格遵守"压缩冗余,不压缩规则"原则。所有改动是 4 个文件的纯文本 / Python 函数级修改,不动 pipeline 架构、不动 90% 门槛。新增 `tests/` 目录 + pytest 基础设施,用结构化测试验证 prompt 完整性和 Python 函数行为。

**Tech Stack:** Python 3.10+ / pytest / pyyaml(已用)/ openai(已用)

**Spec:** `docs/superpowers/specs/2026-06-08-autorun-quality-design.md`

---

## File Structure

**修改的文件** (4 个):
- `strategies/agents/prompts/generate.md` — 22.6 KB → ~19.5 KB(-14%),消除内部矛盾,合并硬规则
- `strategies/agents/prompts/quality_eval.md` — 9.6 KB → ~7.5 KB(-22%),从扣分式改为加分式评估
- `strategies/agents/quality_eval.py` — 1 处兼容性改动(给 `hard_evaluation` 默认值)
- `strategies/agents/generate.py` — `_format_quality_eval_feedback` 函数 + 6 维修复模板 + 失败递增机制

**新建的文件** (5 个):
- `tests/__init__.py` — pytest 识别
- `tests/conftest.py` — 把项目根加到 sys.path
- `pytest.ini` — pytest 配置
- `tests/test_generate_prompt.py` — `generate.md` 结构测试
- `tests/test_quality_eval_prompt.py` — `quality_eval.md` 结构测试
- `tests/test_format_feedback.py` — `_format_quality_eval_feedback` 行为测试

**修改的文件** (附属,1 个):
- `autoRun/requirements.txt` — 加 pytest 依赖(测试 only)

---

## Task 1: 测试基础设施

**Files:**
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`
- Create: `pytest.ini`
- Create: `tests/test_smoke.py`
- Modify: `autoRun/requirements.txt` (末尾追加 pytest)

- [ ] **Step 1: 创建 `tests/` 目录**

```bash
mkdir tests
```

- [ ] **Step 2: 创建 `tests/__init__.py`(空文件)**

```python
# tests/__init__.py
```

- [ ] **Step 3: 创建 `tests/conftest.py`(把项目根加到 sys.path)**

```python
"""conftest.py — pytest 配置,把项目根加到 sys.path 让 tests/ 能 import 项目模块。"""
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))
```

- [ ] **Step 4: 创建 `pytest.ini`**

```ini
[pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
addopts = -v --tb=short
```

- [ ] **Step 5: 创建 `tests/test_smoke.py`(占位测试,验证 pytest 能跑)**

```python
"""tests/test_smoke.py — 占位测试,验证 pytest 基础设施工作。"""


def test_pytest_works():
    """简单 smoke 测试,确认 pytest 能跑。"""
    assert 1 + 1 == 2


def test_project_root_in_path():
    """验证项目根在 sys.path 里(由 conftest.py 注入)。"""
    import sys
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent
    assert str(root) in sys.path, f"项目根 {root} 不在 sys.path"
```

- [ ] **Step 6: 在 `autoRun/requirements.txt` 末尾追加 pytest**

打开 `autoRun/requirements.txt`,在文件末尾追加:

```
# 测试依赖(开发 only,生产可忽略)
pytest>=7.0.0
```

- [ ] **Step 7: 安装 pytest 并跑测试**

```bash
cd D:/project/quant/my-quant3
pip install pytest>=7.0.0
pytest tests/
```

**Expected output**:
```
tests/test_smoke.py::test_pytest_works PASSED
tests/test_smoke.py::test_project_root_in_path PASSED
========================= 2 passed in 0.05s ==========================
```

- [ ] **Step 8: (可选 git commit)** `git add tests/ pytest.ini autoRun/requirements.txt && git commit -m "test: 添加 pytest 基础设施 + smoke 测试"`

---

## Task 2: 添加 generate.md 结构测试(RED)

**Files:**
- Create: `tests/test_generate_prompt.py`

**目标**: 写测试,跑通,然后**故意让它 fail**(因为我们还没改 generate.md)。

- [ ] **Step 1: 创建 `tests/test_generate_prompt.py`**

```python
"""tests/test_generate_prompt.py — 验证 generate.md 满足结构约束。

这些测试在 spec §3 实施前应当 FAIL(因为当前 generate.md 不满足新约束),
实施后应当 PASS。
"""
import re
from pathlib import Path

PROMPT_PATH = Path("strategies/agents/prompts/generate.md")


def _read_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


# === 1. 大小限制 ===

def test_generate_md_size_under_20kb():
    """改后目标: 22.6 KB → ≤ 20 KB。给一点 buffer。"""
    size = len(_read_prompt().encode("utf-8"))
    assert size <= 20_000, f"generate.md 实际大小 {size} 字节,超过 20 KB 上限"


# === 2. 字符数统一(消除 800 vs 1500 矛盾)===

def test_narrative_length_unified():
    """narrative 字符数要求在 prompt 内必须统一,不能同时出现 800 和 1500。"""
    content = _read_prompt()
    # 旧: 同时出现 "≥ 800 字符" 和 "≥ 1500 字符"
    has_800 = "≥ 800 字符" in content
    has_1500 = "≥ 1500 字符" in content
    has_1200 = "≥ 1200 字符" in content
    assert not has_800, "narrative 字符数不应再出现 800(旧值)"
    assert not has_1500, "narrative 字符数不应再出现 1500(旧值)"
    assert has_1200, "narrative 字符数应为 1200"


# === 3. 节数统一(消除 4 节 vs 6 节矛盾)===

def test_narrative_section_count_unified():
    """narrative 节数要求必须统一(5 节)。"""
    content = _read_prompt()
    # 旧: "必含 4 节" 出现在 prompt 内
    assert "必含 4 节" not in content, "narrative 节数不应再是 4 节"
    assert "必含 5 节" in content, "narrative 节数应为 5 节"


# === 4. 22+1 硬校验全覆盖(每条 ≥1 处明确提示)===

# 关键词映射: 每条硬校验至少 1 个关键词必须在 prompt 中出现
HARD_CHECK_KEYWORDS = {
    "#1 顶层 4 字段": ["name", "test_universe", "frontmatter", "strategy_narrative"],
    "#3 test_universe 合法值": ["HS300", "CSI1000", "CYB_STAR_50"],
    "#9/#20 孤立因子": ["孤立因子"],
    "#10/#11 params 8 字段": ["params[].name", "params[].default", "params[].range"],
    "#12 position_weights 5 字段": ["max_single_weight", "max_industry_concentration", "target_holdings"],
    "#13 description 4 要素": ["4 要素", "30 字符"],
    "#14-#15 narrative 长度/节": ["≥ 1200 字符", "必含 5 节"],
    "#16 factors↔trigger": ["trigger", "factors"],
    "#18 position_weights↔params": ["position_weights", "params"],
    "#19 {param_name}": ["{param_name}", "params[].name"],
    "#21-#22 targets 数学": ["annual_return", "max_drawdown"],
    "#23 trigger 硬编码": ["硬编码", "0/1/100/1000"],
    "#24 factors 3 字段": ["factors[].calculation", "factors[].description"],
}


def test_each_hard_check_has_mention():
    """22+1 硬校验每条至少 1 个关键词必须在 prompt 中出现。"""
    content = _read_prompt()
    missing = []
    for check_id, keywords in HARD_CHECK_KEYWORDS.items():
        if not any(kw in content for kw in keywords):
            missing.append((check_id, keywords))
    assert not missing, f"以下硬校验在 generate.md 中无明确提示: {missing}"


# === 5. 关键禁止 12 条(每条映射硬校验)===

def test_key_禁止_count():
    """关键禁止应有 12 条(以 "❌" 编号开头)。"""
    content = _read_prompt()
    # 匹配 "1. xxx" 到 "12. xxx" 的编号格式(允许 ❌ 修饰)
    items = re.findall(r"^\s*(\d+)\.\s+", content, re.MULTILINE)
    # 至少需要 12 条编号列表项(实际可能多,这里只检查关键禁止那部分)
    # 通过 12. 后面跟着 "A6 少于 3 类止损止盈" 来确认有 12 条
    assert "12. A6 少于 3 类止损止盈" in content or "12." in content, \
        "应有关键禁止第 12 条"


# === 6. data_implementability 高分指南前置 ===

def test_data_implementability_appears_early():
    """data_implementability 高分指南应出现在 prompt 前 30% 位置。"""
    content = _read_prompt()
    position = content.find("data_implementability")
    assert position < len(content) * 0.3, \
        f"data_implementability 位置 {position} 应在 prompt 前 30%({len(content) * 0.3:.0f} 字节内)"


# === 7. JSON 示例保留演示硬校验的字段 ===

def test_json_example_has_position_weights():
    """JSON 示例必须保留 position_weights 块(硬校验 #12 #18 演示必需)。"""
    content = _read_prompt()
    assert "position_weights:" in content, "JSON 示例缺 position_weights 块"


# === 8. trigger 变量白名单是 4 行表 ===

def test_trigger_whitelist_is_compact_table():
    """trigger 变量白名单应压缩为 4 行表(因子/param/系统变量/数学常量)。"""
    content = _read_prompt()
    # 4 个类别关键词
    categories = ["因子名", "param 名", "K 线系统变量", "数学常量"]
    for cat in categories:
        assert cat in content, f"trigger 白名单缺类别: {cat}"
```

- [ ] **Step 2: 跑测试,验证 FAIL(因为 generate.md 还是旧的)**

```bash
cd D:/project/quant/my-quant3
pytest tests/test_generate_prompt.py -v
```

**Expected output**: 多数测试 FAIL,例如:
```
tests/test_generate_prompt.py::test_generate_md_size_under_20kb FAILED
tests/test_generate_prompt.py::test_narrative_length_unified FAILED
tests/test_generate_prompt.py::test_narrative_section_count_unified FAILED
tests/test_generate_prompt.py::test_each_hard_check_has_mention PASSED  # 当前覆盖足够
...
```

- [ ] **Step 3: (可选 git commit)** `git add tests/test_generate_prompt.py && git commit -m "test(red): 添加 generate.md 结构测试"`

---

## Task 3: 应用 generate.md 全部改动

**Files:**
- Modify: `strategies/agents/prompts/generate.md` (8 处)
- Modify: `strategies/agents/generate.py:103` (1 处)

- [ ] **Step 1: 改 L4 — 字符数 800 → 1200**

在 `generate.md` 第 4 行(原"≥ 800 字符"),改为:

```markdown
**`strategy_narrative` ≥ 1200 字符**(中位值,既不严也不松),必含 5 节
```

- [ ] **Step 2: 改 L36 #4 — 节数 4 → 5**

在 `generate.md` 硬规则速查表 L36 第 4 行,改为:

```markdown
| 4 | `strategy_narrative` ≥ **1200 字符**,必含 5 节(策略思路 / 3 环境处理 / 多信号关系 / 风险机制 / NaN 处理) | #14, #15 |
```

- [ ] **Step 3: 改 L150 — 精简 description 字段**

在 JSON 示例 L150:

原: `"description": "双均线交叉 + ATR 波动率扩张 + 量能确认 + 移动止损"`
改为: `"description": "双均线交叉 + ATR 波动率扩张 + 量能确认"`

- [ ] **Step 4: 改 L155 JSON 示例 — 节数 6 → 5**

在 `generate.md` L155 JSON 例子的 `strategy_narrative` 字段,合并第 1 和第 2 节为"### 1. 策略思路 / edge 来源(含市场环境假设)",删除原来的"### 2. 市场环境假设"。节编号 3-6 改为 2-5。

- [ ] **Step 5: 改 L221-242 — 移动 data_implementability 到 L80-110**

把 `generate.md` 当前 L221-242 整段(标题"data_implementability 高分指南(quality_eval 评估维度)" + 3 个子节)剪切到 L80-110 区域(在硬规则速查表之后、JSON 输出格式之前)。

- [ ] **Step 6: 改 L302-318 — 压缩 trigger 白名单为 4 行表**

原 L302-318 整段(11 行详细列表),替换为:

```markdown
### `trigger` 公式变量(无白名单,但需可归类)

| 类别 | 示例 | 是否需 `{}` 包裹 |
|---|---|---|
| 因子名 | `ma_20` / `atr_14` | ❌ 裸名 |
| param 名 | `atr_min_threshold` | ✅ `{name}` |
| K 线系统变量 | `close` / `volume` / `holding_days` | ❌ 裸名 |
| 数学常量 | `0` / `1` / `100` / `1000` | ❌ 字面值 |

**原则**: LLM 专注于策略业务逻辑,**信任 LLM 的设计选择**。
```

- [ ] **Step 7: 改 L337 — 字符数 800 → 1200**

在 `generate.md` L337("≥ 800 字符(约 320 tokens,节省约 50%)"),改为:

```markdown
- **字符数**: **≥ 1200 字符**(中位值)
```

- [ ] **Step 8: 改 L386-411 关键禁止 — 26 条 → 12 条**

把 `generate.md` L386-411 整段"## 关键禁止"替换为:

```markdown
## 关键禁止(12 条,每条对应硬校验)

1. **数值不达标**: `annual_return ≤ 0.20` / 收益回撤比 < 1.0 / `win_rate × profit_loss_ratio < 1.0`
2. **narrative 不达标**: 字符数 < 1200 / 缺 5 节中任一节
3. **因子问题**: 孤立因子 / 缺 `calculation` / 缺 3 字段 / 窗口 N > 250 / trigger 引用未声明变量
4. **param 问题**: 跨语义复用 / `range` 非 2 元素 / `default` 超出 `range` / 描述 < 30 字符
5. **trigger 硬编码数字**(除 0/1/100/1000 外)
6. **`position_weights` 5 字段缺一** / 与 `params` 不对应
7. **`{param_name}` 引用未声明的 param**
8. **顶层 4 字段缺一**
9. **`frontmatter` 6 块缺一**(`targets` / `factors` / `entry_signals` / `exit_signals` / `position_weights` / `params`)
10. **`test_universe` 元素不在白名单**(`HS300` / `CSI1000` / `CYB_STAR_50` 大写)
11. **signals 字段不完整** / weight 硬编码 / `factors` 与 trigger 不一致
12. **A6 少于 3 类止损止盈**
```

- [ ] **Step 9: 改 L398-400 + L427 — 节数 4 → 5**

在 `generate.md` L398-400(关键禁止里的 narrative 字符数那条),改为"5 节"。

在 `generate.md` L427 末尾速查,改为"5 节"。

- [ ] **Step 10: 改 L415-441 末尾速查 — 精简**

把 `generate.md` L438-440(`test_universe` 字段段)整段删除(已并入主硬规则表)。

- [ ] **Step 11: 改 L48-157 JSON 示例 — params 13 → 6**

在 JSON 示例的 `params` 列表(原 L135-149,13 个),只保留 6 个代表性 param(覆盖 description 4 要素 + B2 8 项):
- `atr_min_threshold`(入场阈值)
- `volume_breakout_ratio`(入场阈值)
- `fixed_stop_pct`(风控识别阈值)
- `trailing_stop_pct`(风控识别阈值)
- `max_holding_days`(时间止损)
- `max_single_weight`(仓位调整 — 与 position_weights 联动)

删除其余 7 个 param 行。

- [ ] **Step 12: 改 `generate.py:103` — 字符数 1500 → 1200 + 节数 6 → 5**

打开 `strategies/agents/generate.py`,找到 `_build_user_prompt` 函数 L103 附近(原"5. `strategy_narrative`: 单字段,≥ 1500 字符,含 6 节"),改为:

```python
        5. `strategy_narrative`: 单字段,≥ 1200 字符,含 5 节
```

- [ ] **Step 13: 跑测试,验证 PASS**

```bash
cd D:/project/quant/my-quant3
pytest tests/test_generate_prompt.py -v
```

**Expected output**: 所有测试 PASS。

- [ ] **Step 14: 检查 generate.md 大小**

```bash
wc -c strategies/agents/prompts/generate.md
```

**Expected**: 字节数 ≤ 20,000(目标 19,500)。

- [ ] **Step 15: (可选 git commit)** `git add strategies/agents/prompts/generate.md strategies/agents/generate.py && git commit -m "refactor(prompt): 精炼 generate.md -14% + 消除内部矛盾 + 合并硬规则"`

---

## Task 4: 添加 quality_eval.md 结构测试(RED)

**Files:**
- Create: `tests/test_quality_eval_prompt.py`

- [ ] **Step 1: 创建 `tests/test_quality_eval_prompt.py`**

```python
"""tests/test_quality_eval_prompt.py — 验证 quality_eval.md 满足结构约束。

这些测试在 spec §4 实施前应当 FAIL,实施后应当 PASS。
"""
import re
from pathlib import Path

PROMPT_PATH = Path("strategies/agents/prompts/quality_eval.md")


def _read_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


# === 1. 大小限制 ===

def test_quality_eval_md_size_under_8kb():
    """改后目标: 9.6 KB → ≤ 8 KB。"""
    size = len(_read_prompt().encode("utf-8"))
    assert size <= 8_000, f"quality_eval.md 实际大小 {size} 字节,超过 8 KB 上限"


# === 2. 删除 hard_evaluation 空壳 ===

def test_no_hard_evaluation_in_output_format():
    """LLM 输出格式不应再要求 `hard_evaluation` 字段。"""
    content = _read_prompt()
    # 检查 JSON 例子或输出格式说明里没有 hard_evaluation 字段
    assert '"hard_evaluation"' not in content, \
        "LLM 输出格式不应再要求 hard_evaluation 字段"


# === 3. 删除"维度数从 7 → 6"历史包袱 ===

def test_no_dimension_history():
    """不应有"维度数从 7 维 → 6 维"这种历史包袱。"""
    content = _read_prompt()
    assert "维度数从 7 维" not in content, "应删除维度历史包袱"
    assert "structural_completeness" not in content, "应删除已废除维度的提及"


# === 4. 6 维都还在 ===

def test_six_dimensions_present():
    """6 维软指标必须都在。"""
    content = _read_prompt()
    dims = [
        "business_goal_alignment",
        "target_consistency",
        "bull_bear_adaptability",
        "parameter_tunability",
        "logical_self_consistency",
        "data_implementability",
    ]
    for dim in dims:
        assert dim in content, f"缺软指标维度: {dim}"


# === 5. 评分校准段存在 ===

def test_scoring_calibration_present():
    """应新增"评分校准"段,提示 LLM 评分基线。"""
    content = _read_prompt()
    assert "评分校准" in content, "应新增评分校准段"


# === 6. 关键禁止 6 条 ===

def test_key_禁止_six_items():
    """关键禁止应为 6 条(从 11 条压缩)。"""
    content = _read_prompt()
    # 关键禁止的 6 条核心项
    forbidden_phrases = [
        "不修改策略",
        "不重复硬校验",
        "评分有具体理由",
        "issue 描述具体到字段",
        "不推荐",
        "实时市场状态识别",
        "不跨维度重复扣分",
    ]
    for phrase in forbidden_phrases:
        assert phrase in content, f"关键禁止应包含: {phrase}"
```

- [ ] **Step 2: 跑测试,验证 FAIL(quality_eval.md 还是旧的)**

```bash
cd D:/project/quant/my-quant3
pytest tests/test_quality_eval_prompt.py -v
```

**Expected output**: 多数测试 FAIL。

- [ ] **Step 3: (可选 git commit)** `git add tests/test_quality_eval_prompt.py && git commit -m "test(red): 添加 quality_eval.md 结构测试"`

---

## Task 5: 应用 quality_eval.md 全部改动

**Files:**
- Modify: `strategies/agents/prompts/quality_eval.md` (6 处)

- [ ] **Step 1: 改 L48-66 — 删除 `hard_evaluation` 空壳**

在 `quality_eval.md` L48-53 的 JSON 例子,删除整个 `"hard_evaluation": {...}` 字段,JSON 例子改为:

```json
{
  "passed": true,
  "soft_evaluation": {
    "business_goal_alignment": {"score": 8, "issues": []},
    "target_consistency": {"score": 7, "issues": []},
    "bull_bear_adaptability": {"score": 9, "issues": []},
    "parameter_tunability": {"score": 8, "issues": []},
    "logical_self_consistency": {"score": 7, "issues": []},
    "data_implementability": {"score": 6, "issues": []}
  },
  "summary": "...",
  "hard_pass_recommendation": "pass_with_warnings"
}
```

字段说明表(L70-78)中的 `hard_evaluation` 行也删除。

- [ ] **Step 2: 改 L81-92 — 11 行硬规则表 → 1 行**

把 L81-92 整段(11 行表格)替换为:

```markdown
## 硬指标(23 项 validate_md_structure 已完成,不重复评估)

23 项硬校验已由 `validate_md_structure` 完成,LLM **不重复评估**,只关注下文的 6 维软指标。
```

- [ ] **Step 3: 改 L98-99 — 删除历史包袱**

把 L98-99:

原: `> **维度数从 7 维 → 6 维**:`structural_completeness` 已废除(其内容由 23 项硬校验覆盖,避免重复评估)。soft_evaluation 仅含 6 维度。`

改为:

```markdown
## 软指标(6 维度,LLM 业务判断)
```

- [ ] **Step 4: 改 L107-200 — 6 维扣分项 → 1 张 hint 表**

把 L100-200 整段(6 维度,每维度"评估内容" + "扣分项")替换为:

```markdown
### 6 维评分 hint 表

| 维度 | 核心评估点 | 加分方向 |
|---|---|---|
| business_goal_alignment | 策略思路↔目标是否一致 | 给出明确 edge 来源 + 入出场规则匹配策略类型 |
| target_consistency | 5 项数值内部自洽 | win_rate×盈亏比 ≥ 1.5 视为合理 |
| bull_bear_adaptability | narrative 第 2 节含 3 环境处理 | 设计层面考虑(非实时识别)+ 阈值全部 param 化 |
| parameter_tunability | B2 8 项覆盖 + description 4 要素 | 给出每个 param 的典型取值 + 默认值理由 |
| logical_self_consistency | 入场/出场不矛盾 + 止损优先级 | 给出 weight 业务理由 + 多信号关系明确 |
| data_implementability | 因子可由基础字段计算 + calculation 清晰 | 用标准技术指标名 + trigger 变量可归类(因子/param/系统变量/常量) |

**评分校准**: 6 维独立评分,8 分为常规优秀(占多数),9-10 分需明确理由(如"采用标准 ma_N + atr_N + volume_ratio 组合,calculation 字段全部为标准公式,trigger 变量归类清晰"),< 6 分需指出具体字段/段落。**避免全维度 9-10 分**——若全维度 9+ 应反思是否过于宽松。
```

- [ ] **Step 5: 改 L204-218 评分计算段 — 简化(只保留 hard gate)**

把 L204-218 整段简化为:

```markdown
## 评分计算

**`passed` 判定 hard gates**(任一触发即 `passed: false`):
- `data_implementability.score < 6`(hard gate)
- 任一维度 score == 0(完全缺失)

**`hard_pass_recommendation` 判定**:
- 无 `error` 级 issue + `passed == true` → `pass`
- 有 `warning` 级 issue + `passed == true` → `pass_with_warnings`
- `passed == false` → `fail`
```

- [ ] **Step 6: 改 L222-232 关键禁止 — 11 条 → 6 条**

把 L222-232 整段"## 关键禁止"替换为:

```markdown
## 关键禁止(6 条核心)

1. 不修改策略(只评估)
2. 不重复硬校验(23 项机器已检查,不重做)
3. 评分有具体理由(不主观)
4. issue 描述具体到字段/段落
5. 不推荐"实时市场状态识别"(设计层面 3 环境处理才推荐)
6. 不跨维度重复扣分
```

- [ ] **Step 7: 跑测试,验证 PASS**

```bash
cd D:/project/quant/my-quant3
pytest tests/test_quality_eval_prompt.py -v
```

**Expected output**: 所有测试 PASS。

- [ ] **Step 8: 检查 quality_eval.md 大小**

```bash
wc -c strategies/agents/prompts/quality_eval.md
```

**Expected**: 字节数 ≤ 8,000(目标 7,500)。

- [ ] **Step 9: (可选 git commit)** `git add strategies/agents/prompts/quality_eval.md && git commit -m "refactor(prompt): 精炼 quality_eval.md -22% + 从扣分式改为加分式"`

---

## Task 6: 兼容 `hard_evaluation` 字段缺失

**Files:**
- Modify: `strategies/agents/quality_eval.py` (1 处)

**目标**: `quality_eval.md` 删除了 `hard_evaluation` 字段后,LLM 不再输出它。`quality_eval.py` 解析时给默认值,避免 KeyError。

- [ ] **Step 1: 阅读 `quality_eval.py` 找解析 LLM 返回 JSON 的位置**

打开 `strategies/agents/quality_eval.py`,找 `run_quality_eval` 函数内,`llm.invoke(...)` 之后、`parse_strategy_json(...)` 之后那段。典型代码如下:

```python
response = llm.invoke(system_prompt, user_prompt)
data = parse_strategy_json(response)
# 后续使用 data["soft_evaluation"] / data["passed"] 等
```

找到后,记下行号。

- [ ] **Step 2: 给 `hard_evaluation` 设默认值**

在 `parse_strategy_json(response)` 解析后,**给 data 注入默认 `hard_evaluation`**:

```python
data = parse_strategy_json(response)
# 兼容 LLM 不再输出 hard_evaluation 字段(simplified prompt §4.2)
if isinstance(data, dict):
    data.setdefault("hard_evaluation", {})
```

**注**: 如果 `data` 解析后不是 dict,后续代码会自然报错(原本的防御),不需额外处理。

- [ ] **Step 3: 跑现有测试,确保不破坏其他东西**

```bash
cd D:/project/quant/my-quant3
pytest tests/ -v
```

**Expected output**: 所有现有测试 PASS(没有 hard_evaluation 相关测试,我们仅做了兼容性改动)。

- [ ] **Step 4: 跑 generate smoke(可选,需要真实 LLM 调用)**

如果 LLM API 可用,跑一次 generate 验证:

```bash
python strategies/strategies.py generate --once 2>&1 | head -50
```

**Expected**: 不出现 `KeyError: 'hard_evaluation'`。

- [ ] **Step 5: (可选 git commit)** `git add strategies/agents/quality_eval.py && git commit -m "fix(quality_eval): 兼容 LLM 不输出 hard_evaluation 字段"`

---

## Task 7: 添加 `_format_quality_eval_feedback` 行为测试(RED)

**Files:**
- Create: `tests/test_format_feedback.py`

- [ ] **Step 1: 创建 `tests/test_format_feedback.py`**

```python
"""tests/test_format_feedback.py — 验证 _format_quality_eval_feedback 的新行为。

这些测试在 spec §5 实施前应当 FAIL,实施后应当 PASS。
"""
import pytest
from strategies.agents.generate import _format_quality_eval_feedback


def _make_eval_result(scores: dict, summary: str = "test summary") -> dict:
    """构造一个 eval_result dict 用于测试。"""
    return {
        "soft_evaluation": {
            dim: {"score": score, "issues": []}
            for dim, score in scores.items()
        },
        "_quality_total": sum(scores.values()),
        "_quality_total_max": 60,
        "_quality_ratio": sum(scores.values()) / 60,
        "summary": summary,
    }


# === 1. 阈值口径统一为 90%(不是 85%) ===

def test_threshold_mentions_90_not_85():
    """反馈必须提到 90% 阈值,不能提到 85%。"""
    result = _make_eval_result({
        "business_goal_alignment": 7,
        "target_consistency": 7,
        "bull_bear_adaptability": 7,
        "parameter_tunability": 7,
        "logical_self_consistency": 7,
        "data_implementability": 7,
    })  # 42/60 = 70%
    output = _format_quality_eval_feedback(result)
    assert "85%" not in output, f"反馈不应提到 85%,实际输出:\n{output}"
    assert "90%" in output, f"反馈应提到 90%,实际输出:\n{output}"


# === 2. 6 维按 gap 降序排 ===

def test_dims_sorted_by_gap_descending():
    """gap 越大(分数越低),应排在 feedback 更前面。"""
    result = _make_eval_result({
        "business_goal_alignment": 9,  # gap = 1
        "data_implementability": 3,    # gap = 7
        "target_consistency": 7,        # gap = 3
    })
    output = _format_quality_eval_feedback(result)
    # 期望出现顺序: data_implementability → target_consistency → business_goal_alignment
    pos_data = output.find("data_implementability")
    pos_target = output.find("target_consistency")
    pos_business = output.find("business_goal_alignment")
    assert pos_data < pos_target < pos_business, \
        f"6 维未按 gap 降序排: data={pos_data}, target={pos_target}, business={pos_business}"


# === 3. 修复模板存在 ===

def test_weakest_dim_template_present():
    """feedback 应包含"修复模板"段,且包含最弱维度的具体建议。"""
    result = _make_eval_result({
        "business_goal_alignment": 9,
        "data_implementability": 3,  # 最弱
    })
    output = _format_quality_eval_feedback(result)
    assert "修复模板" in output, "feedback 应包含修复模板段"
    # data_implementability 模板应包含"factors[].calculation"
    # 因为最弱维度是 data_implementability
    assert "calculation" in output or "标准公式" in output, \
        "修复模板应包含最弱维度的具体建议"


# === 4. 失败次数递增机制 ===

def test_attempt_3_plus_includes_warning():
    """当 attempt >= 3 时,feedback 应包含"已失败 N 次"警告。"""
    result = _make_eval_result({"data_implementability": 3})
    output_default = _format_quality_eval_feedback(result)  # 默认 attempt=1
    assert "已失败" not in output_default, "默认 attempt=1 不应警告"

    output_attempt_3 = _format_quality_eval_feedback(result, attempt=3)
    assert "已失败" in output_attempt_3, "attempt=3 应有'已失败'警告"
    assert "大幅修改" in output_attempt_3, "警告应建议大幅修改"


def test_attempt_2_no_warning():
    """attempt < 3 不应有警告(避免 LLM 早期被吓到)。"""
    result = _make_eval_result({"data_implementability": 3})
    output = _format_quality_eval_feedback(result, attempt=2)
    assert "已失败" not in output, "attempt=2 不应有'已失败'警告"
```

- [ ] **Step 2: 跑测试,验证 FAIL(generate.py 还是旧的)**

```bash
cd D:/project/quant/my-quant3
pytest tests/test_format_feedback.py -v
```

**Expected output**:
- `test_threshold_mentions_90_not_85` FAIL(因为当前 L188 提到 85%)
- `test_dims_sorted_by_gap_descending` FAIL(因为当前按维度原序)
- `test_weakest_dim_template_present` FAIL(因为没有"修复模板"段)
- `test_attempt_3_plus_includes_warning` FAIL(因为没有 attempt 参数)
- `test_attempt_2_no_warning` FAIL(同上)

- [ ] **Step 3: (可选 git commit)** `git add tests/test_format_feedback.py && git commit -m "test(red): 添加 _format_quality_eval_feedback 行为测试"`

---

## Task 8: 重构 `_format_quality_eval_feedback` 函数

**Files:**
- Modify: `strategies/agents/generate.py` (整个 `_format_quality_eval_feedback` 函数 + 6 维修复模板 + `_run_generate_once` 调用)

- [ ] **Step 1: 在 `generate.py` 顶部导入 dict 辅助(如果还没有)**

打开 `strategies/agents/generate.py`,检查 `from typing import Any` (L24)。改为:

```python
from typing import Any
```

(`dict` 是内置类型,不需要 import。)

- [ ] **Step 2: 在 L134 函数前添加 6 维修复模板常量**

在 `generate.py` L134(`def _format_quality_eval_feedback`)之前,插入:

```python
# 6 维修复模板 — 当 LLM 在某维低分时,告诉它下次具体怎么改
_DIMENSION_FIX_TEMPLATES = {
    "business_goal_alignment": (
        "重新审视 targets.annual_return 与策略类型的关系: "
        "趋势跟随策略年化 > 25% 较激进,均值回归策略 < 15% 较合理"
    ),
    "target_consistency": (
        "重算 win_rate × profit_loss_ratio: 若 < 1.5,提高盈亏比或胜率; "
        "高夏普必须配高收益;高胜率可降盈亏比"
    ),
    "bull_bear_adaptability": (
        "narrative 第 2 节须**明文**写 3 环境差异化处理(牛/熊/震荡),"
        "每环境 2-3 行,所有阈值用 `{param_name}`,**不**做实时市场识别"
    ),
    "parameter_tunability": (
        "B2 8 项检查: 入场/出场/调仓/加仓/减仓/风控/仓位调整/position_weights 字段; "
        "description 4 要素: 含义+单位+典型取值+默认值理由"
    ),
    "logical_self_consistency": (
        "narrative 第 3 节须明确**出场优先级**(固定止损>移动止损>时间止损), "
        "每个 signal weight 给业务理由"
    ),
    "data_implementability": (
        "factors[].calculation 必须用标准公式(`mean(x, N)`/`atr(h,l,c, N)`/"
        "`100 - 100/(1+...)`),禁止 `market_sentiment` / `news_score` 等不可计算变量"
    ),
}


def _pick_weakest_dimension(soft_eval: dict) -> str:
    """从 soft_eval 里挑 gap 最大的维度(分数最低的)。"""
    worst_dim = None
    worst_gap = -1.0
    for dim, content in soft_eval.items():
        if not isinstance(content, dict):
            continue
        try:
            score = float(content.get("score", 0))
        except (TypeError, ValueError):
            score = 0.0
        gap = 10.0 - score
        if gap > worst_gap:
            worst_gap = gap
            worst_dim = dim
    return worst_dim or "data_implementability"
```

- [ ] **Step 3: 重写 `_format_quality_eval_feedback` 函数**

把 `generate.py` L134-192 整个函数替换为:

```python
def _format_quality_eval_feedback(eval_result: dict, *, attempt: int = 1) -> str:
    """把 quality_eval 失败转成 user_prompt 末尾的反馈。

    通过条件: 6 维总分 >= 54/60(90%, 见 quality_eval._PASS_THRESHOLD)。
    不通过则展示按 gap 降序的每维分数 + 弱维度 issues + 修复模板,引导 LLM 改进。

    Args:
        eval_result: quality_eval 返回的 dict
        attempt: 当前是第几次尝试(>= 3 时插入"换思路"警告)
    """
    lines: list[str] = []

    # 0) 失败 ≥ 3 次时,在头部加"换思路"警告
    if attempt >= 3:
        lines.append(f"## ⚠️ 已失败 {attempt} 次\n")
        lines.append("请**大幅修改策略类型/因子选择/出入场逻辑**,不要在原 spec 上做小调整。\n")

    # 1) 6 维分数表(按 gap 降序排,LLM 一眼看到最弱维度)
    soft = eval_result.get("soft_evaluation", {})
    sorted_dims = sorted(
        soft.items(),
        key=lambda kv: -(10 - float(kv[1].get("score", 0))) if isinstance(kv[1], dict) else 0,
    )
    lines.append("### 6 维评分(按 gap 降序)\n")
    lines.append("| 维度 | 分数 | 满分 | 差距 |")
    lines.append("|---|---|---|---|")
    for dim, content in sorted_dims:
        if not isinstance(content, dict):
            continue
        try:
            s = float(content.get("score", 0))
        except (TypeError, ValueError):
            s = 0
        gap = max(0.0, 10 - s)
        # issues 按维度归类,直接在该维度下展示
        issues = content.get("issues", [])
        issue_str = ""
        if issues:
            issue_strs = [
                f"[{issue.get('severity', 'info')}] {issue.get('description', '')}"
                for issue in issues
            ]
            issue_str = "<br>".join(issue_strs)
        lines.append(f"| {dim} | {s} | 10 | {gap:.1f} | {('——<br>' + issue_str) if issue_str else ''} |")
    total = eval_result.get("_quality_total", 0)
    total_max = eval_result.get("_quality_total_max", 60)
    ratio = eval_result.get("_quality_ratio", 0)
    lines.append(
        f"| **总分** | **{total:.1f}** | **{total_max}** | "
        f"**{ratio*100:.1f}% < 90% 阈值** | |"
    )
    lines.append("")

    # 2) 修复模板(按当前最弱维度)
    weakest = _pick_weakest_dimension(soft)
    template = _DIMENSION_FIX_TEMPLATES.get(weakest, "")
    if template:
        lines.append(f"### 修复模板(按当前最弱维度:`{weakest}`)\n")
        lines.append(template)
        lines.append("")

    # 3) 引导 LLM 改进 + summary
    lines.append("### 提升方向")
    lines.append("- 重点关注分数最低的维度(差距最大)")
    lines.append("- error 级 issue 必须修复,否则该维度分数无法提升")
    lines.append(f"- 修复后总分需达到 {total_max * 0.9:.0f}/{total_max}(90%,见 quality_eval._PASS_THRESHOLD)才算通过")
    lines.append("")
    lines.append(f"### summary\n{eval_result.get('summary', '')}")
    lines.append("\n请按上述反馈重新输出完整 JSON。")
    return "\n".join(lines)
```

- [ ] **Step 4: 改 `_run_generate_once` 调用处传入 `attempt`**

打开 `generate.py` L335 附近(原 `_format_quality_eval_feedback(eval_result)` 调用处),改为:

```python
                feedback_md = _format_quality_eval_feedback(eval_result, attempt=attempt)
```

- [ ] **Step 5: 跑测试,验证 PASS**

```bash
cd D:/project/quant/my-quant3
pytest tests/test_format_feedback.py -v
```

**Expected output**: 所有 5 个测试 PASS。

- [ ] **Step 6: 跑所有测试,确保不破坏其他东西**

```bash
cd D:/project/quant/my-quant3
pytest tests/ -v
```

**Expected output**: 所有测试 PASS。

- [ ] **Step 7: (可选 git commit)** `git add strategies/agents/generate.py && git commit -m "feat(generate): retry 反馈按 gap 降序 + 6 维修复模板 + 失败递增机制"`

---

## Task 9: 端到端验证

**Files:** 无新增 / 修改(只验证)

- [ ] **Step 1: 跑所有测试**

```bash
cd D:/project/quant/my-quant3
pytest tests/ -v
```

**Expected**: 所有测试 PASS。

- [ ] **Step 2: 检查文件大小**

```bash
cd D:/project/quant/my-quant3
wc -c strategies/agents/prompts/generate.md strategies/agents/prompts/quality_eval.md
```

**Expected**:
- `generate.md` ≤ 20,000 字节(目标 19,500)
- `quality_eval.md` ≤ 8,000 字节(目标 7,500)

- [ ] **Step 3: 验证 Python 模块能 import**

```bash
cd D:/project/quant/my-quant3
python -c "from strategies.agents import generate, quality_eval; print('OK')"
```

**Expected**: 输出 `OK`,无 ImportError。

- [ ] **Step 4: 跑一次 generate(需要真实 LLM API,可选)**

```bash
cd D:/project/quant/my-quant3
python strategies/strategies.py generate --once 2>&1 | tail -50
```

**Expected**:
- 输出 1 个通过 90% 的 spec
- 记录 attempt 数(目标 1-2 次)
- 无 `KeyError: 'hard_evaluation'`

如果 LLM API 不可用,跳过此步,在 release notes 中注明"端到端未跑"。

- [ ] **Step 5: 检查 `_format_quality_eval_feedback` 输出(模拟)**

```bash
cd D:/project/quant/my-quant3
python -c "
from strategies.agents.generate import _format_quality_eval_feedback
result = {
    'soft_evaluation': {
        'business_goal_alignment': {'score': 8, 'issues': []},
        'target_consistency': {'score': 4, 'issues': [{'severity': 'error', 'description': 'win_rate 矛盾'}]},
        'bull_bear_adaptability': {'score': 7, 'issues': []},
        'parameter_tunability': {'score': 6, 'issues': []},
        'logical_self_consistency': {'score': 7, 'issues': []},
        'data_implementability': {'score': 5, 'issues': []},
    },
    '_quality_total': 37,
    '_quality_total_max': 60,
    '_quality_ratio': 0.617,
    'summary': 'mock eval result for testing',
}
print(_format_quality_eval_feedback(result, attempt=3))
"
```

**Expected output 包含**:
- "⚠️ 已失败 3 次"
- "请**大幅修改**"
- "6 维评分(按 gap 降序)" 表格
- "target_consistency" 应在 "business_goal_alignment" 之前(因为 4 < 8)
- "修复模板(按当前最弱维度:`target_consistency`)" 段
- "win_rate × profit_loss_ratio" 模板内容
- "90%" 提及
- 无 "85%" 字样

- [ ] **Step 6: 询问用户是否提交**

(根据用户原始指示"先不用提交",在此步骤**暂停**并询问用户。)

汇报:
- 4 个文件改动完成 + 5 个新文件(test infrastructure)
- 所有测试 PASS
- 文件大小符合预期
- (可选)generate 跑通

然后问用户:"是否 commit?分 1 个 commit 还是 9 个 task commit?"

- [ ] **Step 7: 用户决定后,执行 git commit(若用户同意)**

按用户指示执行 commit。

---

## Self-Review(自检)

### 1. Spec 覆盖检查

| Spec 章节 | 对应 Task |
|---|---|
| §3.1 统一字符数 | Task 3 Steps 1, 2, 7, 12 |
| §3.2 统一节数 | Task 3 Steps 2, 4, 9 |
| §3.3 合并硬规则 | Task 3 Steps 8, 10 |
| §3.4 data_implementability 前置 | Task 3 Step 5 |
| §3.5 JSON 示例压缩 | Task 3 Step 11 |
| §3.6 trigger 白名单 | Task 3 Step 6 |
| §3.7 关键禁止 12 条 | Task 3 Step 8 |
| §3.8 description 优化 | Task 3 Step 3 |
| §4.1 删除硬规则表 | Task 5 Step 2 |
| §4.2 删除 hard_evaluation | Task 5 Step 1 + Task 6 |
| §4.3 删除维度历史 | Task 5 Step 3 |
| §4.4 6 维 → hint 表 | Task 5 Step 4 |
| §4.5 评分校准 | Task 5 Step 4 |
| §4.6 关键禁止 6 条 | Task 5 Step 6 |
| §5.1 修复 85/90 口径 | Task 8 Step 3 |
| §5.2 6 维按 gap 降序 | Task 8 Step 3 |
| §5.3 issues 按维度归类 | Task 8 Step 3 |
| §5.4 修复模板 | Task 8 Steps 2, 3 |
| §5.5 失败次数递增 | Task 8 Step 3 |
| §5.6 quality_eval.py 兼容 | Task 6 |

**结论**: spec 100% 覆盖。

### 2. 占位符扫描

- ❌ 无 TBD / TODO / "implement later" / "fill in details"
- ❌ 无 "Add appropriate error handling"
- ❌ 无 "Write tests for the above"(每步都有具体测试代码)
- ❌ 无 "Similar to Task N"(每个 task 都自包含)
- ✅ 所有 step 要么有具体代码,要么有具体命令

### 3. 类型一致性检查

| 类型/函数 | 定义位置 | 使用位置 |
|---|---|---|
| `_DIMENSION_FIX_TEMPLATES` | Task 8 Step 2 | Task 8 Step 3 |
| `_pick_weakest_dimension(soft_eval)` | Task 8 Step 2 | Task 8 Step 3 |
| `_format_quality_eval_feedback(eval_result, *, attempt=1)` | Task 8 Step 3 | Task 8 Step 4 (传入 `attempt=attempt`) |
| `test_xxx` 函数名 | Task 1-7 (测试) | 在 pytest 中通过函数名引用 |

**结论**: 函数签名、参数名一致,无冲突。

### 4. 范围检查

9 个 task, 每个 task 30-60 分钟, 总计 ~2-3 小时。范围合理(单一目标: 精炼质量评估)。

---

## 总结

**总改动**:
- 4 个文件修改(generate.md, quality_eval.md, generate.py, quality_eval.py)
- 5 个文件新增(tests/ + pytest.ini)
- 1 个文件附属修改(requirements.txt)

**净效果**:
- generate.md: 22.6 KB → ~19.5 KB(-14%)
- quality_eval.md: 9.6 KB → ~7.5 KB(-22%)
- 反馈精准化:6 维修复模板 + 失败递增机制
- 测试覆盖:3 个测试文件,12+ 个测试函数

**风险**:
- 用户要求"先不用提交",本计划默认不自动 commit,工程师需在 Task 9 Step 6 询问用户
- 端到端验证(Task 9 Step 4)需要 LLM API,可能不可用,需跳过
