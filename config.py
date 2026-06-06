"""
my-quant3 — LLM 配置 (LLM Configuration)

策略生成系统调 LLM 用的全局配置。所有运行时值从环境变量读取,
未设置时使用默认占位（API_KEY 必填，缺失会抛异常）。

字段:
    LLM_BASE_URL   OpenAI 兼容端点（默认: minimaxi）
    LLM_MODEL      模型名（默认: MiniMax-M3）
    LLM_API_KEY    必填（从 .env 读；缺失 → 抛异常）
    temperature    默认 0.7（generate 用 0.3）
    max_tokens     默认 32768（留余量装策略 narrative）
    timeout        默认 180s

使用:
    from config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL, get_chat_kwargs
    kwargs = get_chat_kwargs(temperature=0.3)   # build_llm 时使用
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any


# ===== 加载项目根 .env 文件(在 import 期生效)=====
def _load_env_file() -> None:
    """把 .env 中所有 KEY=VALUE 加载到 os.environ(仅在尚未设置时)。"""
    env_path = Path(__file__).resolve().parent / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        # 不覆盖 shell env 中已显式设置的
        os.environ.setdefault(key, value)


_load_env_file()


# ===== LLM 端点配置（默认 minimaxi / MiniMax-M3，可用 env 覆盖）=====
LLM_BASE_URL: str = os.getenv("LLM_BASE_URL", "https://api.minimaxi.com/v1")
LLM_MODEL: str = os.getenv("LLM_MODEL", "MiniMax-M3")
LLM_API_KEY: str = os.getenv("LLM_API_KEY", "")

# ===== 推理参数 =====
DEFAULT_TEMPERATURE: float = float(os.getenv("LLM_TEMPERATURE", "0.7"))
GENERATE_TEMPERATURE: float = float(os.getenv("LLM_TEMPERATURE_GENERATE", "0.3"))
MAX_TOKENS: int = int(os.getenv("LLM_MAX_TOKENS", "100000"))
TIMEOUT: int = int(os.getenv("LLM_TIMEOUT", "180"))


def require_api_key() -> str:
    """读 .env 文件加载 API key,若仍缺失则抛异常。

    加载顺序: os.environ → 项目根 .env
    """
    global LLM_API_KEY
    if LLM_API_KEY:
        return LLM_API_KEY

    # 尝试从项目根 .env 加载
    env_path = Path(__file__).resolve().parent / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key == "LLM_API_KEY" and value:
                os.environ["LLM_API_KEY"] = value
                LLM_API_KEY = value
                return LLM_API_KEY

    raise RuntimeError(
        "LLM_API_KEY 未配置。请在 .env 文件或环境变量中设置 LLM_API_KEY。"
    )


def get_chat_kwargs(*, temperature: float | None = None) -> dict[str, Any]:
    """构造传给 LLM chat 调用的 kwargs。

    Args:
        temperature: 覆盖默认温度（generate 模式通常传 0.3）

    Returns:
        dict 含 base_url / api_key / model / temperature / max_tokens / timeout
    """
    api_key = require_api_key()
    return {
        "base_url": LLM_BASE_URL,
        "api_key": api_key,
        "model": LLM_MODEL,
        "temperature": temperature if temperature is not None else DEFAULT_TEMPERATURE,
        "max_tokens": MAX_TOKENS,
        "timeout": TIMEOUT,
    }


__all__ = [
    "LLM_BASE_URL",
    "LLM_MODEL",
    "LLM_API_KEY",
    "DEFAULT_TEMPERATURE",
    "GENERATE_TEMPERATURE",
    "MAX_TOKENS",
    "TIMEOUT",
    "require_api_key",
    "get_chat_kwargs",
]
