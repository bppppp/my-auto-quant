"""回填 by-stock 文件中缺失的名称/行业/上市时间"""
from __future__ import annotations
import sys
from pathlib import Path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path: sys.path.insert(0, str(_PROJECT_ROOT))
import pandas as pd

DATA_DIR = _PROJECT_ROOT / "data"
STOCK_DIR = DATA_DIR / "data-by-stock-bs"
BASIC_CSV = DATA_DIR / "stock_basic_info.csv"
INDUSTRY_CSV = DATA_DIR / "industry_snapshot.csv"

# 读基础信息
basic = pd.read_csv(BASIC_CSV, dtype={"code": str})
bmap = {}
for _, r in basic.iterrows():
    c = str(r["code"])
    od = r.get("outDate", "")
    bmap[c] = {
        "名称": r.get("code_name", ""),
        "上市时间": r.get("ipoDate", ""),
        "退市时间": od if pd.notna(od) and str(od) not in ("", "None", "nan") else "-",
    }
print(f"基础信息: {len(bmap)} 只")

# 读行业分类
imap = {}
if INDUSTRY_CSV.exists():
    ind = pd.read_csv(INDUSTRY_CSV, dtype={"code": str})
    for _, r in ind.iterrows():
        imap[str(r["code"])] = r.get("industry", "")
    print(f"行业: {len(imap)} 只")

# 回填
files = sorted(STOCK_DIR.glob("*.csv"))
print(f"回填 {len(files)} 个文件...")
for i, f in enumerate(files):
    code = f.stem
    df = pd.read_csv(f)
    if code in bmap:
        df["名称"] = bmap[code]["名称"]
        df["上市时间"] = bmap[code]["上市时间"]
        df["退市时间"] = bmap[code]["退市时间"]
    if code in imap:
        df["所属行业"] = imap[code]
    df.to_csv(f, index=False, encoding="utf-8-sig")
    if (i+1) % 200 == 0:
        print(f"  {i+1}/{len(files)}")
print(f"完成: {len(files)} 个文件已更新")
