"""
重试 baostock 失败的股票
策略: 2 进程 + 1s sleep (低限流), 失败的进重试队列
最终: 单进程扫尾剩余失败
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
LOG_FILE = DATA_DIR / "baostock_retry.log"
STATE_FILE = DATA_DIR / "baostock_retry_state.json"

START_DATE = "2018-01-01"
END_DATE = "2026-05-31"


def _log(msg: str) -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def worker(task_queue, retry_queue, out_dir, pid, max_retries=3):
    """子进程: 取任务, 拉数据, 失败入 retry 队列."""
    import baostock as bs
    bs.login()
    done = 0
    while True:
        try:
            bs_code = task_queue.get(timeout=5)
        except Exception:
            break
        code6 = bs_code.split(".")[1]
        out_path = out_dir / f"{code6}.csv"
        if out_path.exists() and out_path.stat().st_size > 100:
            done += 1
            continue

        t0 = time.time()
        rows = []
        for attempt in range(max_retries):
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
                    if rows:  # 必须有数据
                        break
                time.sleep(1.0)  # 限流防护
            except Exception:
                time.sleep(1.0)
        elapsed = time.time() - t0

        if rows:
            df = pd.DataFrame(rows, columns=["date","open","high","low","close","volume","amount"])
            df.to_csv(out_path, index=False, encoding="utf-8-sig")
            done += 1
            if done % 20 == 0 or done < 3:
                _log(f"  [pid={pid}] OK #{done} {bs_code} {len(rows)}行 {elapsed:.1f}s")
        else:
            # 失败 → 入重试队列
            retry_queue.put(bs_code)
            _log(f"  [pid={pid}] FAIL {bs_code} {elapsed:.1f}s → retry")
            time.sleep(2.0)  # 失败后多睡
    bs.logout()


def single_worker_retry(retry_queue, out_dir, log_prefix="RETRY"):
    """单进程扫尾重试队列."""
    import baostock as bs
    bs.login()
    done = 0
    while True:
        try:
            bs_code = retry_queue.get(timeout=10)
        except Exception:
            break
        code6 = bs_code.split(".")[1]
        out_path = out_dir / f"{code6}.csv"
        if out_path.exists() and out_path.stat().st_size > 100:
            done += 1
            continue
        t0 = time.time()
        rows = []
        for attempt in range(5):  # 更多重试
            try:
                rs = bs.query_history_k_data_plus(
                    bs_code, "date,open,high,low,close,volume,amount",
                    start_date=START_DATE, end_date=END_DATE,
                    frequency="d", adjustflag="3",
                )
                if rs.error_code == "0":
                    while rs.next():
                        rows.append(rs.get_row_data())
                    if rows:
                        break
                time.sleep(2.0)
            except Exception:
                time.sleep(2.0)
        elapsed = time.time() - t0
        if rows:
            df = pd.DataFrame(rows, columns=["date","open","high","low","close","volume","amount"])
            df.to_csv(out_path, index=False, encoding="utf-8-sig")
            done += 1
            _log(f"  [{log_prefix}] OK #{done} {bs_code} {len(rows)}行 {elapsed:.1f}s")
        else:
            _log(f"  [{log_prefix}] GIVEUP {bs_code} {elapsed:.1f}s")
    bs.logout()
    return done


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=2, help="第一阶段 worker 数 (1-4)")
    parser.add_argument("--start", choices=["phase1", "phase2", "auto"], default="auto")
    args = parser.parse_args()

    STOCK_BS_DIR.mkdir(parents=True, exist_ok=True)

    # 读失败列表
    failures_path = DATA_DIR / "baostock_mp_failures.json"
    if failures_path.exists():
        with open(failures_path, encoding="utf-8") as f:
            failed_codes = [x[0] for x in json.load(f)]
    else:
        failed_codes = []
    _log(f"=== 重试启动: {len(failed_codes)} 只待重试, {args.workers} 进程 ===")

    if not failed_codes:
        _log("无失败, 跳过")
        return

    # 阶段 1: 多进程
    task_queue = mp.Queue()
    for c in failed_codes:
        task_queue.put(c)
    retry_queue = mp.Queue()

    t_total = time.time()
    procs = []
    for pid in range(args.workers):
        p = mp.Process(target=worker, args=(task_queue, retry_queue, STOCK_BS_DIR, pid), daemon=False)
        p.start()
        procs.append(p)
        _log(f"启动 worker {pid} (pid={p.pid})")

    for p in procs:
        p.join(timeout=10)

    _log(f"阶段 1 完成, 耗时 {(time.time()-t_total)/60:.1f} min")

    # 阶段 2: 单进程扫尾
    retry_count = retry_queue.qsize()
    _log(f"=== 阶段 2: 单进程扫尾 {retry_count} 只 ===")
    if retry_count > 0:
        done = single_worker_retry(retry_queue, STOCK_BS_DIR, "RETRY")
        _log(f"阶段 2 完成, 拿到 {done} 只, 耗时 {(time.time()-t_total)/60:.1f} min 总")

    # 最终统计
    final_count = len(list(STOCK_BS_DIR.glob("*.csv")))
    _log(f"=== 最终: by-stock-bs 共 {final_count} 只 ===")
    STATE_FILE.write_text(json.dumps({
        "ts": datetime.now().isoformat(),
        "phase1_workers": args.workers,
        "total_files": final_count,
    }, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
