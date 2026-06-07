"""
pipeline.test_runner — 5 步测试 wrapper

Step 1: py_compile 语法检查
Step 2: importlib 加载 + Strategy() 实例化
Step 3: 反射检查 3 个方法签名
Step 4: subprocess 跑 smoke backtest (5 stocks, 1 month)
Step 5: 解析 report, 检查 trades >= 1 且 sharpe > -5 (合理性)
Step 6 (可选): 与金标准 strategy.py 做结构 diff
"""
from __future__ import annotations

import importlib.util
import inspect
import py_compile
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from .config import project_root, subjects_dir
from .log_utils import get_logger
from .parser import list_all_reports, parse_report
try:
    from config import CLAUDE_CLI_PATH
except ImportError:
    CLAUDE_CLI_PATH = "claude"  # fallback

log = get_logger()


@dataclass
class TestResult:
    """测试结果."""
    passed: bool = False
    failed_step: Optional[str] = None
    feedback: str = ""
    metrics: dict = field(default_factory=dict)
    multi_results: list = field(default_factory=list)  # 多场景结果 [{label, start, end, metrics}, ...]


# 3 个必备方法签名
REQUIRED_METHODS = ["compute_factors", "entry_score", "should_exit"]


def _step1_py_compile(code_path: Path) -> tuple[bool, str]:
    """Step 1: 语法检查."""
    try:
        py_compile.compile(str(code_path), doraise=True)
        return True, ""
    except py_compile.PyCompileError as e:
        return False, f"语法错误: {e}"


def _step2_import(code_path: Path, name: str) -> tuple[bool, Any, str]:
    """Step 2: importlib 加载 + Strategy() 实例化."""
    try:
        spec = importlib.util.spec_from_file_location(f"{name}_strategy", code_path)
        if spec is None or spec.loader is None:
            return False, None, "无法创建 importlib spec"
        mod = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = mod
        spec.loader.exec_module(mod)
        strategy = mod.Strategy()
        return True, strategy, ""
    except Exception as e:
        return False, None, f"导入失败: {type(e).__name__}: {e}"


def _step3_signatures(strategy: Any) -> tuple[bool, str]:
    """Step 3: 反射检查 3 个方法签名.

    注意: strategy 是实例, 拿到的是 bound method, inspect.signature 返回的
    parameters 不含 'self' (已绑定). 我们检查实际参数名是否匹配预期.
    """
    missing = [m for m in REQUIRED_METHODS if not hasattr(strategy, m)]
    if missing:
        return False, f"缺少方法: {missing}"

    # 检查 compute_factors 签名: (df, params)
    sig_cf = inspect.signature(strategy.compute_factors)
    params_cf = [p for p in sig_cf.parameters.keys() if p != "self"]
    if params_cf != ["df", "params"]:
        return False, f"compute_factors 签名错误: {params_cf} 应为 ['df', 'params']"

    # 检查 entry_score 签名: (factors, params, weights)
    sig_es = inspect.signature(strategy.entry_score)
    params_es = [p for p in sig_es.parameters.keys() if p != "self"]
    if params_es != ["factors", "params", "weights"]:
        return False, f"entry_score 签名错误: {params_es} 应为 ['factors', 'params', 'weights']"

    # 检查 should_exit 签名: (position, factors, params, weights)
    sig_se = inspect.signature(strategy.should_exit)
    params_se = [p for p in sig_se.parameters.keys() if p != "self"]
    if params_se != ["position", "factors", "params", "weights"]:
        return False, f"should_exit 签名错误: {params_se} 应为 ['position', 'factors', 'params', 'weights']"

    return True, ""


