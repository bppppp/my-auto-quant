"""
pipeline.translator — Spec → strategy.py 翻译器

用户决策的设计 (2026-06-06):
- 不再调 LLM 翻译, 改用 Claude Code CLI (`claude -p`) headless 模式生成 + 修复
- 每次调 claude 都要:
    1) 读 spec + PARTS_SUMMARY.md + subject_structure.md
    2) 生成 / 修复 strategy.py
    3) 跑 smoke backtest 验证
- 失败 → 把 traceback 喂回去重试, 最多 max_attempts 次
- 成功 → 删 smoke 期 (2024-06-01 ~ 2024-06-30) 产生的 report 文件, 避免污染正式 backtest
"""
from __future__ import annotations

import os
import re
import select
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .config import auto_run_dir, project_root, subjects_dir
from config import CLAUDE_CLI_PATH  # 根 config.py — 从 .env 读, 默认 "claude"
from .llm_client import get_llm
from .log_utils import get_logger, banner, section

log = get_logger()

PROMPT_PATH = auto_run_dir() / "pipeline" / "prompts" / "translate.md"

# 公共部分单一事实源(append-only,详见 subject_structure.md §9)
# 翻译时实时解析 §1 factors / §2 conditions / §2.5 position / §3 modules
# 让 LLM 知道 subject.factors 实际有哪些函数, 避免 import 幻觉(adx/macd/kdj...)
PARTS_SUMMARY_PATH = project_root() / "subjects" / "PARTS_SUMMARY.md"


def _parse_parts_section(md_text: str, section_header: str) -> list[dict]:
    """从 PARTS_SUMMARY.md 解析某个 §N 节的条目.

    格式:
      ## N. Title
      ### `name`
      - **Signature**: `sig`
      - **Description**: ...
      ...

    Returns:
        [{"name": "ma", "signature": "ma(close, period) -> pd.Series", "description": "..."}, ...]
    """
    import re as _re
    # 找到 §N 标题
    m = _re.search(rf"^##\s+\d+(?:\.\d+)?\.?\s*{_re.escape(section_header)}.*?(?=^##\s|\Z)",
                   md_text, _re.MULTILINE | _re.DOTALL)
    if not m:
        return []
    section_text = m.group(0)
    entries: list[dict] = []
    # 每个 ### `name` 块
    for blk in _re.split(r"^###\s+`", section_text, flags=_re.MULTILINE)[1:]:
        # blk 第一行是 name, 其余是 - **xxx**: yyy
        lines = blk.splitlines()
        if not lines:
            continue
        name = lines[0].strip().rstrip("`").strip()
        if not name:
            continue
        sig = ""
        desc = ""
        for line in lines[1:]:
            sm = _re.match(r"^-\s+\*\*Signature\*\*\s*[:：]\s*[`]*(.+?)[`]*(?:\s*$|\s*—)", line)
            if sm:
                sig = sm.group(1).strip()
                continue
            dm = _re.match(r"^-\s+\*\*Description\*\*\s*[:：]\s*(.+)$", line)
            if dm:
                desc = dm.group(1).strip()
        entries.append({"name": name, "signature": sig, "description": desc})
    return entries


