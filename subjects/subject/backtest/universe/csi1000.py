"""中证 1000 股票池. 见 subject.md §3 / data/config.py.

通过 importlib 动态加载 ``data/config.py`` (避免污染 sys.path).
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

from .hs300 import _add_suffix  # 复用 _add_suffix


_data_config_path = Path(__file__).resolve().parents[4] / "data" / "config.py"
_spec = importlib.util.spec_from_file_location("data_config", _data_config_path)
if _spec is None or _spec.loader is None:
    raise ImportError(f"Cannot load data/config.py from {_data_config_path}")
_data_config = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_data_config)

# 带交易所后缀的 CSI1000 codes
_RAW_CSI1000: list[str] = _data_config.CSI1000

CSI1000_CODES: list[str] = [_add_suffix(c) for c in _RAW_CSI1000]
"""中证 1000 全部成分股, 带交易所后缀, 与 data_loader preprocess 后的 ``df['代码']`` 对齐."""
