# Watch 模式公共因子预计算 — 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 通过一次性预计算 `subject.factors` 库的 7 个公共因子并落盘,让回测时优先查表,消除 582,000 次冗余 `compute_factors` 调用,把单次 10y HS300 params 回测从 25:16 压到 ~3-5 min,weight 模式从 20:14 压到 ~3-5 min。

**Architecture:** 一次性预计算脚本(per-stock 落盘 CSV) + ContextVar 传递当前 stock code + 7 个 factor 函数加 cache check(透明加速,strategy 0 改动) + runner 集成。缺则回退运行时,**无破坏性**。

**Tech Stack:** Python 3.12 / pandas / contextvars / pytest

**参考规范**: `docs/superpowers/specs/2026-06-08-watch-mode-precompute-design.md`

**重要约束(用户偏好)**: **不在 commit 步骤自动 commit**,所有任务完成后,询问用户。

---

## File Structure

| 路径 | 责任 |
|------|------|
| `subjects/pre_compute_factor.py` (new) | 一次性预计算入口(CLI),读 data-by-stock 写 data-by-stock-factor |
| `subjects/subject/factors/_cache.py` (new) | ContextVar + 模块级 cache + try_get_cached_factor |
| `subjects/subject/factors/{ma,atr,rsi,donchian,volume_ratio,mom}.py` (modify) | 各加 3 行 cache check(7 个函数) |
| `subjects/subject/backtest/data_loader/by_stock_factor.py` (new) | try_load_stock_factor(code) |
| `subjects/subject/backtest/runner.py` (modify) | _run_params + _run_weight 加 preload + bind_current_code |
| `tests/test_precomputed_factors.py` (new) | 3 只样本股 CSV vs 实时计算对账 |
| `data/data-by-stock-factor/{code}_factor.csv` (生成物) | 预计算落盘,git 忽略 |

---

### Task 1: 写 `subjects/pre_compute_factor.py`

**Files:**
- Create: `subjects/pre_compute_factor.py`

- [ ] **Step 1: 写主入口框架(无 factor 计算,先打通 CLI + 遍历 + 写空文件)**

```python
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

# 公共因子白名单:列名 = 因子函数 + "_" + period
# (按 spec §1,3 个 strategy 用的并集)
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
    """计算单只股的 factor CSV,返回 (success, message)."""
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
    """从 SOURCE_DIR 提取所有股票 code(去后缀)."""
    codes = []
    for f in sorted(SOURCE_DIR.glob("*_金玥数据.csv")):
        # 文件名格式: {code}_金玥数据.csv
        stem = f.stem  # "{code}_金玥数据"
        if "_金玥数据" in stem:
            codes.append(stem.replace("_金玥数据", ""))
    return codes


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="忽略 mtime,全量重算")
    parser.add_argument("--codes", type=str, default="", help="指定股票代码,逗号分隔")
    args = parser.parse_args()

    if args.codes:
        codes = [c.strip() for c in args.codes.split(",") if c.strip()]
    else:
        codes = list_target_codes()

    print(f"[pre_compute_factor] 处理 {len(codes)} 只股, target = {TARGET_DIR}")
    if args.force:
        print(f"[pre_compute_factor] --force 模式,忽略 mtime")
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
```

- [ ] **Step 2: 跑通 1 只股的端到端**

```bash
cd D:\project\quant\my-quant3
python subjects/pre_compute_factor.py --codes 000001
```

Expected:
- stdout: `处理 1 只股, target = D:\project\quant\my-quant3\data\data-by-stock-factor`
- stdout: `完成: OK=1, SKIP=0, FAIL=0, 耗时 <2s`
- 验证文件存在:`ls data/data-by-stock-factor/000001_factor.csv` → 显示文件
- 验证列数:`head -1 data/data-by-stock-factor/000001_factor.csv` → `日期,close,ma_5,ma_10,ma_20,ma_30,ma_60,atr_14,rsi_14,donchian_high_20,donchian_low_20,volume_ratio_20,mom_60`

