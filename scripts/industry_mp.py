"""2 进程 + sleep(1) 拉行业分类"""
from __future__ import annotations
import sys, time, json, multiprocessing as mp
from pathlib import Path
from datetime import datetime

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))
import pandas as pd

DATA_DIR = _PROJECT_ROOT / "data"
LOG_FILE = DATA_DIR / "baostock_gen.log"
INDUSTRY_CSV = DATA_DIR / "industry_snapshot.csv"

def _code6_to_bs(code6):
    if code6.startswith(("60","68","90","11","13")): return f"sh.{code6}"
    if code6.startswith(("92","83","43","87")): return f"bj.{code6}"
    return f"sz.{code6}"

def _log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f: f.write(line + "\n")
    except: pass

def worker(task_queue, out_path, pid):
    import baostock as bs
    bs.login()
    done = 0
    rows_local = []
    while True:
        try:
            bs_code = task_queue.get(timeout=5)
        except:
            break
        code6 = bs_code.split(".")[1]
        try:
            rs = bs.query_stock_industry(code=bs_code)
            if rs.error_code == "0":
                while rs.next():
                    row = rs.get_row_data()
                    r1 = row[0] if len(row)>0 else ""
                    r2 = row[1] if len(row)>1 else bs_code
                    r3 = row[2] if len(row)>2 else ""
                    r4 = row[3] if len(row)>3 else ""
                    r5 = row[4] if len(row)>4 else ""
                    rows_local.append({
                        "code": r2.split(".")[-1] if "." in r2 else r2,
                        "bs_code": r2, "code_name": r3,
                        "industry": r4, "industry_classification": r5,
                    })
                    break
        except Exception as e:
            _log(f"  [pid={pid}] FAIL {bs_code}: {e}")
        time.sleep(1)  # 限流防护
        done += 1
        if done % 50 == 0:
            _log(f"  [pid={pid}] done {done}")
    bs.logout()
    # 合并写入
    if rows_local:
        df = pd.DataFrame(rows_local)
        if out_path.exists():
            existing = pd.read_csv(out_path, dtype={"code": str})
            df = pd.concat([existing, df], ignore_index=True).drop_duplicates(subset=["code"], keep="last")
        df.to_csv(out_path, index=False, encoding="utf-8-sig")

def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    from data.config import HS300, CSI1000, CYB_STAR_50
    all_codes = sorted(set(HS300)|set(CSI1000)|set(CYB_STAR_50))
    bs_codes = [_code6_to_bs(c) for c in all_codes]

    # 断点续跑
    done = set()
    if INDUSTRY_CSV.exists():
        existing = pd.read_csv(INDUSTRY_CSV, dtype={"code": str})
        done = set(existing["code"].astype(str).tolist())
        _log(f"已有 {len(done)} 只, 跳过已完成")

    target = [b for b in bs_codes if b.split(".")[1] not in done]
    _log(f"=== 2 进程行业分类: 待拉 {len(target)} 只 ===")
    if not target:
        _log("全部完成!")
        return

    task_queue = mp.Queue()
    for t in target:
        task_queue.put(t)

    t0 = time.time()
    procs = []
    for pid in range(2):
        p = mp.Process(target=worker, args=(task_queue, INDUSTRY_CSV, pid), daemon=False)
        p.start()
        procs.append(p)
        _log(f"启动 worker {pid} (pid={p.pid})")

    for p in procs:
        p.join(timeout=3600)

    # 最后去重
    df = pd.read_csv(INDUSTRY_CSV, dtype={"code": str})
    df = df.drop_duplicates(subset=["code"], keep="last")
    df.to_csv(INDUSTRY_CSV, index=False, encoding="utf-8-sig")
    _log(f"步骤 2 完成: {len(df)} 只, 耗时 {(time.time()-t0)/60:.1f} 分钟")
    pass  # state saved

if __name__ == "__main__":
    main()
