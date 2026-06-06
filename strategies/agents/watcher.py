"""
src.agents.watcher — watchdog + debounce (策略调优持续监听)

来源: strategies.md §6.3 / §15.7
行为:
  - 先跑一次 `first_run`(once)
  - watchdog 监听 watch_dir 下 glob_pattern 新增
  - debounce debounce_seconds 触发回调
  - 串行处理（短时间多份报告一份一份处理）
  - max_iterations 达到上限自动退出
  - Ctrl+C 退出

实现:
  - 优先用 watchdog 库（pip install watchdog）
  - fallback: 简易 polling 循环（每 1s 检查 glob）
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Callable

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


class Watcher:
    """单次监听的封装（不启动线程,run_watch 串行驱动）。

    Args:
        watch_dir: 监听目录
        glob_pattern: 文件 glob 模式（report_v*.md / report_signals_v*.md）
        on_change: 回调 fn(path: Path) -> None
        debounce_seconds: 去抖时间（默认 5s）
        create_only: 仅响应 created 事件（不响应 modified）
        max_iterations: 最大回调次数
    """

    def __init__(
        self,
        *,
        watch_dir: Path,
        glob_pattern: str,
        on_change: Callable[[Path], None],
        debounce_seconds: float = 5.0,
        create_only: bool = True,
        max_iterations: int = 20,
    ):
        self.watch_dir = watch_dir
        self.glob_pattern = glob_pattern
        self.on_change = on_change
        self.debounce_seconds = debounce_seconds
        self.create_only = create_only
        self.max_iterations = max_iterations
        self._iteration_count = 0
        self._stop_requested = False
        self._seen_files: set[str] = set()

    def stop(self) -> None:
        """请求停止（Ctrl+C 时调用）"""
        self._stop_requested = True

    def known_files(self) -> set[str]:
        """返回 watch_dir 下已存在的 glob 匹配文件名集合（用于 first_run 后建立基线）。"""
        if not self.watch_dir.exists():
            return set()
        return {p.name for p in self.watch_dir.glob(self.glob_pattern)}

    def find_new_files(self) -> list[Path]:
        """返回 watch_dir 下新增的文件（与首次基线对比）。"""
        current = self.known_files()
        new = current - self._seen_files
        return [self.watch_dir / n for n in sorted(new)]


def run_watch(
    watcher: Watcher,
    *,
    first_run: Callable[[], object] | None = None,
) -> None:
    """驱动 watcher 主循环。

    1. 跑 first_run
    2. 记录已知文件基线
    3. 循环检查新增文件,debounce 后触发回调
    4. max_iterations 达上限 / Ctrl+C 退出
    """
    print(f"[watch] 启动监听: dir={watcher.watch_dir} pattern={watcher.glob_pattern}")
    print(f"[watch] debounce={watcher.debounce_seconds}s create_only={watcher.create_only}")
    print(f"[watch] max_iterations={watcher.max_iterations}")

    # 1) 跑一次 first_run
    if first_run is not None:
        try:
            print("[watch] 先跑一次 first_run ...")
            first_run()
        except Exception as e:
            print(f"[watch] first_run 失败（继续监听）: {e}")

    # 2) 记录基线
    watcher._seen_files = watcher.known_files()
    print(f"[watch] 已知基线文件: {len(watcher._seen_files)} 个")

    # 3) 主循环（fallback polling；用 watchdog 库时另启线程）
    try:
        _run_with_watchdog(watcher)
    except ImportError:
        print("[watch] 未安装 watchdog,降级为 polling 模式")
        _run_with_polling(watcher)


def _run_with_polling(watcher: Watcher) -> None:
    """无 watchdog 时的简易 polling（每 1s 检查新增文件）。"""
    last_check = time.time()
    while not watcher._stop_requested:
        if watcher._iteration_count >= watcher.max_iterations:
            print(f"[watch] 达到 max_iterations={watcher.max_iterations} 自动退出")
            break

        time.sleep(1.0)
        now = time.time()
        if now - last_check < watcher.debounce_seconds:
            continue
        last_check = now

        new_files = watcher.find_new_files()
        if not new_files:
            continue

        # 触发回调（debounce 期内新增的一组一起触发）
        watcher._iteration_count += 1
        for f in new_files:
            print(f"[watch] 检测到新文件: {f.name}")
            try:
                watcher.on_change(f)
            except Exception as e:
                print(f"[watch] 回调失败: {type(e).__name__}: {e}")
            watcher._seen_files.add(f.name)


def _run_with_watchdog(watcher: Watcher) -> None:
    """用 watchdog 库的版本（更高效）"""
    from watchdog.events import FileSystemEventHandler  # type: ignore
    from watchdog.observers import Observer  # type: ignore
    import fnmatch

    class _Handler(FileSystemEventHandler):
        def __init__(self, parent: "Watcher"):
            self.parent = parent
            self._pending: dict[str, float] = {}
            self._last_trigger = 0.0

        def _maybe_match(self, path: str) -> bool:
            return fnmatch.fnmatch(Path(path).name, self.parent.glob_pattern)

        def on_created(self, event):
            if event.is_directory:
                return
            if not self._maybe_match(event.src_path):
                return
            self.parent._seen_files.add(Path(event.src_path).name)
            self._pending[event.src_path] = time.time()
            self._check_debounce()

        def on_modified(self, event):
            if self.parent.create_only:
                return
            if event.is_directory:
                return
            if not self._maybe_match(event.src_path):
                return
            self._pending[event.src_path] = time.time()
            self._check_debounce()

        def _check_debounce(self):
            now = time.time()
            if now - self._last_trigger < self.parent.debounce_seconds:
                return
            if not self._pending:
                return
            if self.parent._iteration_count >= self.parent.max_iterations:
                return
            self.parent._iteration_count += 1
            self._last_trigger = now
            pending_paths = list(self._pending.keys())
            self._pending.clear()
            for p in pending_paths:
                try:
                    self.parent.on_change(Path(p))
                except Exception as e:
                    print(f"[watch] 回调失败: {type(e).__name__}: {e}")

    handler = _Handler(watcher)
    observer = Observer()
    observer.schedule(handler, str(watcher.watch_dir), recursive=False)
    observer.start()
    print(f"[watch] watchdog 启动: {watcher.watch_dir}")

    try:
        while not watcher._stop_requested:
            time.sleep(0.5)
            if watcher._iteration_count >= watcher.max_iterations:
                print(f"[watch] 达到 max_iterations 自动退出")
                break
    except KeyboardInterrupt:
        print("\n[watch] Ctrl+C 收到,准备退出...")
        watcher.stop()
    finally:
        observer.stop()
        observer.join()


__all__ = ["Watcher", "run_watch"]