- [ ] **Step 3: 验证 mtime 增量(重跑应 SKIP)**

```bash
python subjects/pre_compute_factor.py --codes 000001
```

Expected:
- `完成: OK=0, SKIP=1, FAIL=0, 耗时 <1s`
- 文件未被重写(`stat` mtime 不变)

- [ ] **Step 4: 验证 --force 重算**

```bash
python subjects/pre_compute_factor.py --codes 000001 --force
```

Expected:
- `完成: OK=1, SKIP=0, FAIL=0, 耗时 <2s`
- 文件 mtime 更新

- [ ] **Step 5: 跑全量 HS300 预计算(性能基线)**

```bash
# 准备 3 个池子的代码列表(临时 inline,后面再优化)
python -c "
from subjects.pre_compute_factor import list_target_codes
codes = list_target_codes()
print(','.join(codes[:300]))
" > /tmp/hs300_codes.txt
python subjects/pre_compute_factor.py --codes "$(cat /tmp/hs300_codes.txt | tr '\n' ',' | sed 's/,$//')"
```

Expected:
- 跑 300 股,`完成: OK=300, SKIP=0, FAIL=<5, 耗时 <90s`
- 如果 FAIL > 0,记录到 stderr 的失败列表(后续检查源数据)

**注意**:本任务**不 commit**(用户偏好)。

---

### Task 2: 写 `subjects/subject/factors/_cache.py` 模块

**Files:**
- Create: `subjects/subject/factors/_cache.py`
- Create: `tests/test_factor_cache.py`

- [ ] **Step 1: 写失败的测试(RED)**

`tests/test_factor_cache.py`:
```python
"""测试 _cache 模块: ContextVar + 模块级 cache + try_get_cached_factor."""
import pandas as pd
import pytest

from subject.factors import _cache


def test_try_get_returns_none_when_no_code():
    """未设 current code 时,返回 None."""
    assert _cache.try_get_cached_factor("ma_5") is None


def test_try_get_returns_none_when_factor_df_missing():
    """设了 current code 但 _factor_cache 没该股,返回 None."""
    token = _cache.bind_current_code("000001")
    try:
        assert _cache.try_get_cached_factor("ma_5") is None
    finally:
        _cache.reset_current_code(token)


def test_try_get_returns_series_when_hit():
    """命中 cache,返回 Series."""
    df = pd.DataFrame({
        "日期": pd.date_range("2024-01-01", periods=10),
        "ma_5": [float(i) for i in range(10)],
    })
    _cache.bind_factor_cache("000001", df)
    token = _cache.bind_current_code("000001")
    try:
        result = _cache.try_get_cached_factor("ma_5")
        assert result is not None
        assert list(result) == [float(i) for i in range(10)]
    finally:
        _cache.reset_current_code(token)
        _cache.bind_factor_cache("000001", None)


def test_try_get_returns_none_when_column_missing():
    """Factor DF 有,但列名不在,返回 None."""
    df = pd.DataFrame({"日期": pd.date_range("2024-01-01", periods=5), "ma_5": [1.0, 2, 3, 4, 5]})
    _cache.bind_factor_cache("000002", df)
    token = _cache.bind_current_code("000002")
    try:
        assert _cache.try_get_cached_factor("ma_100") is None  # 列不存在
    finally:
        _cache.reset_current_code(token)
        _cache.bind_factor_cache("000002", None)


def test_try_get_slices_to_length():
    """输入 length < cache 长度,截取到 length."""
    df = pd.DataFrame({"日期": pd.date_range("2024-01-01", periods=10), "ma_5": [float(i) for i in range(10)]})
    _cache.bind_factor_cache("000003", df)
    token = _cache.bind_current_code("000003")
    try:
        result = _cache.try_get_cached_factor("ma_5", length=3)
        assert result is not None
        assert len(result) == 3
        assert list(result) == [0.0, 1.0, 2.0]  # iloc[:3]
    finally:
        _cache.reset_current_code(token)
        _cache.bind_factor_cache("000003", None)


def test_bind_factor_cache_none_removes():
    """bind_factor_cache(code, None) 移除该股 cache."""
    df = pd.DataFrame({"日期": [1], "ma_5": [1.0]})
    _cache.bind_factor_cache("000004", df)
    _cache.bind_factor_cache("000004", None)  # 移除
    token = _cache.bind_current_code("000004")
    try:
        assert _cache.try_get_cached_factor("ma_5") is None
    finally:
        _cache.reset_current_code(token)
```

