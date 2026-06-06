"""沪深 300 股票池. 见 subject.md §3 / data/config.py.

通过 importlib 动态加载 ``data/config.py`` (避免污染 sys.path).
"""
from __future__ import annotations

import importlib.util
from pathlib import Path


_data_config_path = Path(__file__).resolve().parents[4] / "data" / "config.py"
_spec = importlib.util.spec_from_file_location("data_config", _data_config_path)
if _spec is None or _spec.loader is None:
    raise ImportError(f"Cannot load data/config.py from {_data_config_path}")
_data_config = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_data_config)

# 带交易所后缀的 HS300 codes (与 data_loader.preprocess 一致)
_RAW_HS300: list[str] = _data_config.HS300


def _add_suffix(code: str) -> str:
    if code.startswith(("60", "68")):
        return code + ".SH"
    if code.startswith(("00", "30", "20")):
        return code + ".SZ"
    if code.startswith(("92", "83")):
        return code + ".BJ"
    return code


HS300_CODES: list[str] = [_add_suffix(c) for c in _RAW_HS300]
"""沪深 300 全部成分股, 带交易所后缀, 与 data_loader preprocess 后的 ``df['代码']`` 对齐."""
