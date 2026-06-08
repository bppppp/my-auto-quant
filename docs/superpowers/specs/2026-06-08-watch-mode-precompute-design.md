# Watch 模式公共因子预计算 — 设计文档

## Context

**问题**: 用户在 `python subjects/<strategy>/generated/strategy.py --monitor` 的 watch 模式下迭代调优策略时,**每改一次 spec 文件就要重跑一次完整回测**,单次 params 模式 10y HS300 实测 **25:16**,weight 模式 **20:14**。一次 spec 改动触发一次回测 → 迭代周期 ~25min,严重影响调优效率。

**根因**(基于 2026-06-08 真实 benchmark):
- params 模式每只股 5.05s,其中 99% 耗时在 `compute_factors(df.iloc[:i+1], params)` 的逐 bar 重算(300 股 × 1942 bar = **582,600 次冗余调用**)
- weight 模式每交易日 0.625s,其中 95% 同样是 `compute_factors` 重算
- 数据 IO(load_csv + load_day)只占总耗时 0.5-5%,**不是瓶颈**
- BacktestRunner 重建(YAML/importlib/universe/logger)只占 0.1%

**已存在的资源**: `subjects/subject/factors/` 库(7 个函数:`ma / atr / rsi / donchian_high / donchian_low / volume_ratio / mom`),**所有 3 个现有 strategy 100% 只用这 7 个函数**。这是天然的"公共因子白名单"。

**目标**: 一次性预计算所有公共因子(per-stock 落盘到 `data/data-by-stock-factor/{code}_factor.csv`),回测时优先查表,缺则回退到运行时计算。**预期把单次回测从 25min 压到 3-5min**。

**约束**(用户决策 2026-06-08):
- 不动 `autoRun/pipeline.py`(本次范围限定 watch 模式)
- 不动 strategy 代码(strategy.py 100% 调用 subject.factors 库,通过库层透明加速)
- 落盘 + 回退(无则跳过,不会因预计算缺失而崩)
- 严格不自动 commit(完成后询问用户)

---

## 关键设计原则

1. **透明加速**: strategy 代码 0 改动,通过 `subject.factors` 库内部 cache check 实现
2. **优雅回退**: 预计算 CSV 缺失/损坏/缺列,自动回退运行时,**不影响功能**
3. **增量预计算**: 基于 source CSV mtime 检查,只算缺/过期的
4. **可回滚**: 全部 additive 变更,`git checkout + rm` 即可回到现状

---

## §1 预计算脚本设计

**入口**: `D:\project\quant\my-quant3\subjects\pre_compute_factor.py`

**调用方式**:
```bash
python subjects/pre_compute_factor.py              # 增量(只算缺/过期)
python subjects/pre_compute_factor.py --force      # 强制全量重算
python subjects/pre_compute_factor.py --codes 000001,000002   # 指定股票
```

**输入**: `data/data-by-stock/{code}_金玥数据.csv`(5841 个文件,4.7GB)

**输出**: `D:\project\quant\my-quant3\data\data-by-stock-factor\{code}_factor.csv`
- 每只股一个 CSV,文件名 `{code}_factor.csv`(与原 CSV 同前缀)
- 缺失源 CSV 的股:跳过,记录到 stderr

**输出列(13 列)**:
```
日期, close, ma_5, ma_10, ma_20, ma_30, ma_60,
atr_14, rsi_14, donchian_high_20, donchian_low_20,
volume_ratio_20, mom_60
```

| 因子函数 | period(s) | 理由 |
|----------|-----------|------|
| `ma(close, N)` | 5, 10, 20, 30, 60 | 3 strategy 取并集 |
| `atr(H,L,C, 14)` | 14 | 3/3 strategy 用 |
| `rsi(close, 14)` | 14 | 2/3 strategy 用 |
| `donchian_high/low(_, 20)` | 20 | 1/3 strategy 用 |
| `volume_ratio(V, 20)` | 20 | 3/3 strategy 用 |
| `mom(close, 60)` | 60 | 1/3 strategy 用 |
| `close` | — | 原始价,3/3 strategy 用 |

**预计算规模**:
- 300 股 × ~2000 行 × 13 列 × 8 字节 ≈ 60MB
- 实际 CSV 文本 ~80MB,disk 上 ~80MB

**预计算耗时估算**:
- 单股:load CSV 24ms + 11 个 factor × 5-15ms ≈ 175ms/股
- 5841 股全量: ~17 min(用户**不需要**全量,只算实际用到的 universe)
- HS300 300 股: ~52s