- [ ] **Step 2: 跑测试验证 FAIL**

```bash
pytest tests/test_factor_cache.py -v
```

Expected: `ModuleNotFoundError: No module named 'subject.factors._cache'`

- [ ] **Step 3: 写最小实现 _cache.py**

`subjects/subject/factors/_cache.py`:
```python
"""subject.factors 内部 cache: ContextVar 传递当前 stock code + 模块级 cache.

API:
    bind_current_code(code) -> Token         # 设置当前 stock code
    reset_current_code(token) -> None        # reset(配对使用)
    bind_factor_cache(code, df) -> None      # 注入/移除某只股的 factor DF
    try_get_cached_factor(col, length=None) -> pd.Series | None

使用场景: runner 在主循环内 bind_current_code, factor 函数 try_get_cached_factor 命中。
"""
from __future__ import annotations

import contextvars
from typing import Optional

import pandas as pd

_current_code: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "factor_current_code", default=None
)
_factor_cache: dict[str, pd.DataFrame] = {}


def bind_current_code(code: Optional[str]) -> contextvars.Token:
    """设置当前激活的 stock code,返回 Token 用于 reset."""
    return _current_code.set(code)


def reset_current_code(token: contextvars.Token) -> None:
    """重置 current code(配对 bind_current_code 使用)."""
    _current_code.reset(token)


def bind_factor_cache(code: str, factor_df: Optional[pd.DataFrame]) -> None:
    """注入/移除某只股的 factor DataFrame. None = 移除(禁用 cache)."""
    if factor_df is not None:
        _factor_cache[code] = factor_df
    else:
        _factor_cache.pop(code, None)


def try_get_cached_factor(col: str, length: int | None = None) -> Optional[pd.Series]:
    """查当前 stock 的预计算 Series. col 不存在 / code 未设 / length 截取 后返回 None."""
    code = _current_code.get()
    if code is None:
        return None
    df = _factor_cache.get(code)
    if df is None or col not in df.columns:
        return None
    series = df[col]
    if length is not None and len(series) > length:
        series = series.iloc[:length].reset_index(drop=True)
    return series


__all__ = [
    "bind_current_code",
    "reset_current_code",
    "bind_factor_cache",
    "try_get_cached_factor",
]
```

- [ ] **Step 4: 跑测试验证 PASS**

```bash
pytest tests/test_factor_cache.py -v
```

Expected: 全部 6 个 PASS

**注意**:本任务**不 commit**。

---

### Task 3: 修改 7 个 factor 函数加 cache check

**Files:**
- Modify: `subjects/subject/factors/ma.py`
- Modify: `subjects/subject/factors/atr.py`
- Modify: `subjects/subject/factors/rsi.py`
- Modify: `subjects/subject/factors/donchian.py`
- Modify: `subjects/subject/factors/volume_ratio.py`
- Modify: `subjects/subject/factors/mom.py`

- [ ] **Step 1: 读 7 个 factor 文件的当前内容**

```bash
cat subjects/subject/factors/ma.py
cat subjects/subject/factors/atr.py
cat subjects/subject/factors/rsi.py
cat subjects/subject/factors/donchian.py
cat subjects/subject/factors/volume_ratio.py
cat subjects/subject/factors/mom.py
```

记录每个文件的 import 区 + 函数签名(下一步要改)。

- [ ] **Step 2: 修改 `ma.py`**

在 `ma` 函数体内,**最前面**加 3 行:

