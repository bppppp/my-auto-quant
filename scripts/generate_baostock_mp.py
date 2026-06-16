"""
多进程 baostock K 线拉取 (4-8 进程并行)
比单进程快 4-8 倍, 但有 baostock 限流风险

Usage:
  python scripts/generate_baostock_mp.py 4      # 4 进程
  python scripts/generate_baostock_mp.py 8      # 8 进程
"""
from __future__ import annotations

import sys
import time
import json
import argparse
import multiprocessing as mp
from pathlib import Path
from datetime import datetime

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import pandas as pd

DATA_DIR = _PROJECT_ROOT / "data"
STOCK_BS_DIR = DATA_DIR / "data-by-stock-bs"
LOG_FILE = DATA_DIR / "baostock_mp.log"
FAILURES_JSON = DATA_DIR / "baostock_mp_failures.json"

START_DATE = "2018-01-01"
END_DATE = "2026-05-31"


def _code6_to_bs(code6: str) -> str:
    if code6.startswith(("60", "68", "90", "11", "13")):
        return f"sh.{code6}"
    if code6.startswith(("92", "83", "43", "87")):
        return f"bj.{code6}"
    return f"sz.{code6}"


def _load_universe() -> list[str]:
    from data.config import HS300, CSI1000, CYB_STAR_50
    all_codes = sorted(set(HS300) | set(CSI1000) | set(CYB_STAR_50))
    return [_code6_to_bs(c) for c in all_codes]


def _log(msg: str) -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def worker(task_queue, out_dir, pid, summary):
    """子进程: 从队列取任务, 拉 K 线."""
    import baostock as bs
    bs.login()
    done = 0
    while True:
        try:
            idx, bs_code = task_queue.get(timeout=2)
        except Exception:
            break
        code6 = bs_code.split(".")[1]
        out_path = out_dir / f"{code6}.csv"
        if out_path.exists() and out_path.stat().st_size > 100:
            # 已完成, 跳过
            done += 1
            continue
        t0 = time.time()
        rows = []
        for attempt in range(3):
            try:
                rs = bs.query_history_k_data_plus(
                    bs_code,
                    "date,open,high,low,close,volume,amount",
                    start_date=START_DATE, end_date=END_DATE,
                    frequency="d", adjustflag="3",
                )
                if rs.error_code == "0":
                    while rs.next():
                        rows.append(rs.get_row_data())
                    break
                else:
                    time.sleep(0.5)
            except Exception:
                time.sleep(0.5)
        if not rows:
            summary.put((pid, bs_code, "failed", 0))
        else:
            df = pd.DataFrame(rows, columns=["date","open","high","low","close","volume","amount"])
            df.to_csv(out_path, index=False, encoding="utf-8-sig")
            elapsed = time.time() - t0
            summary.put((pid, bs_code, "ok", len(rows)))
        done += 1
        if done % 25 == 0:
            _log(f"  [pid={pid}] done {done}, latest {bs_code} {len(rows) if rows else 0}行 {time.time()-t0:.1f}s")
    bs.logout()
    summary.put((pid, "EXIT", "done", done))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("workers", type=int, nargs="?", default=4, help="进程数 (1-8)")
    args = parser.parse_args()

    n_workers = max(1, min(8, args.workers))
    STOCK_BS_DIR.mkdir(parents=True, exist_ok=True)
    _log(f"=== 多进程 K 线拉取: {n_workers} 进程 ===")

    universe = _load_universe()
    _log(f"股票池: {len(universe)} 只")

    # 断点续跑
    done = {p.stem for p in STOCK_BS_DIR.glob("*.csv")}
    target = [(i, b) for i, b in enumerate(universe) if b.split(".")[1] not in done]
    _log(f"已完成 {len(done)}, 待拉 {len(target)}")
    if not target:
        _log("全部完成")
        return

    # 队列 + 汇总
    task_queue = mp.Queue()
    for t in target:
        task_queue.put(t)
    summary = mp.Queue()

    t_total = time.time()
    procs = []
    for pid in range(n_workers):
        p = mp.Process(target=worker, args=(task_queue, STOCK_BS_DIR, pid, summary), daemon=False)
        p.start()
        procs.append(p)
        _log(f"启动 worker {pid} (pid={p.pid})")

    # 收集结果
    finished_workers = 0
    failures = []
    while finished_workers < n_workers:
        try:
            pid, code, status, n = summary.get(timeout=10)
            if status == "EXIT":
                finished_workers += 1
            elif status == "failed":
                failures.append((code, "all 3 attempts failed"))
            # ok 的不打印, 太密集
        except Exception:
            # 检查子进程是否还活着
            alive = sum(1 for p in procs if p.is_alive())
            if alive == 0:
                break

    for p in procs:
        p.join(timeout=5)

    elapsed = (time.time() - t_total) / 60
    _log(f"=== 完成: 拉 {len(target)} 只, 失败 {len(failures)} 只, 耗时 {elapsed:.1f} 分钟 ===")
    if failures:
        _log(f"失败列表(前 20): {failures[:20]}")
        FAILURES_JSON.write_text(json.dumps(failures, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
