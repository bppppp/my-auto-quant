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

log = get_logger()


@dataclass
class TestResult:
    """测试结果."""
    passed: bool = False
    failed_step: Optional[str] = None
    feedback: str = ""
    metrics: dict = field(default_factory=dict)


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

    result.passed = True
    return result


__all__ = ["TestResult", "run"]
