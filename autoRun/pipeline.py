"""
my-quant3 autoRun 流水线主入口

完整流程: A 生成 → B 翻译 → C params 20 轮 → D 选最优 →
          E weight 20 轮 → F 选最优 → H 导出到 result/ → G 下一策略

Usage:
  python pipeline.py check-env                          # 检查环境
  python pipeline.py --batch 5 --params-rounds 20 --weight-rounds 20 --reset   
  python pipeline.py --reset --batch 5 --params-rounds 20 --weight-rounds 20 清空重新来
  python pipeline.py --strategy ma_cross_atr_volume     # 单策略
  python pipeline.py --from-stage B                    # 从某阶段开始
  python pipeline.py --reset                            # 清空 state.json
  python pipeline.py --dry-run                          # 只显示计划
"""
from __future__ import annotations

import argparse
import io
import os
import re
import shutil
import signal
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# Windows: 强制 UTF-8 输出 (避免 emoji/中文乱码)
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# autoRun/pipeline.py → autoRun/ → my-quant3/
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# subjects/subject/ 是 Python package 'subject', 需要把 subjects/ 加到 sys.path
_SUBJECTS_PARENT = _PROJECT_ROOT / "subjects"
if str(_SUBJECTS_PARENT) not in sys.path:
    sys.path.insert(0, str(_SUBJECTS_PARENT))

from autoRun.pipeline.config import (  # noqa: E402
    PipelineConfig,
    auto_run_dir,
    project_root,
    result_dir,
    subjects_dir,
)
from autoRun.pipeline.exporter import export as export_result  # noqa: E402
from autoRun.pipeline.log_utils import banner, get_logger, section  # noqa: E402
from autoRun.pipeline.parser import list_all_reports, parse_report  # noqa: E402
from autoRun.pipeline.scorer import score  # noqa: E402
from autoRun.pipeline.state import (  # noqa: E402
    STATE_PATH,
    STAGE_EXPORTED,
    STAGE_FAILED,
    STAGE_GENERATED,
    STAGE_JQ_FAILED,
    STAGE_PARAMS_DONE,
    STAGE_PARAMS_LOOP,
    STAGE_PICKED_H,
    STAGE_PICKED_PARAMS,
    STAGE_PICKED_WEIGHT,
    STAGE_TRANSLATED,
    STAGE_WEIGHT_DONE,
    STAGE_WEIGHT_LOOP,
    State,
)
from autoRun.pipeline.translator import (  # noqa: E402
    TranslationFailed,
    translate,
)
from autoRun.pipeline.jq_translator import (  # noqa: E402
    generate_jq_script,
)

log = get_logger()

# ========== Ctrl+C / 信号处理 ==========

# 全局子进程注册表: 记录所有正在运行的 subprocess.Popen 对象
# 当收到 SIGINT/SIGTERM 时, 遍历并强杀所有子进程, 防止孤儿进程残留
_running_subprocesses: set[subprocess.Popen] = set()
_interrupted = False
# 指向当前 main_loop 的 State 实例, 用于信号处理时保存最新进度
_current_state: "State | None" = None  # noqa: F821


def _register_subprocess(proc: subprocess.Popen) -> None:
    """注册一个正在运行的子进程, 用于 Ctrl+C 时级联清理."""
    _running_subprocesses.add(proc)


def _unregister_subprocess(proc: subprocess.Popen) -> None:
    """子进程正常退出后注销."""
    _running_subprocesses.discard(proc)


def _cleanup_stray_processes(strategy_name: str = "") -> None:
    """清理残留的子进程（只清理已完成的，防止误杀正在运行的进程）。

    清理策略：
    1. 只清理已注册的子进程（通过 Popen.poll() 判断是否已完成）
    2. 只杀当前 pipeline 主进程的直接子进程（不杀孙进程/兄弟进程）
    3. 不根据命令行关键词杀进程（避免误杀其他正在运行的策略）

    Args:
        strategy_name: 当前策略名, 用于日志标记
    """
    import subprocess as _subprocess

    log.info(f"    🧹 清理残留进程...")

    # 1. 清理已注册的子进程（只清理已完成的）
    cleaned = 0
    for proc in list(_running_subprocesses):
        try:
            poll_result = proc.poll()
            if poll_result is not None:
                # 进程已结束，安全清理
                try:
                    proc.wait(timeout=2)  # 确保完全退出
                except Exception:
                    pass
                _running_subprocesses.discard(proc)
                cleaned += 1
                log.info(f"      → 回收已结束进程 pid={proc.pid} (exit={poll_result})")
            else:
                # 进程仍在运行，不杀（可能是嵌套调用的子进程）
                log.info(f"      → 跳过仍在运行的进程 pid={proc.pid}")
        except Exception:
            pass

    # 2. 只杀当前 pipeline 主进程的直接子进程（如果进程树中有残留）
    try:
        if sys.platform == "win32":
            current_pid = os.getpid()
            # 获取所有 python.exe 进程的 PID 和命令行
            result = _subprocess.run(
                ["powershell", "-Command",
                 f"(Get-CimInstance Win32_Process -Filter \"Name='python.exe'\") | "
                 f"Select-Object ProcessId,ParentProcessId,CommandLine | "
                 f"ConvertTo-Json -Compress"],
                capture_output=True, text=True, timeout=15,
            )
            if result.returncode == 0 and result.stdout.strip():
                import json as _json
                try:
                    data = _json.loads(result.stdout)
                    if isinstance(data, dict):
                        data = [data]
                    for proc_info in data:
                        pid = proc_info.get("ProcessId")
                        parent_pid = proc_info.get("ParentProcessId")
                        cmdline = proc_info.get("CommandLine", "") or ""
                        if pid is None or parent_pid is None:
                            continue
                        # 只杀当前进程的直接子进程，且命令行包含 strategy_name 或 pipeline 相关关键词
                        if parent_pid == current_pid and pid != current_pid:
                            # 检查是否是 pipeline 相关的进程
                            if strategy_name and strategy_name in cmdline:
                                try:
                                    _subprocess.run(["taskkill", "/PID", str(pid), "/F", "/T"],
                                                   capture_output=True, timeout=5)
                                    log.info(f"      → 已终止残留子进程 pid={pid}")
                                    cleaned += 1
                                except Exception:
                                    pass
                except (_json.JSONDecodeError, TypeError):
                    pass
    except Exception as e:
        log.warning(f"      ⚠️ 进程清理异常: {e}")

    if cleaned == 0:
        log.info(f"    🧹 无需清理（无残留进程）")
    else:
        log.info(f"    🧹 清理完成 ({cleaned} 个进程)")