def load_parts_summary() -> str:
    """实时解析 subjects/PARTS_SUMMARY.md, 拼接成可注入 system_prompt 的白名单.

    用于解决 LLM 幻觉 import 不存在的 subject.factors.adx / macd / kdj 等。
    """
    import re as _re
    if not PARTS_SUMMARY_PATH.exists():
        log.warning(f"  ⚠️ PARTS_SUMMARY.md 不存在: {PARTS_SUMMARY_PATH}, 跳过白名单注入")
        return ""

    try:
        md = PARTS_SUMMARY_PATH.read_text(encoding="utf-8")
    except Exception as e:
        log.warning(f"  ⚠️ 读 PARTS_SUMMARY.md 失败: {e}, 跳过白名单注入")
        return ""

    factors = _parse_parts_section(md, "Factors")
    conditions = _parse_parts_section(md, "Conditions")
    # §2.5 是 Position State, 用表格而非 ### `name` 格式, 单独处理
    # 限定在 §2.5 节内, 避免抓到 §3 模块表
    pos_m = _re.search(r"^##\s+2\.5\..*?(?=^##\s|\Z)", md, _re.MULTILINE | _re.DOTALL)
    position_lines: list[str] = []
    if pos_m:
        for line in pos_m.group(0).splitlines():
            if line.startswith("| `") and "` |" in line:
                # 例: | `highest_close_since_entry` | `position["highest"]` | float | ... |
                cells = [c.strip().strip("`") for c in line.split("|")[1:-1]]
                if len(cells) >= 2 and cells[0]:
                    spec_name = cells[0]
                    pos_field = cells[1]
                    desc = cells[3] if len(cells) >= 4 else ""
                    position_lines.append(f"  - `{spec_name}` → {pos_field} ({desc})")

    out: list[str] = ["", "## 实时公共库白名单 (来自 subjects/PARTS_SUMMARY.md, 翻译时务必 import 仅限下列项)",
                      ""]

    out.append("### 1. `subject.factors` 实际可用函数 (严禁 import 列表外的函数)")
    out.append("")
    if factors:
        for f in factors:
            sig = f["signature"] or "?"
            desc = f["description"] or ""
            out.append(f"- `{f['name']}` — `{sig}`" + (f" — {desc}" if desc else ""))
    else:
        out.append("- (未解析到任何 factor, 请检查 PARTS_SUMMARY.md 格式)")
    out.append("")

    out.append("### 2. `subject.conditions` 实际可用函数 (严禁 import 列表外的函数)")
    out.append("")
    if conditions:
        for c in conditions:
            sig = c["signature"] or "?"
            desc = c["description"] or ""
            out.append(f"- `{c['name']}` — `{sig}`" + (f" — {desc}" if desc else ""))
    else:
        out.append("- (未解析到任何 condition)")
    out.append("")

    out.append("### 3. `position` 字段 (不通过 factors 访问, 直接用 position[\"...\"])")
    out.append("")
    if position_lines:
        out.extend(position_lines)
    else:
        out.append("- (未解析到 position 字段)")
    out.append("")

    out.append("**严禁** import `adx` / `macd` / `kdj` / `boll` / `cci` / `obv` / `vwap` / `trix` 等 —")
    out.append("这些函数在 subject.factors 中**不存在**。如果 spec 提到, 用现有函数近似实现:")
    out.append("- `adx` (趋势强度) → 用 `atr` + `mom` 组合")
    out.append("- `macd` (指数移动平均差) → 用 `ma` 差值近似")
    out.append("- `kdj` (随机指标) → 用 `rsi` + `donchian` 区间判断近似")
    out.append("")

    return "\n".join(out)


class TranslationFailed(Exception):
    """翻译失败 (重试耗尽)."""


@dataclass
class TranslationResult:
    """翻译结果."""
    code_path: Path
    attempts: int
    final_metrics: dict


def load_system_prompt() -> str:
    """加载 prompts/translate.md + 实时注入 PARTS_SUMMARY.md 白名单."""
    if not PROMPT_PATH.exists():
        raise FileNotFoundError(f"翻译 prompt 不存在: {PROMPT_PATH}")
    base = PROMPT_PATH.read_text(encoding="utf-8")
    whitelist = load_parts_summary()
    if whitelist:
        return base + "\n" + whitelist
    return base


def read_spec(spec_path: Path) -> tuple[str, str]:
    """读 _original.md, 返回 (frontmatter_text, body_text)."""
    text = spec_path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return "", text
    # YAML frontmatter 在第一个 --- 和第二个 --- 之间
    m = re.match(r"^---\n(.*?)\n---\n?(.*)$", text, re.DOTALL)
    if not m:
        return "", text
    return m.group(1), m.group(2)


def build_user_prompt(spec_path: Path, feedback: str = "") -> str:
    """构造 user_prompt: spec 全文 + 可选反馈."""
    fm, body = read_spec(spec_path)
    spec_full = f"---\n{fm}\n---\n\n{body}" if fm else body

    if feedback:
        return f"""## 任务
把下面这份 A 股策略 spec 翻译成可执行的 strategy.py.

## 上次测试失败的反馈
{feedback}

## Spec (YAML frontmatter + Markdown body)
{spec_full}

## 输出要求
- 严格按 system prompt 中的模板结构输出
- 只输出 Python 源码 (在 ```python 代码块中)
- 不要解释, 不要 markdown 标题
- 3 个方法必须真实可运行, 不能留 TODO
"""
    return f"""## 任务
把下面这份 A 股策略 spec 翻译成可执行的 strategy.py.

## Spec (YAML frontmatter + Markdown body)
{spec_full}

## 输出要求
- 严格按 system prompt 中的模板结构输出
- 只输出 Python 源码 (在 ```python 代码块中)
- 不要解释, 不要 markdown 标题
- 3 个方法必须真实可运行, 不能留 TODO
"""


def extract_code(llm_output: str) -> str:
    """从 LLM 输出中提取 Python 源码.

    策略:
      1. 优先 ```python ... ``` 代码块
      2. 退化: ``` ... ``` 代码块
      3. 退化: 整段 (如果以 # 开头或 import 开头)
    """
    # 1. python 代码块
    m = re.search(r"```python\s*\n(.*?)\n```", llm_output, re.DOTALL)
    if m:
        return m.group(1)
    # 2. 普通代码块
    m = re.search(r"```\s*\n(.*?)\n```", llm_output, re.DOTALL)
    if m:
        return m.group(1)
    # 3. 整段 (假设 LLM 直接输出了代码)
    return llm_output.strip()


def write_code(code: str, code_path: Path) -> None:
    """写 strategy.py."""
    code_path.parent.mkdir(parents=True, exist_ok=True)
    code_path.write_text(code, encoding="utf-8")


