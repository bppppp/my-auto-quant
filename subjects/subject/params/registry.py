"""ParamDef + register_param 全局注册表.

见 PARTS_SUMMARY.md §4.

用法 (Python 不支持 ``@decorator`` 直接修饰变量赋值, 用**直接调用**模式)::

    from subject.params import ParamDef, register_param

    VOL_BREAKOUT = register_param(ParamDef(
        name="vol_breakout_threshold",
        default=1.5,
        range=(1.0, 3.0),
        type=float,
        description="量能放大倍数阈值",
    ))
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ParamDef:
    """参数元数据定义 (不可变, 用作注册键).

    Attributes:
        name: 参数名 (与 spec.params[i].name 一致).
        default: 默认值.
        range: (min, max) 闭区间.
        type: float | int | str.
        description: 中文描述.
    """

    name: str
    default: Any
    range: tuple[float, float]
    type: type
    description: str = ""


# 全局注册表: name -> ParamDef
_REGISTRY: dict[str, ParamDef] = {}


def register_param(p: ParamDef) -> ParamDef:
    """装饰器 / 直接调用: 将 ParamDef 注册到全局表.

    同时支持两种用法::

        @register_param
        VOL_BREAKOUT = ParamDef(...)

        # 或
        register_param(ParamDef(...))
    """
    if not isinstance(p, ParamDef):
        raise TypeError(f"register_param expects ParamDef, got {type(p).__name__}")
    if p.name in _REGISTRY:
        # 同名重复注册 → 警告但不抛错 (允许策略覆盖公共)
        existing = _REGISTRY[p.name]
        if existing != p:
            import warnings
            warnings.warn(
                f"ParamDef name={p.name!r} already registered with different "
                f"definition; overriding."
            )
    _REGISTRY[p.name] = p
    return p


def get_param(name: str) -> ParamDef | None:
    """按名取 ParamDef, 未注册返回 None."""
    return _REGISTRY.get(name)


def all_params() -> dict[str, ParamDef]:
    """返回当前所有已注册 ParamDef 的快照."""
    return dict(_REGISTRY)