**行为细节**:
- 默认:跳过已存在且 mtime 有效的 factor CSV
- `--force`:忽略 mtime,全量重算
- 失败处理:某只股失败,log error 继续下一只(不中断)
- 进度:每 50 只打印一次,最终打印 `OK: N, FAIL: M, SKIP: K`
- 自动创建 `data-by-stock-factor/` 目录(mkdir parents)

---

## §2 回测集成设计

**核心**: 通过 `contextvars.ContextVar` 在 runner 和 factor 函数间传递"当前 stock code",7 个 factor 函数内部增加 cache check。

### 2.1 新文件

**`subjects/subject/factors/_cache.py`**(新):
```python
import contextvars
from typing import Optional
import pandas as pd

_current_code: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("current_code", default=None)
_factor_cache: dict[str, pd.DataFrame] = {}

def bind_current_code(code: Optional[str]) -> contextvars.Token:
    """设置当前 stock code,返回 token 用于 reset。"""
    return _current_code.set(code)

def reset_current_code(token: contextvars.Token) -> None:
    _current_code.reset(token)

def bind_factor_cache(code: str, factor_df: Optional[pd.DataFrame]) -> None:
    """设置某只股的预计算因子 factor_df。None = 移除(禁用 cache)。"""
    if factor_df is not None:
        _factor_cache[code] = factor_df
    elif code in _factor_cache:
        del _factor_cache[code]

def try_get_cached_factor(col: str, length: int | None = None) -> Optional[pd.Series]:
    """查当前 stock 的预计算 Series。length 用于对齐输入 series 长度。"""
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
```

**`subjects/subject/backtest/data_loader/by_stock_factor.py`**(新):
```python
def try_load_stock_factor(code: str) -> Optional[pd.DataFrame]:
    """读 data-by-stock-factor/{code}_factor.csv,返回 DataFrame 或 None。
    
    失败模式(返回 None,不抛):文件不存在、解析失败、缺'日期'列。
    """
    path = DATA_ROOT / "data-by-stock-factor" / f"{code}_factor.csv"
    if not path.exists():
        return None
    try:
        df = pd.read_csv(path, dtype={"日期": str}, keep_default_na=False)
        df["日期"] = pd.to_datetime(df["日期"])
        return df
    except Exception:
        return None
```

### 2.2 修改 7 个 factor 函数

每个文件加 3 行(以 `ma.py` 为例,其他 6 个同样模式):

```python
# subjects/subject/factors/ma.py
from ._cache import try_get_cached_factor

def ma(series: pd.Series, period: int) -> pd.Series:
    cached = try_get_cached_factor(f"ma_{period}", length=len(series))
    if cached is not None:
        return cached
    return series.rolling(period).mean()
```

7 个文件:`ma.py / atr.py / rsi.py / donchian.py / volume_ratio.py / mom.py`(`donchian.py` 含 `donchian_high` 和 `donchian_low` 两个函数,都改)。

### 2.3 runner 集成

**`runner.py:_run_params`(per-stock 循环)**:
- 在 for 循环内,加:
```python
code6 = code.split(".")[0]  # e.g. "000001.SZ" → "000001"
factor_df = try_load_stock_factor(code6)
bind_factor_cache(code6, factor_df)  # None 也传,= 禁用 cache
token = bind_current_code(code6)
try:
    # ... 原有 strategy.compute_factors 调用
    pass
finally:
    reset_current_code(token)
```

**`runner.py:_run_weight`(preload 段,511-525)**:
- 在 `for code in self.universe` 内,与 `load_stock` 同步调 `try_load_stock_factor`
- 存到 `stock_factor_history: dict[str, pd.DataFrame]`(预计算缺失则不存)
- 主循环内,在调 `strategy.compute_factors` 之前:
  ```python
  code6 = code.split(".")[0]
  factor_df = stock_factor_history.get(code6)  # 可能为 None
  bind_factor_cache(code6, factor_df)
  token = bind_current_code(code6)
  try:
      factors = strategy.compute_factors(hist, params)
  finally:
      reset_current_code(token)
  ```

**context 隔离**:用 `bind_current_code` 返回的 `Token` + `reset_current_code(token)` 配对,放在 try/finally 内保证异常路径也 reset。

---

## §3 错误处理 & 边界场景

| 场景 | 行为 | 是否需调整 |
|------|------|----------|
| Factor CSV 不存在 | `try_load_stock_factor` 返回 None → cache 禁用 → 走运行时 | 默认 |
| Factor CSV 缺某列(如 `ma_100`) | 该 factor 调用回退,**其他 factor 仍命中** | 默认 |
| Factor CSV 解析失败 | 返回 None → 整股回退运行时 | 默认 |
| Factor CSV 日期范围 < price CSV | 用现有范围,超出 bar 走运行时 | 默认 |
| **Input series 长度 < cached 长度** | **`try_get_cached_factor` 截取到 length** | ⭐ 关键 |
| 多线程(将来 autoRun ThreadPoolExecutor) | ContextVar 每线程独立 | 默认 |

