"""回测日志工具. 见 subject.md §3 (数据格式) / subject_structure.md §5.

提供双 handler logger:
- FileHandler → subjects/{strategy_name}/log/backtest_{timestamp}.log (INFO 完整保存)
- StreamHandler → console (WARNING 起, 避免 backtest 跑时刷屏)

⚠️ 2026-06-15 调整: console handler 改 WARNING — 之前 INFO 会让 backtest 跑 300 只
股票时刷几万行, 在 autoRun 流水线或重定向日志里累积几个 G. file handler 保持 INFO
完整记录, 调试时去 subjects/<name>/log/backtest_*.log 看.

日志格式: ``YYYY-MM-DD HH:MM:SS [LEVEL] message``
"""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path


_LOG_FORMAT = "%(asctime)s [%(levelname)s] %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# FileHandler 用 level (默认 INFO, 完整记录)
# StreamHandler (console) 用 CONSOLE_LEVEL (默认 WARNING, 不刷屏)
CONSOLE_LEVEL = logging.WARNING


def setup_backtest_logger(
    strategy_name: str,
    subjects_dir: str | Path,
    level: int = logging.INFO,
) -> tuple[logging.Logger, Path]:
    """为指定策略创建回测 logger (双 handler: 文件 + console).

    Args:
        strategy_name: 策略目录名, 用于 logger 命名 + log 文件路径.
        subjects_dir: subjects 根目录 (含所有策略的目录), 一般为 ``Path(".")`` (cwd = subjects/).
        level: 日志级别, 同时影响 file handler. 默认 INFO.

    Returns:
        (logger, log_file_path) 元组. log_file_path 可传给 report / 给用户提示.
    """
    subjects_dir = Path(subjects_dir)
    log_dir = subjects_dir / strategy_name / "log"
    log_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    log_file = log_dir / f"backtest_{timestamp}.log"

    # logger 命名按策略隔离 (避免多策略并行 / 重入时冲突)
    logger_name = f"backtest.{strategy_name}"
    logger = logging.getLogger(logger_name)
    logger.setLevel(level)
    # 清理可能的旧 handler (重跑场景)
    logger.handlers.clear()

    formatter = logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT)

    # FileHandler — INFO 完整保存 (调试时查)
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setLevel(level)
    fh.setFormatter(formatter)
    logger.addHandler(fh)

    # StreamHandler (console) — WARNING 起, 避免 backtest 跑 300 只股票刷屏
    ch = logging.StreamHandler()
    ch.setLevel(CONSOLE_LEVEL)
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    # 不让 root logger 重复打印 (避免双输出)
    logger.propagate = False

    logger.info(f"=== Log file: {log_file} ===")
    return logger, log_file


def get_backtest_logger(strategy_name: str) -> logging.Logger:
    """获取已创建的 logger (供 runner 内部模块复用). 不存在则返回 root 警告."""
    return logging.getLogger(f"backtest.{strategy_name}")


__all__ = ["setup_backtest_logger", "get_backtest_logger"]
