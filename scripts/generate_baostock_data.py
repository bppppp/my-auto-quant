"""
按 D:\my-auto-quant\create_baostock.md 方案生成 baostock 前复权数据集

7 步流程:
  1. 拉基础信息 (5 min)
  2. 拉行业分类 (2 min)
  3. 拉 K 线核心 (单进程 ~130 min)
  4. 后处理生成 by-day (~5 min)
  5. 后处理补字段 (~5 min)
  6. (不自动) 切换数据源 — 需手动改 _paths.py
  7. (不自动) 验证 — 需手动跑回测

Usage:
  python scripts/generate_baostock_data.py all           # 跑完整 5 步
  python scripts/generate_baostock_data.py basic        # 仅步骤 1
  python scripts/generate_baostock_data.py industry      # 仅步骤 2
  python scripts/generate_baostock_data.py kline         # 仅步骤 3
  python scripts/generate_baostock_data.py by_day        # 仅步骤 4
  python scripts/generate_baostock_data.py enrich        # 仅步骤 5
  python scripts/generate_baostock_data.py status        # 查看进度
"""
from __future__ import annotations

import argparse
import os
import sys
import time
import json
from pathlib import Path
from datetime import datetime

# 项目根加到 sys.path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# Windows: 强制 UTF-8
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import pandas as pd

# ============== 常量 ==============
DATA_DIR = _PROJECT_ROOT / "data"
STOCK_BS_DIR = DATA_DIR / "data-by-stock-bs"
DAY_BS_DIR = DATA_DIR / "data-by-day-bs"
UNIVERSE_CSV = DATA_DIR / "stock_universe.csv"
BASIC_CSV = DATA_DIR / "stock_basic_info.csv"
INDUSTRY_CSV = DATA_DIR / "industry_snapshot.csv"
STATE_JSON = DATA_DIR / "baostock_gen_state.json"
LOG_FILE = DATA_DIR / "baostock_gen.log"

START_DATE = "2018-01-01"
END_DATE = "2026-05-31"


# ============== 工具 ==============
def _code6_to_bs(code6: str) -> str:
    """6 位纯数字 -> baostock 格式 (sh.600000 / sz.000001 / bj.92xxxx)."""
    if code6.startswith(("60", "68", "90", "11", "13")):
        return f"sh.{code6}"
    if code6.startswith(("92", "83", "43", "87")):
        return f"bj.{code6}"
    return f"sz.{code6}"


def _bs_to_code6(bs_code: str) -> str:
    """sh.600000 / sz.000001 / bj.920001 -> 6 位."""
    return bs_code.split(".")[1]


def _log(msg: str) -> None:
    """写日志到文件 + stdout."""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def _load_universe() -> pd.DataFrame:
    """读股票池 (HS300+CSI1000+CYB_STAR_50 去重)."""
    from data.config import HS300, CSI1000, CYB_STAR_50
    all_codes = sorted(set(HS300) | set(CSI1000) | set(CYB_STAR_50))
    df = pd.DataFrame({
        "code6": all_codes,
        "bs_code": [_code6_to_bs(c) for c in all_codes],
    })
    return df


def _save_state(stage: str, **kwargs) -> None:
    """保存进度状态 (用于断点续跑)."""
    state = {}
    if STATE_JSON.exists():
        try:
            state = json.loads(STATE_JSON.read_text(encoding="utf-8"))
        except Exception:
            state = {}
    state[stage] = {"ts": datetime.now().isoformat(), **kwargs}
    STATE_JSON.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_state() -> dict:
    if not STATE_JSON.exists():
        return {}
    try:
        return json.loads(STATE_JSON.read_text(encoding="utf-8"))
    except Exception:
        return {}