```python
from ._cache import try_get_cached_factor

def ma(series: pd.Series, period: int) -> pd.Series:
    cached = try_get_cached_factor(f"ma_{period}", length=len(series))
    if cached is not None:
        return cached
    return series.rolling(period).mean()  # 原实现
```

- [ ] **Step 3: 修改 `atr.py`**

同理加 3 行:

```python
from ._cache import try_get_cached_factor

def atr(high, low, close, period: int = 14) -> pd.Series:
    cached = try_get_cached_factor("atr_14", length=len(close))
    if cached is not None:
        return cached
    # 原实现
    ...
```

- [ ] **Step 4: 修改 `rsi.py`**

```python
from ._cache import try_get_cached_factor

def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    cached = try_get_cached_factor("rsi_14", length=len(close))
    if cached is not None:
        return cached
    # 原实现
    ...
```

- [ ] **Step 5: 修改 `donchian.py`**

两个函数都改:

```python
from ._cache import try_get_cached_factor

def donchian_high(high, period: int) -> pd.Series:
    cached = try_get_cached_factor("donchian_high_20", length=len(high))
    if cached is not None:
        return cached
    # 原实现
    ...

def donchian_low(low, period: int) -> pd.Series:
    cached = try_get_cached_factor("donchian_low_20", length=len(low))
    if cached is not None:
        return cached
    # 原实现
    ...
```

- [ ] **Step 6: 修改 `volume_ratio.py`**

```python
from ._cache import try_get_cached_factor

def volume_ratio(volume, period: int = 20) -> pd.Series:
    cached = try_get_cached_factor("volume_ratio_20", length=len(volume))
    if cached is not None:
        return cached
    # 原实现
    ...
```

- [ ] **Step 7: 修改 `mom.py`**

```python
from ._cache import try_get_cached_factor

def mom(close, period: int) -> pd.Series:
    cached = try_get_cached_factor("mom_60", length=len(close))
    if cached is not None:
        return cached
    # 原实现
    ...
```

- [ ] **Step 8: 跑 _cache 测试 + 验证运行时回退仍正常**

```bash
pytest tests/test_factor_cache.py -v
```

Expected: 6 个 PASS

再跑一次**未预计算**的回测(确认回退路径):

```bash
# 删 1 只股的 factor CSV,看是否仍能跑
rm -f data/data-by-stock-factor/000001_factor.csv
cd subjects
python ma_cross_atr_volume/generated/strategy.py --start-date 2024-01-01 --end-date 2024-12-31 2>&1 | tail -10
cd ..
```

Expected: 正常完成,生成 report_v1.md(用 v1 之前的最新 version 编号)

**注意**:本任务**不 commit**。

---

### Task 4: 写 `subjects/subject/backtest/data_loader/by_stock_factor.py`

**Files:**
- Create: `subjects/subject/backtest/data_loader/by_stock_factor.py`
- Create: `tests/test_by_stock_factor.py`

- [ ] **Step 1: 写失败的测试(RED)**

`tests/test_by_stock_factor.py`:
```python
"""测试 try_load_stock_factor: 文件存在/不存在/损坏 三种情况."""
import pytest

from subject.backtest.data_loader.by_stock_factor import try_load_stock_factor


def test_returns_none_for_missing_file(tmp_path, monkeypatch):
    """文件不存在返回 None,不抛异常."""
    # 把 DATA_ROOT 临时改成 tmp_path
    import subject.backtest.data_loader.by_stock_factor as mod
    monkeypatch.setattr(mod, "DATA_ROOT", tmp_path)
    assert try_load_stock_factor("999999") is None


def test_returns_df_for_valid_file(tmp_path, monkeypatch):
    """有效 CSV 返回 DataFrame."""
    import pandas as pd
    import subject.backtest.data_loader.by_stock_factor as mod
    monkeypatch.setattr(mod, "DATA_ROOT", tmp_path)
    (tmp_path / "data-by-stock-factor").mkdir()
    pd.DataFrame({
        "日期": ["2024-01-01", "2024-01-02", "2024-01-03"],
        "close": [10.0, 11.0, 12.0],
        "ma_5": [10.0, 10.5, 11.0],
    }).to_csv(tmp_path / "data-by-stock-factor" / "000001_factor.csv", index=False)
    df = try_load_stock_factor("000001")
    assert df is not None
    assert len(df) == 3
    assert "close" in df.columns


def test_returns_none_for_corrupt_file(tmp_path, monkeypatch):
    """文件存在但解析失败,返回 None."""
    import subject.backtest.data_loader.by_stock_factor as mod
    monkeypatch.setattr(mod, "DATA_ROOT", tmp_path)
    (tmp_path / "data-by-stock-factor").mkdir()
    (tmp_path / "data-by-stock-factor" / "000001_factor.csv").write_text("not,a,valid\ncsv\"\"\"")
    assert try_load_stock_factor("000001") is None
```