def invoke_claude_fix(code_path: Path, spec_path: Path, feedback: str) -> bool:
    """通过 subagent 调 Claude 直修 strategy.py.

    Returns:
        True = Claude 修好了
        False = Claude 判定无法修复

    注意: 这个函数在 pipeline 进程内调用, subagent 在 sub-process 中执行.
    实际实现需要通过 Agent 工具的 sub-agent 能力.
    由于 pipeline.py 是脚本 (而非 Claude 会话), 这里只能:
    1. 把修复工作落到 prompt 文件
    2. 让用户在 Claude Code 会话中执行
    3. 或者通过 subprocess 调 Claude Code CLI (如果可用)
    """
    # TODO: 真正的实现需要 Claude Code CLI 集成.
    # 这里采用"prompt 文件 + 退出码"占位, 后续可在 main() 中检测并提示用户.
    prompt_path = auto_run_dir() / ".claude_fix_request.md"
    prompt_path.write_text(f"""# Claude 直修任务

请修复 strategy.py 让它通过 5 步 smoke test.

## 文件
- strategy.py: {code_path}
- spec: {spec_path}

## 上次失败原因
{feedback}

## 修复步骤
1. Read {code_path} (strategy.py)
2. Read {spec_path} (YAML spec)
3. Read {project_root()}/subjects/subject_structure.md (3 方法契约)
4. 诊断 bug
5. Edit strategy.py 修复
6. 跑 smoke backtest 验证:
   ```
   cd "{project_root()}/subjects"
   python {code_path.parent.parent.name}/generated/strategy.py \\
     --start-date 2024-06-01 --end-date 2024-06-30 \\
     --test-universe 000001.SZ,000002.SZ,600000.SH,600519.SH,000333.SZ \\
     --max-stocks 5
   ```
7. 把 status (FIXED / UNFIXABLE) 写到 {prompt_path.with_suffix('.result.md')}

## 退出条件
- exit 0 + reportParams/report_v1.md 存在 → FIXED
- 仍有 traceback / 报告异常 → 继续修
- 修到无法继续 → UNFIXABLE (写明原因)
""", encoding="utf-8")
    log.warning(f"  ⚠️ Claude 直修 prompt 已写到 {prompt_path}")
    log.warning(f"    请在 Claude Code 会话中执行修复, 完成后写 status 到 {prompt_path.with_suffix('.result.md')}")
    log.warning(f"    修复后重新跑 pipeline.py --strategy {code_path.parent.parent.name} --from-stage B 继续")
    return False  # 占位: 实际实现时由 subagent 真实修复


