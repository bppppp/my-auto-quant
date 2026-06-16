"""
pipeline.log_utils — 统一日志

- 控制台 + 文件双 handler
- 文件位置: autoRun/logs/pipeline_<date>.log
- 提供 banner / section / log_print 等便利函数

⚠️ 2026-06-15 精简: 文件大小 50MB → 5MB, 保留份数 3 → 1, 减少历史日志堆积.
"""
from __future__ import annotations

import logging
import os
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

# 文件大小上限 (5MB) + 保留份数 (1 份备份)
MAX_LOG_SIZE = 5 * 1024 * 1024
MAX_LOG_BACKUPS = 1


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

    # 文件 — 5MB 轮转, 保留 1 份
    log_dir = auto_run_dir() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")
    log_file = log_dir / f"pipeline_{today}.log"

    class _RotatingFileHandler(logging.FileHandler):
        """带大小限制的文件 handler，超过阈值则轮转（重命名为 .1, ...）"""
        def emit(self, record):
            try:
                self._maybe_rotate()
                super().emit(record)
                self.flush()
            except Exception:
                pass

        def _maybe_rotate(self):
            if self.baseFilename and os.path.exists(self.baseFilename):
                try:
                    size = os.path.getsize(self.baseFilename)
                    if size >= self.MAX_LOG_SIZE:
                        self._rotate_log()
                except Exception:
                    pass

        def _rotate_log(self):
            """轮转日志文件，最多保留 MAX_LOG_BACKUPS 份"""
            base = self.baseFilename
            # 先删最老的备份
            oldest = f"{base}.{MAX_LOG_BACKUPS}"
            if os.path.exists(oldest):
                try:
                    os.unlink(oldest)
                except Exception:
                    pass
            # 依次前移
            for i in range(MAX_LOG_BACKUPS - 1, 0, -1):
                old = f"{base}.{i}"
                new = f"{base}.{i + 1}"
                if os.path.exists(old):
                    try:
                        os.rename(old, new)
                    except Exception:
                        pass
            # 当前 → .1
            try:
                os.rename(base, f"{base}.1")
            except Exception:
                pass
            # 重新打开文件
            self.close()
            self.stream = None
            self._open()

    file_handler = _RotatingFileHandler(log_file, encoding="utf-8")
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
