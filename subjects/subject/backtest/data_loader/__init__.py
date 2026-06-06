"""数据加载层 (params mode → data-by-stock/, weight mode → data-by-day/).

见 subject.md §3 + §5 (数据源硬绑定) + subject_structure.md §5.

入口:
- :func:`load_stock` —— params 模式, 按代码加载单股全历史
- :func:`load_day` —— weight 模式, 按日期加载单日横截面
"""

from ._paths import DATA_ROOT
from .preprocess import preprocess
from .by_stock import load_stock
from .by_day import load_day

__all__ = ["DATA_ROOT", "preprocess", "load_stock", "load_day"]
