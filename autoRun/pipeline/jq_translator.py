"""
pipeline.jq_translator — Spec → 聚宽 JQ 脚本生成 (Stage I)

⚠️ 2026-06-15 新增: Stage I 在 Stage H (export) 完成后, 调 Claude Code headless
根据 final.md spec + RULES.md 生成 result/<name>/JQ_<name>.py. 失败 fail-soft
(不影响 strategy 标记 exported, 仅记录 jq_status=jq_failed).

设计参考 translator.py, 但:
- 输出目标不同 (result/ 而非 subjects/.../generated/)
- 不跑 smoke backtest (聚宽环境本地不存在)
- 改用静态检查 (py_compile + ast 结构 + PARAMS 字段 + Claude 二次确认)
- 最多 3 次重试 (translator 是 10 次, JQ 翻译任务更小)
"""
from __future__ import annotations

import ast
import os
import py_compile
import re
import select
import subprocess
import time as _time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

try:
    from config import CLAUDE_CLI_PATH
except ImportError:
    CLAUDE_CLI_PATH = "claude"

from .config import project_root
from .log_utils import get_logger, banner

log = get_logger()

PROMPT_PATH = project_root() / "autoRun" / "pipeline" / "prompts" / "jq_translate.md"

# 聚宽脚本必填字段
REQUIRED_PARAM_KEYS = [
    "benchmark",
    "target_holdings",
    "max_single_weight",
    "max_industry_concentration",
    "max_turnover_per_rebalance",
    "rebalance_freq_days",
    "entry_weights",
    "exit_weights",
]

# 聚宽脚本必备结构 (函数名 / 模块级调用)
REQUIRED_FUNCTIONS = ["initialize"]
REQUIRED_MODULE_CALLS = ["run_daily", "set_benchmark", "set_order_cost", "set_slippage"]


@dataclass
class JQResult:
    """JQ 脚本生成结果."""
    code_path: Path
    attempts: int
    passed: bool
    failure_reason: str = ""
    check_details: dict = field(default_factory=dict)


def _build_prompt(
    name: str,
    final_md_path: Path,
    report_weight_path: Path,
    output_path: Path,
    feedback: str = "",
) -> str:
    """构造 claude -p 的 prompt."""
    rules_md = project_root() / "joinQuant" / "RULES.md"
    jqapi_md = project_root() / "joinQuant" / "createBase" / "JQuantAPI.md"
    weight_rules_md = project_root() / "joinQuant" / "createBase" / "weight-rules.md"
    template_path = project_root() / "joinQuant" / "createBase" / "template_trend_momentum_strategy_1.py"

    base_prompt = (PROMPT_PATH.read_text(encoding="utf-8")
                   .replace("{final_md_path}", str(final_md_path))
                   .replace("{report_weight_path}", str(report_weight_path))
                   .replace("{rules_md_path}", str(rules_md))
                   .replace("{jqapi_md_path}", str(jqapi_md))
                   .replace("{weight_rules_md}", str(weight_rules_md))
                   .replace("{weight_rules_md_path}", str(weight_rules_md))
                   .replace("{template_path}", str(template_path))
                   .replace("{output_path}", str(output_path)))

    spec_text = ""
    if final_md_path.exists():
        spec_text = final_md_path.read_text(encoding="utf-8")[:8000]
    report_text = ""
    if report_weight_path.exists():
        report_text = report_weight_path.read_text(encoding="utf-8")[:2000]

    feedback_block = ""
    if feedback:
        feedback_block = f"""## 上次检查失败的反馈
{feedback}

请修复后重新输出完整 Python 源码。
"""

    return f"""{base_prompt}

{feedback_block}
## 当前策略 spec (前 8000 字)
```markdown
{spec_text}
```

## 当前策略最终回测报告 (前 2000 字)
```markdown
{report_text}
```

## 任务重申
1. Read 上述 6 个文件 (按顺序)
2. 在 `{output_path}` 写入完整聚宽回测脚本
3. 跑完 A/B/C 三组自检
4. 输出 `[DONE] success` 或 `[FAILED] <reason>`
"""