- [ ] **Step 2: 跑测试验证 FAIL**

```bash
pytest tests/test_by_stock_factor.py -v
```

Expected: `ModuleNotFoundError` 或 import error

- [ ] **Step 3: 写实现**

`subjects/subject/backtest/data_loader/by_stock_factor.py`:
```python
"""按股票代码读 data-by-stock-factor/{code}_factor.csv.

失败模式(返回 None, 不抛):
- 文件不存在
- CSV 解析失败
- 缺少'日期'列
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import pandas as pd

# 复用 data_loader/_paths.py 的 DATA_ROOT
from ._paths import DATA_ROOT


def try_load_stock_factor(code: str) -> Optional[pd.DataFrame]:
    """读 data-by-stock-factor/{code}_factor.csv, 返回 DataFrame 或 None."""
    path = DATA_ROOT / "data-by-stock-factor" / f"{code}_factor.csv"
    if not path.exists():
        return None
    try:
        df = pd.read_csv(path, dtype={"日期": str}, keep_default_na=False)
        df["日期"] = pd.to_datetime(df["日期"])
        return df
    except Exception:
        return None


__all__ = ["try_load_stock_factor"]
```

- [ ] **Step 4: 跑测试验证 PASS**

```bash
pytest tests/test_by_stock_factor.py -v
```

Expected: 3 个 PASS

**注意**:本任务**不 commit**。

---

### Task 5: 集成到 `runner.py`

**Files:**
- Modify: `subjects/subject/backtest/runner.py` (_run_params + _run_weight)

- [ ] **Step 1: 读 runner.py 当前 `_run_params` 段(行 262-313)确定插入点**

```bash
sed -n '262,313p' subjects/subject/backtest/runner.py
```

记录 `for code in self.universe` 循环体位置(在 `load_stock` 之后,strategy.compute_factors 之前)。

- [ ] **Step 2: 读 runner.py 当前 `_run_weight` 段(行 511-525)preload 段**

```bash
sed -n '500,560p' subjects/subject/backtest/runner.py
```

记录 `stock_history` preload 循环结束位置。

- [ ] **Step 3: 读 runner.py 当前 `_run_weight` 主循环段(行 580-606 附近)**

```bash
sed -n '575,615p' subjects/subject/backtest/runner.py
```

记录主循环里 `strategy.compute_factors` 调用点(在 `for code in hist.index` 循环里)。

- [ ] **Step 4: 在文件顶部加 import**

在 runner.py 顶部 import 区加:

```python
from subject.factors._cache import bind_current_code, reset_current_code, bind_factor_cache
from subject.backtest.data_loader.by_stock_factor import try_load_stock_factor
```

- [ ] **Step 5: 修改 `_run_params` 段**

在 `for code in self.universe:` 循环内、`load_stock` 之后、`backtest 单股计算` 之前,定位原有的 `strategy.compute_factors(df, params)` 调用,把 try/finally **包住**它(不是替换):

```python
# === 预计算公共因子 bind (包住原 compute_factors 调用) ===
code6 = code.split(".")[0]
factor_df = try_load_stock_factor(code6)
bind_factor_cache(code6, factor_df)
token = bind_current_code(code6)
try:
    factors = strategy.compute_factors(df, params)  # ← 原本就有的一行,保留
    # ... 后续 entry/exit 计算保持原样
finally:
    reset_current_code(token)
```

