"""
pipeline.llm_client — LLM 客户端 (复用 strategies.agents.base_agent.build_llm)

不重新实现 LLM 调用, 直接 import 已有模块.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

# 把项目根加入 sys.path, 让 strategies.config / base_agent 可导入
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


def get_llm(temperature: float = 0.3, enable_thinking: bool = True) -> Any:
    """构造 LLM 实例.

    复用 strategies.agents.base_agent.build_llm.

    Args:
        temperature: 0.3 for generate, 0.7 for optimize 等
        enable_thinking: 是否启用 think 模式 (默认 True)

    Returns:
        LLM 实例, 有 invoke(system_prompt, user_prompt) -> str 方法
    """
    from strategies.agents.base_agent import build_llm
    from strategies.config import get_llm_settings

    settings = get_llm_settings(
        temperature=temperature,
        enable_thinking=enable_thinking,
    )
    return build_llm(settings)


def get_llm_settings(temperature: float = 0.3, enable_thinking: bool = True) -> Any:
    """仅获取 settings (不开 LLM 连接)."""
    from strategies.config import get_llm_settings as _get
    return _get(temperature=temperature, enable_thinking=enable_thinking)


__all__ = ["get_llm", "get_llm_settings"]
