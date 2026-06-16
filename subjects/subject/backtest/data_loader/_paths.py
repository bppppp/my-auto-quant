"""数据根路径配置 — 所有数据目录的唯一入口.

默认: ``<project_root>/data`` (subject package 4 层父目录 + data/)
覆盖: 环境变量 ``DATA_ROOT`` / ``DATA_SOURCE``.

``subject_structure.md §5`` + ``subject.md §3.0``.
"""
from __future__ import annotations

import os
from pathlib import Path

# subject/backtest/data_loader/_paths.py → 5 层父目录 = 项目根
_THIS = Path(__file__).resolve()
_DEFAULT_DATA_ROOT = _THIS.parents[4] / "data"

# ===== 数据源切换 =====
# 'gold' (金玥) / 'bs' (baostock 前复权, 跟 JQ MAE 仅 0.6 元)
DATA_SOURCE: str = os.environ.get("DATA_SOURCE", "bs")

_DATA_ROOT: Path = Path(os.environ.get("DATA_ROOT", str(_DEFAULT_DATA_ROOT)))

if DATA_SOURCE == "bs":
    STOCK_DIR: Path = _DATA_ROOT / "data-by-stock-bs"
    DAY_DIR: Path = _DATA_ROOT / "data-by-day-bs"
    STOCK_FILE_SUFFIX: str = ".csv"          # {code}.csv
    DAY_FILE_SUFFIX: str = ".csv"            # {date}.csv
else:
    STOCK_DIR: Path = _DATA_ROOT / "data-by-stock"
    DAY_DIR: Path = _DATA_ROOT / "data-by-day"
    STOCK_FILE_SUFFIX: str = "_金玥数据.csv"  # {code}_金玥数据.csv
    DAY_FILE_SUFFIX: str = "_金玥数据.csv"    # {date}_金玥数据.csv

# 因子目录 (独立于数据源, 根据数据源自动区分)
if DATA_SOURCE == "bs":
    FACTOR_DIR: Path = _DATA_ROOT / "data-by-stock-factor-bs"
else:
    FACTOR_DIR: Path = _DATA_ROOT / "data-by-stock-factor"

# 向后兼容
DATA_ROOT: Path = _DATA_ROOT
"""行情数据根目录."""

STOCK_FILE_PATTERN: str = f"*{STOCK_FILE_SUFFIX}"
"""用于 glob 匹配 by-stock 文件."""