**关键修正**:params 模式 `df.iloc[:i+1]` 长度递增,缓存的 Series 是全长。**`try_get_cached_factor(col, length=len(series))` 自动截取到对齐**。

### 数据一致性

**`tests/test_precomputed_factors.py`**(新):
- 抽 3 只样本股(HS300 / CSI1000 / 创业板 各 1)
- 对每只股,跑预计算 CSV vs 实时 `subject.factors` 函数,逐位比对 13 列
- 失败 → pre-compute 实现错误

---

## §4 验证 / 回滚 / 实施步骤

### 验证步骤(按顺序)

1. **单元测试**:`pytest tests/test_precomputed_factors.py -v` → 全 PASS
2. **预计算**:`python subjects/pre_compute_factor.py` → 输出 `OK: N, FAIL: 0, SKIP: K`
3. **增量验证**:重跑应 < 1s(mtime 命中)
4. **Benchmark 对比**(关键):
   - params 10y HS300:基线 25:16 → 预期 3-5min,报告数值一致
   - weight 10y HS300:基线 20:14 → 预期 3-5min,报告数值一致
5. **回退验证**:删某只 factor CSV,确认 backtest 仍正常完成
6. **watch 模式**:启动 monitor,改 spec,触发延迟 5-10s + 单次 < 5min

### 性能对比记录

| 测试 | 基线 | 优化后 | 加速比 | 验证 |
|------|------|--------|--------|------|
| params 10y HS300 | 25:16 | (待测) | (待测)x | 报告数值一致 |
| weight 10y HS300 | 20:14 | (待测) | (待测)x | 报告数值一致 |
| watch 模式触发延迟 | ~25min | (待测) | (待测)x | UX 改善 |

### 回滚(完全回到现状)

```bash
git checkout subjects/subject/factors/ subjects/subject/backtest/runner.py
rm -rf data/data-by-stock-factor/
rm -f subjects/pre_compute_factor.py \
      subjects/subject/factors/_cache.py \
      subjects/subject/backtest/data_loader/by_stock_factor.py \
      tests/test_precomputed_factors.py
```

回滚耗时 < 2 min,无数据损坏风险。

### 实施步骤(本轮顺序,预计 ~2.5h)

| # | 内容 | 耗时 |
|---|------|------|
| 1 | 写 `subjects/pre_compute_factor.py` + 13 列 CSV 输出 | 30 min |
| 2 | 写 `subjects/subject/factors/_cache.py` + 7 个 factor 函数加 cache check | 20 min |
| 3 | 写 `subjects/subject/backtest/data_loader/by_stock_factor.py` | 10 min |
| 4 | 改 `runner.py:_run_params + _run_weight` 集成 | 20 min |
| 5 | 写 `tests/test_precomputed_factors.py`(3 只样本股对账) | 15 min |
| 6 | 跑 pre-compute + 跑 params/weight benchmark + 验证报告一致 | 20 min |
| 7 | 写 docs(README + 设计说明) | 15 min |

**严格不自动 commit**(用户偏好):全部完成后,询问用户。

---

## Critical Files

### 新建
- `subjects/pre_compute_factor.py` — 一次性预计算入口
- `subjects/subject/factors/_cache.py` — ContextVar + cache 模块
- `subjects/subject/backtest/data_loader/by_stock_factor.py` — `try_load_stock_factor`
- `tests/test_precomputed_factors.py` — 数值一致性单测

### 修改
- `subjects/subject/factors/{ma,atr,rsi,donchian,volume_ratio,mom}.py` — 各加 3 行 cache check
- `subjects/subject/backtest/runner.py`:`_run_params` + `_run_weight` 加 preload 和 bind

### 不动
- 任何 `subjects/*/generated/strategy.py` — strategy 代码 0 改动
- `autoRun/pipeline.py` — 本轮范围限定
- `subjects/subject/cli/main.py` — 通过 runner 间接生效

---

## Out of Scope (Future)

- ❌ 预计算白名单自动扩展(新 factor 需手动加到 pre_compute_factor.py)
- ❌ 增量预计算(目前是按股粒度的"跳过"而非"增量写入新行")
- ❌ 远程/分布式缓存
- ❌ 自动检测 `subject/factors/*.py` 实现变更并失效 cache(目前依赖 mtime + 手动 `--force`)
- ❌ 公共因子库新增算子(本轮只覆盖现有 7 个)
- ❌ autoRun pipeline 集成(用户决策:本轮不动 pipeline)
- ❌ data-by-day 横截面公共计算(本次只动 data-by-stock)
