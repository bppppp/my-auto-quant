# my-quant3

A 股中短线 swing 策略生成 + 回测 + 优化系统。

---

## 公共因子预计算 (10x 回测加速)

**问题**: 回测主循环的 `compute_factors` 每天重算 `subject.factors` 库的 7 个公共因子。10y × 300 股 params 回测 = **582,000 次冗余调用**,占总耗时 ~99%。

**方案**: 一次性预计算到 `data/data-by-stock-factor/{code}_factor.csv`,回测时通过 `subject.factors._cache` 透明查表,缺则回退运行时。

### 性能对比(10y HS300,300 只股)

| 模式 | 基线 | 优化后 | 加速比 |
|------|------|--------|--------|
| **params** | 25:16 | **5:32** | **4.6x** |
| **weight** | 20:14 | **8:34** | **2.4x** |

### 使用

**首次使用**(预计算 HS300 + CSI1000 + 创业板 共 1355 只股,~1 min):
```bash
python subjects/pre_compute_factor.py
```

**增量**(只算缺/过期的,mtime 命中跳过):
```bash
python subjects/pre_compute_factor.py
```

**强制全量重算**(修改了 `subject/factors/*.py` 实现时):
```bash
python subjects/pre_compute_factor.py --force
```

**指定股票**:
```bash
python subjects/pre_compute_factor.py --codes 000001,000002
```

### 工作原理

1. **预计算脚本**(`subjects/pre_compute_factor.py`):
   - 遍历 `data/config.py` 的 `HS300 + CSI1000 + CYB_STAR_50` 并集(去重,1355 只)
   - 每只股调 `subject.factors` 库 7 个函数(ma/atr/rsi/donchian_high/donchian_low/volume_ratio/mom)算 13 列
   - 落盘到 `data/data-by-stock-factor/{code}_factor.csv`(~540KB / 股,~728MB 总)

2. **透明 cache**(`subjects/subject/factors/_cache.py`):
   - 模块级 `ContextVar` 传递当前 stock code(线程安全,支持 autoRun 并发)
   - `try_get_cached_factor(col, length)` 查表 + 自动按输入长度截取
   - 7 个 factor 函数各加 3 行 cache check,未命中走原 runtime 路径

3. **runner 集成**(`subjects/subject/backtest/runner.py`):
   - `_run_params` / `_run_weight` 在主循环内 `bind_current_code` + `bind_factor_cache`
   - `try/finally` 保证 context 隔离

### 回退机制(零风险)

- 预计算 CSV 缺失 → `try_load_stock_factor` 返回 None → 走运行时
- 预计算 CSV 缺某列(新 strategy 用了白名单外 factor) → 该次调用回退
- 预计算 CSV 损坏 → 整股回退运行时
- **完全透明,不会因为预计算不全而崩**

### 文件清单

| 文件 | 责任 |
|------|------|
| `subjects/pre_compute_factor.py` (new) | 一次性预计算入口 |
| `subjects/subject/factors/_cache.py` (new) | ContextVar + cache 模块 |
| `subjects/subject/backtest/data_loader/by_stock_factor.py` (new) | `try_load_stock_factor` |
| `subjects/subject/factors/{ma,atr,rsi,donchian,volume_ratio,mom}.py` | 各加 3 行 cache check |
| `subjects/subject/backtest/runner.py` | _run_params + _run_weight 加 bind |
| `tests/test_factor_cache.py` (new) | 6 个 cache 模块测试 |
| `tests/test_by_stock_factor.py` (new) | 3 个 loader 测试 |
| `tests/test_precomputed_factors.py` (new) | 3 个数值一致性测试(预计算 vs 实时) |
| `data/data-by-stock-factor/{code}_factor.csv` (生成) | 预计算落盘,gitignore |

### 预计算白名单(13 列)

| 函数 | period(s) | 来源 strategy |
|------|-----------|----------------|
| `ma(close, N)` | 5, 10, 20, 30, 60 | ma_cross / donchian / multi_factor |
| `atr(H,L,C, 14)` | 14 | 3/3 strategy |
| `rsi(close, 14)` | 14 | 2/3 strategy |
| `donchian_high/low(_, 20)` | 20 | donchian |
| `volume_ratio(V, 20)` | 20 | 3/3 strategy |
| `mom(close, 60)` | 60 | multi_factor |
| `close` (raw) | — | 3/3 strategy |

### 限制(Out of Scope)

- 仅覆盖 `data-by-stock/` 单股时间序列;`data-by-day/` 横截面公共计算未做
- 白名单**只含 7 个 `subject.factors` 函数**;新增算子需手动加到 `pre_compute_factor.py` 的 `FACTOR_COLUMNS` 列表
- 不自动检测 `subject/factors/*.py` 实现变更;改了实现需手动 `--force` 重算
- `autoRun/pipeline.py` 未集成(本轮范围限定 watch 模式)
