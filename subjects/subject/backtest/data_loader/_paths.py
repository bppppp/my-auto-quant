"""数据根路径配置.

默认: ``<project_root>/data`` (subject package 4 层父目录 + data/)
覆盖: 环境变量 ``DATA_ROOT``.

``subject_structure.md §5`` + ``subject.md §3.0``.
"""
from __future__ import annotations

import os
from pathlib import Path

# subject/backtest/data_loader/_paths.py → 5 层父目录 = 项目根
# parents[0] = data_loader/, parents[1] = backtest/, parents[2] = subject/,
# parents[3] = subjects/, parents[4] = 项目根 (my-quant3/)
_THIS = Path(__file__).resolve()
_DEFAULT_DATA_ROOT = _THIS.parents[4] / "data"

DATA_ROOT: Path = Path(os.environ.get("DATA_ROOT", str(_DEFAULT_DATA_ROOT)))
"""行情数据根目录, 包含 ``data-by-stock/`` 和 ``data-by-day/`` 两个子目录."""