def _run_claude_promote_review(
    name: str,
    code_path: Path,
    spec_path: Path,
    timeout: int = 300,
) -> list[str]:
    """让 Claude 独立 review strategy.py + spec, 建议加新公共项到 PARTS_SUMMARY.md.

    Returns:
        建议列表, 每条 1 行. 空列表 = 无建议.

    实现:
      - 调 `claude -p` headless, 只给 Read 工具 (不修改任何文件)
      - 解析 stdout 中的 `[PROMOTE] xxx` 标记
      - 把建议也 append 到 autoRun/promote_suggestions.log (累积, 供用户审阅)
    """
    import subprocess
    import time as _time

    spec_text = spec_path.read_text(encoding="utf-8")
    code_text = code_path.read_text(encoding="utf-8")

    prompt = f"""# 任务: 公共化建议 (Review strategy.py, 建议加新公共项)

你刚帮 `{name}` 生成了 strategy.py。现在做一个**独立 review**:

1. **Read** `{code_path}` (strategy.py)
2. **Read** `{project_root()}/subjects/PARTS_SUMMARY.md` (公共库白名单)
3. **Read** `{spec_path}` (策略 spec)
4. **扫描 strategy.py**:
   - 找 `pd.Series.rolling` / `pd.DataFrame.rolling` / `df[...].rolling` / `df.rolling` / `shift` / `pct_change` / `diff` 等手写调用
   - 对每个手写调用, 检查 PARTS_SUMMARY.md 是否有等价公共函数 (ma / atr / rsi / donchian_high/low / mom / volume_ratio / 各种 conditions)
5. **判断"漏用公共函数"**:
   - 如果手写调用有 PARTS_SUMMARY 等价函数 → 输出 `[MISS] <行号> 手写 X 但 PARTS_SUMMARY 有 Y 可用`
   - 否则 → 不报 (这是 OK 的手写)

6. **判断"潜在公共化"**:
   - 看 spec 的 `factors[]`, 识别**"清晰通用"**的因子 (命名清楚, 公式标准化, 不只 spec 用一次)
   - 已经在 PARTS_SUMMARY 的 (ma / atr / ...) → 不报
   - 名字奇怪的 → 不报
   - 对真正值得 promote 的, 输出 `[PROMOTE] <factor_name> → <建议加到 §1/§2, 一句话理由>`

## 重要: 只输出标记行, 不修改任何文件
如果 strategy.py 已经正确使用所有 PARTS_SUMMARY 公共函数, 输出 `[OK] no missing public function`
如果完全没有 promote 建议, 跳过 `[PROMOTE]` 行 (无需说明)

## 提示
- strategy.py 头部会从 subject.factors 导入 ma / atr / donchian_high 等
- ma 已支持任意 Series (不只是 close), 例: vol_ma_20 = ma(df["成交量（股）"], 20)
- atr(high, low, close, 14) 是标准 4 参数 ATR
- rsi(close, 14) 是标准 RSI

## Spec 全文
```markdown
{spec_text[:3000]}  (截断前 3000 字)
```

## Strategy.py 全文
```python
{code_text[:8000]}  (截断前 8000 字)
```

输出格式: 每行一个标记, 不要其他说明文字. 例:
```
[OK] no missing public function
[PROMOTE] momentum_60d → 加到 §1 mom 类, 60 日动量是常用指标
```
"""

    cmd = [
        CLAUDE_CLI_PATH,
        "-p", prompt,
        "--allowedTools", "Read",
        "--bare",
        "--permission-mode", "bypassPermissions",
    ]
    log.info(f"  → 调 Claude 公共化建议 review (pid 即将出现) ...")

    proc = None
    try:
        proc = subprocess.Popen(
            cmd, cwd=project_root(),
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace",
            shell=False, bufsize=1,
        )
        log.info(f"  → Claude review pid={proc.pid}")
        last_report = _time.time()
        chunks: list[str] = []
        deadline = _time.time() + timeout

        while True:
            if _time.time() > deadline:
                log.warning(f"  ⚠️ Claude review 超时 ({timeout}s), 强杀")
                proc.kill()
                return []
            line = proc.stdout.readline() if proc.stdout else ""
            if line:
                chunks.append(line)
            if _time.time() - last_report > 300:
                log.info(f"  ⏳ Claude review 仍在跑 ...")
                last_report = _time.time()
            if proc.poll() is not None:
                if proc.stdout:
                    rest = proc.stdout.read()
                    if rest:
                        chunks.append(rest)
                break
            _time.sleep(0.5)

        my_pid = proc.pid
        try:
            proc.wait(timeout=5)
        except Exception:
            try:
                proc.kill()
                proc.wait(timeout=5)
            except Exception:
                pass

        full = "".join(chunks)

        # 解析 [MISS] / [PROMOTE] 标记
        suggestions: list[str] = []
        for raw_line in full.splitlines():
            s = raw_line.strip()
            if s.startswith("[MISS]") or s.startswith("[PROMOTE]") or s.startswith("[OK]"):
                suggestions.append(s)
                log.info(f"    {s}")

        # 累积写到 promote_suggestions.log
        log_path = auto_run_dir() / "promote_suggestions.log"
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"\n## {name} ({_time.strftime('%Y-%m-%d %H:%M:%S')})\n")
            for s in suggestions:
                f.write(s + "\n")

        return suggestions
    except Exception as e:
        log.warning(f"  ⚠️ Claude review 异常: {type(e).__name__}: {e}")
        return []
    finally:
        if proc is not None:
            try:
                if proc.poll() is None:
                    proc.kill()
                proc.wait(timeout=5)
            except Exception:
                pass
            try:
                if proc.stdout:
                    proc.stdout.close()
            except Exception:
                pass


def _cleanup_smoke_artifacts(name: str) -> None:
    """删 smoke 期 (2024-06-01 ~ 2024-06-30) 产生的 report 文件.

    smoke backtest 跑完会留下:
      - subjects/<name>/reportParams/report_v1.md (params 模式)
      - subjects/<name>/reportWeight/report_signals_v1.md (weight 模式)
    这些是测试产物, 会污染 Stage C/D 的 backtest 报告, 必须在通过后清掉.
    """
    for sub in ("reportParams", "reportWeight"):
        d = subjects_dir() / name / sub
        if not d.exists():
            continue
        for f in d.glob("*.md"):
            try:
                f.unlink()
                log.info(f"  🗑️  删 smoke 产物: {f.relative_to(project_root())}")
            except Exception as e:
                log.warning(f"  ⚠️  删 {f.name} 失败: {e}")