**注意**:try/finally 必须包住 `strategy.compute_factors(df, params)` 那一行(行 399 附近)。其他行(entry signal、exit signal、trade 记录)保持原样不动。

- [ ] **Step 6: 修改 `_run_weight` preload 段**

在 `_run_weight` 的 `stock_history` 循环后加 `stock_factor_history`:

```python
# 紧跟 stock_history preload 之后
stock_factor_history: dict[str, pd.DataFrame] = {}
for code in self.universe:
    factor_df = try_load_stock_factor(code.split(".")[0])
    if factor_df is not None:
        stock_factor_history[code.split(".")[0]] = factor_df
self.logger.info(
    f"preloaded factors for {len(stock_factor_history)}/{len(self.universe)} stocks"
)
```

- [ ] **Step 7: 修改 `_run_weight` 主循环**

在主循环 `for code in hist.index` 内,`strategy.compute_factors(hist, params)` 之前加:

```python
code6 = code.split(".")[0]
factor_df = stock_factor_history.get(code6)
bind_factor_cache(code6, factor_df)
token = bind_current_code(code6)
try:
    factors = strategy.compute_factors(hist, params)
finally:
    reset_current_code(token)
```

- [ ] **Step 8: 跑一次小回测,确认无报错**

```bash
cd subjects
python ma_cross_atr_volume/generated/strategy.py --start-date 2024-01-01 --end-date 2024-12-31 2>&1 | tail -20
cd ..
```

Expected: 正常完成,生成新 report_v*.md,日志含 "preloaded factors for 300/300 stocks"

**注意**:本任务**不 commit**。

---

### Task 6: 写 `tests/test_precomputed_factors.py`(数值一致性对账)

**Files:**
- Create: `tests/test_precomputed_factors.py`

- [ ] **Step 1: 写测试**

```python
"""验证 pre_compute_factor 生成的 CSV 与 subject.factors 实时计算结果一致.

测试策略: 选 3 个样本股(HS300 / CSI1000 / 创业板 各 1),
         对每只股读取 factor CSV,与实时调用 subject.factors 对比 13 列.
"""
from pathlib import Path

import pandas as pd
import pytest

from subject.factors import (
    ma, atr, rsi, donchian_high, donchian_low, volume_ratio, mom,
)
from subject.backtest.data_loader.by_stock import load_stock
from subject.backtest.data_loader.by_stock_factor import try_load_stock_factor

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = PROJECT_ROOT / "data"

# 3 个样本股(各取一个,确保覆盖不同池子)
SAMPLE_CODES = ["000001", "600519", "300750"]


@pytest.mark.parametrize("code", SAMPLE_CODES)
def test_factor_csv_matches_runtime(code: str):
    """每只样本股: factor CSV 的 13 列与 subject.factors 实时结果逐位相等."""
    # 1) 实时计算
    df = load_stock(code)
    runtime = {
        "close": df["收盘价"],
        "ma_5": ma(df["收盘价"], 5),
        "ma_10": ma(df["收盘价"], 10),
        "ma_20": ma(df["收盘价"], 20),
        "ma_30": ma(df["收盘价"], 30),
        "ma_60": ma(df["收盘价"], 60),
        "atr_14": atr(df["最高价"], df["最低价"], df["收盘价"], 14),
        "rsi_14": rsi(df["收盘价"], 14),
        "donchian_high_20": donchian_high(df["最高价"], 20),
        "donchian_low_20": donchian_low(df["最低价"], 20),
        "volume_ratio_20": volume_ratio(df["成交量（股）"], 20),
        "mom_60": mom(df["收盘价"], 60),
    }
    # 2) 读 factor CSV
    cached_df = try_load_stock_factor(code)
    if cached_df is None:
        pytest.skip(f"no pre-computed factor CSV for {code} — run pre_compute_factor first")
    # 3) 逐列比对(NaN == NaN 用 pandas testing)
    for col, expected in runtime.items():
        assert col in cached_df.columns, f"missing column {col}"
        actual = cached_df[col]
        pd.testing.assert_series_equal(
            actual.reset_index(drop=True),
            expected.reset_index(drop=True),
            check_names=False,
            check_dtype=False,  # 允许 dtype 微差(f64 vs f32)
            atol=1e-9,
            obj=col,
        )
```