def _kill_all_subprocesses() -> None:
    """强杀所有已注册的子进程."""
    procs = list(_running_subprocesses)
    for proc in procs:
        try:
            if proc.poll() is None:
                log.warning(f"  → 清理子进程 pid={proc.pid}")
                proc.kill()
                try:
                    proc.wait(timeout=3)
                except Exception:
                    pass
        except Exception:
            pass
        _running_subprocesses.discard(proc)


def _on_interrupt(signum: int, frame) -> None:
    """SIGINT / SIGTERM handler.

    - 第一次 Ctrl+C: 保存 state, 清理子进程, 退出
    - 第二次 Ctrl+C: 立即强退 (防止卡在 state.save())
    """
    global _interrupted
    if _interrupted:
        log.warning("⚠️ 第二次中断, 立即退出 (不保存 state)")
        _kill_all_subprocesses()
        os._exit(130)
    _interrupted = True
    log.warning(f"\n⚠️ 收到中断信号 (signal={signum}), 正在保存进度...")
    _kill_all_subprocesses()
    # 优先用 main_loop 中的内存 State (含最新进度), 回退到磁盘版本
    try:
        if _current_state is not None:
            if _current_state.has_pending():
                _current_state.save()
                log.info(f"  → state.json 已保存 (内存版本)")
        else:
            from autoRun.pipeline.state import State, STATE_PATH
            state = State.load()
            if state.has_pending():
                state.save()
                log.info(f"  → state.json 已保存 (磁盘版本)")
    except Exception as e:
        log.warning(f"  ⚠️ 保存 state 失败: {e}")
    log.warning("已退出.")
    os._exit(130)


# 注册信号 handler
signal.signal(signal.SIGINT, _on_interrupt)
signal.signal(signal.SIGTERM, _on_interrupt)


# ========== 路径冲突解决 ==========

def resolve_name_conflict(name: str) -> str:
    """冲突时自动加 _1 / _2 / _3 数字后缀."""
    from autoRun.pipeline.config import subjects_dir as _sd
    existing = [p.name for p in _sd().iterdir() if p.is_dir()] if _sd().exists() else []
    if name not in existing:
        return name
    for n in range(1, 1000):
        candidate = f"{name}_{n}"
        if candidate not in existing:
            return candidate
    raise RuntimeError(f"无法为 {name!r} 找到唯一名")


def rename_strategy_dir(old_name: str, new_name: str) -> Path:
    """重命名 subjects/<old>/ → subjects/<new>/, 同步改 spec / v1 文件名 + name 字段.

    会扫描所有子目录 (strategiesParam/, strategiesWeight/), 替换 <old_name>_* → <new_name>_*
    """
    old_dir = subjects_dir() / old_name
    new_dir = subjects_dir() / new_name
    if not old_dir.exists():
        raise FileNotFoundError(f"{old_dir} 不存在")
    old_dir.rename(new_dir)

    # 改 _original.md 内 name 字段 + 文件名
    for md in new_dir.glob("*_original.md"):
        content = md.read_text(encoding="utf-8")
        content = re.sub(
            rf"^name:\s*{re.escape(old_name)}\s*$",
            f"name: {new_name}",
            content,
            count=1,
            flags=re.MULTILINE,
        )
        new_md = new_dir / md.name.replace(old_name, new_name)
        md.rename(new_md)
        new_md.write_text(content, encoding="utf-8")

    # 改所有子目录里的 v1.md / weight_v1.md 文件名
    # 包括顶层, strategiesParam/, strategiesWeight/
    for sub in ("", "strategiesParam", "strategiesWeight"):
        base = new_dir / sub if sub else new_dir
        if not base.exists():
            continue
        for pattern in (f"{old_name}_v1.md", f"{old_name}_weight_v1.md"):
            for f in base.glob(pattern):
                new_f = base / f.name.replace(old_name, new_name)
                if f != new_f:
                    f.rename(new_f)
                    log.info(f"    重命名: {f.name} → {new_f.name}")

    return new_dir


# ========== Stage A: 生成新策略 ==========

