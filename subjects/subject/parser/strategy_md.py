"""策略 spec YAML frontmatter 解析器.

见 PARTS_SUMMARY.md §3 / subject_structure.md §4.2 / subject.md §1.

文件格式::

    ---
    name: <strategy_name>
    factors:
    - name: ma_5
      ...
    ---
    <Markdown body>
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


# 必填 frontmatter 段 (subject.md §1.1)
_REQUIRED_FRONTMATTER_KEYS = (
    "name",
    "factors",
    "entry_signals",
    "exit_signals",
    "params",
    "test_universe",
    "targets",
)


def parse_strategy_spec(path: str | Path) -> dict[str, Any]:
    """解析策略 spec 文件, 返回 frontmatter dict.

    Args:
        path: ``<strategy>/<name>_original.md`` 或 ``strategiesParam/<name>_v<n>.md`` 路径.

    Returns:
        dict: frontmatter 内容 (含 name / factors / entry_signals / exit_signals /
            params / test_universe / targets 等段).

    Raises:
        FileNotFoundError: 文件不存在.
        ValueError: 缺少 ``---`` 包裹的 YAML frontmatter, 或必填段缺失.
        yaml.YAMLError: YAML 格式错误.
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Strategy spec not found: {p}")

    text = p.read_text(encoding="utf-8")

    # 找到第一个 --- 行
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError(f"{p}: file must start with '---' (YAML frontmatter)")

    # 找第二个 --- 行
    end_idx = None
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            end_idx = i
            break
    if end_idx is None:
        raise ValueError(f"{p}: missing closing '---' for YAML frontmatter")

    yaml_text = "\n".join(lines[1:end_idx])
    frontmatter = yaml.safe_load(yaml_text)
    if not isinstance(frontmatter, dict):
        raise ValueError(f"{p}: YAML frontmatter must parse to a dict")

    _validate_frontmatter(p, frontmatter)
    return frontmatter


def _validate_frontmatter(path: Path, fm: dict[str, Any]) -> None:
    """校验必填段. 缺失任何一项 → ValueError."""
    missing = [k for k in _REQUIRED_FRONTMATTER_KEYS if k not in fm]
    if missing:
        raise ValueError(
            f"{path}: missing required frontmatter keys: {missing}. "
            f"Required: {list(_REQUIRED_FRONTMATTER_KEYS)}"
        )
    # 段类型校验
    for key in ("factors", "entry_signals", "exit_signals", "params", "test_universe"):
        v = fm[key]
        if not isinstance(v, list):
            raise ValueError(
                f"{path}: frontmatter[{key!r}] must be a list, got {type(v).__name__}"
            )
