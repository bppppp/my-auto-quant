"""
strategies.agents.log_utils — 统一打印 + 日志落盘

所有 print() 调用都走本模块的 `log_print()`,同时输出到:
  1. stdout(控制台)—— 沿用原本 print 行为,加毫秒级时间戳 + 标签前缀
  2. strategies/log/run.log(追加模式)—— 供事后排查

用法:
    from strategies.agents.log_utils import log_print
    log_print("[generate] 正在调 LLM...")
    log_print("[generate] LLM 返回", f"耗时 {elapsed:.1f}s")
"""
from __future__ import annotations

import sys
import threading
from datetime import datetime
from pathlib import Path


# Windows 终端默认 GBK,会让 CJK/emoji 乱码。启动时把 stdout/stderr 强制包成 utf-8。
def _try_reconfigure_stdout_utf8() -> None:
    import io
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream is None:
            continue
        # 拿到底层 binary buffer,重新包一层 utf-8 TextIOWrapper
        raw = getattr(stream, "buffer", None)
        if raw is None:
            continue
        try:
            new_stream = io.TextIOWrapper(
                raw,
                encoding="utf-8",
                errors="replace",
                line_buffering=True,
            )
            setattr(sys, stream_name, new_stream)
        except Exception:
            pass


_try_reconfigure_stdout_utf8()


# 日志文件路径:strategies/log/run.log
_LOG_DIR = Path(__file__).resolve().parent.parent / "log"
_LOG_DIR.mkdir(parents=True, exist_ok=True)
_LOG_FILE = _LOG_DIR / "run.log"

# 文件句柄懒加载(单进程足够,watch 模式也在主线程跑回调)
_FH = None
_FH_LOCK = threading.Lock()


def _get_fh():
    global _FH
    if _FH is None:
        _FH_LOCK.acquire()
        try:
            if _FH is None:
                _FH = _LOG_FILE.open("a", encoding="utf-8")
        finally:
            _FH_LOCK.release()
    return _FH


def _ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]  # 毫秒


def _safe_stdout_write(line: str) -> None:
    """stdout 写入,GBK 等窄字符终端下把不可编码字符降级为 ?。

    优先尝试原样写入(支持 reconfigure 后的 utf-8 / linux 终端);
    失败则降级为 ASCII 兼容输出(emoji 等替换为 ?)。
    """
    try:
        sys.stdout.write(line)
        sys.stdout.flush()
        return
    except UnicodeEncodeError:
        pass
    # 降级:逐字符 encode,失败的用 ? 替代
    enc = sys.stdout.encoding or "utf-8"
    safe = line.encode(enc, errors="replace").decode(enc, errors="replace")
    sys.stdout.write(safe)
    sys.stdout.flush()


def log_print(*args, **kwargs) -> None:
    """同时输出到 stdout + log 文件。

    自动加上 [HH:MM:SS.mmm] 时间戳前缀;
    默认 end="\\n",与 print 一致;不强制 flush(由调用方控制)。
    Windows GBK 等窄字符终端下会自动降级,emoji 等不可编码字符变成 ?。

    重要行为:
      - **stdout** 严格遵守 `end` 参数(传 `end=""` 可实现行内覆盖,
        配合 `\\r` 用,例如 LLM 调用的"⏳ 等待..."+"\\r✓ 返回完成"模式)
      - **log 文件** 始终以换行结尾(忽略 `end`),保证每行日志独立成行,
        不会被下一条 timestamp 前缀粘连成一行
    """
    sep = kwargs.get("sep", " ")
    end = kwargs.get("end", "\n")
    msg = sep.join(str(a) for a in args)
    ts = _ts()
    # stdout:遵守 end(允许行内覆盖)
    _safe_stdout_write(f"[{ts}] {msg}{end}")
    # log 文件:始终换行,保持每行独立可被 grep/awk 解析
    try:
        fh = _get_fh()
        fh.write(f"[{ts}] {msg}\n")
        fh.flush()
    except Exception:
        # 日志落盘失败不能影响主流程
        pass


def log_overwrite(*args, **kwargs) -> None:
    """行内覆盖上一条 stdout 输出（log 文件仍独立成行）。

    用法: 配合 `log_print(..., end="")` 的"⏳ 等待"行,
    后续用 `log_overwrite("✓ 返回完成 | ...")` 覆盖上一行 stdout,
    同时 log 文件也写入一行干净的"✓ 返回完成"。

    实现:
      - stdout: `\\r\\033[2K` (回车 + ANSI clear-to-eol) + 内容 + `\\n`
      - log 文件: 写入新一行(无 \\r / \\033)
    """
    sep = kwargs.get("sep", " ")
    msg = sep.join(str(a) for a in args)
    ts = _ts()
    # stdout:回车 + 清行 + timestamp + 内容 + 换行
    _safe_stdout_write(f"\r\033[2K[{ts}] {msg}\n")
    # log 文件:干净一行
    try:
        fh = _get_fh()
        fh.write(f"[{ts}] {msg}\n")
        fh.flush()
    except Exception:
        pass


def banner(title: str, *, width: int = 60) -> None:
    """打印分隔条 + 标题(大段操作开始/结束时使用)。"""
    bar = "=" * width
    log_print(bar)
    log_print(f"  {title}")
    log_print(bar)


def section(title: str) -> None:
    """打印小节标题。"""
    log_print("")
    log_print(f"--- {title} ---")


def log_file_path() -> Path:
    """返回 log 文件路径(供测试/排查用)。"""
    return _LOG_FILE


__all__ = ["log_print", "log_overwrite", "banner", "section", "log_file_path"]