- [ ] **Step 2: 跑测试(应 PASS,前提:Task 1 跑过 pre-compute)**

```bash
pytest tests/test_precomputed_factors.py -v
```

Expected: 3 个 PASS(每个样本股一个)

如果 FAIL:
- 检查 Task 1 的 pre-compute 是否对这 3 只股都成功(用 `ls data/data-by-stock-factor/000001_factor.csv` 验证)
- 检查 factor 函数实现是否一致(对比 pre_compute_factor.py 的 FACTOR_COLUMNS 与测试里的 runtime dict)

**注意**:本任务**不 commit**。

---

### Task 7: 跑完整 benchmark(关键验证)

**Files:** 无修改,只读 + 跑命令

- [ ] **Step 1: 记录基线**

基线(2026-06-08 15:04 ~ 15:50 实测):
- params 10y HS300: **25:16 (1516s)**, 36026 trades
- weight 10y HS300: **20:14 (1214s)**, 1660 trades, 388 rebalances

最新 report:
- `subjects/ma_cross_atr_volume/reportParams/report_v*.md`(最新 version)
- `subjects/ma_cross_atr_volume/reportWeight/report_signals_v*.md`

记录最新 version 号(从文件名提取)。

- [ ] **Step 2: 跑 params 模式 benchmark**

```bash
cd D:\project\quant\my-quant3
time python subjects/ma_cross_atr_volume/generated/strategy.py --start-date 2016-01-01 --end-date 2026-01-01
```

记录:
- wall time
- 生成的 report version 号
- 报告里关键指标(annual_return, sharpe, win_rate 等)

- [ ] **Step 3: 跑 weight 模式 benchmark**

```bash
cd D:\project\quant\my-quant3
time python subjects/ma_cross_atr_volume/generated/strategy.py weight --start-date 2016-01-01 --end-date 2026-01-01
```

记录:
- wall time
- 报告里关键指标

- [ ] **Step 4: 对比报告数值**

逐字段对比基线报告 vs 优化后报告:
- `annual_return` / `avg_annual_return_rate` / `avg_annual_return_amount`
- `win_rate` / `profit_loss_ratio` / `sharpe` / `max_drawdown`
- `trades` 计数
- 各 signal 的触发次数 / 胜率

Expected: **所有字段完全一致**(因为是同一组公共因子,只是预先算了)

如果不一致:
- 检查 `subject/factors/*.py` 是否有改动
- 检查 `data-by-stock-factor/` 是否有 mtime 过期(预计算 CSV 是更老版本)
- 用 `python subjects/pre_compute_factor.py --force` 重算

- [ ] **Step 5: 计算加速比,填表**

| 模式 | 基线 | 优化后 | 加速比 |
|------|------|--------|--------|
| params 10y HS300 | 25:16 | _?_ | _?_x |
| weight 10y HS300 | 20:14 | _?_ | _?_x |

- [ ] **Step 6: watch 模式快速验证**

```bash
cd D:\project\quant\my-quant3
# 终端 1: 启动 watch
python subjects/ma_cross_atr_volume/generated/strategy.py --monitor
# 终端 2: 触发(在另一个 shell)
touch subjects/ma_cross_atr_volume/strategiesParam/ma_cross_atr_volume_v99.md
```

Expected:
- 终端 1 在 5-10s debounce 后开始跑
- 单次回测 < 5 min(对比之前的 ~25min)
- 终端 1 输出新 report

**注意**:本任务**不 commit**。

---

### Task 8: 写 README 更新

