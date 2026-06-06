"""
pipeline.translator — Spec → strategy.py 翻译器

用户确认的简化设计:
- LLM 1 次生成 strategy.py
- 失败 → Claude 直接读代码 + spec + traceback, 修复 (通过 subagent)
- 最多 10 次尝试 (1 LLM + 9 Claude 直修)
- 仍失败 → 跳过该策略

注意: Claude 直修通过 subagent (Agent 工具) 异步执行.
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .config import auto_run_dir, project_root, subjects_dir
from .llm_client import get_llm
from .log_utils import get_logger, banner, section
from .test_runner import TestResult, run as run_test

log = get_logger()

PROMPT_PATH = auto_run_dir() / "pipeline" / "prompts" / "translate.md"


class TranslationFailed(Exception):
    """翻译失败 (重试耗尽)."""


@dataclass
class TranslationResult:
    """翻译结果."""
    code_path: Path
    attempts: int
    final_metrics: dict


def load_system_prompt() -> str:
    """加载 prompts/translate.md."""
    if not PROMPT_PATH.exists():
        raise FileNotFoundError(f"翻译 prompt 不存在: {PROMPT_PATH}")
    return PROMPT_PATH.read_text(encoding="utf-8")


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
3. Read D:/project/quant/my-quant3/subjects/subject_structure.md (3 方法契约)
4. 诊断 bug
5. Edit strategy.py 修复
6. 跑 smoke backtest 验证:
   ```
   cd D:/project/quant/my-quant3/subjects
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


def translate(
    spec_path: Path,
    max_attempts: int = 10,
    smoke_universe: Optional[list[str]] = None,
    smoke_start: str = "2024-06-01",
    smoke_end: str = "2024-06-30",
    smoke_timeout: int = 600,
    on_test_fail=None,  # 回调: (attempt, code_path, test_result) -> bool (True=已修好, False=放弃)
) -> TranslationResult:
    """翻译 spec → strategy.py.

    流程:
      1. 读 spec, 构造 prompt, 调 LLM 生成
      2. 写 strategy.py
      3. 跑 5 步测试
      4. 通过 → 返回
      5. 失败 → 调 on_test_fail 回调 (默认 invoke_claude_fix, 实际修复由 Claude subagent)
      6. 最多 max_attempts 次, 仍失败抛 TranslationFailed

    Args:
        spec_path: subjects/<name>/<name>_original.md 路径
        max_attempts: 最多尝试次数 (默认 10)
        smoke_universe: 5 股 smoke test
        smoke_start / smoke_end: smoke 日期
        smoke_timeout: smoke backtest 超时秒数 (默认 600, 由 config.smoke_timeout 覆盖)
        on_test_fail: 测试失败时的回调函数
            签名: (attempt: int, code_path: Path, test_result: TestResult) -> bool
            返回 True = 已修好 (重测), False = 放弃

    Returns:
        TranslationResult(code_path, attempts, final_metrics)

    Raises:
        TranslationFailed: 重试耗尽
    """
    if on_test_fail is None:
        on_test_fail = _default_fix_handler

    if not spec_path.exists():
        raise FileNotFoundError(f"spec 不存在: {spec_path}")

    name = spec_path.parent.name
    code_path = spec_path.parent / "generated" / "strategy.py"

    if smoke_universe is None:
        smoke_universe = [
            "000001.SZ", "000002.SZ", "600000.SH", "600519.SH", "000333.SZ",
        ]

    banner(f"翻译 spec → strategy.py: {name}")
    log.info(f"  spec: {spec_path}")
    log.info(f"  code: {code_path}")
    log.info(f"  max_attempts: {max_attempts}")
    log.info(f"  smoke_timeout: {smoke_timeout}s")

    system_prompt = load_system_prompt()
    llm = get_llm(temperature=0.3, enable_thinking=True)
    last_feedback = None

    for attempt in range(1, max_attempts + 1):
        log.info(f"━━━ Attempt {attempt}/{max_attempts} ━━━")

        if attempt == 1:
            # 第 1 次: LLM 生成
            user_prompt = build_user_prompt(spec_path, feedback=last_feedback or "")
            log.info(f"  → 调 LLM 生成 strategy.py ...")
            try:
                llm_output = llm.invoke(system_prompt, user_prompt)
            except Exception as e:
                log.error(f"  LLM 调用失败: {type(e).__name__}: {e}")
                raise
            code = extract_code(llm_output)
            if not code or "TRANSLATION FAILED" in code:
                last_feedback = "LLM 未能生成有效代码"
                log.warning(f"  LLM 未生成代码, 重试")
                continue
            write_code(code, code_path)
            log.info(f"  → 已写 {code_path} ({len(code)} 字符)")

        # 跑 5 步测试
        log.info(f"  → 跑 5 步测试 ...")
        test_result = run_test(
            code_path=code_path,
            name=name,
            smoke_universe=smoke_universe,
            smoke_start=smoke_start,
            smoke_end=smoke_end,
            timeout=smoke_timeout,
        )

        if test_result.passed:
            banner(f"✅ 翻译成功 (attempt {attempt})", char="=")
            log.info(f"  metrics: {test_result.metrics}")
            return TranslationResult(
                code_path=code_path,
                attempts=attempt,
                final_metrics=test_result.metrics,
            )

        # 失败
        last_feedback = (
            f"Attempt {attempt} 测试失败: {test_result.failed_step}\n"
            f"{test_result.feedback}"
        )
        log.warning(f"  ❌ {test_result.failed_step}: {test_result.feedback[:300]}")

        if attempt < max_attempts:
            # 调回调修复
            log.info(f"  → 调修复回调 (Claude 直修) ...")
            fixed = on_test_fail(attempt, code_path, test_result)
            if not fixed:
                log.error(f"  修复回调返回 False, 放弃")
                raise TranslationFailed(
                    f"修复回调在 attempt {attempt} 放弃. 最后失败: {test_result.failed_step}"
                )
            log.info(f"  → 修复回调声称已修好, 重测")

    # 重试耗尽
    raise TranslationFailed(
        f"翻译 {max_attempts} 次仍失败. 最后失败: {last_feedback}"
    )


def _default_fix_handler(attempt: int, code_path: Path, test_result: TestResult) -> bool:
    """默认修复回调: 通过 subagent 调 Claude 直修.

    当前实现: 写 prompt 文件, 让用户手动在 Claude Code 会话中执行.
    未来可改成 subprocess 调 Claude Code CLI.
    """
    spec_path = code_path.parent.parent / f"{code_path.parent.parent.name}_original.md"
    return invoke_claude_fix(code_path, spec_path, test_result.feedback)


__all__ = [
    "TranslationFailed",
    "TranslationResult",
    "translate",
    "load_system_prompt",
    "build_user_prompt",
    "extract_code",
]
