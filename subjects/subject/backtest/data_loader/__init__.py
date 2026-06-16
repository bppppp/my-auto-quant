"""数据加载层 (params mode → data-by-stock/, weight mode → data-by-day/).

见 subject.md §3 + §5 (数据源硬绑定) + subject_structure.md §5.

入口:
- :func:`load_stock` —— params 模式, 按代码加载单股全历史
- :func:`load_day` —— weight 模式, 按日期加载单日横截面
"""

from ._paths import DATA_ROOT, DATA_SOURCE, STOCK_DIR, DAY_DIR, FACTOR_DIR, STOCK_FILE_SUFFIX, STOCK_FILE_PATTERN
from .preprocess import preprocess
from .by_stock import load_stock
from .by_day import load_day
from .by_stock_factor import try_load_stock_factor, get_factor_cache_stats, clear_factor_cache

__all__ = [
    "DATA_ROOT", "DATA_SOURCE", "STOCK_DIR", "DAY_DIR", "FACTOR_DIR",
    "STOCK_FILE_SUFFIX", "STOCK_FILE_PATTERN",
    "preprocess", "load_stock", "load_day",
    "try_load_stock_factor", "get_factor_cache_stats", "clear_factor_cache",
]