def run_stage_a_generate(config: PipelineConfig) -> str:
    """Stage A: 调 strategies.py generate, 自动解决命名冲突.

    generate 含 quality_eval,可能耗时 30 分钟 - 1+ 小时,timeout 由 config.generate_timeout 控制.
    设置为 None 表示不设超时 (依赖外部 Ctrl+C).

    注意: LLM 大输出在 Windows PIPE 上偶尔会被截断, 因此 fallback 到扫 subjects/ 最新目录.
    """
    import time

    # 记录调用前 subjects/ 内目录的 mtime, 用于 fallback
    subjects_root = subjects_dir()
    before = {p.name: p.stat().st_mtime for p in subjects_root.iterdir() if p.is_dir()} if subjects_root.exists() else {}

    cmd = [sys.executable, "strategies/strategies.py", "generate"]
    timeout_str = f"{config.generate_timeout}s" if config.generate_timeout is not None else "无限制"
    log.info(f"  $ {' '.join(cmd)}  (timeout={timeout_str})")
    result = subprocess.run(
        cmd, cwd=project_root(), capture_output=True, text=True,
        encoding="utf-8", errors="replace",
        timeout=config.generate_timeout,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"generate exit {result.returncode}\n"
            f"STDOUT: {(result.stdout or '')[-500:]}\n"
            f"STDERR: {(result.stderr or '')[-500:]}"
        )

    # 解析 LLM 输出
    candidate: Optional[str] = None
    m = re.search(r"\[generate\] 成功: subjects/([^/]+)/", result.stdout or "")
    if m:
        candidate = m.group(1)
    else:
        # Fallback: 扫 subjects/ 找 mtime 最新且晚于调用前的目录
        log.warning("  ⚠️ stdout 解析失败, fallback 扫 subjects/ 最新目录")
        if not subjects_root.exists():
            raise RuntimeError(f"无法从 generate 输出解析策略名: {(result.stdout or '')[-500:]}\n且 subjects/ 不存在")
        after = [(p, p.stat().st_mtime) for p in subjects_root.iterdir() if p.is_dir()]
        new_dirs = [(p, t) for p, t in after if p.name not in before or t > before[p.name]]
        if not new_dirs:
            raise RuntimeError(f"无法从 generate 输出解析策略名: {(result.stdout or '')[-500:]}\n且未发现新策略目录")
        new_dirs.sort(key=lambda x: x[1], reverse=True)
        candidate = new_dirs[0][0].name
        log.info(f"  → fallback 解析: {candidate} (mtime={time.ctime(new_dirs[0][1])})")

    unique = resolve_name_conflict(candidate)
    if unique != candidate:
        log.info(f"  → 候选名 {candidate!r} 已存在, 重命名为 {unique!r}")
        rename_strategy_dir(candidate, unique)
    else:
        log.info(f"  → 策略名: {unique}")
    return unique


# ========== Stage B: 翻译 ==========

def run_stage_b_translate(name: str, config: PipelineConfig) -> Path:
    """Stage B: 翻译 spec → strategy.py."""
    spec_path = subjects_dir() / name / f"{name}_original.md"
    log.info(f"  → 翻译 {name} (max_attempts={config.translate_max_attempts}, smoke_timeout={config.smoke_timeout}s)")
    result = translate(
        spec_path=spec_path,
        max_attempts=config.translate_max_attempts,
        smoke_universe=list(config.smoke_universe),
        smoke_start=config.smoke_start,
        smoke_end=config.smoke_end,
        smoke_timeout=config.smoke_timeout,
    )
    return result.code_path


# ========== Stage C: params 调优 20 轮 ==========

def run_stage_c_params_loop(name: str, config: PipelineConfig, state: State) -> None:
    """Stage C: params 调优 N 轮."""
    log.info(f"  → params 调优 {config.params_rounds} 轮 (日期: {config.backtest_start} ~ {config.backtest_end})")
    # 使用 backtest 范围 (与 smoke test 区分: smoke 验证能用, backtest 用于调优)
    start_date = config.backtest_start
    end_date = config.backtest_end
    for round_n in range(1, config.params_rounds + 1):
        log.info(f"  [params {round_n}/{config.params_rounds}]")
        try:
            run_backtest(name, mode="params", timeout=config.backtest_timeout,
                         start_date=start_date, end_date=end_date)
            metrics = parse_latest(name, mode="params")
            if metrics:
                state.record_params(name, round_n, metrics)
                log.info(f"    annual_return={metrics.get('annual_return', 'N/A'):.4f}")
            else:
                state.record_params_failure(name, round_n, "no metrics")
        except Exception as e:
            log.warning(f"  [params {round_n}] 失败, 跳过本轮: {type(e).__name__}: {e}")
            state.record_params_failure(name, round_n, str(e))

        if round_n < config.params_rounds:
            try:
                run_cli("optimize", [name, "once"], timeout=config.cli_timeout)
            except Exception as e:
                log.warning(f"  [params {round_n}] optimize 失败: {e}")
    state.set_stage(name, STAGE_PARAMS_DONE)
    state.save()


# ========== Stage D: 选最优 params + 复制到 strategiesWeight/v1 ==========

