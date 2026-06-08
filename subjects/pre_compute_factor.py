"""一次性预计算公共因子 → data/data-by-stock-factor/{code}_factor.csv.

使用:
    python subjects/pre_compute_factor.py                  # 增量(基于 mtime)
    python subjects/pre_compute_factor.py --force          # 强制全量
    python subjects/pre_compute_factor.py --codes 000001,000002   # 指定股票
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

# 提前加 sys.path(直接 python subjects/pre_compute_factor.py 跑时需要)
_HERE = Path(__file__).resolve()
_SUBJECTS = _HERE.parent  # subjects/
_PROJECT = _SUBJECTS.parent  # my-quant3/
for p in [_SUBJECTS, _PROJECT]:
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from subject.factors import (  # noqa: E402
    ma, atr, rsi, donchian_high, donchian_low, volume_ratio, mom,
)
from subject.backtest.data_loader.by_stock import load_stock  # noqa: E402
from data.config import HS300, CSI1000, CYB_STAR_50  # noqa: E402

# 公共因子白名单:列名 = 因子函数 + "_" + period
# (按 spec §1, 3 个 strategy 用的并集)
FACTOR_COLUMNS = [
    ("close", lambda df: df["收盘价"]),
    ("ma_5", lambda df: ma(df["收盘价"], 5)),
    ("ma_10", lambda df: ma(df["收盘价"], 10)),
    ("ma_20", lambda df: ma(df["收盘价"], 20)),
    ("ma_30", lambda df: ma(df["收盘价"], 30)),
    ("ma_60", lambda df: ma(df["收盘价"], 60)),
    ("atr_14", lambda df: atr(df["最高价"], df["最低价"], df["收盘价"], 14)),
    ("rsi_14", lambda df: rsi(df["收盘价"], 14)),
    ("donchian_high_20", lambda df: donchian_high(df["最高价"], 20)),
    ("donchian_low_20", lambda df: donchian_low(df["最低价"], 20)),
    ("volume_ratio_20", lambda df: volume_ratio(df["成交量（股）"], 20)),
    ("mom_60", lambda df: mom(df["收盘价"], 60)),
]

DATA_ROOT = _PROJECT / "data"
SOURCE_DIR = DATA_ROOT / "data-by-stock"
TARGET_DIR = DATA_ROOT / "data-by-stock-factor"


def compute_one(code: str) -> tuple[bool, str]:
    """计算单只股的 factor CSV, 返回 (success, message)."""
    src = SOURCE_DIR / f"{code}_金玥数据.csv"
    if not src.exists():
        return False, f"source not found: {src.name}"
    dst = TARGET_DIR / f"{code}_factor.csv"
    if dst.exists() and dst.stat().st_mtime >= src.stat().st_mtime:
        return True, "skip (mtime valid)"

    try:
        df = load_stock(code)
    except Exception as e:
        return False, f"load_stock failed: {type(e).__name__}: {e}"

    # 算每个 factor column
    out = {"日期": df["日期"]}
    for col_name, fn in FACTOR_COLUMNS:
        try:
            out[col_name] = fn(df).values
        except Exception as e:
            return False, f"compute {col_name} failed: {type(e).__name__}: {e}"

    import pandas as pd
    out_df = pd.DataFrame(out)
    dst.parent.mkdir(parents=True, exist_ok=True)
    out_df.to_csv(dst, index=False)
    return True, f"wrote {len(out_df)} rows"


def list_target_codes() -> list[str]:
    """默认返回 HS300 + CSI1000 + CYB_STAR_50 三个池子的并集(去重, 保持顺序).

    这是 watch 模式测试中最常用的 universe(对应 data/config.py 的官方列表,
    最后更新 2026-06-01). 用并集一次性覆盖 3 个池, 后续 watch 任意子集都命中.
    """
    seen: set[str] = set()
    out: list[str] = []
    for code in HS300 + CSI1000 + CYB_STAR_50:
        if code not in seen:
            seen.add(code)
            out.append(code)
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="忽略 mtime, 全量重算")
    parser.add_argument("--codes", type=str, default="", help="指定股票代码, 逗号分隔")
    args = parser.parse_args()

    if args.codes:
        codes = [c.strip() for c in args.codes.split(",") if c.strip()]
    else:
        codes = list_target_codes()

    print(f"[pre_compute_factor] 处理 {len(codes)} 只股, target = {TARGET_DIR}")
    if args.force:
        print(f"[pre_compute_factor] --force 模式, 忽略 mtime")
    t0 = time.perf_counter()
    ok = fail = skip = 0
    for i, code in enumerate(codes, 1):
        if args.force and (TARGET_DIR / f"{code}_factor.csv").exists():
            (TARGET_DIR / f"{code}_factor.csv").unlink()
        success, msg = compute_one(code)
        if not success:
            fail += 1
            print(f"  [{i}/{len(codes)}] {code}: FAIL — {msg}", file=sys.stderr)
        elif "skip" in msg:
            skip += 1
        else:
            ok += 1
        if i % 50 == 0:
            print(f"  [progress {i}/{len(codes)}] ok={ok} skip={skip} fail={fail}")
    elapsed = time.perf_counter() - t0
    print(f"\n[pre_compute_factor] 完成: OK={ok}, SKIP={skip}, FAIL={fail}, 耗时 {elapsed:.1f}s")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
