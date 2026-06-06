"""
pipeline.parser — 报告 .md 解析器

从 report_v*.md / report_signals_v*.md 中提取 7 项指标:
- annual_return
- avg_annual_return_rate
- avg_annual_return_amount
- win_rate
- profit_loss_ratio
- sharpe
- max_drawdown

严格过滤 monitor 报告 (带 _YYYY-MM-DD 后缀).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .config import subjects_dir
from .log_utils import get_logger

log = get_logger()

# 7 项指标的解析正则
# 报告格式:
#   | 年化收益 | annual_return | 15.3333% |
#   | 夏普 | sharpe | 1.0401 |
#   | 最大回撤 | max_drawdown | -10.3983% |
METRIC_KEYS = {
    "annual_return": r"\|\s*annual_return\s*\|\s*([-\d.,%]+)\s*\|",
    "avg_annual_return_rate": r"\|\s*avg_annual_return_rate\s*\|\s*([-\d.,%]+)\s*\|",
    "avg_annual_return_amount": r"\|\s*avg_annual_return_amount\s*\|\s*([-\d.,]+)\s*\|",
    "win_rate": r"\|\s*win_rate\s*\|\s*([-\d.,%]+)\s*\|",
    "profit_loss_ratio": r"\|\s*profit_loss_ratio\s*\|\s*([-\d.,]+)\s*\|",
    "sharpe": r"\|\s*sharpe\s*\|\s*([-\d.,]+)\s*\|",
    "max_drawdown": r"\|\s*max_drawdown\s*\|\s*([-\d.,%]+)\s*\|",
}


def _parse_value(raw: str) -> Optional[float]:
    """'7.2981%' → 0.072981; '1.0401' → 1.0401; '-20.4892%' → -0.204892."""
    s = raw.replace(",", "").strip()
    if not s or s == "-":
        return None
    if s.endswith("%"):
        return float(s[:-1]) / 100
    return float(s)


def parse_report(report_path: Path) -> dict[str, float]:
    """解析报告 .md, 返回 7 项指标 dict.

    Args:
        report_path: report_v<N>.md 或 report_signals_v<N>.md 的路径

    Returns:
        {annual_return: 0.073, sharpe: 0.96, max_drawdown: -0.20, ...}
        缺失的指标不会出现在 dict 中
    """
    if not report_path.exists():
        raise FileNotFoundError(f"报告不存在: {report_path}")

    text = report_path.read_text(encoding="utf-8")
    metrics: dict[str, float] = {}
    for key, pattern in METRIC_KEYS.items():
        m = re.search(pattern, text)
        if m:
            v = _parse_value(m.group(1))
            if v is not None:
                metrics[key] = v
    return metrics


# ========== 报告列表 (严格过滤 monitor 报告) ==========

_PARAMS_REPORT_RE = re.compile(r"^report_v(\d+)\.md$")
_WEIGHT_REPORT_RE = re.compile(r"^report_signals_v(\d+)\.md$")
_MONITOR_REPORT_RE = re.compile(r"^report_(?:signals_)?v\d+_\d{4}-\d{2}-\d{2}.*\.md$")


def _get_reports_dir(name: str, mode: str) -> Path:
    """获取报告目录."""
    sub = "reportParams" if mode == "params" else "reportWeight"
    return subjects_dir() / name / sub


def list_all_reports(name: str, mode: str) -> list[tuple[int, Path]]:
    """列出所有 standard reports, 按 v<N> 升序.

    Args:
        name: 策略名
        mode: "params" 或 "weight"

    Returns:
        [(1, Path), (2, Path), ...] 按 v 数字升序
    """
    reports_dir = _get_reports_dir(name, mode)
    if not reports_dir.exists():
        return []
    pattern = _PARAMS_REPORT_RE if mode == "params" else _WEIGHT_REPORT_RE
    out: list[tuple[int, Path]] = []
    for p in reports_dir.iterdir():
        if not p.is_file():
            continue
        m = pattern.match(p.name)
        if m:
            out.append((int(m.group(1)), p))
    out.sort(key=lambda x: x[0])
    return out


def find_monitor_reports(name: str, mode: str) -> list[Path]:
    """列出所有 monitor 报告 (带 _YYYY-MM-DD 后缀), 仅供调试用.

    Pipeline 永远不用这些.
    """
    reports_dir = _get_reports_dir(name, mode)
    if not reports_dir.exists():
        return []
    return [p for p in reports_dir.iterdir() if p.is_file() and _MONITOR_REPORT_RE.match(p.name)]


def parse_latest_report(name: str, mode: str) -> dict[str, float]:
    """解析最新一份 standard report, 返回指标 dict.

    严格匹配 `report_v<N>.md` (params) 或 `report_signals_v<N>.md` (weight),
    忽略 monitor 报告.

    Raises:
        FileNotFoundError: 没有 standard report 时
    """
    all_reports = list_all_reports(name, mode)
    if not all_reports:
        reports_dir = _get_reports_dir(name, mode)
        monitor_files = find_monitor_reports(name, mode)
        raise FileNotFoundError(
            f"{reports_dir} 下没有 standard report。\n"
            f"  - 期望文件名: report_v<N>.md 或 report_signals_v<N>.md\n"
            f"  - 找到的 monitor 文件: {[p.name for p in monitor_files[:3]]}\n"
            f"  - 原因: monitor 模式生成的报告带 _YYYY-MM-DD 后缀, 不被 pipeline 识别"
        )

    latest_n, latest_path = all_reports[-1]
    log.debug(f"  [parse_latest_report] mode={mode} 选 v{latest_n}: {latest_path.name}")
    return parse_report(latest_path)


def parse_all_reports(name: str, mode: str) -> list[tuple[int, dict[str, float]]]:
    """解析所有 standard reports.

    Returns:
        [(1, {annual_return: 0.05, ...}), (2, {...}), ...] 按 v 升序
    """
    return [(v, parse_report(p)) for v, p in list_all_reports(name, mode)]


__all__ = [
    "parse_report",
    "list_all_reports",
    "find_monitor_reports",
    "parse_latest_report",
    "parse_all_reports",
]
