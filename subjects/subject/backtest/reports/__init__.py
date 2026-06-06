"""回测报告生成 (Markdown 格式). 见 subject.md §6 / subject_structure.md §7."""

from .params_mode import render_params_report
from .weight_mode import render_weight_report

__all__ = ["render_params_report", "render_weight_report"]