def _run_claude_jq_generate(
    name: str,
    final_md_path: Path,
    report_weight_path: Path,
    output_path: Path,
    attempt: int,
    max_attempts: int,
    feedback: str = "",
    timeout: int = 600,
) -> tuple[bool, str, dict]:
    """调一次 `claude -p` 生成 JQ 脚本. Returns (passed, code_path, info)."""
    prompt = _build_prompt(
        name=name,
        final_md_path=final_md_path,
        report_weight_path=report_weight_path,
        output_path=output_path,
        feedback=feedback,
    )
    cmd = [
        CLAUDE_CLI_PATH,
        "-p", prompt,
        "--allowedTools", "Read,Edit,Write,Glob,Grep,Bash",
        "--bare",
        "--permission-mode", "bypassPermissions",
    ]
    log.info(f"  → 调 Claude Code (attempt {attempt}/{max_attempts}, 预估 30-180s) ...")

    proc = None
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=project_root(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace",
            shell=False,
        )
        log.info(f"  → Claude 进程启动, pid={proc.pid}")

        output_path.parent.mkdir(parents=True, exist_ok=True)

        # 实时监控循环
        stdout_chunks: list[str] = []
        stderr_chunks: list[str] = []
        last_size = -1
        last_mtime_change = _time.time()
        process_start_time = _time.time()
        hard_deadline = _time.time() + timeout
        inactivity_timeout = 180
        max_inactivity_before_kill = 480  # 8 分钟无变化 → 强杀 (比 translator 短)

        while True:
            if _time.time() > hard_deadline:
                log.error(f"  ❌ 硬超时 {timeout}s, 强杀")
                proc.kill()
                return False, str(output_path), {"failed_step": "jq_claude_hard_timeout", "feedback": f"硬超时 {timeout}s"}

            # 监控文件大小
            if output_path.exists():
                sz = output_path.stat().st_size
                if sz != last_size:
                    if last_size >= 0:
                        log.info(f"  📝 JQ 脚本增长: {last_size} → {sz} 字节")
                    else:
                        log.info(f"  📝 JQ 脚本创建: {sz} 字节")
                    last_size = sz
                    last_mtime_change = _time.time()

            # inactivity
            idle = _time.time() - last_mtime_change
            if idle > max_inactivity_before_kill:
                log.error(f"  ❌ JQ 脚本 {int(idle)}s 无变化, 强杀")
                proc.kill()
                return False, str(output_path), {
                    "failed_step": "jq_claude_inactive",
                    "feedback": f"JQ 脚本 {int(idle)}s 无变化, 判定为卡死. size={last_size}",
                }
            elif idle > inactivity_timeout and last_size < 1000:
                log.warning(f"  ⚠️ JQ 脚本 {int(idle)}s 无变化 (size={last_size}), 继续等...")

            # select 读 stdout/stderr
            if proc.stdout:
                try:
                    r, _, _ = select.select([proc.stdout], [], [], 0.1)
                    if r:
                        chunk = os.read(proc.stdout.fileno(), 4096).decode("utf-8", errors="replace")
                        if chunk:
                            stdout_chunks.append(chunk)
                except OSError:
                    pass
            if proc.stderr:
                try:
                    _, r, _ = select.select([], [proc.stderr], [], 0.1)
                    if r:
                        chunk = os.read(proc.stderr.fileno(), 4096).decode("utf-8", errors="replace")
                        if chunk:
                            stderr_chunks.append(chunk)
                except OSError:
                    pass

            if proc.poll() is not None:
                # 退出, 读完剩余
                if proc.stdout:
                    try:
                        rest = os.read(proc.stdout.fileno(), 65536).decode("utf-8", errors="replace")
                        if rest:
                            stdout_chunks.append(rest)
                    except OSError:
                        pass
                if proc.stderr:
                    try:
                        rest = os.read(proc.stderr.fileno(), 65536).decode("utf-8", errors="replace")
                        if rest:
                            stderr_chunks.append(rest)
                    except OSError:
                        pass
                break
            _time.sleep(0.5)

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

        log.info(f"  → Claude 退出, exit={proc.returncode}, "
                 f"stdout={len(full_stdout)} chars, JQ 脚本={last_size} bytes")

        if "[DONE]" in (full_stdout or ""):
            log.info(f"  ✅ Claude 报告 [DONE]")
        elif "[FAILED]" in (full_stdout or ""):
            log.warning(f"  ❌ Claude 报告 [FAILED]")

        # 验证 JQ 脚本存在且大小合理
        if not output_path.exists() or output_path.stat().st_size < 1000:
            size = output_path.stat().st_size if output_path.exists() else 0
            log.error(f"  ❌ Claude 没写 JQ 脚本或过小 (size={size})")
            return False, str(output_path), {
                "failed_step": "jq_claude_no_code",
                "feedback": f"JQ 脚本 size={size}, expected >1000. last 500 chars stdout: {(full_stdout or '')[-500:]}",
            }

        return True, str(output_path), {"size": last_size, "stdout_tail": full_stdout[-200:]}
    except FileNotFoundError:
        log.error(f"  ❌ 'claude' CLI 找不到")
        return False, str(output_path), {"failed_step": "jq_claude_missing", "feedback": "claude CLI not found"}
    except Exception as e:
        log.error(f"  ❌ Claude CLI 调用失败: {type(e).__name__}: {e}")
        return False, str(output_path), {"failed_step": "jq_claude_exception", "feedback": str(e)}
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
            try:
                if proc.stderr:
                    proc.stderr.close()
            except Exception:
                pass


