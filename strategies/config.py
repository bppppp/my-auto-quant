"""
strategies.config — 运行时配置 (LLMSettings + RuntimeSettings)

集中管理 LLM 调用参数 + 策略生成系统的运行时可调参数。
环境变量优先级最高，未设置时使用 defaults。

使用:
    from strategies.config import LLMSettings, RuntimeSettings, get_llm_settings
    llm = get_llm_settings(temperature=0.3)
    rt = RuntimeSettings()
    print(rt.self_eval_max_retries)
"""

from __future__ import annotations

import os
from dataclasses import dataclass


# ====================================================================
# LLM Settings — 单次 LLM 调用参数
# ====================================================================
@dataclass(frozen=True)
class LLMSettings:
    """LLM 调用参数（不可变，便于跨调用复用同一 LLM 实例）。"""

    base_url: str
    model: str
    api_key: str
    temperature: float
    max_tokens: int
    timeout: int
    enable_thinking: bool = False
    # 不同 provider 的 thinking.type 取值不同:
    #   DeepSeek V4: "enabled" / "disabled"
    #   MiniMax:     "adaptive" / "disabled"  (用 "enabled" 会被 API 拒 400)
    # 切换 provider 时只需在 .env 改 LLM_THINKING_TYPE,不改代码。
    thinking_type: str = "adaptive"
    # DeepSeek 思考强度:low|medium|high|max;空字符串=不传该字段(MiniMax 不支持,留空)
    reasoning_effort: str = "high"

    def to_chat_kwargs(self) -> dict:
        """构造传给 chat 调用的 kwargs（不暴露 api_key 的 logging 安全版本）。"""
        return {
            "base_url": self.base_url,
            "api_key": self.api_key,
            "model": self.model,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "timeout": self.timeout,
        }


def get_llm_settings(
    *,
    temperature: float | None = None,
    enable_thinking: bool = False,
) -> LLMSettings:
    """根据环境变量构造 LLMSettings。

    Args:
        temperature: 覆盖默认温度（None = 走环境变量默认）
        enable_thinking: 是否启用 think 模式（generate 持续开启 / mode 2/3 周期开启）。
                         可被 LLM_ENABLE_THINKING env 覆盖(0=强制关, 1=强制开)
    """
    # 延迟导入避免循环:根 config.py 在项目根,本文件 strategies/config.py 在 strategies/
    # 路径深度:strategies/config.py → strategies/ → my-quant3/(=parent.parent)
    import sys
    from pathlib import Path
    _root = Path(__file__).resolve().parent.parent  # my-quant3/
    if str(_root) not in sys.path:
        sys.path.insert(0, str(_root))

    from config import (  # type: ignore  # 根 config.py
        DEFAULT_TEMPERATURE,
        GENERATE_TEMPERATURE,
        LLM_API_KEY,
        LLM_BASE_URL,
        LLM_MODEL,
        MAX_TOKENS,
        TIMEOUT,
        require_api_key,
    )

    api_key = LLM_API_KEY or require_api_key()

    # env override for think mode
    env_think = os.getenv("LLM_ENABLE_THINKING")
    if env_think is not None:
        if env_think in ("0", "false", "False", "no", "NO"):
            enable_thinking = False
        elif env_think in ("1", "true", "True", "yes", "YES"):
            enable_thinking = True
        # other values: keep the caller's value

    return LLMSettings(
        base_url=os.getenv("LLM_BASE_URL", LLM_BASE_URL),
        model=os.getenv("LLM_MODEL", LLM_MODEL),
        api_key=api_key,
        temperature=temperature if temperature is not None else GENERATE_TEMPERATURE,
        max_tokens=int(os.getenv("LLM_MAX_TOKENS", str(MAX_TOKENS))),
        timeout=int(os.getenv("LLM_TIMEOUT", str(TIMEOUT))),
        enable_thinking=enable_thinking,
        thinking_type=os.getenv("LLM_THINKING_TYPE", "adaptive"),
        reasoning_effort=os.getenv("LLM_REASONING_EFFORT", "high"),
    )


# ====================================================================
# Runtime Settings — 策略生成系统运行时参数
# ====================================================================
@dataclass(frozen=True)
class RuntimeSettings:
    """策略生成/调优系统的运行时可调参数。"""

    self_eval_max_retries: int = 20  # 模式 1(generate)—— 直到通过 90% 阈值
    debounce_seconds: float = 5.0
    watch_create_only: bool = True
    max_listen_iterations: int = 20
    max_reports_reference: int = 5
    tune_cycle_rounds: int = 4  # 3+1 think 策略的周期长度(已废弃,前 3 模式都强制 think)
    # 各模式独立的 LLM 重试上限
    optimize_max_retries: int = 3     # 模式 2(optimize)
    factor_weights_max_retries: int = 3  # 模式 3(factor_weights)
    # 连接类错误(网络/SSL/超时)重试上限——配错 endpoint 时不卡几小时
    connection_max_retries: int = 2

    @classmethod
    def from_env(cls) -> "RuntimeSettings":
        """从环境变量构造(可覆盖默认值)。"""
        return cls(
            self_eval_max_retries=int(os.getenv("SELF_EVAL_MAX_RETRIES", "20")),
            debounce_seconds=float(os.getenv("DEBOUNCE_SECONDS", "5.0")),
            watch_create_only=os.getenv("WATCH_CREATE_ONLY", "1") not in ("0", "false", "False"),
            max_listen_iterations=int(os.getenv("MAX_LISTEN_ITERATIONS", "20")),
            max_reports_reference=int(os.getenv("MAX_REPORTS_REFERENCE", "5")),
            tune_cycle_rounds=int(os.getenv("TUNE_CYCLE_ROUNDS", "4")),
            optimize_max_retries=int(os.getenv("OPTIMIZE_MAX_RETRIES", "3")),
            factor_weights_max_retries=int(os.getenv("FACTOR_WEIGHTS_MAX_RETRIES", "3")),
            connection_max_retries=int(os.getenv("CONNECTION_MAX_RETRIES", "2")),
        )


__all__ = [
    "LLMSettings",
    "RuntimeSettings",
    "get_llm_settings",
]
