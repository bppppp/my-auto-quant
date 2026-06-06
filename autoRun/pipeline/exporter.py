"""
pipeline.exporter — Stage H 最终输出

把 best_params + best_weight 复制到 {project_root}/result/<name>/

简化设计: 全部 copy, 不做 merge.
- best weight v1 = best params 完整副本
- best weight v<N> (N>1) 是 v1 演化来的, 已经验证
- 所以 result/<name>_final.md 直接 = 最佳 weight 版本的 spec
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from .config import subjects_dir
from .log_utils import get_logger

log = get_logger()


@dataclass
class ExportResult:
    """导出结果."""
    target_dir: Path
    final_md: Path
    report_final: Path
    report_weight_final: Path


def export(
    strategy_name: str,
    best_params_version: str,   # e.g. "v15"
    best_weight_version: str,   # e.g. "v18"
    result_dir: Path,
) -> ExportResult:
    """复制 3 个文件到 result/<strategy_name>/.

    Args:
        strategy_name: 策略名
        best_params_version: 最佳 params 版本 (e.g. "v15")
        best_weight_version: 最佳 weight 版本 (e.g. "v18", 含 v1=best_params 副本)
        result_dir: result/ 根目录

    Returns:
        ExportResult 含 3 个文件路径

    Raises:
        FileNotFoundError: 源文件不存在
    """
    target_dir = result_dir / strategy_name
    target_dir.mkdir(parents=True, exist_ok=True)

    subject_dir = subjects_dir() / strategy_name

    # 1. _final.md = 最佳 weight 版本的 spec
    src_final = subject_dir / "strategiesWeight" / f"{strategy_name}_weight_{best_weight_version}.md"
    if not src_final.exists():
        raise FileNotFoundError(f"未找到最佳 weight spec: {src_final}")
    final_md = target_dir / f"{strategy_name}_final.md"
    shutil.copy2(src_final, final_md)
    log.info(f"  ✅ {final_md.name}  ← strategiesWeight/{src_final.name}")

    # 2. report_final.md = 最佳 params 模式的 report
    report_final = target_dir / "report_final.md"
    src_params_report = subject_dir / "reportParams" / f"report_{best_params_version}.md"
    if src_params_report.exists():
        shutil.copy2(src_params_report, report_final)
        log.info(f"  ✅ {report_final.name}  ← reportParams/{src_params_report.name}")
    else:
        log.warning(f"  ⚠️ params 报告不存在: {src_params_report}, 跳过")
        report_final = target_dir / "report_final.md"  # 仍返回预期路径

    # 3. report_weight_final.md = 最佳 weight 模式的 report
    report_weight_final = target_dir / "report_weight_final.md"
    src_weight_report = subject_dir / "reportWeight" / f"report_signals_{best_weight_version}.md"
    if src_weight_report.exists():
        shutil.copy2(src_weight_report, report_weight_final)
        log.info(f"  ✅ {report_weight_final.name}  ← reportWeight/{src_weight_report.name}")
    else:
        log.warning(f"  ⚠️ weight 报告不存在: {src_weight_report}, 跳过")
        report_weight_final = target_dir / "report_weight_final.md"

    return ExportResult(
        target_dir=target_dir,
        final_md=final_md,
        report_final=report_final,
        report_weight_final=report_weight_final,
    )


__all__ = ["ExportResult", "export"]