def run_stage_d_pick_best_params(name: str, config: PipelineConfig, state: State) -> None:
    """Stage D: argmax(annual_return) 选最优 params + 复制到 strategiesWeight/v1."""
    all_reports = list_all_reports(name, mode="params")
    if not all_reports:
        raise RuntimeError(f"未找到任何 params 报告 for {name!r}")

    scored: list[tuple[int, float, dict]] = []
    for v, path in all_reports:
        m = parse_report(path)
        ar = m.get("annual_return", float("-inf"))
        scored.append((v, ar, m))
    scored.sort(key=lambda x: x[1], reverse=True)

    best_v, best_annual, best_metrics = scored[0]
    best_v_str = f"v{best_v}"
    log.info(f"  → 最佳 params: {best_v_str} (annual_return={best_annual:.4f})")
    log.info(f"    Top 3:")
    for v, ar, _ in scored[:3]:
        marker = " ←" if v == best_v else ""
        log.info(f"      v{v}: annual_return={ar:.4f}{marker}")

    state.set_best_params(name, best_v_str, best_annual)

    # 关键: 复制 best_params → strategiesWeight/v1 (作为 weight 调优起点)
    src = subjects_dir() / name / "strategiesParam" / f"{name}_{best_v_str}.md"
    dst = subjects_dir() / name / "strategiesWeight" / f"{name}_weight_v1.md"
    if not src.exists():
        raise FileNotFoundError(f"最佳 params spec 不存在: {src}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    log.info(f"  → 已复制 {best_v_str} → strategiesWeight/weight_v1.md (weight 调优起点)")

    # 同时保存一份到策略根目录, 方便直接查看当前最佳 params
    root_copy = subjects_dir() / name / f"{name}_{best_v_str}.md"
    shutil.copy2(src, root_copy)
    log.info(f"  → 已复制 {best_v_str} → {name}/ (策略根目录)")

    state.set_stage(name, STAGE_PICKED_PARAMS)
    state.save()


# ========== Stage E: weight 调优 20 轮 ==========

def run_stage_e_weight_loop(name: str, config: PipelineConfig, state: State) -> None:
    """Stage E: weight 调优 N 轮 (起点是 v1 = best params 副本)."""
    # 前置检查: strategiesWeight/<name>_weight_v1.md 必须存在
    weight_v1 = subjects_dir() / name / "strategiesWeight" / f"{name}_weight_v1.md"
    if not weight_v1.exists():
        log.warning(f"  ⚠️ weight_v1.md 不存在, 回退到 Stage D (重新复制 best params)")
        run_stage_d_pick_best_params(name, config, state)
    log.info(f"  → weight 调优 {config.weight_rounds} 轮 (v1 是 best params 副本, 日期: {config.backtest_start} ~ {config.backtest_end})")
    # 使用 backtest 范围 (与 smoke test 区分)
    start_date = config.backtest_start
    end_date = config.backtest_end
    for round_n in range(1, config.weight_rounds + 1):
        log.info(f"  [weight {round_n}/{config.weight_rounds}]")
        try:
            run_backtest(name, mode="weight", timeout=config.backtest_timeout,
                         start_date=start_date, end_date=end_date)
            metrics = parse_latest(name, mode="weight")
            if metrics:
                state.record_weight(name, round_n, metrics)
                log.info(f"    annual_return={metrics.get('annual_return', 'N/A'):.4f}")
            else:
                state.record_weight_failure(name, round_n, "no metrics")
        except Exception as e:
            log.warning(f"  [weight {round_n}] 失败, 跳过本轮: {type(e).__name__}: {e}")
            state.record_weight_failure(name, round_n, str(e))

        if round_n < config.weight_rounds:
            try:
                run_cli("factor_weights", [name, "once"], timeout=config.cli_timeout)
            except Exception as e:
                log.warning(f"  [weight {round_n}] factor_weights 失败: {e}")
    state.set_stage(name, STAGE_WEIGHT_DONE)
    state.save()


# ========== Stage F: 选最优 weight ==========

def run_stage_f_pick_best_weight(name: str, config: PipelineConfig, state: State) -> None:
    """Stage F: argmax(annual_return) 选最优 weight."""
    all_reports = list_all_reports(name, mode="weight")
    if not all_reports:
        raise RuntimeError(f"未找到任何 weight 报告 for {name!r}")

    scored: list[tuple[int, float, dict]] = []
    for v, path in all_reports:
        m = parse_report(path)
        ar = m.get("annual_return", float("-inf"))
        scored.append((v, ar, m))
    scored.sort(key=lambda x: x[1], reverse=True)

    best_v, best_annual, best_metrics = scored[0]
    best_v_str = f"v{best_v}"
    log.info(f"  → 最佳 weight: {best_v_str} (annual_return={best_annual:.4f})")
    log.info(f"    Top 3:")
    for v, ar, _ in scored[:3]:
        marker = " ←" if v == best_v else ""
        log.info(f"      v{v}: annual_return={ar:.4f}{marker}")

    state.set_best_weight(name, best_v_str, best_annual)
    state.set_stage(name, STAGE_PICKED_WEIGHT)
    state.save()


# ========== Stage H: 导出到 result/ ==========

def run_stage_h_export(name: str, config: PipelineConfig, state: State) -> None:
    """Stage H: 3 个文件 copy 到 result/<name>/.

    ⚠️ 2026-06-15 调整: H 完后不再 mark_exported, 改 set_stage(STAGE_PICKED_H).
    Stage I (JQ 脚本生成) 跑完后再统一 mark_exported. 这样支持断点续跑 (H 完后
    中断, 下次从 I 继续).
    """
    best_params = state.get(name).best_params_version
    best_weight = state.get(name).best_weight_version
    if not best_params or not best_weight:
        raise RuntimeError(f"{name}: 缺少 best_params ({best_params}) 或 best_weight ({best_weight})")

    log.info(f"  → 导出 best_params={best_params} + best_weight={best_weight}")
    result = export_result(
        strategy_name=name,
        best_params_version=best_params,
        best_weight_version=best_weight,
        result_dir=config.result_dir,
    )
    log.info(f"  → 已写入 {result.target_dir}/")
    state.set_stage(name, STAGE_PICKED_H)
    state.save()


# ========== Stage I: 生成聚宽 JQ 脚本 (2026-06-15 新增) ==========

def run_stage_i_jq(name: str, config: PipelineConfig, state: State) -> None:
    """Stage I: 调 Claude Code 生成 result/<name>/JQ_<name>.py.

    ⚠️ 2026-06-15 新增. fail-soft: 失败不抛异常, 仅记 jq_status=jq_failed.
    Stage I 失败不影响 mark_exported (因为 H 已经成功导出, 策略本质可用).
    """
    final_md = config.result_dir / name / f"{name}_final.md"
    report_weight_md = config.result_dir / name / "report_weight_final.md"
    jq_output = config.result_dir / name / f"JQ_{name}.py"

    if not final_md.exists():
        log.warning(f"  ⚠️ {final_md} 不存在, 跳过 Stage I")
        rec = state.get(name)
        rec.jq_status = "failed"
        rec.jq_failure_reason = f"final_md 不存在: {final_md}"
        state.set_stage(name, STAGE_JQ_FAILED)
        state.save()
        return

    try:
        result = generate_jq_script(
            name=name,
            final_md_path=final_md,
            report_weight_path=report_weight_md,
            output_path=jq_output,
            max_attempts=3,
        )
        rec = state.get(name)
        rec.jq_code_path = str(jq_output)
        rec.jq_attempts = result.attempts
        if result.passed:
            rec.jq_status = "generated"
            rec.jq_failure_reason = ""
            state.set_stage(name, STAGE_EXPORTED)  # 整个流水线结束
            log.info(f"  ✅ Stage I 完成, 标记 exported")
        else:
            rec.jq_status = "failed"
            rec.jq_failure_reason = result.failure_reason
            state.set_stage(name, STAGE_JQ_FAILED)
            log.warning(f"  ⚠️ Stage I 失败 (fail-soft, 不影响 exported 标记): {result.failure_reason[:200]}")
            # ⚠️ fail-soft: 仍 mark_exported 让 has_pending 跳过, 但 jq_status 留下记录
            state.set_stage(name, STAGE_EXPORTED)
            log.info(f"  → 策略 {name} 标记 exported (JQ 失败仅作记录)")
        state.save()
    except Exception as e:
        # Stage I 任何意外都 fail-soft
        log.exception(f"Stage I 异常 (fail-soft): {e}")
        rec = state.get(name)
        rec.jq_status = "failed"
        rec.jq_failure_reason = f"{type(e).__name__}: {e}"
        state.set_stage(name, STAGE_EXPORTED)  # 仍 exported
        state.save()


# ========== Subprocess 辅助 ==========

def run_cli(subcommand: str, args: list[str], timeout: int | None = 1800) -> None:
    """调 strategies.py 子命令 (generate/optimize/factor_weights/list).

    ⚠️ 2026-06-15 精简: 不再实时回显每行 stdout (5 年 × 300 股刷几万行, 累积几个 G).
    只在 exit 时报总输出大小, 失败时打 last 30 行. 调试用文件 log: autoRun/logs/pipeline_<date>.log.

    Args:
        timeout: 子进程超时秒数,None 表示不设超时 (依赖外部 Ctrl+C).
    """
    import time as _time
    cmd = [sys.executable, "-u", "strategies/strategies.py", subcommand] + args
    timeout_str = f"{timeout}s" if timeout is not None else "无限制"
    log.info(f"    $ {' '.join(cmd)}  (timeout={timeout_str})")

    proc = subprocess.Popen(
        cmd, cwd=project_root(),
        stdout=subprocess.DEVNULL,  # ⚠️ 2026-06-15: 丢弃 stdout, 避免刷屏
        stderr=subprocess.DEVNULL,  # 同步丢弃 stderr
        shell=False,
    )
    _register_subprocess(proc)
    try:
        start_time = _time.time()
        deadline = _time.time() + timeout if timeout else float("inf")
        last_heartbeat = _time.time()

        while True:
            if _time.time() > deadline:
                log.error(f"    ❌ {subcommand} 超时 ({timeout}s), 强杀")
                proc.kill()
                raise RuntimeError(f"{subcommand} 超时 {timeout}s")

            if proc.poll() is not None:
                break

            # 10 分钟一次心跳 (比之前 5min 减少一半, 减少日志量)
            if _time.time() - last_heartbeat > 600:
                elapsed = int(_time.time() - start_time)
                log.info(f"    ⏳ {subcommand} 仍在跑, pid={proc.pid}, 已 {elapsed}s")
                last_heartbeat = _time.time()
            _time.sleep(1.0)  # 比 0.5s 省 CPU

        elapsed = int(_time.time() - start_time)
        if proc.returncode != 0:
            log.error(f"    ❌ {subcommand} exit {proc.returncode}, 耗时 {elapsed}s")
            raise RuntimeError(f"{subcommand} exit {proc.returncode}")
        log.info(f"    ✅ {subcommand} 完成, 耗时 {elapsed}s")
    finally:
        _unregister_subprocess(proc)
        # 确保进程被回收 (kill 已退出的不会报错)
        try:
            if proc.poll() is None:
                proc.kill()
            proc.wait(timeout=5)
        except Exception:
            pass


def run_backtest(name: str, mode: str, timeout: int | None = 1800,
                 start_date: str | None = None, end_date: str | None = None) -> None:
    """调 subject.cli run 跑 backtest.

    ⚠️ 2026-06-15 精简: 不再实时回显 stdout (回测 5 年 × 300 股会刷几万行).
    完整 stdout 由 backtest 自己的 logger 写到 subjects/<name>/log/backtest_*.log.

    Args:
        timeout: 子进程超时秒数,None 表示不设超时.
        start_date: 起始日期 (YYYY-MM-DD), 默认 None (使用回测引擎默认 5 年).
        end_date: 结束日期 (YYYY-MM-DD), 默认 None (使用数据末日).
    """
    import time as _time
    cmd = [
        sys.executable, "-u",  # unbuffered
        "-m", "subject.cli", "run",
        "--strategy", name,
        "--mode", mode,
    ]
    if mode == "weight":
        cmd += ["--weight-test", name]
    if start_date:
        cmd += ["--start-date", start_date]
    if end_date:
        cmd += ["--end-date", end_date]
    timeout_str = f"{timeout}s" if timeout is not None else "无限制"
    log.info(f"    $ {' '.join(cmd)} (cwd=subjects/, timeout={timeout_str})")

    proc = subprocess.Popen(
        cmd, cwd=subjects_dir(),
        stdout=subprocess.DEVNULL,  # ⚠️ 2026-06-15: 丢弃 stdout
        stderr=subprocess.DEVNULL,  # 同步丢弃 stderr
        shell=False,
    )
    _register_subprocess(proc)
    try:
        start_time = _time.time()
        deadline = _time.time() + timeout if timeout else float("inf")
        last_heartbeat = _time.time()

        while True:
            if _time.time() > deadline:
                log.error(f"    ❌ backtest 超时 ({timeout}s), 强杀")
                proc.kill()
                raise RuntimeError(f"backtest {mode} 超时 {timeout}s")

            if proc.poll() is not None:
                break

            if _time.time() - last_heartbeat > 600:
                elapsed = int(_time.time() - start_time)
                log.info(f"    ⏳ backtest {mode} 仍在跑, pid={proc.pid}, 已 {elapsed}s")
                last_heartbeat = _time.time()
            _time.sleep(1.0)

        elapsed = int(_time.time() - start_time)
        if proc.returncode != 0:
            log.error(f"    ❌ backtest {mode} exit {proc.returncode}, 耗时 {elapsed}s")
            raise RuntimeError(f"backtest {mode} exit {proc.returncode}")
        log.info(f"    ✅ backtest {mode} 完成, 耗时 {elapsed}s")
    finally:
        _unregister_subprocess(proc)
        try:
            if proc.poll() is None:
                proc.kill()
            proc.wait(timeout=5)
        except Exception:
            pass


def parse_latest(name: str, mode: str) -> dict:
    """从最新 report 解析指标."""
    from autoRun.pipeline.parser import parse_latest_report
    return parse_latest_report(name, mode)


# ========== 主循环 ==========

STAGE_ORDER = ["A", "B", "C", "D", "E", "F", "H", "I"]


def main_loop(args, config: PipelineConfig) -> int:
    global _current_state
    state = State.load() if not args.reset else State()
    _current_state = state  # 让 Ctrl+C handler 能保存最新进度
    if not state.started_at:
        state.started_at = ""

    consecutive_translate_failures = 0
    batch_count = 0

    while batch_count < config.batch_size:
        # 决定本轮策略
        if args.strategy:
            strategy_name = args.strategy
            # 从 state 恢复当前阶段（支持断点续跑）
            rec = state.get(strategy_name)
            if rec.stage in (STAGE_EXPORTED, STAGE_FAILED):
                # ⚠️ 2026-06-15: --strategy 单策略模式下, 已 exported = 已完成,
                # **直接退出**而不是 continue (continue 会让 batch_count 不增加, 死循环)
                log.info(f"策略 {strategy_name} 已完成({rec.stage}), 退出 (单策略模式)")
                if rec.jq_status:
                    log.info(f"  Stage I 状态: jq_status={rec.jq_status}, code={rec.jq_code_path}")
                # 走强制退出路径
                _kill_all_subprocesses()
                os._exit(0)
            # ⚠️ 2026-06-15: CLI --from-stage 显式覆盖 state 推断的 start_stage
            # (之前 --from-stage 是死参数, 只在 docstring 里出现过)
            start_stage = args.from_stage or current_stage_letter(rec.stage)
            if args.from_stage:
                log.info(f"  → CLI 覆盖: 从 Stage {args.from_stage} 开始 (state 推断: {current_stage_letter(rec.stage)})")
        elif state.has_pending():
            strategy_name = state.current_strategy or next_pending(state)
            start_stage = current_stage_letter(state.get(strategy_name).stage)
        else:
            # Stage A: 生成新策略
            log.info("━━━ Stage A: generate ━━━")
            try:
                strategy_name = run_stage_a_generate(config)
            except Exception as e:
                log.error(f"Stage A 失败: {e}")
                consecutive_translate_failures += 1
                if consecutive_translate_failures >= config.consecutive_failures_threshold:
                    return maybe_exit_on_failures(args, consecutive_translate_failures)
                continue
            state.get(strategy_name)  # 确保记录存在
            state.set_stage(strategy_name, STAGE_GENERATED)
            state.save()
            start_stage = "B"

        # 跑该策略的所有阶段
        try:
            for stage in STAGE_ORDER:
                if stage_letter_to_index(stage) < stage_letter_to_index(start_stage):
                    continue
                log.info(f"━━━ Stage {stage}: {strategy_name} ━━━")
                run_one_stage(stage, strategy_name, config, state)
                if stage == "B":
                    consecutive_translate_failures = 0
                state.save()

            batch_count += 1
            state.current_strategy = ""
            state.save()

        except TranslationFailed as e:
            log.error(f"Stage B (translate) 失败: {e}")
            consecutive_translate_failures += 1
            state.mark_failed(strategy_name, reason=str(e))
            state.save()  # 落盘: 标记 failed 状态,避免下次 has_pending() 误判
            if consecutive_translate_failures >= config.consecutive_failures_threshold:
                return maybe_exit_on_failures(args, consecutive_translate_failures)
        except Exception as e:
            log.exception(f"Stage 失败: {e}")
            state.mark_failed(strategy_name, reason=f"{type(e).__name__}: {e}")
            state.save()  # 落盘: 同上
            # ⚠️ 2026-06-15: 强制清理 + 强制退出 (原行为: 非 auto return 1, auto 隐式 return None — 都改成强制退出)
            _kill_all_subprocesses()
            os._exit(1)

    log.info(f"━━━ 批次完成: {batch_count} 个策略 ━━━")
    # ⚠️ 2026-06-15: 强制清理子进程 + 立即退出, 防止 node/claude 子进程残留
    # 让 Python 不走 atexit (避免 daemon 线程 / 句柄未释放卡住)
    _force_exit_after_return = True
    if _force_exit_after_return:
        log.info("━━━ 清理子进程后立即退出 ━━━")
        _kill_all_subprocesses()
        os._exit(0)
    return 0


def run_one_stage(stage: str, name: str, config: PipelineConfig, state: State) -> None:
    """分发到具体 stage."""
    if stage == "A":
        # 已在 main_loop 处理
        return
    elif stage == "B":
        run_stage_b_translate(name, config)
        state.set_stage(name, STAGE_TRANSLATED)
    elif stage == "C":
        run_stage_c_params_loop(name, config, state)
    elif stage == "D":
        run_stage_d_pick_best_params(name, config, state)
    elif stage == "E":
        run_stage_e_weight_loop(name, config, state)
    elif stage == "F":
        run_stage_f_pick_best_weight(name, config, state)
    elif stage == "H":
        run_stage_h_export(name, config, state)
    elif stage == "I":
        run_stage_i_jq(name, config, state)  # ⚠️ 2026-06-15 新增
    else:
        raise ValueError(f"未知 stage: {stage}")


def next_pending(state: State) -> str:
    for n, r in state.strategies.items():
        if r.stage not in (STAGE_EXPORTED, STAGE_FAILED):
            return n
    return ""


def current_stage_letter(stage: str) -> str:
    mapping = {
        "init": "A",
        "generated": "B",
        "translated": "C",    # B 完成后进入 params 调优
        "params_loop": "C",
        "params_done": "D",
        "picked_params": "E",
        "weight_loop": "E",
        "weight_done": "F",
        "picked_weight": "H",
        "picked_h": "I",       # ⚠️ 2026-06-15 新增: H 完后进入 I
        "jq_failed": "I",      # JQ 失败时续跑也跳到 I
        "exported": "Z",
        "failed": "Z",
    }
    return mapping.get(stage, "A")


def stage_letter_to_index(letter: str) -> int:
    return STAGE_ORDER.index(letter) if letter in STAGE_ORDER else 0


def maybe_exit_on_failures(args, n: int) -> int:
    log.warning(f"\n⚠️ 连续 {n} 个策略翻译失败")
    log.info("   请检查:")
    log.info("   1. .env 中的 LLM_API_KEY / LLM_BASE_URL / LLM_MODEL")
    log.info("   2. 最近 1-2 个 _original.md 是否合理")
    log.info("   3. 重跑: python pipeline.py --strategy <name> --from-stage B")
    # ⚠️ 2026-06-15: 强制清理 + 强制退出, 防止 claude/node 子进程残留
    _kill_all_subprocesses()
    code = 1 if args.auto else 2
    os._exit(code)
    return code  # 不可达, 仅 type-check


# ========== check-env 子命令 ==========

def cmd_check_env(_args) -> int:
    """检查环境是否就绪."""
    banner("my-quant3 环境检查", char="━")
    warnings = []

    # 1. .env
    env_path = project_root() / ".env"
    if not env_path.exists():
        warnings.append(f"❌ .env 不存在 ({env_path})")
        warnings.append("   → 复制 .env.example 为 .env 并填入 LLM_API_KEY")
    else:
        try:
            from config import LLM_API_KEY
            if not LLM_API_KEY:
                warnings.append("❌ .env 存在但 LLM_API_KEY 为空")
            else:
                print(f"✅ .env 存在, LLM_API_KEY 已配置")
        except Exception as e:
            warnings.append(f"❌ 加载 .env 失败: {e}")

    # 2. Python 依赖
    for pkg in ["openai", "watchdog", "yaml", "pandas", "numpy"]:
        try:
            __import__(pkg)
            print(f"✅ {pkg} 已安装")
        except ImportError:
            warnings.append(f"❌ {pkg} 未安装 — 运行: pip install -r autoRun/requirements.txt")

    # 3. 数据目录
    data_dir = project_root() / "data"
    if not data_dir.exists():
        warnings.append(f"❌ data/ 不存在 ({data_dir})")
        warnings.append("   → 回测需要金玥数据, 见 data/README.md §1")
    else:
        n_stock = len(list((data_dir / "data-by-stock").glob("*.csv"))) if (data_dir / "data-by-stock").exists() else 0
        n_day = sum(1 for _ in (data_dir / "data-by-day").glob("*/*_金玥数据.csv")) if (data_dir / "data-by-day").exists() else 0
        print(f"✅ data/ 存在: {n_stock} 只股票, {n_day} 个横截面文件")

    # 4. 关键模块
    for mod in ["strategies.agents.base_agent", "subject.backtest.runner"]:
        try:
            __import__(mod)
            print(f"✅ {mod} 可导入")
        except ImportError as e:
            warnings.append(f"❌ {mod} 导入失败: {e}")

    # 5. state.json
    print(f"📝 state.json: {STATE_PATH} ({'存在' if STATE_PATH.exists() else '不存在 (首次运行)'})")

    print()
    if warnings:
        banner("发现问题", char="━")
        for w in warnings:
            print(w)
        return 1
    else:
        banner("✅ 环境就绪, 可以跑流水线", char="=")
        return 0


# ========== argparse ==========

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="pipeline",
        description="my-quant3 autoRun 自动化流水线",
    )
    sub = parser.add_subparsers(dest="cmd")

    # 默认 (无子命令) 跑流水线
    parser.add_argument("--batch", type=int, default=None, help="一次跑几个策略 (覆盖 config)")
    parser.add_argument("--strategy", default=None, help="只跑指定策略")
    parser.add_argument("--from-stage", default=None, choices=["A", "B", "C", "D", "E", "F", "H", "I"], help="从某阶段开始 (⚠️ 2026-06-15: 加上 I, 单独跑 Stage I)")
    parser.add_argument("--params-rounds", type=int, default=None, help="params 调优轮数 (覆盖 config)")
    parser.add_argument("--weight-rounds", type=int, default=None, help="weight 调优轮数 (覆盖 config)")
    parser.add_argument("--translate-max", type=int, default=None, help="翻译重试上限 (覆盖 config)")
    parser.add_argument("--reset", action="store_true", help="清空 state.json")
    parser.add_argument("--dry-run", action="store_true", help="只显示计划不执行")
    parser.add_argument("--auto", action="store_true", help="无人值守模式, 连续失败不暂停")
    parser.add_argument("--result-dir", default=None, help="覆盖 result 输出目录")
    # 各阶段 timeout (秒),传 0 表示禁用 timeout
    parser.add_argument("--generate-timeout", type=int, default=None, help="策略生成 timeout (秒, 默认 18000/5h, 0=禁用)")
    parser.add_argument("--cli-timeout", type=int, default=None, help="optimize/factor_weights timeout (秒, 默认 1800/30m, 0=禁用)")
    parser.add_argument("--backtest-timeout", type=int, default=None, help="单次回测 timeout (秒, 默认 3600/1h, 0=禁用)")
    parser.add_argument("--smoke-timeout", type=int, default=None, help="翻译 smoke backtest timeout (秒, 默认 600/10m)")
    parser.add_argument("--backtest-start", default=None, help="params/weight backtest 起始日期 YYYY-MM-DD (默认 2019-01-01)")
    parser.add_argument("--backtest-end", default=None, help="params/weight backtest 结束日期 YYYY-MM-DD (默认 2023-12-31)")

    # check-env 子命令
    sub.add_parser("check-env", help="检查环境是否就绪")

    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    if args.cmd == "check-env":
        return cmd_check_env(args)

    # 构造 config
    overrides = {}
    if args.batch:
        overrides["batch_size"] = args.batch
    if args.params_rounds:
        overrides["params_rounds"] = args.params_rounds
    if args.weight_rounds:
        overrides["weight_rounds"] = args.weight_rounds
    if args.translate_max:
        overrides["translate_max_attempts"] = args.translate_max
    if args.result_dir:
        overrides["result_dir"] = Path(args.result_dir)
    if args.generate_timeout is not None:
        overrides["generate_timeout"] = args.generate_timeout if args.generate_timeout > 0 else None
    if args.cli_timeout is not None:
        overrides["cli_timeout"] = args.cli_timeout if args.cli_timeout > 0 else None
    if args.backtest_timeout is not None:
        overrides["backtest_timeout"] = args.backtest_timeout if args.backtest_timeout > 0 else None
    if args.smoke_timeout is not None:
        overrides["smoke_timeout"] = args.smoke_timeout
    if args.backtest_start is not None:
        overrides["backtest_start"] = args.backtest_start
    if args.backtest_end is not None:
        overrides["backtest_end"] = args.backtest_end
    config = PipelineConfig(**overrides) if overrides else PipelineConfig()

    if args.dry_run:
        banner("my-quant3 pipeline 计划 (dry-run)", char="━")
        print(f"  batch_size: {config.batch_size}")
        print(f"  params_rounds: {config.params_rounds}")
        print(f"  weight_rounds: {config.weight_rounds}")
        print(f"  translate_max_attempts: {config.translate_max_attempts}")
        print(f"  result_dir: {config.result_dir}")
        print(f"  smoke_universe: {config.smoke_universe}")
        print(f"  smoke_date:     {config.smoke_start} ~ {config.smoke_end}")
        print(f"  backtest_date:  {config.backtest_start} ~ {config.backtest_end}")
        # 各阶段 timeout
        def _fmt(t):
            if t is None:
                return "无限制 (依赖外部 Ctrl+C)"
            if t >= 60:
                return f"{t}s ({t/3600:.1f}h)"
            return f"{t}s"
        print(f"  generate_timeout:    {_fmt(config.generate_timeout)}")
        print(f"  cli_timeout:         {_fmt(config.cli_timeout)}")
        print(f"  backtest_timeout:    {_fmt(config.backtest_timeout)}")
        print(f"  smoke_timeout:       {_fmt(config.smoke_timeout)}")
        return 0

    banner("my-quant3 pipeline 启动", char="=")
    log.info(f"  配置文件: {config}")
    try:
        return main_loop(args, config)
    except KeyboardInterrupt:
        log.warning("\n⚠️ 用户中断 (KeyboardInterrupt), 正在退出...")
        _kill_all_subprocesses()
        os._exit(130)  # 2026-06-15: 强制退出, 防止 claude/node 子进程残留
    except Exception as e:
        log.exception(f"❌ 未捕获异常: {e}")
        _kill_all_subprocesses()
        os._exit(1)  # 同样强制退出
    # 兜底: 走到这里也强制退出
    _kill_all_subprocesses()
    os._exit(0)


if __name__ == "__main__":
    sys.exit(main())