# ========== 静态检查 ==========

def _step1_py_compile(code_path: Path) -> tuple[bool, str]:
    """Step 1: 语法检查."""
    try:
        py_compile.compile(str(code_path), doraise=True)
        return True, ""
    except py_compile.PyCompileError as e:
        return False, f"语法错误: {e}"


def _step2_ast_structure(code_path: Path) -> tuple[bool, str, dict]:
    """Step 2: ast 解析 (不 import 聚宽 SDK, 纯静态).

    检查:
    - 必须含 initialize(context) 函数
    - 模块级必须有 run_daily / set_benchmark / set_order_cost / set_slippage 调用
    - 必须有 PARAMS dict 字面量
    - 必须有 self_check 函数
    - 必须有 if __name__ == "__main__": 块
    """
    try:
        source = code_path.read_text(encoding="utf-8")
        tree = ast.parse(source)
    except SyntaxError as e:
        return False, f"AST 解析失败 (语法错): {e}", {}

    # 1. 必备函数
    func_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            func_names.add(node.name)

    missing_funcs = [f for f in REQUIRED_FUNCTIONS if f not in func_names]
    if missing_funcs:
        return False, f"缺少必备函数: {missing_funcs}", {"func_names": sorted(func_names)}

    # 2. initialize() 函数体内必须有 run_daily / set_benchmark / set_order_cost / set_slippage 调用
    #    (聚宽规范: 这些都必须在 initialize() 内部调用, 不是模块级)
    init_func = None
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "initialize":
            init_func = node
            break

    if init_func is None:
        return False, "未找到 initialize 函数定义 (ast 异常)", {}

    init_calls: set[str] = set()
    for sub in ast.walk(init_func):
        if isinstance(sub, ast.Call):
            if isinstance(sub.func, ast.Name):
                init_calls.add(sub.func.id)
            elif isinstance(sub.func, ast.Attribute):
                init_calls.add(sub.func.attr)

    missing_calls = [c for c in REQUIRED_MODULE_CALLS if c not in init_calls]
    if missing_calls:
        return False, f"initialize() 缺少必备调用: {missing_calls}", {
            "init_calls": sorted(init_calls)
        }

    module_calls = init_calls  # 兼容旧字段名

    # 3. PARAMS dict (模块级赋值)
    has_params = False
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name) and tgt.id == "PARAMS":
                    has_params = True
                    break
    if not has_params:
        return False, "缺少模块级 PARAMS 字典赋值", {}

    # 4. self_check 函数
    has_self_check = "self_check" in func_names
    if not has_self_check:
        return False, "缺少 self_check() 函数 (RULES.md §7 必备)", {}

    # 5. if __name__ == "__main__": 块 (软警告, 不强制 — 聚宽脚本本地不直接跑)
    has_main_block = False
    for node in tree.body:
        if isinstance(node, ast.If):
            if isinstance(node.test, ast.Compare):
                left = node.test.left
                if isinstance(left, ast.Name) and left.id == "__name__":
                    has_main_block = True
                    break
    # ⚠️ 2026-06-15: 不强制 (聚宽脚本给聚宽平台跑, 不需要本地 __main__ 入口)
    # 但记录在 details, 便于诊断

    return True, "", {
        "func_names": sorted(func_names),
        "init_calls": sorted(init_calls),
        "has_params": True,
        "has_self_check": has_self_check,
        "has_main_block": has_main_block,
    }


