"""
pipeline.log_utils — 统一日志

- 控制台 + 文件双 handler
- 文件位置: autoRun/logs/pipeline_<date>.log
- 提供 banner / section / log_print 等便利函数
"""
from __future__ import annotations

import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from .config import auto_run_dir

# Windows: 强制 UTF-8 输出 (避免 emoji/中文乱码)
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

_LOG_FORMAT = "%(asctime)s [%(levelname)s] %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
_INITIALIZED = False


def get_logger(name: str = "pipeline") -> logging.Logger:
    """获取 pipeline logger (单例)."""
    global _INITIALIZED
    logger = logging.getLogger(name)
    if _INITIALIZED:
        return logger

    logger.setLevel(logging.INFO)
    logger.propagate = False

    # 控制台
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(logging.Formatter(_LOG_FORMAT, _DATE_FORMAT))
    logger.addHandler(console)

    # 文件
    log_dir = auto_run_dir() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")
    log_file = log_dir / f"pipeline_{today}.log"
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(logging.Formatter(_LOG_FORMAT, _DATE_FORMAT))
    logger.addHandler(file_handler)

    # 实时 flush: FileHandler 换成行缓冲 subclass, 避免长 subprocess 期间看不到日志
    class _LineBufferedFileHandler(logging.FileHandler):
        def emit(self, record):
            super().emit(record)
            try:
                self.flush()
            except Exception:
                pass

    # 把刚才加的 file_handler 替换为行缓冲版本
    logger.removeHandler(file_handler)
    file_handler.close()
    file_handler = _LineBufferedFileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(logging.Formatter(_LOG_FORMAT, _DATE_FORMAT))
    logger.addHandler(file_handler)

    _INITIALIZED = True
    logger.info(f"━━━ pipeline 启动 (log: {log_file}) ━━━")
    return logger


def banner(title: str, char: str = "━", width: int = 60) -> None:
    """打印大标题横幅."""
    line = char * width
    log = get_logger()
    log.info(line)
    log.info(f"  {title}")
    log.info(line)


def section(title: str) -> None:
    """打印小节标题."""
    log = get_logger()
    log.info(f"── {title} ──")


def log_print(msg: str, level: int = logging.INFO) -> None:
    """打印并记录一条消息."""
    get_logger().log(level, msg)


# 兼容旧 API: strategies.agents.log_utils 里的 log_overwrite 等
def log_overwrite(msg: str) -> None:
    """覆盖式打印 (用于进度条等)."""
    sys.stdout.write(f"\r{msg}")
    sys.stdout.flush()


__all__ = [
    "get_logger",
    "banner",
    "section",
    "log_print",
    "log_overwrite",
]