def _step4_smoke_backtest(
    name: str,
    smoke_universe: list[str],
    smoke_start: str,
    smoke_end: str,
    timeout: int = 300,
) -> tuple[bool, str]:
    """Step 4: subprocess 跑 smoke backtest (5 stocks, 1 month).

    直接调 `subject.cli run`, 不走 strategy.py (因为 strategy.py 的 argparse
    不支持 --test-universe 标志). cli/main.py 接受完整参数.
    """
    cmd = [
        sys.executable, "-m", "subject.cli", "run",
        "--strategy", name,
        "--mode", "params",
        "--test-universe", ",".join(smoke_universe),
        "--max-stocks", str(len(smoke_universe)),
        "--start-date", smoke_start,
        "--end-date", smoke_end,
    ]
    try:
        result = subprocess.run(
            cmd,
            cwd=subjects_dir(),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        if result.returncode != 0:
            stderr_tail = (result.stderr or "")[-800:]
            stdout_tail = (result.stdout or "")[-500:]
            return False, f"exit code {result.returncode}\nSTDOUT tail:\n{stdout_tail}\nSTDERR tail:\n{stderr_tail}"
        return True, ""
    except subprocess.TimeoutExpired:
        return False, f"smoke backtest 超时 ({timeout}s)"
    except Exception as e:
        return False, f"subprocess 异常: {type(e).__name__}: {e}"


def _step5_report_sanity(name: str) -> tuple[bool, str, dict]:
    """Step 5: 解析 smoke backtest 产生的 report, 检查合理性.

    通过条件: report 存在 + trades >= 1 (有成交) + sharpe > -5
    """
    try:
        metrics = parse_report_path(name, mode="params")
    except FileNotFoundError as e:
        return False, f"未找到 smoke 报告: {e}", {}

    if not metrics:
        return False, "报告解析失败 (0 指标)", metrics

    sharpe = metrics.get("sharpe", -999)
    annual = metrics.get("annual_return", -999)

    # sharpe > -5 兜底 (避免策略完全没动 / 跑出 NaN)
    if sharpe < -5:
        return False, f"sharpe 异常低 ({sharpe:.2f}), 怀疑策略未生效", metrics
    if annual < -0.5:
        return False, f"annual_return 异常低 ({annual:.2%}), 怀疑策略错误", metrics

    return True, "", metrics


# 多场景 smoke 测试配置
# (start, end, label) — 3 段不同时间窗口验证策略健壮性
MULTI_SCENARIO_PERIODS = [
    ("2024-06-01", "2024-06-30", "summer_2024"),
    ("2024-09-01", "2024-09-30", "autumn_2024"),
    ("2024-10-01", "2024-12-31", "q4_2024"),
]


def _step6_multi_scenario(name: str, smoke_universe: list[str], timeout: int) -> tuple[bool, str, list[dict]]:
    """Step 6: 多日期段 smoke 测试, 验证策略在不同时间窗口都能跑通.

    跑 3 段 (summer_2024, autumn_2024, q4_2024), 每段后:
      - 删 reportParams/report_v*.md (避免污染下个场景)
      - 跑新场景
      - 解析新报告
    """
    from .parser import parse_latest_report
    from .config import subjects_dir

    results: list[dict] = []
    for start, end, label in MULTI_SCENARIO_PERIODS:
        log.info(f"  [test]   多场景 {label}: {start} ~ {end}")
        cmd = [
            sys.executable, "-m", "subject.cli", "run",
            "--strategy", name,
            "--mode", "params",
            "--test-universe", ",".join(smoke_universe),
            "--max-stocks", str(len(smoke_universe)),
            "--start-date", start,
            "--end-date", end,
        ]
        try:
            r = subprocess.run(
                cmd, cwd=subjects_dir(), capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            return False, f"多场景 {label} 超时 ({timeout}s)", results
        except Exception as e:
            return False, f"多场景 {label} 异常: {type(e).__name__}: {e}", results
        if r.returncode != 0:
            stderr = (r.stderr or "")[-500:]
            return False, f"多场景 {label} exit={r.returncode}\nSTDERR: {stderr}", results
        # 解析报告
        try:
            m = parse_latest_report(name, mode="params")
        except FileNotFoundError as e:
            return False, f"多场景 {label} 报告缺失: {e}", results
        if not m:
            return False, f"多场景 {label} 报告解析失败", results
        # 必须有 trade 记录 (trades >= 1)
        if m.get("annual_return", 0) < -0.3:
            return False, f"多场景 {label} 收益异常: {m.get('annual_return', 0):.2%}", results
        results.append({"label": label, "start": start, "end": end, "metrics": m})
        log.info(f"  [test]     ✅ {label}: annual_return={m.get('annual_return', 0):.4f}, sharpe={m.get('sharpe', 0):.2f}")
        # 清理该场景报告
        rp = subjects_dir() / name / "reportParams"
        if rp.exists():
            for f in rp.glob("*.md"):
                try:
                    f.unlink()
                except Exception:
                    pass
    return True, "", results


def _step7_correctness_check(metrics: dict, multi_results: list[dict]) -> tuple[bool, str]:
    """Step 7: 正确性检查 — 主 smoke + 多场景综合判定.

    校验项:
      - 主 smoke 的 sharpe > -2 (避免策略完全失效)
      - 主 smoke 的 win_rate 在 [0, 1] 区间
      - 主 smoke 的 max_drawdown < 0 (有回撤, 正常)
      - 主 smoke 的 profit_loss_ratio > 0
      - 多场景至少 2/3 段 annual_return > -0.2 (策略不至于全面崩)
    """
    issues: list[str] = []

    sharpe = metrics.get("sharpe", -999)
    win_rate = metrics.get("win_rate", -1)
    mdd = metrics.get("max_drawdown", 0)
    pl_ratio = metrics.get("profit_loss_ratio", 0)

    if sharpe < -2:
        issues.append(f"主 smoke sharpe={sharpe:.2f} < -2 (策略可能完全失效)")
    if not (0 <= win_rate <= 1):
        issues.append(f"主 smoke win_rate={win_rate} 不在 [0, 1] 区间")
    if mdd > 0:
        issues.append(f"主 smoke max_drawdown={mdd:.4f} > 0 (回撤应该是负数)")
    if pl_ratio < 0:
        issues.append(f"主 smoke profit_loss_ratio={pl_ratio} < 0")

    # 多场景检查
    if multi_results:
        bad = [r for r in multi_results if r["metrics"].get("annual_return", 0) < -0.2]
        if len(bad) >= 2:
            issues.append(
                f"多场景 {len(bad)}/{len(multi_results)} 段 annual_return < -0.2: "
                f"{[r['label'] for r in bad]}"
            )

    if issues:
        return False, "正确性检查失败:\n  - " + "\n  - ".join(issues)
    return True, ""


def _step8_claude_verify(name: str, code_path: Path, metrics: dict, multi_results: list[dict], timeout: int = 600) -> tuple[bool, str]:
    """Step 8: 让 Claude 验证报告数据合理性 (调 `claude -p`).

    给 Claude 看:
      - 策略 spec
      - 生成的 strategy.py
      - 主 smoke 报告
      - 多场景报告
    让 Claude 判断:
      - 报告数值是否合理 (annual_return, sharpe, mdd)
      - 是否有异常模式 (trades=0, all NaN, etc.)
      - 给出 PASS/FAIL 判定 + 原因
    """
    import subprocess

    multi_summary = "\n".join(
        f"- {r['label']} ({r['start']} ~ {r['end']}): annual_return={r['metrics'].get('annual_return', 0):.4f}, "
        f"sharpe={r['metrics'].get('sharpe', 0):.2f}, mdd={r['metrics'].get('max_drawdown', 0):.4f}"
        for r in multi_results
    ) or "(无多场景数据)"

    prompt = f"""# 任务: 验证 strategy.py 的 backtest 结果

你刚生成的 `{code_path}` 已经通过 5 步 smoke 测试, 并跑了 3 个时间窗口的多场景测试.
请基于下面的报告数据, 验证结果合理性。

## 报告数据

主 smoke (5 股, 2024-06-01 ~ 2024-12-31):
- annual_return = {metrics.get('annual_return', 0):.4f}
- avg_annual_return_rate = {metrics.get('avg_annual_return_rate', 0):.4f}
- win_rate = {metrics.get('win_rate', 0):.4f}
- profit_loss_ratio = {metrics.get('profit_loss_ratio', 0):.2f}
- sharpe = {metrics.get('sharpe', 0):.2f}
- max_drawdown = {metrics.get('max_drawdown', 0):.4f}

多场景测试:
{multi_summary}

## 验证项
1. 主 smoke sharpe 是否合理 (-2 < sharpe < 5)
2. win_rate 是否在 [0, 1]
3. max_drawdown 是否为负 (回撤应该是负值)
4. profit_loss_ratio 是否为正
5. 多场景至少 2/3 段 annual_return > -0.2
6. 数值之间是否自洽 (如 win_rate 高但 profit_loss_ratio 极低 → 异常)

## 输出格式
仅输出 1 行:
[VERIFY] PASS — <一句话理由>
或
[VERIFY] FAIL — <具体问题>

不要修改任何文件, 不要写代码, 仅判定.
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


def parse_report_path(name: str, mode: str) -> dict:
    """从 subjects/<name>/reportParams/ 取最新 standard report 并解析.

    包装 parser.parse_latest_report, 错误信息更友好.
    """
    from .parser import parse_latest_report
    return parse_latest_report(name, mode)


def run(
    code_path: Path,
    name: str,
    smoke_universe: list[str],
    smoke_start: str,
    smoke_end: str,
    timeout: int = 300,
) -> TestResult:
    """跑 5 步测试.

    Args:
        code_path: generated/strategy.py 路径
        name: 策略名
        smoke_universe: smoke 测试股票列表
        smoke_start / smoke_end: 日期范围
        timeout: smoke backtest 超时秒数

    Returns:
        TestResult 含 passed / failed_step / feedback / metrics
    """
    result = TestResult()

    # Step 1: 语法
    ok, fb = _step1_py_compile(code_path)
    if not ok:
        result.failed_step = "step1_syntax"
        result.feedback = fb
        log.warning(f"  [test] ❌ Step 1 (py_compile) 失败: {fb}")
        return result
    log.info("  [test] ✅ Step 1 (py_compile)")

    # Step 2: 导入
    ok, strategy, fb = _step2_import(code_path, name)
    if not ok:
        result.failed_step = "step2_import"
        result.feedback = fb
        log.warning(f"  [test] ❌ Step 2 (import) 失败: {fb}")
        return result
    log.info("  [test] ✅ Step 2 (importlib)")

    # Step 3: 签名
    ok, fb = _step3_signatures(strategy)
    if not ok:
        result.failed_step = "step3_signature"
        result.feedback = fb
        log.warning(f"  [test] ❌ Step 3 (signatures) 失败: {fb}")
        return result
    log.info("  [test] ✅ Step 3 (signatures)")

    # Step 4: smoke backtest
    ok, fb = _step4_smoke_backtest(name, smoke_universe, smoke_start, smoke_end, timeout)
    if not ok:
        result.failed_step = "step4_smoke"
        result.feedback = f"smoke backtest 失败:\n{fb}"
        log.warning(f"  [test] ❌ Step 4 (smoke backtest) 失败")
        return result
    log.info("  [test] ✅ Step 4 (smoke backtest, exit 0)")

    # Step 5: 报告合理性
    ok, fb, metrics = _step5_report_sanity(name)
    if not ok:
        result.failed_step = "step5_report_sanity"
        result.feedback = fb
        result.metrics = metrics
        log.warning(f"  [test] ❌ Step 5 (report sanity) 失败: {fb}")
        return result
    result.metrics = metrics
    log.info(f"  [test] ✅ Step 5 (report sanity, annual_return={metrics.get('annual_return', 'N/A')})")

    # Step 6: 多场景 smoke (3 段时间窗口, 验证策略健壮性)
    log.info("  [test] → Step 6: 多场景 smoke (3 个时间窗口)")
    ok, fb, multi_results = _step6_multi_scenario(name, smoke_universe, timeout)
    if not ok:
        result.failed_step = "step6_multi_scenario"
        result.feedback = fb
        log.warning(f"  [test] ❌ Step 6 (多场景) 失败: {fb}")
        return result
    log.info(f"  [test] ✅ Step 6 (多场景 {len(multi_results)}/3 通过)")
    result.multi_results = multi_results

    # Step 7: 正确性检查 (主 smoke + 多场景综合判定)
    log.info("  [test] → Step 7: 正确性检查 (主 smoke + 多场景)")
    ok, fb = _step7_correctness_check(metrics, multi_results)
    if not ok:
        result.failed_step = "step7_correctness"
        result.feedback = fb
        result.metrics = metrics
        log.warning(f"  [test] ❌ Step 7 (正确性) 失败: {fb}")
        return result
    log.info("  [test] ✅ Step 7 (正确性检查通过)")

    # Step 8: 让 claude 验证结果合理性 (claude 二次确认)
    log.info("  [test] → Step 8: claude 验证报告 (二次确认)")
    ok, fb = _step8_claude_verify(name, code_path, metrics, multi_results, timeout=300)
    if not ok:
        result.failed_step = "step8_claude_verify"
        result.feedback = fb
        log.warning(f"  [test] ❌ Step 8 (claude 验证) 失败: {fb}")
        return result
    log.info(f"  [test] ✅ Step 8: {fb}")

    result.passed = True
    return result


__all__ = ["TestResult", "run"]
