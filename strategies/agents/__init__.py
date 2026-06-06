"""
strategies.agents — 策略生成 4 模式实现 + 共享工具

模块:
    base_agent     — 共享工具(路径/.md读写/报告/硬校验/JSON解析/G锁死)
    generate       — 模式 1(generate)
    optimize       — 模式 2(optimize once/watch)
    factor_weights — 模式 3(factor_weights once/watch)
    quality_eval   — 业务质量评估(仅模式 1)
    watcher        — watchdog + debounce(watch 模式用)
    prompts/       — system prompt 源文件
"""

__all__ = [
    "base_agent",
    "generate",
    "optimize",
    "factor_weights",
    "quality_eval",
    "watcher",
]
