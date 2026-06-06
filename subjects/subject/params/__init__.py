"""参数元类型 —— 见 PARTS_SUMMARY.md §4.

公共库**只放** ParamDef dataclass + @register_param 装饰器, **不放** 具体参数值
(具体值跟随策略 spec).
"""

from .registry import ParamDef, register_param, get_param, all_params

__all__ = ["ParamDef", "register_param", "get_param", "all_params"]