# ============== 步骤 1: 基础信息 ==============
def step1_basic() -> None:
    """拉所有股票的基础信息 (名称/上市时间/退市时间)."""
    import baostock as bs

    _log("=" * 60)
    _log("步骤 1: 拉基础信息")
    _log("=" * 60)

    universe = _load_universe()
    _log(f"股票池: {len(universe)} 只")

    if BASIC_CSV.exists():
        existing = pd.read_csv(BASIC_CSV, dtype={"code": str})
        existing_codes = set(existing["code"].astype(str).tolist())
        _log(f"已有 {len(existing_codes)} 只基础信息, 跳过已完成")
    else:
        existing = None
        existing_codes = set()

    lg = bs.login()
    _log(f"baostock login: {lg.error_code} {lg.error_msg}")

    rows = []
    if existing is not None:
        rows = existing.to_dict("records")

    target_codes = [c for c in universe["bs_code"].tolist() if _bs_to_code6(c) not in existing_codes]
    _log(f"待补拉: {len(target_codes)} 只")

    t_total = time.time()
    for i, bs_code in enumerate(target_codes):
        t0 = time.time()
        try:
            rs = bs.query_stock_basic(code=bs_code)
            if rs.error_code != "0":
                _log(f"  [{i+1}] {bs_code}: error {rs.error_code} {rs.error_msg}")
                continue
            while rs.next():
                row = rs.get_row_data()
                # row: code, code_name, ipoDate, outDate, type, status
                # 防御: 字段可能不足
                r0 = row[0] if len(row) > 0 else bs_code
                r1 = row[1] if len(row) > 1 else ""
                r2 = row[2] if len(row) > 2 else ""
                r3 = row[3] if len(row) > 3 else ""
                r4 = row[4] if len(row) > 4 else "1"
                r5 = row[5] if len(row) > 5 else "1"
                rows.append({
                    "code": r0.split(".")[1],
                    "bs_code": r0,
                    "code_name": r1,
                    "ipoDate": r2,
                    "outDate": r3,
                    "type": r4,
                    "status": r5,
                })
        except Exception as e:
            _log(f"  [{i+1}] {bs_code}: exception {e}")
            continue

        elapsed = time.time() - t0
        if (i + 1) % 50 == 0 or i < 3:
            _log(f"  [{i+1}/{len(target_codes)}] {bs_code} {elapsed:.1f}s")

        # 增量保存: 每 100 条写一次
        if (i + 1) % 100 == 0:
            try:
                pd.DataFrame(rows).drop_duplicates(subset=["code"], keep="last").to_csv(
                    BASIC_CSV, index=False, encoding="utf-8-sig"
                )
            except Exception as e:
                _log(f"  增量保存失败: {e}")

    bs.logout()

    df = pd.DataFrame(rows).drop_duplicates(subset=["code"], keep="last")
    df.to_csv(BASIC_CSV, index=False, encoding="utf-8-sig")
    _log(f"步骤 1 完成: 共 {len(df)} 只基础信息, 写入 {BASIC_CSV}")
    _log(f"总耗时: {(time.time() - t_total) / 60:.1f} 分钟")
    _save_state("step1_basic", total=len(df))


# ============== 步骤 2: 行业分类 ==============
def step2_industry() -> None:
    """拉申万一级行业分类."""
    import baostock as bs

    _log("=" * 60)
    _log("步骤 2: 拉行业分类")
    _log("=" * 60)

    universe = _load_universe()
    bs_codes = universe["bs_code"].tolist()

    # 断点续跑
    if INDUSTRY_CSV.exists():
        existing = pd.read_csv(INDUSTRY_CSV, dtype={"code": str})
        existing_codes = set(existing["code"].astype(str).tolist())
        _log(f"已有 {len(existing_codes)} 只行业, 跳过已完成")
    else:
        existing = None
        existing_codes = set()

    lg = bs.login()
    _log(f"baostock login: {lg.error_code} {lg.error_msg}")

    rows = []
    if existing is not None:
        rows = existing.to_dict("records")

    target = [b for b in bs_codes if _bs_to_code6(b) not in existing_codes]
    _log(f"待补拉: {len(target)} 只")

    t_total = time.time()
    for i, bs_code in enumerate(target):
        t0 = time.time()
        try:
            rs = bs.query_stock_industry(code=bs_code)
            if rs.error_code != "0":
                continue
            while rs.next():
                row = rs.get_row_data()
                # 实际返回: [0]=更新日期 [1]=代码 [2]=名称 [3]=申万行业 [4]=证监会行业
                r0 = row[0] if len(row) > 0 else ""
                r1 = row[1] if len(row) > 1 else bs_code
                r2 = row[2] if len(row) > 2 else ""
                r3 = row[3] if len(row) > 3 else ""
                r4 = row[4] if len(row) > 4 else ""
                rows.append({
                    "code": r1.split(".")[-1] if "." in r1 else r1,
                    "bs_code": r1,
                    "code_name": r2,
                    "industry": r3,
                    "industry_classification": r4,
                })
                break
        except Exception as e:
            _log(f"  [{i+1}] {bs_code}: exception {e}")
            continue

        elapsed = time.time() - t0
        if (i + 1) % 100 == 0 or i < 3:
            eta_min = (len(target) - i - 1) * elapsed / 60
            _log(f"  [{i+1}/{len(target)}] {elapsed:.1f}s, ETA {eta_min:.0f}min")

        # 增量保存: 每 100 条写一次
        if (i + 1) % 100 == 0:
            try:
                pd.DataFrame(rows).drop_duplicates(subset=["code"], keep="last").to_csv(
                    INDUSTRY_CSV, index=False, encoding="utf-8-sig"
                )
            except Exception:
                pass

    bs.logout()

    df = pd.DataFrame(rows).drop_duplicates(subset=["code"], keep="last")
    df.to_csv(INDUSTRY_CSV, index=False, encoding="utf-8-sig")
    _log(f"步骤 2 完成: {len(df)} 只行业, 写入 {INDUSTRY_CSV}")
    _log(f"总耗时: {(time.time() - t_total) / 60:.1f} 分钟")
    _save_state("step2_industry", total=len(df))