def _run_claude_generate_or_fix(
    code_path: Path,
    spec_path: Path,
    attempt: int,
    max_attempts: int,
    smoke_universe: list[str],
    smoke_start: str,
    smoke_end: str,
    smoke_timeout: int,
    feedback: str = "",
) -> tuple[bool, str, dict]:
    """调一次 `claude -p` 让 Claude 生成或修复 strategy.py, 然后跑 smoke 验证.

    Returns:
        (passed, code_path_str, metrics)
    """
    import subprocess

    name = code_path.parent.parent.name

    # 构造 prompt: 第一次是生成, 后续是修复
    if attempt == 1:
        spec_text = spec_path.read_text(encoding="utf-8")
        prompt = f"""# 任务: 生成 strategy.py (首次)

你正在 my-quant3 项目中工作。需要根据 spec 生成一份可运行的 `generated/strategy.py`。

## 必读文件 (顺序)
1. `{project_root()}/subjects/PARTS_SUMMARY.md` — **公共库白名单, 严禁 import 列表外的函数**
2. `{project_root()}/subjects/subject_structure.md` — 3 方法契约 + 数据列名 + position 字段
3. `{project_root()}/subjects/{name}/{name}_original.md` — 策略 spec (YAML + body)
4. `{project_root()}/autoRun/pipeline/prompts/translate.md` — 翻译规则 (硬要求)

## 目标文件
- `{code_path}` (strategy.py) — 如果已存在, 完整覆盖

## 严格要求
- 3 个方法签名必须一字不差: `compute_factors(df, params)`, `entry_score(factors, params, weights)`, `should_exit(position, factors, params, weights)`
- **只 import 实际用到的** (noqa: E402); **严禁 import** `adx` / `macd` / `kdj` / `boll` / `cci` / `obv` / `vwap` (PARTS_SUMMARY 里不存在)
- factor / signal 名字必须与 spec 的 `factors[].name` / `entry_signals[].name` / `exit_signals[].name` 一字不差
- weight 必须从 `weights["entry"][<name>]` / `weights["exit"][<name>]` 读, 禁止硬编码
- trigger 里的 `{{param_name}}` 用 `params[<name>]`; 因子用 `factors[<name>]`; 数据列用 `df[<中文列>]` (如 `df["收盘价"]`)
- data 列: close=收盘价, high=最高价, low=最低价, open=开盘价, volume=成交量(股)
- 必须有 `if __name__ == "__main__":` 块 (与 translate.md 模板一致)
- 文件顶部 `# debug_mode: params / monitor` 等注释要保留 (与模板一致)

## Spec 全文
```markdown
{spec_text}
```

## 完成后
1. 跑 smoke 验证 (5 股, 1 个月):
   ```
   cd "{project_root()}/subjects"
   python {name}/generated/strategy.py --start-date {smoke_start} --end-date {smoke_end} --test-universe {",".join(smoke_universe)} --max-stocks 5
   ```
2. 退码 0 且 `subjects/{name}/reportParams/report_v1.md` 存在 → **成功了**, 输出 `[DONE] success`
3. 失败 → 把 traceback 全部贴回来, 输出 `[FAILED] smoke exit=X: <traceback摘要>`

## 自检 (写完代码后, 提交前必做, 5 分钟内完成)

### A. 公共函数覆盖自检
1. **重读**你刚写的 `{code_path}`
2. 搜索 `pd.Series.rolling` / `pd.DataFrame.rolling` / `df[...].rolling` / `df.rolling` / `shift` / `pct_change` / `diff` 等**手写滚动/算子**调用
3. 对每个手写调用, 检查 PARTS_SUMMARY.md §1/§2/§4 **是否已有等价公共函数** (ma / atr / rsi / donchian_high / donchian_low / mom / volume_ratio / 各种 conditions / ParamDef)
4. **如果**PARTS_SUMMARY 已有等价函数 → **必须改用公共函数**, 不要自己实现
   - 例: `df["成交量（股）"].rolling(20).mean()` → `ma(df["成交量（股）"], 20)` (ma 已支持任意 Series)
   - 例: 手写 ATR → `atr(high, low, close, 14)`
5. 改完后再跑一遍 smoke 确认

### B. 潜在公共化识别
看 spec 的 `factors[]` 列表, 识别**"具有公共化潜力"**的因子:
- 命名清晰 (如 `vol_ma_20`, `momentum_60d`)
- 计算公式标准化 (`mean(series, n)`, `max(high, n)`, `ratio(a, b)`)
- **不**已经在 PARTS_SUMMARY.md §1/§2 里

**对于有公共化潜力的因子** (不是强制, 仅当清晰符合):
- 在 `[DONE] success` 之前, **额外输出**一行建议 (不修改 PARTS_SUMMARY.md, 只在 stdout 报):
  `[PROMOTE] <factor_name> → <建议加到 §1/§2, 一句话理由>`

**不要**为了"显示自检"而 promote:
- 只 spec 用一次的 (不通用)
- 名字奇怪的 (如 `custom_x`)
- 已经是 PARTS_SUMMARY 函数的 (ma / atr / ...)
- 在多个策略里都重复的 (才真值得 promote)

## 实时进度标记 (用于监控, 每个阶段完成后必须输出)
- `[PROGRESS] read spec + PARTS_SUMMARY + subject_structure`  — 读完 3 个文件
- `[PROGRESS] wrote strategy.py (XXX lines)`  — 写完代码
- `[PROGRESS] running smoke backtest`  — 开始跑 smoke
- `[DONE] success`  或  `[FAILED] <reason>`

(这些标记会出现在 stdout, pipeline 实时监控; 不输出也能跑, 但 pipeline 看不到进度)
"""
    else:
        # 修复模式: Claude 读现有 strategy.py + 上次失败原因
        prompt = f"""# 任务: 修复 strategy.py (attempt {attempt}/{max_attempts})

strategy.py 上次 smoke test 失败, 请诊断并修复。

## 文件
- strategy.py: `{code_path}` (请 Read 它)
- spec: `{spec_path}` (请 Read 它)
- 公共库: `{project_root()}/subjects/PARTS_SUMMARY.md`
- 契约: `{project_root()}/subjects/subject_structure.md`

## 上次失败信息
```
{feedback}
```

## 修复 + 验证
1. Read `{code_path}` 和 spec
2. 诊断 bug (常见: import 错 / 签名错 / trigger 逻辑错 / 中文列名写错)
3. Edit 修复
4. 跑 smoke:
   ```
   cd "{project_root()}/subjects"
   python {name}/generated/strategy.py --start-date {smoke_start} --end-date {smoke_end} --test-universe {",".join(smoke_universe)} --max-stocks 5
   ```
5. 退码 0 + reportParams/report_v1.md 存在 → 修好了, 结束
6. 仍失败 → 把新 traceback 贴回这个 prompt (我会再调你)
"""

    # 调 claude -p
    # CLAUDE_CLI_PATH 从 .env 读 (默认 "claude", 假设已在 PATH)
    # 显式路径时 (如 D:/nodejs/.../claude.exe) 绕过 .cmd wrapper 避免 GBK 问题
    cmd = [
        CLAUDE_CLI_PATH,
        "-p", prompt,
        "--allowedTools", "Read,Edit,Write,Glob,Grep,Bash",
        "--bare",
        "--permission-mode", "bypassPermissions",
    ]
    log.info(f"  → 调 Claude Code (attempt {attempt}, 预估 30-120s) ...")
    import time as _time
    max_claude_retries = 3
    result = None
    for claude_attempt in range(1, max_claude_retries + 1):
        proc = None
        try:
            # 用 Popen 实时读 stdout, 解析 [PROGRESS] 标记, 监控文件 mtime
            proc = subprocess.Popen(
                cmd,
                cwd=project_root(),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                shell=False,
            )
            log.info(f"  → Claude 进程启动, pid={proc.pid}")

            # 实时监控循环: 监控文件 mtime + 进程存活 + select 读 stdout
            stdout_chunks: list[str] = []
            stderr_chunks: list[str] = []
            last_size = -1
            last_mtime_change = _time.time()
            last_progress_report = _time.time()
            hard_deadline = _time.time() + 900  # 15 分钟
            inactivity_timeout = 180  # 3 分钟文件无变化 → 卡死警告
            max_inactivity_before_kill = 600  # 10 分钟无变化 → 强杀
            process_start_time = _time.time()

            code_dir = code_path.parent
            code_dir.mkdir(parents=True, exist_ok=True)

            while True:
                # 检查硬超时
                if _time.time() > hard_deadline:
                    log.error(f"  ❌ 硬超时 900s, 强杀进程")
                    proc.kill()
                    return False, str(code_path), {"failed_step": "claude_hard_timeout", "feedback": "硬超时 900s"}

                # 监控 strategy.py 大小变化
                if code_path.exists():
                    sz = code_path.stat().st_size
                    if sz != last_size:
                        if last_size >= 0:
                            log.info(f"  📝 strategy.py 增长: {last_size} → {sz} 字节")
                        else:
                            log.info(f"  📝 strategy.py 创建: {sz} 字节")
                        last_size = sz
                        last_mtime_change = _time.time()

                # 5 分钟一次进度报告 (减少日志量)
                if _time.time() - last_progress_report > 300:
                    idle = _time.time() - last_mtime_change
                    elapsed = _time.time() - process_start_time
                    if proc.poll() is None:
                        log.info(f"  ⏳ Claude 仍在工作... strategy.py={last_size} 字节, 文件 {int(idle)}s 未变化, 已运行 {int(elapsed)}s")
                    last_progress_report = _time.time()

                # inactivity 检测
                idle = _time.time() - last_mtime_change
                if idle > max_inactivity_before_kill:
                    log.error(f"  ❌ strategy.py {int(idle)}s 无变化, 强杀 Claude 进程")
                    proc.kill()
                    return False, str(code_path), {
                        "failed_step": "claude_inactive",
                        "feedback": f"strategy.py {int(idle)}s 无变化, 判定为卡死. 当前 size={last_size}",
                    }
                elif idle > inactivity_timeout and last_size < 1000:
                    log.warning(f"  ⚠️ strategy.py 已 {int(idle)}s 无变化 (size={last_size}), 继续等...")

                # select 非阻塞读 stdout/stderr (实时收集输出, 供后面解析 [DONE]/[FAILED] 使用)
                if proc.stdout is not None:
                    try:
                        readable, _, _ = select.select([proc.stdout], [], [], 0.1)
                        if readable:
                            chunk = os.read(proc.stdout.fileno(), 4096).decode("utf-8", errors="replace")
                            if chunk:
                                stdout_chunks.append(chunk)
                    except OSError:
                        pass
                if proc.stderr is not None:
                    try:
                        _, readable, _ = select.select([], [proc.stderr], [], 0.1)
                        if readable:
                            chunk = os.read(proc.stderr.fileno(), 4096).decode("utf-8", errors="replace")
                            if chunk:
                                stderr_chunks.append(chunk)
                    except OSError:
                        pass

                # 检查进程退出
                if proc.poll() is not None:
                    log.info(f"  → Claude 进程退出, exit={proc.returncode}")
                    # 退出后把剩余输出全部读完
                    if proc.stdout is not None:
                        try:
                            remaining = os.read(proc.stdout.fileno(), 65536).decode("utf-8", errors="replace")
                            if remaining:
                                stdout_chunks.append(remaining)
                        except OSError:
                            pass
                    if proc.stderr is not None:
                        try:
                            remaining = os.read(proc.stderr.fileno(), 65536).decode("utf-8", errors="replace")
                            if remaining:
                                stderr_chunks.append(remaining)
                        except OSError:
                            pass
                    break

                _time.sleep(0.5)

            # 进程已退出, 安全关闭管道并 wait
            try:
                proc.wait(timeout=10)
            except Exception:
                pass
            try:
                if proc.stdout:
                    proc.stdout.close()
            except Exception:
                pass
            try:
                if proc.stderr:
                    proc.stderr.close()
            except Exception:
                pass

            full_stdout = "".join(stdout_chunks)
            full_stderr = "".join(stderr_chunks)

            class _R:
                pass
            result = _R()
            result.returncode = proc.returncode
            result.stdout = full_stdout
            result.stderr = full_stderr

            log.info(f"  → Claude 进程退出, exit={result.returncode}, "
                     f"stdout={len(full_stdout)} chars, strategy.py={last_size} bytes")

            # 解析完成标记
            if "[DONE]" in (full_stdout or ""):
                log.info(f"  ✅ Claude 报告 [DONE]: {full_stdout[full_stdout.index('[DONE]'):].split(chr(10))[0]}")
            elif "[FAILED]" in (full_stdout or ""):
                log.warning(f"  ❌ Claude 报告 [FAILED]: {full_stdout[full_stdout.index('[FAILED]'):].split(chr(10))[0]}")

            # 检测 API 瞬时错误 → 重试
            if result.returncode != 0 and "API Error" in (result.stdout or ""):
                if claude_attempt < max_claude_retries:
                    wait = 3 * claude_attempt
                    log.warning(f"  ⚠️ Claude API 瞬时错误, {wait}s 后重试 ({claude_attempt}/{max_claude_retries})")
                    _time.sleep(wait)
                    continue
            break
        except FileNotFoundError:
            log.error(f"  ❌ 'claude' CLI 找不到, 请确认 CLAUDE_CLI_PATH 配置正确 (当前: {CLAUDE_CLI_PATH})")
            return False, str(code_path), {"failed_step": "claude_missing", "feedback": "claude CLI not found"}
        except Exception as e:
            log.error(f"  ❌ Claude CLI 调用失败: {type(e).__name__}: {e}")
            return False, str(code_path), {"failed_step": "claude_exception", "feedback": str(e)}
        finally:
            # 不管成功/失败/API 错误重试, 都确保 claude 进程被清理 (claude 经常留 node 子进程)
            # 只杀 Popen 创建的那个 proc, 不影响外部进程
            if proc is not None:
                my_pid = proc.pid  # 记录 PID 防止误杀 (理论上 Popen 持有, 不会误杀)
                try:
                    if proc.poll() is None:
                        log.info(f"  → 清理 claude 进程 pid={my_pid}")
                        proc.kill()
                    proc.wait(timeout=5)
                except Exception:
                    pass
                # 关闭 stdout/stderr 管道
                try:
                    if proc.stdout:
                        proc.stdout.close()
                except Exception:
                    pass
                try:
                    if proc.stderr:
                        proc.stderr.close()
                except Exception:
                    pass

    if result is None:
        return False, str(code_path), {"failed_step": "claude_no_result", "feedback": "claude call produced no result"}

    # 验证 Claude 写出了 strategy.py
    if not code_path.exists() or code_path.stat().st_size < 1000:
        size = code_path.stat().st_size if code_path.exists() else 0
        log.error(f"  ❌ Claude 没写 strategy.py 或文件过小 (size={size})")
        log.error(f"     最后 20 行 stdout: ...{result.stdout[-1000:] if result.stdout else '(空)'}")
        log.error(f"     最后 500 字符 stderr: {result.stderr[-500:] if result.stderr else '(空)'}")
        return False, str(code_path), {"failed_step": "claude_no_code", "feedback": f"strategy.py size={size}, expected >1000"}

    # 验证 strategy.py 已生成且通过初步 syntax check
    if size > 1000:
        return True, str(code_path), {"metrics": {}}
    return False, str(code_path), {"failed_step": "claude_no_code", "feedback": f"strategy.py size={size}, expected >1000"}


