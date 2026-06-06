"""
strategies — my-quant3 策略生成系统

子包:
    config        — LLMSettings + RuntimeSettings
    strategies    — CLI 入口(本目录的 strategies.py)
    agents        — 4 模式实现 + 共享工具 + 评估 + 监听
        base_agent, generate, optimize, factor_weights, quality_eval, watcher
        prompts/{generate,optimize,factor_weights,quality_eval}.md
"""

__version__ = "0.1.0"