# ============== 步骤 3: K 线核心 ==============
def step3_kline(resume: bool = True) -> None:
    """拉 K 线 (单进程, ~130 分钟)."""
    import baostock as bs

    _log("=" * 60)
    _log("步骤 3: 拉 K 线 (核心, 单进程)")
    _log("=" * 60)

    STOCK_BS_DIR.mkdir(parents=True, exist_ok=True)

    universe = _load_universe()
    bs_codes = universe["bs_code"].tolist()

    # 断点续跑
    done = set()
    if resume and STOCK_BS_DIR.exists():
        done = {p.stem for p in STOCK_BS_DIR.glob("*.csv")}
        _log(f"断点续跑: 已完成 {len(done)} 只")

    target = [b for b in bs_codes if _bs_to_code6(b) not in done]
    _log(f"目标: {len(target)} 只 (总共 {len(bs_codes)} 只)")

    lg = bs.login()
    _log(f"baostock login: {lg.error_code} {lg.error_msg}")

    t_total = time.time()
    failures = []

    for i, bs_code in enumerate(target):
        code6 = _bs_to_code6(bs_code)
        t0 = time.time()
        out_path = STOCK_BS_DIR / f"{code6}.csv"

        rows = []
        try:
            # 重试 3 次
            for attempt in range(3):
                rs = bs.query_history_k_data_plus(
                    bs_code,
                    "date,open,high,low,close,volume,amount",
                    start_date=START_DATE,
                    end_date=END_DATE,
                    frequency="d",
                    adjustflag="3",  # 前复权
                )
                if rs.error_code == "0":
                    while rs.next():
                        rows.append(rs.get_row_data())
                    break
                else:
                    _log(f"  [{code6}] attempt {attempt+1} error: {rs.error_msg}")
                    time.sleep(1)
            else:
                failures.append((bs_code, "all 3 attempts failed"))
                continue
        except Exception as e:
            failures.append((bs_code, str(e)))
            continue

        # 保存
        df = pd.DataFrame(rows, columns=["date", "open", "high", "low", "close", "volume", "amount"])
        df.to_csv(out_path, index=False, encoding="utf-8-sig")

        elapsed = time.time() - t0
        if (i + 1) % 25 == 0 or i < 3:
            eta_min = (len(target) - i - 1) * elapsed / 60
            _log(f"  [{i+1}/{len(target)}] {code6} {len(rows)}行 {elapsed:.1f}s, ETA {eta_min:.0f}min")

    bs.logout()

    elapsed_total = (time.time() - t_total) / 60
    _log(f"步骤 3 完成: {len(target)} 只, 失败 {len(failures)} 只, 耗时 {elapsed_total:.1f} 分钟")
    if failures:
        _log(f"  失败列表(前 10): {failures[:10]} ...")
        (DATA_DIR / "baostock_failures.json").write_text(
            json.dumps(failures, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    _save_state("step3_kline", done=len(done) + len(target) - len(failures), failed=len(failures))


# ============== 步骤 4: 生成 by-day ==============
def step4_by_day() -> None:
    """读 by-stock, 按日期 group 生成 by-day/{YYYY}/{date}.csv."""
    _log("=" * 60)
    _log("步骤 4: 后处理生成 by-day")
    _log("=" * 60)

    if not STOCK_BS_DIR.exists():
        _log("请先跑步骤 3")
        return

    DAY_BS_DIR.mkdir(parents=True, exist_ok=True)

    files = sorted(STOCK_BS_DIR.glob("*.csv"))
    _log(f"读 {len(files)} 个 by-stock 文件...")

    all_dfs = []
    for i, f in enumerate(files):
        df = pd.read_csv(f, dtype={"code": str})
        all_dfs.append(df)
        if (i + 1) % 200 == 0:
            _log(f"  读 {i+1}/{len(files)}")

    big = pd.concat(all_dfs, ignore_index=True)
    big["date"] = pd.to_datetime(big["date"])
    _log(f"合并后: {len(big)} 行, {big['date'].min().date()} ~ {big['date'].max().date()}")

    # 按日期 group
    grouped = big.groupby("date")
    _log(f"按日期 group: {len(grouped)} 个交易日")

    for i, (date, group) in enumerate(grouped):
        date_str = date.strftime("%Y-%m-%d")
        year_dir = DAY_BS_DIR / str(date.year)
        year_dir.mkdir(parents=True, exist_ok=True)
        out = year_dir / f"{date_str}.csv"
        # 列重命名: date -> 日期
        g = group.rename(columns={"date": "日期", "open": "开盘价", "high": "最高价",
                                   "low": "最低价", "close": "收盘价",
                                   "volume": "成交量(股)", "amount": "成交额(元)"})
        g.to_csv(out, index=False, encoding="utf-8-sig")
        if (i + 1) % 200 == 0:
            _log(f"  写 {i+1}/{len(grouped)} 交易日")

    _log(f"步骤 4 完成: by-day 写入 {DAY_BS_DIR}")
    _save_state("step4_by_day", days=len(grouped))

# ============== 步骤 5: 补字段 ==============
def step5_enrich() -> None:
    """读 by-stock, 补前收盘价/涨幅/均线/名称/行业等 38 列."""
    _log("=" * 60)
    _log("步骤 5: 后处理补字段 (38 列对齐)")
    _log("=" * 60)

    if not STOCK_BS_DIR.exists():
        _log("请先跑步骤 3")
        return

    # 读基础信息
    if not BASIC_CSV.exists():
        _log("缺少 stock_basic_info.csv, 跳过基础信息补齐")
        basic_df = pd.DataFrame()
    else:
        basic_df = pd.read_csv(BASIC_CSV, dtype={"code": str})

    if not INDUSTRY_CSV.exists():
        _log("缺少 industry_snapshot.csv, 跳过行业补齐")
        industry_df = pd.DataFrame()
    else:
        industry_df = pd.read_csv(INDUSTRY_CSV, dtype={"code": str})

    # 合并基础信息字典
    basic_map = {}
    if not basic_df.empty and "code" in basic_df.columns:
        for _, r in basic_df.iterrows():
            basic_map[str(r["code"])] = {
                "name": r.get("code_name", ""),
                "ipoDate": r.get("ipoDate", ""),
                "outDate": r.get("outDate", "") if pd.notna(r.get("outDate")) else "",
            }
    industry_map = {}
    if not industry_df.empty and "code" in industry_df.columns:
        for _, r in industry_df.iterrows():
            industry_map[str(r["code"])] = r.get("industry", "")

    files = sorted(STOCK_BS_DIR.glob("*.csv"))
    _log(f"补 {len(files)} 个文件...")

    COLS = [
        "日期", "代码", "名称", "所属行业",
        "开盘价", "最高价", "最低价", "收盘价", "前收盘价",
        "成交量(股)", "成交额(元)", "换手率", "涨幅%", "振幅%",
        "是否ST", "量比", "3日涨幅%", "6日涨幅%", "10日涨幅%", "25日涨幅%",
        "是否涨停", "总股本(股)", "流通股本(股)", "总市值(元)", "流通市值(元)",
        "滚动市盈率", "市净率", "滚动市销率",
        "5日线", "10日线", "20日线", "30日线", "60日线", "120日线", "250日线",
        "上市时间", "退市时间", "是否融资融券",
    ]

    for i, f in enumerate(files):
        code = f.stem
        df = pd.read_csv(f)
        df["date"] = pd.to_datetime(df["date"])

        # 类型转换
        for c in ["open", "high", "low", "close"]:
            df[c] = pd.to_numeric(df[c], errors="coerce")
        df["volume"] = pd.to_numeric(df["volume"], errors="coerce")
        df["amount"] = pd.to_numeric(df["amount"], errors="coerce")

        # 计算字段
        df["前收盘价"] = df["close"].shift(1)
        df["涨幅%"] = (df["close"] - df["前收盘价"]) / df["前收盘价"] * 100
        df["振幅%"] = (df["high"] - df["low"]) / df["前收盘价"] * 100

        # 均线
        for n in [5, 10, 20, 30, 60, 120, 250]:
            df[f"{n}日线"] = df["close"].rolling(n).mean()

        # 涨幅 rolling
        for n in [3, 6, 10, 25]:
            df[f"{n}日涨幅%"] = df["close"].pct_change(n) * 100

        # 是否涨停
        df["是否涨停"] = (df["涨幅%"] >= 9.5).fillna(False)

        # 静态字段
        df["代码"] = code
        df["名称"] = basic_map.get(code, {}).get("name", "")
        df["所属行业"] = industry_map.get(code, "")
        df["是否ST"] = False
        df["量比"] = None
        df["总股本(股)"] = None
        df["流通股本(股)"] = None
        df["总市值(元)"] = None
        df["流通市值(元)"] = None
        df["换手率"] = None
        df["滚动市盈率"] = None
        df["市净率"] = None
        df["滚动市销率"] = None
        df["上市时间"] = basic_map.get(code, {}).get("ipoDate", "")
        out_date = basic_map.get(code, {}).get("outDate", "")
        df["退市时间"] = out_date if out_date and out_date != "None" else "-"
        df["是否融资融券"] = False

        # 列对齐
        df = df.rename(columns={
            "date": "日期", "open": "开盘价", "high": "最高价",
            "low": "最低价", "close": "收盘价", "volume": "成交量(股)",
            "amount": "成交额(元)",
        })

        # 保证 38 列顺序
        for c in COLS:
            if c not in df.columns:
                df[c] = None
        df = df[COLS]

        df.to_csv(f, index=False, encoding="utf-8-sig")
        if (i + 1) % 100 == 0:
            _log(f"  补 {i+1}/{len(files)}")

    _log(f"步骤 5 完成: 38 列已对齐")
    _save_state("step5_enrich", files=len(files))


# ============== 状态 ==============
def cmd_status() -> None:
    state = _load_state()
    print("=" * 60)
    print("生成进度状态")
    print("=" * 60)
    for stage, info in state.items():
        print(f"  {stage}: {info}")

    print()
    print(f"by-stock 文件数: {len(list(STOCK_BS_DIR.glob('*.csv'))) if STOCK_BS_DIR.exists() else 0}")
    print(f"by-day 年份数: {len(list(DAY_BS_DIR.glob('*'))) if DAY_BS_DIR.exists() else 0}")
    print(f"基础信息: {'OK' if BASIC_CSV.exists() else 'NO'}")
    print(f"行业: {'OK' if INDUSTRY_CSV.exists() else 'NO'}")
    print(f"日志: {LOG_FILE}")


# ============== main ==============
def main():
    parser = argparse.ArgumentParser(description="baostock 数据集生成")
    parser.add_argument("stage", choices=["all", "basic", "industry", "kline", "by_day", "enrich", "status"],
                        help="执行的步骤")
    parser.add_argument("--no-resume", action="store_true", help="不续跑, 重新拉")
    args = parser.parse_args()

    if args.stage == "status":
        cmd_status()
        return

    _log(f"=== 启动: stage={args.stage} ===")
    if args.stage in ("all", "basic"):
        step1_basic()
    if args.stage in ("all", "industry"):
        step2_industry()
    if args.stage in ("all", "kline"):
        step3_kline(resume=not args.no_resume)
    if args.stage in ("all", "by_day"):
        step4_by_day()
    if args.stage in ("all", "enrich"):
        step5_enrich()
    _log(f"=== 完成: stage={args.stage} ===")


if __name__ == "__main__":
    main()