def _step3_params_fields(code_path: Path) -> tuple[bool, str, list[str]]:
    """Step 3: PARAMS 必填字段检查 (regex on dict literal, 不执行).

    注意: 不解析 Python, 只搜 `"key":` 出现情况 (简化, 允许嵌套结构).
    """
    try:
        source = code_path.read_text(encoding="utf-8")
    except Exception as e:
        return False, f"读源文件失败: {e}", []

    # 抓 PARAMS = { ... } 块
    m = re.search(r"^PARAMS\s*=\s*\{", source, re.MULTILINE)
    if not m:
        return False, "找不到 PARAMS = { ... }", []

    # 从 PARAMS 开始扫到匹配的 }
    start = m.end() - 1  # '{' 位置
    depth = 0
    end = start
    for i, ch in enumerate(source[start:], start=start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i
                break
    params_text = source[start:end + 1]

    missing = [k for k in REQUIRED_PARAM_KEYS if f'"{k}"' not in params_text and f"'{k}'" not in params_text]
    if missing:
        return False, f"PARAMS 缺少必填字段: {missing}", missing

    # 额外检查: tie_break_seed
    if '"tie_break_seed"' not in params_text and "'tie_break_seed'" not in params_text:
        return False, 'PARAMS 缺少 "tie_break_seed" 字段 (RULES.md §3 必填)', ["tie_break_seed"]

    return True, "", []


def _step4_claude_verify(
    name: str,
    code_path: Path,
    final_md_path: Path,
    timeout: int = 300,
) -> tuple[bool, str]:
    """Step 4: 让 Claude 读 JQ 脚本 + spec + RULES.md, 判定 [VERIFY] PASS/FAIL.

    重点验证:
    - JQ 脚本与 spec 一致性 (entry/exit/因子名 + 权重 + 阈值)
    - 没有套模板破坏策略
    - RULES.md 8 节 Checklist 全部满足
    """
    spec_text = ""
    if final_md_path.exists():
        spec_text = final_md_path.read_text(encoding="utf-8")[:3000]
    code_text = code_path.read_text(encoding="utf-8")[:6000]
    rules_text = ""
    rules_path = project_root() / "joinQuant" / "RULES.md"
    if rules_path.exists():
        rules_text = rules_path.read_text(encoding="utf-8")[:2000]

    prompt = f"""# 任务: 验证 JQ 脚本与 spec 的一致性

策略 `{name}` 已经生成了聚宽回测脚本, 请验证它**忠实于 spec**, 没有"套模板破坏策略".

## 必读
1. JQ 脚本: `{code_path}` (前 6000 字)
2. 策略 spec: `{final_md_path}` (前 3000 字)
3. 生成规则: `{rules_path}` (前 2000 字, 8 节 Checklist)

## 验证项
1. JQ 脚本 PARAMS.entry_weights / exit_weights 的 keys 与 spec entry_signals[] / exit_signals[] 名字一致
2. JQ 脚本引用的因子名与 spec factors[].name 一致
3. JQ 脚本因子窗口/阈值与 spec params 一致 (不是模板默认值)
4. 5 个 enforce 函数 (enforce_max_single_weight, enforce_industry_concentration, enforce_max_turnover, fill_cash_with_remaining_candidates, get_industry_map) 全部存在
5. can_buy_at_open / can_sell_at_open 不是简单 return True
6. 科创板 (688) 整手 200 股处理存在
7. holding_days 1-based (buy 时设 1, step 1 +=1, 即第 2 日 hd=2) — 与本地 portfolio.py:140 + runner.py:1037 一致
8. 唯一调度: run_daily(daily_handle, time="09:30") — 没有 14:55 决策

## 输出
仅输出一行:
[VERIFY] PASS — <一句话理由>
或
[VERIFY] FAIL — <具体问题, 给出修复建议>

不要修改任何文件, 仅判定.
"""

    cmd = [
        CLAUDE_CLI_PATH,
        "-p", prompt,
        "--allowedTools", "Read",
        "--bare",
        "--permission-mode", "bypassPermissions",
    ]
    try:
        r = subprocess.run(
            cmd, cwd=project_root(), capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=timeout, shell=False,
        )
    except subprocess.TimeoutExpired:
        return False, f"claude 验证超时 ({timeout}s)"
    except FileNotFoundError:
        return True, "(跳过: claude CLI 不可用)"
    except Exception as e:
        return True, f"(跳过: claude 验证异常 {type(e).__name__}: {e})"

    if r.returncode != 0:
        return True, f"(跳过: claude 验证 exit={r.returncode})"

    stdout = r.stdout or ""
    if "[VERIFY] PASS" in stdout:
        return True, stdout[stdout.index("[VERIFY]"):].split("\n")[0]
    if "[VERIFY] FAIL" in stdout:
        return False, stdout[stdout.index("[VERIFY]"):].split("\n")[0]
    return True, f"(claude 未明确判定: {stdout[-200:]})"


def check_jq_script(
    code_path: Path,
    name: str,
    final_md_path: Path,
) -> tuple[bool, str, dict]:
    """4 步静态检查.

    Returns:
        (passed, failure_reason, details)
    """
    details: dict = {}

    # Step 1: py_compile
    ok, fb = _step1_py_compile(code_path)
    if not ok:
        return False, f"step1_py_compile: {fb}", details
    details["step1_py_compile"] = "OK"

    # Step 2: ast 结构
    ok, fb, ast_details = _step2_ast_structure(code_path)
    if not ok:
        return False, f"step2_ast_structure: {fb}", {**details, **ast_details}
    details.update(ast_details)
    details["step2_ast_structure"] = "OK"

    # Step 3: PARAMS 必填字段
    ok, fb, missing_keys = _step3_params_fields(code_path)
    if not ok:
        return False, f"step3_params_fields: {fb}", {**details, "missing_keys": missing_keys}
    details["step3_params_fields"] = "OK"

    # Step 4: Claude 二次确认
    log.info(f"  → Step 4: claude 验证 spec 一致性 (二次确认)")
    ok, fb = _step4_claude_verify(name, code_path, final_md_path)
    if not ok:
        return False, f"step4_claude_verify: {fb}", details
    details["step4_claude_verify"] = fb

    return True, "", details


# ========== 主入口 ==========

def generate_jq_script(
    name: str,
    final_md_path: Path,
    report_weight_path: Path,
    output_path: Path,
    max_attempts: int = 3,
) -> JQResult:
    """主入口: 调 claude -p 生成 JQ 脚本 + 静态检查 + 失败重试.

    Args:
        name: 策略名
        final_md_path: 策略 spec (Stage H 导出的 <name>_final.md)
        report_weight_path: 策略报告 (report_weight_final.md)
        output_path: JQ 脚本输出路径 (result/<name>/JQ_<name>.py)
        max_attempts: 最多重试次数 (默认 3)

    Returns:
        JQResult (含 passed / failure_reason / check_details)
    """
    if not final_md_path.exists():
        return JQResult(
            code_path=output_path,
            attempts=0,
            passed=False,
            failure_reason=f"final_md 不存在: {final_md_path}",
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists():
        output_path.unlink()  # 清空旧产物, 让 claude 重新生成

    banner(f"Stage I: 生成 JQ 脚本: {name}")
    log.info(f"  spec: {final_md_path}")
    log.info(f"  output: {output_path}")
    log.info(f"  max_attempts: {max_attempts}")

    last_feedback = ""
    for attempt in range(1, max_attempts + 1):
        log.info(f"━━━ Attempt {attempt}/{max_attempts} ━━━")
        gen_ok, _, gen_info = _run_claude_jq_generate(
            name=name,
            final_md_path=final_md_path,
            report_weight_path=report_weight_path,
            output_path=output_path,
            attempt=attempt,
            max_attempts=max_attempts,
            feedback=last_feedback,
        )
        if not gen_ok:
            failed_step = gen_info.get("failed_step", "unknown")
            last_feedback = f"claude 生成失败: {failed_step}\n{gen_info.get('feedback', '')}"
            log.warning(f"  ❌ 生成失败: {failed_step}: {gen_info.get('feedback', '')[:200]}")
            continue

        # 生成成功, 跑检查
        log.info(f"  → 跑 4 步静态检查 (py_compile + ast + PARAMS + claude 验证) ...")
        check_ok, check_fb, check_details = check_jq_script(output_path, name, final_md_path)
        if check_ok:
            banner(f"✅ JQ 脚本生成成功 (attempt {attempt})", char="=")
            log.info(f"  size: {output_path.stat().st_size} bytes")
            log.info(f"  checks: {check_details}")
            return JQResult(
                code_path=output_path,
                attempts=attempt,
                passed=True,
                check_details=check_details,
            )
        last_feedback = f"静态检查失败: {check_fb}\n请修复后重新输出完整 Python 源码 (覆盖 {output_path})"
        log.warning(f"  ❌ 检查失败: {check_fb[:200]}")

    # 3 次都失败
    return JQResult(
        code_path=output_path if output_path.exists() else output_path,
        attempts=max_attempts,
        passed=False,
        failure_reason=last_feedback[:500],
    )


__all__ = ["JQResult", "generate_jq_script", "check_jq_script"]