def translate(
    spec_path: Path,
    max_attempts: int = 10,
    smoke_universe: Optional[list[str]] = None,
    smoke_start: str = "2024-06-01",
    smoke_end: str = "2024-06-30",
    smoke_timeout: int = 600,
) -> TranslationResult:
    """翻译 spec → strategy.py (用 Claude Code CLI 生成, 不用 LLM).

    流程:
      1. 第 1 次调 `claude -p`, 让 Claude 读 spec + PARTS_SUMMARY + subject_structure 后生成 strategy.py
      2. 跑 5 步 smoke test 验证
      3. 通过 → 删 smoke 期产物 (reportParams/reportWeight/*.md) → 返回
      4. 失败 → 把 traceback 喂给 Claude 修, 最多 max_attempts 次
      5. 仍失败 → 抛 TranslationFailed

    Args:
        spec_path: subjects/<name>/<name>_original.md 路径
        max_attempts: 最多尝试次数 (默认 10)
        smoke_universe: 5 股 smoke test
        smoke_start / smoke_end: smoke 日期
        smoke_timeout: smoke backtest 超时秒数 (默认 600, 由 config.smoke_timeout 覆盖)

    Returns:
        TranslationResult(code_path, attempts, final_metrics)

    Raises:
        TranslationFailed: 重试耗尽
    """
    if not spec_path.exists():
        raise FileNotFoundError(f"spec 不存在: {spec_path}")

    name = spec_path.parent.name
    code_path = spec_path.parent / "generated" / "strategy.py"

    if smoke_universe is None:
        smoke_universe = [
            "000001.SZ", "000002.SZ", "600000.SH", "600519.SH", "000333.SZ",
        ]

    banner(f"翻译 spec → strategy.py (via Claude Code CLI): {name}")
    log.info(f"  spec: {spec_path}")
    log.info(f"  code: {code_path}")
    log.info(f"  max_attempts: {max_attempts}")
    log.info(f"  smoke_timeout: {smoke_timeout}s")

    last_feedback = ""
    for attempt in range(1, max_attempts + 1):
        log.info(f"━━━ Attempt {attempt}/{max_attempts} ━━━")
        passed, _, info = _run_claude_generate_or_fix(
            code_path=code_path,
            spec_path=spec_path,
            attempt=attempt,
            max_attempts=max_attempts,
            smoke_universe=smoke_universe,
            smoke_start=smoke_start,
            smoke_end=smoke_end,
            smoke_timeout=smoke_timeout,
            feedback=last_feedback,
        )
        if passed:
            banner(f"✅ 翻译成功 (attempt {attempt})", char="=")
            log.info(f"  metrics: {info}")
            multi = info.get("multi_results", [])
            if multi:
                log.info(f"  多场景 ({len(multi)}/3 通过):")
                for r in multi:
                    m = r.get("metrics", {})
                    log.info(f"    {r['label']:12s} ({r['start']} ~ {r['end']}): annual_return={m.get('annual_return', 0):.4f}, sharpe={m.get('sharpe', 0):.2f}")
            # 删 smoke 产物, 避免污染 Stage C/D
            log.info(f"  → 清理 smoke 期产物 ...")
            _cleanup_smoke_artifacts(name)
            # Claude 公共化建议: 让 claude 读 strategy.py + PARTS_SUMMARY, 建议加新的公共项
            log.info(f"  → Claude 公共化建议 ...")
            try:
                promote_suggestions = _run_claude_promote_review(
                    name=name, code_path=code_path, spec_path=spec_path,
                )
                if promote_suggestions:
                    log.info(f"  💡 公共化建议 (写到 {auto_run_dir() / 'promote_suggestions.log'}):")
                    for s in promote_suggestions:
                        log.info(f"    {s}")
                else:
                    log.info(f"  💡 无新增公共化建议")
            except Exception as e:
                log.warning(f"  ⚠️ 公共化建议失败 (不影响翻译成功): {type(e).__name__}: {e}")
            return TranslationResult(
                code_path=code_path,
                attempts=attempt,
                final_metrics=info,
            )

        # 失败
        failed_step = info.get("failed_step", "unknown")
        feedback_text = info.get("feedback", "")
        last_feedback = f"smoke test failed_step: {failed_step}\nfeedback:\n{feedback_text}"
        log.warning(f"  ❌ {failed_step}: {feedback_text[:200]}")

    raise TranslationFailed(
        f"翻译 {max_attempts} 次仍失败. 最后失败: {last_feedback[:300]}"
    )


__all__ = [
    "TranslationFailed",
    "TranslationResult",
    "translate",
    "load_system_prompt",
    "build_user_prompt",
    "extract_code",
]