**Files:**
- Modify: `subjects/pre_compute_factor.py`(已存在,加 docstring 不需要)
- Modify: `README.md`(项目根,如不存在则新建)

- [ ] **Step 1: 写 README "预计算公共因子" 节**

如果 README.md 存在,在适当位置加:

```markdown
## 公共因子预计算 (10x 回测加速)

回测主循环的 `compute_factors` 重复计算 `subject.factors` 库的 7 个公共因子 ~582,000 次/策略,占耗时 95%。一次性预计算到 `data/data-by-stock-factor/{code}_factor.csv` 可消除此开销。

**首次使用**:
```bash
# 预计算 HS300 300 只股(约 1 min)
python subjects/pre_compute_factor.py
```

**增量**(只算缺/过期的):
```bash
python subjects/pre_compute_factor.py
```

**强制全量**(修改了 `subject/factors/*.py` 实现时):
```bash
python subjects/pre_compute_factor.py --force
```

**指定股票**:
```bash
python subjects/pre_compute_factor.py --codes 000001,000002
```

**回退机制**: 预计算 CSV 缺失/损坏/缺列,自动回退运行时计算,**不影响功能**。

**性能** (10y HS300):
- params: 25:16 → 3-5 min
- weight: 20:14 → 3-5 min
```

**注意**:本任务**不 commit**。

---

### Task 9: 询问用户(收尾)

**Files:** 无修改

- [ ] **Step 1: 汇报完成情况**

给用户的汇报清单:
- 4 个新文件:`subjects/pre_compute_factor.py` / `subjects/subject/factors/_cache.py` / `subjects/subject/backtest/data_loader/by_stock_factor.py` / `tests/test_precomputed_factors.py` + `tests/test_factor_cache.py` / `tests/test_by_stock_factor.py`
- 修改文件:`subjects/subject/factors/{ma,atr,rsi,donchian,volume_ratio,mom}.py` 各加 3 行
- 修改文件:`subjects/subject/backtest/runner.py` 加 2 段 bind 代码
- 所有测试 PASS
- Benchmark 加速比:params X_x, weight X_x(填实际值)
- 报告数值与基线**完全一致**

- [ ] **Step 2: 询问 commit 方式**

按用户偏好,**询问**而不是自动 commit。可选:
- 1 个整体 commit:`perf(backtest): 公共因子预计算 + 透明 cache 加速 (params 25min→Xmin)`
- 分批 commit:按 task 分 3-5 个
- 不 commit,继续调整

---

## Verification Summary

| 检查项 | 命令/方法 | 预期 |
|-------|---------|------|
| 预计算正确性 | `pytest tests/test_precomputed_factors.py -v` | 3 PASS |
| Cache 模块 | `pytest tests/test_factor_cache.py -v` | 6 PASS |
| 因子加载 | `pytest tests/test_by_stock_factor.py -v` | 3 PASS |
| 预计算 mtime 增量 | 跑 2 次,第二次 < 1s | SKIP 命中 |
| Params benchmark | 跑 10y HS300 | < 5 min |
| Weight benchmark | 跑 10y HS300 | < 5 min |
| 报告数值一致 | 对比新旧 report 字段 | 逐位相等 |
| Watch 模式 | 启动 monitor,触发 spec 改动 | 5-10s + 单次 < 5min |

## Rollback

```bash
git checkout subjects/subject/factors/ subjects/subject/backtest/runner.py
rm -rf data/data-by-stock-factor/
rm -f subjects/pre_compute_factor.py \
      subjects/subject/factors/_cache.py \
      subjects/subject/backtest/data_loader/by_stock_factor.py \
      tests/test_precomputed_factors.py \
      tests/test_factor_cache.py \
      tests/test_by_stock_factor.py
```

耗时 < 2 min,无数据损坏风险。

## Out of Scope (本计划不动)

- ❌ 预计算白名单自动扩展
- ❌ data-by-day 横截面公共计算
- ❌ autoRun pipeline 集成
- ❌ 远程缓存
- ❌ 自动检测 `subject/factors/*.py` 实现变更
