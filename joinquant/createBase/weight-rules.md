# 本地 Weight 回测引擎 → 聚宽脚本对接规范

> **目的**: 当一个新策略从本地 weight 模式 (`subjects/subject/backtest/runner.py::_run_weight`) 翻译到聚宽脚本时, 本文档提供逐项对照规则, 避免回测结果出现巨大差距的常见陷阱.
>
> **适用范围**: 任何从本地 weight 引擎迁移到聚宽回测的策略. 本文档只描述**对接规范**, 不绑定具体策略/因子/参数.

---

## 0. 摘要 — 一句话原则

> **T-1 严格无前视 + 单一组合管理 + score 加权选股 + 5 个仓位约束链式应用 + 出场每天检查 + 入场只在调仓日**

如果聚宽脚本与本地回测的 `annual_return` / `total_return` 差距 > **5%**, 请**逐项**对照本文档的章节排查.

---

## 1. 决策时序模型 (最重要)

### 1.1 严格 T-1 因子 + T 开盘成交

**本地**:
```python
# runner.py 主循环
for bar_idx, date_str in enumerate(trading_dates, 1):  # bar_idx 从 1 开始
    if bar_idx == 1:
        # 第一天: 跳过所有交易, 只记初始 value
        continue

    # 用 T-1 数据计算因子 (严格无前视!)
    hist_t1 = hist.iloc[:idx_today]  # 不含当日的历史切片
    factors = strategy.compute_factors(hist_t1, params)
    prev_close = hist_t1["收盘价"].iloc[-1]  # T-1 收盘价

    # 决策时点的 "当前价" = T-1 收盘价
    pos_dict["current_price"] = prev_close

    # 用 T 开盘价成交
    if can_sell_at_open(bar_series, prev_close, code):
        open_px = float(bar_series["开盘价"])
        # 卖出
```

**聚宽对应**:
```python
run_daily(daily_handle, time="09:30")  # 09:30 触发, 严格对齐

def daily_handle(context):
    g.bar_index += 1
    if g.bar_index == 1:
        return  # 首日跳过

    # 用 attribute_history (默认不含当日) 拿 T-1 数据
    df = attribute_history(stock, n, "1d", [...], skip_paused=True, df=True, fq="pre")
    # df.iloc[-1] 就是 T-1 收盘 K 线 ← 与本地 hist.iloc[:idx_today] 等价

    # 用 get_current_data().last_price (T 开盘价) 成交
```

### 1.2 ⚠️ 关键陷阱: 不要在 14:55 决策

**错误做法** (实盘风格):
```python
run_daily(generate_signals, time="14:55")    # 用当日盘中数据
run_daily(execute_pending, time="09:30")     # 次日开盘成交
```

**问题**: 14:55 时 `attribute_history` 拿到的最新一根 K 线包含**当日盘中数据**, 等价"用部分 T 日数据决策" → 与本地 T-1 严格视角不同, 回测结果会偏乐观.

**正确做法**: 09:30 统一触发, 决策 + 执行在同一个回调.

### 1.3 bar_idx 计数规则

| bar_idx | 本地行为 | 聚宽对应 |
|---|---|---|
| 1 (首日) | `continue`, 只记 daily_value | `return`, 不做任何交易 |
| 2,3,4 | 仅出场检查, 不调仓 | 同左 |
| freq, 2×freq, ... | 出场 + 调仓 (`bar_idx % freq == 0`) | 同左 |

**关键事实** (2026-06 更新, 修正 `should_rebalance` docstring 的错误描述):
- 本地 runner.py 用 `for bar_idx, date_str in enumerate(trading_dates, 1)` → **bar_idx 是 1-based** (1, 2, 3, ...)
- `if bar_idx == 1: continue` 跳过首日 (没有 T-1 数据)
- `should_rebalance(bar_idx, freq)` 触发条件 `bar_idx % freq == 0`, freq=5 时首次 rebalance 在 bar_idx=5
- ⚠️ `subjects/subject/backtest/portfolio.py:should_rebalance` 的 docstring 写"0-based, 0,5,10..."是**误导**, 实际 runner 传的是 1-based, 触发点为 5, 10, 15, ...

```python
def should_rebalance(bar_index, freq):
    if freq <= 0:
        return False
    return bar_index % freq == 0
```


---

## 2. 入场逻辑

### 2.1 入场分两步: 算分 (每天) + 选股 (调仓日)

**本地**:
```python
# 每天: 算所有股票的 score
for code in day_data:
    factors = strategy.compute_factors(hist_t1, params)
    score = strategy.entry_score(factors, params, weights)
    scores[code] = score

# 只在调仓日选 top N + 调仓
if should_rebalance(bar_idx, freq):
    top_codes = rank_top_n(scores, target_n, seed=42)
```

### 2.2 ⚠️ scores 为空时的行为 — 高坑

**本地**:
```python
top_codes = rank_top_n(scores, target_n, seed=42)
if top_codes:        # ← 注意这个 if!
    # ... 调仓 (卖出不在 target 的 + 买入新进的)

# 没有 else: 即 top_codes 为空 → 整个调仓块不执行 → 持仓不动
```

**聚宽对应**:
```python
def _do_rebalance(scores, ...):
    top_codes = rank_top_n(scores, target_n, seed=42)
    if not top_codes:
        log.info("无 score>0 候选, 跳过调仓 (持仓不动)")
        return  # ← 必须 return! 不能继续执行清仓逻辑

    # 后续调仓逻辑...
```

**为什么这个坑大?** 弱市/震荡市无信号时, 错误实现会**全部清仓变现金**, 与本地"持仓继续扛"行为完全相反, 收益曲线差异巨大.

### 2.3 rank_top_n 排序规则

```python
def rank_top_n(scores, top_n, seed=42):
    positives = [(k, v) for k, v in scores.items() if v > 0]
    positives.sort(key=lambda kv: (kv[1], kv[0]), reverse=True)  # score 降序, code 升序
    result = [k for k, _ in positives[:top_n]]
    # 同 score 用 random.shuffle 打乱 (避免每次固定选某几只)
    if seed is not None and len(result) > 1:
        all_scores = set(v for _, v in positives[:top_n])
        if len(all_scores) == 1:
            random.seed(seed)
            random.shuffle(result)
    return result
```

⚠️ `seed=42` 必须保留, 保证回测可复现.

### 2.4 entry_score 计算

```python
def entry_score(factors, p):
    """score = Σ(触发信号 × entry_weights[信号])"""
    triggered = get_triggered_signals(factors, p)
    score = 0.0
    for sig in triggered:
        score += float(p["entry_weights"].get(sig, 0.0))
    return score
```

### 2.5 ⚠️ 高坑: scores 必须含**所有股票**(包括持仓), 不要过滤持仓

**本地** `runner.py`:
```python
for code, row in day_data.items():      # ← 遍历所有股票
    ...
    scores[code] = score                  # ← 不论是否持仓, 都算 score
```

**错误实现**(会让调仓日"卖光所有持仓"):
```python
scores = {}
for stock, f in factors_by_code.items():
    if stock not in g.holdings:           # ← 这行是 bug
        s = entry_score(f, p)
        if s > 0:
            scores[stock] = s
```

**为什么是高坑?**
- `scores` 里少了持仓 → `rank_top_n` 选的 top N 全是新候选
- `target_weights` 全部都是新候选 → 卖出块的 `if stock in target_weights: continue` 永远不命中
- → 调仓日**所有持仓被无差别卖出**, 违背"留赢家, 卖输家"的核心意图

**正确实现**:
```python
scores = {}
for stock, f in factors_by_code.items():
    s = entry_score(f, p)
    if s > 0:
        scores[stock] = s
# 不过滤持仓. 持仓股在 universe 中, 会自动进入 scores.
# 持仓不在 universe 时 (罕见), 单独 fallback 补算后加入 scores.
```

**buy 块已经有 `if stock in g.holdings: continue` 保护**, 所以保留持仓股的 score 不会导致"重复买".

如果策略只有 1 个入场信号 (weight = 1.0), 则 score ∈ {0, 1.0}, **所有候选 score 相同, 必须靠 seed shuffle 选股**.

---

## 3. 出场逻辑 (与入场完全独立)

### 3.1 出场每天检查, 不受 rebalance_freq 限制

**本地**:
```python
# 每天的主循环都执行:
for code in list(portfolio.positions.keys()):
    exit_sig = strategy.should_exit(pos_dict, factors, params, weights)
    if exit_sig:
        if can_sell_at_open(...):
            portfolio.sell(...)
```

**聚宽对应**:
```python
def daily_handle(context):
    # ... 不论是不是调仓日 ...

    # step 4: 出场决策 (每天都做)
    for stock in list(g.holdings.keys()):
        exit_sig = should_exit(...)
        if exit_sig:
            _execute_sell(...)

    # step 5: 调仓 (只在调仓日)
    if should_rebalance(bar_idx, p["rebalance_freq_days"]):
        _do_rebalance(...)
```

### 3.2 ⚠️ 高坑: exit_weights 仅决定优先级, 不决定是否触发

```python
def should_exit(factors, holding, current_price, p):
    exit_w = p["exit_weights"]
    # 按 weight 降序遍历, 第一个触发就 return
    for sig in sorted(exit_w, key=exit_w.get, reverse=True):
        if _check_exit_signal(sig, ...):
            return sig    # ← 触发就返回, 不管 weight 大小!
    return None
```

**真相**: 即使某个出场信号 `weight` 非常小 (例如 `1e-8`), **它仍然会被检查并可能触发**, 仅排在优先级最末.

### 3.2.1 ✅ 正确实现: 任何 `weight > 0` 的信号都参与触发

按 weight 降序遍历, **第一个满足触发条件的信号就出场**; `weight == 0` 才是真正禁用.

**实现**:
```python
def should_exit(factors, holding, current_price, p):
    exit_w = p["exit_weights"]
    # weight == 0 才是真正"禁用"; 任何 weight > 0 的信号都参与触发, 仅按优先级排序
    active_sigs = [s for s, w in exit_w.items() if w > 0]
    for sig in sorted(active_sigs, key=exit_w.get, reverse=True):
        if _check_exit_signal(sig, factors, holding, current_price, p):
            return sig
    return None
```

> **.final.md 与脚本必须一致**: spec 里把某信号 weight 调到极小 (如 `1e-8`),
> 脚本 `should_exit` 必须保留该信号 (仅排在最末), 触发条件成立时仍会平仓.
> **weight 仅决定优先级, 不决定是否启用**.

### 3.3 出场信号优先级 (通用示例)

| 信号 | 典型 weight 量级 | 触发条件 | 备注 |
|---|---|---|---|
| 优先级最高 | 高 (e.g. 1.0+) | 由 spec 定义 | 最先检查 |
| 普通优先级 | 中 (e.g. 0.3~1.0) | 由 spec 定义 | |
| 最低优先级 | 极小 (e.g. 1e-8) | 由 spec 定义 | **仍会触发, 仅兜底** |

> 如果想**真正禁用**某个信号, 二选一:
> 1. 将其 `weight` 设为 `0` (`should_exit` 跳过 `weight == 0` 的信号, 保留 spec 原值便于追溯)
> 2. 直接从 `exit_weights` 中删除该键 (暴力, 改动 spec)
>
> **不要靠极小 weight (如 `1e-8`) 实现禁用**: 极小 weight 仅表示"低优先级", 触发条件成立时仍会平仓.

### 3.4 持仓不在 universe 时的处理

策略文档要求"所有持仓都要走出场决策", 即使股票被剔出 universe 也要继续监控:

```python
# step 3: 算因子时, 给持仓股单独算 (universe 中可能没有)
for stock in list(g.holdings.keys()):
    if stock not in factors_by_code:
        f = calc_factors_t1(stock, context, n=100)
        if f is not None:
            factors_by_code[stock] = f
```


---

## 4. 5 个仓位约束 (链式应用, 软约束 + 归一化)

### 4.1 完整调用链

```python
target_weights = {c: 1.0 / target_n for c in top_codes}  # 等权起步
target_weights = enforce_max_single_weight(target_weights, max_single)
target_weights = enforce_industry_concentration(target_weights, industry_map, max_industry)
current_weights = portfolio.weights(prices)
target_weights = enforce_max_turnover(current_weights, target_weights, max_turnover)
```

### 4.2 enforce_max_single_weight (单票上限)

**算法**: 超出 max_pct 的部分**按比例分配给其他未触顶的股票**, 最后归一化.

```python
def enforce_max_single_weight(weights, max_pct):
    out = {}
    excess = 0.0
    for code, w in weights.items():
        if w > max_pct:
            excess += w - max_pct
            out[code] = max_pct
        else:
            out[code] = w
    if excess > 0:
        others = {k: v for k, v in out.items() if v < max_pct}
        others_total = sum(others.values())
        if others_total > 0:
            scale = (others_total + excess) / others_total
            for k in others:
                out[k] *= scale
        else:
            for k in out:
                out[k] = max_pct
    # ⚠️ 仅当 sum > 1 + epsilon (overweight) 时 re-normalize;
    #    sum < 1 (underweight) 时保留, 由 fill_cash 补齐.
    #    错误实现 `if abs(s-1) > epsilon` 会让 cap 失效.
    s = sum(out.values())
    if s > 1.0 + 1e-6:
        out = {k: v / s for k, v in out.items()}
    return out
```

⚠️ **不要**实现成"超限就剔除该股", 那是硬约束, 与本地软约束不同.

### 4.3 enforce_industry_concentration (行业上限)

**算法**: 超限行业**按比例缩放该行业内所有股票的权重**, 触发缩放后归一化.

```python
def enforce_industry_concentration(weights, industry_map, max_pct):
    industry_total = {}
    for code, w in weights.items():
        ind = industry_map.get(code, "unknown")
        industry_total[ind] = industry_total.get(ind, 0.0) + w
    scale = {}
    for ind, total in industry_total.items():
        scale[ind] = max_pct / total if total > max_pct else 1.0
    out = {}
    any_scaled = False
    for code, w in weights.items():
        ind = industry_map.get(code, "unknown")
        out[code] = w * scale[ind]
        if scale[ind] < 1.0:
            any_scaled = True
    # ⚠️ 仅当 sum > 1 + epsilon 时 re-normalize; sum < 1 时保留 (fill_cash 补).
    if any_scaled:
        s = sum(out.values())
        if s > 1.0 + 1e-6:
            out = {k: v / s for k, v in out.items()}
    return out
```

### 4.4 ⚠️ 行业映射必须用历史快照, 不是当前快照

**本地**: `load_industry_map(universe, date_str)` 从历史的当日横截面读历史快照.

**聚宽对应**:
```python
def get_industry_map(stock_list, date=None):
    if date is not None:
        ind = get_industry(stock_list, date=date)  # ← 必须传 date!
    else:
        ind = get_industry(stock_list)
    # ...

# 调用时:
g.industry_map = get_industry_map(g.universe, date=context.previous_date)
```

**为什么是高坑?** 同一只股票在不同年代可能属于不同行业 (行业分类会调整). 用当前快照会导致行业约束错位.

### 4.5 enforce_max_turnover (换手上限)

```python
def enforce_max_turnover(current, target, max_pct):
    turnover = sum(abs(target.get(c, 0) - current.get(c, 0)) for c in set(target)|set(current)) / 2.0
    if turnover <= max_pct:
        return target
    # 超限: 目标向当前方向回退
    scale = max_pct / turnover
    out = {}
    for c in set(target) | set(current):
        cur = current.get(c, 0.0)
        tgt = target.get(c, 0.0)
        out[c] = cur + (tgt - cur) * scale
    # ⚠️ 本地不 re-normalize, 保留 sum < 1 由 fill_cash 补齐.
    #    聚宽错误实现 `if abs(s-1) > epsilon: normalize` 会破坏 turnover 缩放语义.
    s = sum(out.values())
    if s > 1.0 + 1e-6:
        out = {k: v / s for k, v in out.items()}
    return out
```

### 4.5.1 fill_cash_with_remaining_candidates (现金沉淀填补)

**本地** `runner.py` 在 3 个 enforce 之后**显式调用** `fill_cash_with_remaining_candidates`,
用剩余候选股把 industry / turnover 缩放留下的 cash 沉淀填满.

**为什么需要?** 当 `max_industry` 把某个行业缩到上限, 或者 `max_turnover` 把整体缩到上限,
target_weights 的 sum 可能 < 1, 剩余 cash 不会被投资, 拖累收益.

**实现**:
```python
def fill_cash_with_remaining_candidates(
    target_weights, scores, target_n, max_single,
    industry_map=None, max_industry=1.0,
    cash_threshold=0.01, max_n_multiplier=2.0,
):
    if not scores or not target_weights:
        return target_weights

    leftover = 1.0 - sum(target_weights.values())
    if leftover < cash_threshold:    # 残留 < 1% 不补
        return target_weights

    in_target = set(target_weights.keys())
    # 按 score 降序, score > 0, 不在 target 中
    candidates = sorted(
        [(c, s) for c, s in scores.items() if c not in in_target and s > 0],
        key=lambda x: x[1],
        reverse=True,
    )

    out = dict(target_weights)
    max_n = int(target_n * max_n_multiplier)

    for code, _score in candidates:
        if len(out) >= max_n:        # 持仓数上限 = target_n × 2
            break
        leftover = 1.0 - sum(out.values())
        if leftover < cash_threshold:
            break

        new_w = leftover
        if max_single > 0 and new_w > max_single:
            new_w = max_single

        if industry_map is not None and max_industry < 1.0:
            ind = industry_map.get(code, "unknown")
            current_ind_total = sum(
                w for c, w in out.items()
                if industry_map.get(c, "unknown") == ind
            )
            ind_room = max_industry - current_ind_total
            if ind_room <= 0:
                continue
            if new_w > ind_room:
                new_w = ind_room

        if new_w < cash_threshold:
            continue

        out[code] = new_w

    return out
```

**调用位置** (`_do_rebalance` 中):
```python
target_weights = enforce_max_single_weight(target_weights, max_single)
target_weights = enforce_industry_concentration(target_weights, g.industry_map, max_industry)
current_weights = _compute_current_weights(context)
target_weights = enforce_max_turnover(current_weights, target_weights, max_turnover)

# ↓↓↓ 必须加 ↓↓↓
target_weights = fill_cash_with_remaining_candidates(
    target_weights=target_weights,
    scores=scores,                  # ← scores 含所有股票 (含持仓), 详见 §2.5
    target_n=target_n,
    max_single=max_single,
    industry_map=g.industry_map,
    max_industry=max_industry,
)
```

**为什么容易漏?** 3 个 enforce 函数都不修改 sum 之外的逻辑,
调用者如果不显式补 fill_cash, 就不会有"现金补齐"这一步.
本地 runner 在 3 个 enforce 之后紧跟着调 fill_cash, 是一对耦合的调用.

### 4.6 ⚠️ 常见漏实现的约束

| 约束 | 默认值 (本地) | 是否容易漏 |
|---|---|---|
| max_single_weight | 0.10 | 中 |
| max_industry_concentration | 0.30 | 中 |
| **max_turnover_per_rebalance** | **0.50** | **高 (实盘风格脚本常漏!)** |
| target_holdings | 8 | 低 |
| rebalance_freq_days | 5 | 低 |


---

## 5. 持仓状态管理

### 5.1 holding_days 按交易日累加 (非日历日)

**本地** `Portfolio.update_after_bar`:
```python
def update_after_bar(self, code, close):
    pos = self.positions.get(code)
    if pos is None:
        return
    pos.highest = max(pos.highest, close)
    pos.holding_days += 1   # ← 每根 K 线 +1, 不是日历日
```

**本地** `Portfolio.buy` (P3 修复, line 142):
```python
self.positions[code] = Position(
    code=code, shares=shares,
    entry_price=effective_entry, entry_date=date,
    highest=price, holding_days=1,    # ← 1-based, 不是 0
    entry_signals=entry_signals or [],
)
```

**关键事实** (2026-06 更新, **P3 修复**):
- buy 时 hd=**1** (1-based, 与 params 模式口径一致)
- 旧版 hd=0 + update_after_bar +=1 实际是 1-based 但容易在 weight 模式 day-2 立即 exit 时记录为 hd=0
- 新版直接 buy 设 hd=1, 统一跨模式口径

**聚宽对应**:
```python
# _execute_buy 中:
g.holdings[stock] = {
    "entry_price": effective_entry,
    "highest_close": open_px,
    "holding_days": 1,    # ← 1-based, 对齐本地 P3 修复
    ...
}

# daily_handle step 1 中:
for stock in list(g.holdings.keys()):
    h = g.holdings[stock]
    h["highest_close"] = _max(h.get("highest_close", h["entry_price"]), t1_close)
    h["prev_close"] = t1_close
    h["holding_days"] += 1   # ← 每个交易日 +1
```

⚠️ **错误实现**: `(context.current_dt.date() - entry_date.date()).days` 是日历日, 会比交易日多 ~30% (周末/假日).

⚠️ **常见错实现**: buy 时设 `holding_days=0` (旧版习惯, 已 P3 修复). 这会让 time_stop 晚 1 天触发:
- max_holding_days=45 时, 正确 (hd=1 起步) 在 buy 日 + 44 触发
- 错误 (hd=0 起步) 在 buy 日 + 45 触发, 差 1 个交易日

> 时间类出场信号 (如 `holding_days >= N`) 用日历日会**提前**触发 (日历日走得更快),
> 与本地行为**相差近一倍**.

### 5.2 highest_close 更新时机

**本地**: 在出场决策**之后**, 调仓**之前**, 用 T 收盘价更新.

```python
# 3. 出场决策
for code in positions:
    exit_sig = should_exit(...)
    # ...

# 收盘后更新 highest 和 holding_days
for code in positions:
    if code in day_data:
        close = float(day_data[code]["收盘价"])
        portfolio.update_after_bar(code, close)

# 4. 调仓
if should_rebalance(...):
    # ...
```

**聚宽对应**: 在下一日的 step 1 用 `attribute_history(1)` 拿 T-1 close 补做:

```python
# step 1: 更新 highest_close
for stock in list(g.holdings.keys()):
    h = g.holdings[stock]
    df = attribute_history(stock, 1, "1d", ["close"], skip_paused=True, df=True, fq="pre")
    t1_close = float(df["close"].iloc[-1])
    h["highest_close"] = max(h.get("highest_close", h["entry_price"]), t1_close)
    h["prev_close"] = t1_close
    h["holding_days"] += 1
```

### 5.3 entry_price 含费用调整

**本地** `Portfolio.buy`:
```python
amount = price * shares
fee = calc_buy_fee(amount, code)
effective_entry = (amount + fee) / shares   # 含费
self.positions[code] = Position(entry_price=effective_entry, ...)
```

**聚宽对应**:
```python
def _execute_buy(stock, open_px, shares, ...):
    # ...下单成交后...
    actual_amount = open_px * actual_shares
    actual_fee = max(actual_amount * commission_rate, min_commission)
    effective_entry = (actual_amount + actual_fee) / actual_shares
    g.holdings[stock] = {"entry_price": effective_entry, ...}
```

⚠️ 不要直接用 `entry_price = open_px`, PnL 会偏乐观.

### 5.4 持仓状态字典完整字段

```python
g.holdings[stock] = {
    "entry_price": effective_entry,    # 含费成交价
    "entry_date": context.current_dt,   # 入场日期
    "highest_close": open_px,           # 持仓期间最高收盘价
    "holding_days": 1,                  # 持仓交易日 (P3 修复: 买入当日=1, 次日=2)
    "shares": actual_shares,            # 持仓股数
    "entry_signals": [...],             # 触发入场的信号列表 (用于统计)
    "prev_close": open_px,              # 上一交易日收盘价 (用于决策)
}
```

> ⚠️ 旧版 `holding_days: 0` 与本地 P3 修复不一致, 已修正为 `1`. 详见 §5.1.

---

## 6. A 股交易规则

### 6.1 板块涨跌幅限制

| 板块 | 代码前缀 | 涨跌幅 |
|---|---|---|
| 沪主板 | 60xxxx | ±10% |
| 深主板 | 000/001/002/003xxx | ±10% |
| 创业板 | 30xxxx | ±20% |
| 科创板 | 68xxxx | ±20% |
| 北交所 | 4/8/92xxxx | ±30% |
| ST | 任何 | ±5% |

### 6.2 ST/北交所过滤 — universe 阶段

**本地** `exclude_st` + `exclude_bj` 在 `_run_weight` 主循环开始就过滤:
```python
df = exclude_bj(df)
df = exclude_st(df)
df = df[df["代码"].isin(set(self.universe))].copy()
```

**聚宽对应**: 聚宽 09:30 时 `cd.is_st` / `cd.paused` 不可靠, 推荐:
1. 北交所用代码前缀过滤 (确定性)
2. ST 信任 universe 本身已剔除 (一般不含)
3. 不要在 filter_universe 里调 attribute_history (太慢)

```python
def filter_universe(raw_list, context):
    """简化: 只剔除北交所. 大盘指数成员稳定, 不做其他过滤."""
    out = []
    for s in raw_list:
        if _is_bj(s):
            continue
        out.append(s)
    return out

def _is_bj(stock):
    bare = stock.split(".")[0]
    return bare.startswith(("4", "8", "92"))
```

### 6.3 涨停/跌停判断 — 决策阶段

**本地** `can_buy_at_open` / `can_sell_at_open`:
```python
def can_buy_at_open(bar, prev_close, code, epsilon=0.01):
    if bar.is_st:
        return False
    open_px = float(bar["开盘价"])
    limit_pct = get_limit_pct(code, is_st)
    limit_up_px = prev_close * (1.0 + limit_pct)
    if open_px > limit_up_px - epsilon:
        return False
    return True
```

**聚宽对应** (2026-06 更新): 聚宽 09:30 时 `d.paused` / `d.is_st` 不可靠, 但 `d.high_limit` / `d.low_limit` / `d.last_price` 仍可用. 之前推荐"极简版 return True"虽方便, 但**会让 sell 路径在跌停时下废单** (买入路径靠 `order.filled == 0` 兜底, 但卖出没有等效检查).

**推荐实现** (检查 d.high_limit / d.low_limit):
```python
def can_buy_at_open(d, stock):
    """T 日开盘能否买入. 检查涨停 (last_price >= high_limit) 防止废单.
    本地等价检查 bar.low == bar.high == limit_price (一字板).
    注: d.high_limit = 0 表示无涨跌幅限制 (如新股上市首日), 此时不阻拦.
    """
    if d is None:
        return False
    if d.high_limit > 0 and d.last_price is not None and d.last_price > 0:
        if d.last_price >= d.high_limit - 0.01:
            return False  # 涨停: 不能买入
    return True

def can_sell_at_open(d, stock):
    """T 日开盘能否卖出. 检查跌停 (last_price <= low_limit) 防止废单."""
    if d is None:
        return False
    if d.low_limit > 0 and d.last_price is not None and d.last_price > 0:
        if d.last_price <= d.low_limit + 0.01:
            return False  # 跌停: 不能卖出
    return True
```

> **为什么不简化成 return True?** 
> 买入路径有 `order.filled == 0` 兜底, 卖单虽然也有 `order_result` 检查, 但**跌停时 order 会返回非 None 但 filled=0**, 此时若继续走 `_execute_sell` 的删除持仓逻辑, 会丢失正确的"等明天"语义. 提前在 can_sell_at_open 拦截更准确.
> **为什么不查 d.paused?** 09:30 时这个字段对未撮合股票默认 True, 误判严重.

### 6.4 ⚠️ order() 涨停处理 — 必须检查 filled

**聚宽特性**: 涨停时 `order(stock, shares)` 返回 `Order` 对象, **但 `filled = 0`**.

```python
def _execute_buy(stock, ...):
    order_result = order(stock, shares)
    if order_result is None:
        return  # 下单完全失败

    # 检查实际成交股数 (涨停时为 0)
    filled_shares = getattr(order_result, "filled", 0)
    if filled_shares == 0:
        log.info("下单未成交 (涨停/无对手盘): %s" % stock)
        return

    actual_shares = int(filled_shares)
    # 用实际成交股数计算 entry_price
```

### 6.5 科创板 / 创业板限价单

**聚宽特性**: 科创板 (688xxx) 默认必须用 `LimitOrderStyle`:

```python
if stock.startswith("688"):
    limit_price = min(open_px * 1.005, 9999.99)
    order_result = order(stock, shares, LimitOrderStyle(limit_price))
else:
    order_result = order(stock, shares)
```

### 6.6 ⚠️ 科创板买入整手 200 股 (不是 100!)

**A 股规则**: 科创板 (688xxx) 单笔买入申报**最低 200 股**, 卖出可不足 200 股 (零股卖出).
主板/中小板/创业板仍为 100 股/手. 北交所已在前置过滤剔除.

**错误实现** (整手 100, 会被聚宽拒单):
```python
shares = int(amount / open_px / 100) * 100   # 688 也会被错误按 100 整手
```

**正确实现**:
```python
# 科创板 200 股/手, 其他 100 股/手
lot_size = 200 if stock.startswith("688") else 100
shares = int(amount / open_px / lot_size) * lot_size
if shares < lot_size:
    continue   # 不够 1 手, 跳过 (避免 0 股订单)
```

**为什么是高坑?** 科创板 200 股整手是上交所的特殊规定, 容易和"全市场 100 股"混淆.
若按 100 整手买 688, 聚宽会按 100 股下单, 系统直接拒单, 日志里只有 `order_result.filled=0`,
不会报"参数错误", 排查困难.

### 6.7 ⚠️ 科创板卖出限价也要加 9999.99 上限

买入端有 `_min(open_px * 1.005, 9999.99)` 的上限保护. 卖出端常被遗漏:

**错误实现** (只有下限, 无上限):
```python
if stock.startswith("688"):
    limit_price = _max(open_px * 0.995, 0.01)   # ← 只有下限
    if limit_price >= 10000:
        limit_price = 9999.99                   # ← 这个判断对卖出端无效 (0.995x 不会 >= 10000)
    order_result = order(stock, -shares, LimitOrderStyle(limit_price))
```

**正确实现** (买入卖出都用 `_min(..., 9999.99)`):
```python
if stock.startswith("688"):
    limit_price = _max(open_px * 0.995, 0.01)   # 下限: 不低于 0.01
    limit_price = _min(limit_price, 9999.99)    # 上限: 不高于 9999.99
    order_result = order(stock, -shares, LimitOrderStyle(limit_price))
```

**为什么是坑?** 卖出 `_max(open_px * 0.995, 0.01)` 在正常股价下不可能 ≥ 10000,
但若遇到极端情况 (退市残留/异常高价/数据错误), 9999.99 上限可避免 order 被聚宽拒为"价格超限".


---

## 7. 聚宽环境陷阱 (与本地差异源)

### 7.1 ⚠️ `from jqdata import *` 会覆盖 Python 内置函数

**症状**:
```
TypeError: '>' not supported between instances of 'dict_values' and 'int'
```

**原因**: 聚宽全局命名空间引入了 numpy, `numpy.sum(dict_values)` 返回原对象而非标量.

**修复**: 文件顶部用 `builtins` 别名:
```python
import builtins
_sum = builtins.sum
_max = builtins.max
_min = builtins.min
```

**必须替换的 5 处**:
| 调用 | 风险 |
|---|---|
| `sum(d.values())` | 高 (报错) |
| `sum(generator)` | 高 |
| `max(a, b)` (2-arg) | **极高** (numpy.max 把 b 当 axis) |
| `min(a, b)` (2-arg) | **极高** |

### 7.2 ⚠️ `attribute_history` 每股调用极慢

**症状**: 大 universe 每天数千次 API 调用, 回测速度从分钟级降到小时级.

**修复**: 用 `history()` 批量获取:
```python
def calc_factors_batch(stock_list, context, n=100):
    """4 次 API 拿所有股票数据, 替代 N×4 次."""
    df_close = history(n, "1d", "close", stock_list, df=True, skip_paused=False, fq="pre")
    df_high = history(n, "1d", "high", stock_list, df=True, skip_paused=False, fq="pre")
    df_low = history(n, "1d", "low", stock_list, df=True, skip_paused=False, fq="pre")
    df_volume = history(n, "1d", "volume", stock_list, df=True, skip_paused=False, fq="pre")

    out = {}
    for stock in stock_list:
        if stock not in df_close.columns:
            continue
        close = df_close[stock]
        # ... 计算因子
        out[stock] = {...}
    return out
```

**性能对比** (假设 universe=N 只股票, 5 年回测):
| 方法 | API 调用 | 耗时 |
|---|---|---|
| 每股 attribute_history(100) | ~N/天 | 数小时 |
| 批量 history(100) | ~4/天 | 几分钟 |

### 7.3 ⚠️ `get_current_data()` 在 09:30 不可靠

**症状**: `filter_universe` 把候选股票全部判定为 `paused=True`.

**原因**: 09:30 触发时是开盘瞬间, 连续竞价刚开始, 聚宽对未撮合股票的 `cd.paused`/`cd.is_st`/`cd.last_price` 默认值不可靠.

**修复**: 不要在 universe 过滤阶段依赖 `cd.paused`/`cd.is_st`:
```python
def filter_universe(raw_list, context):
    """只剔除北交所, 其他过滤交给后续阶段."""
    out = []
    for s in raw_list:
        if _is_bj(s):
            continue
        out.append(s)
    return out
```

**价格 fallback 链**:
```python
# 买入时获取价格 (优先级链):
open_px = 0
if d is not None and d.last_price > 0:
    open_px = float(d.last_price)      # 优先: 实时价
else:
    f = factors_by_code.get(stock)
    if f is not None and f.get("close") > 0:
        open_px = float(f["close"])     # Fallback: T-1 收盘价
if open_px <= 0:
    continue   # 完全无效, 跳过
```

### 7.4 ⚠️ 默认 fq 复权方式

| 项 | 本地 | 聚宽 |
|---|---|---|
| 复权方式 | CSV 自带的前复权 | 必须显式传 `fq="pre"` |

聚宽 `attribute_history(stock, n, "1d", [...], fq="pre")` 必须传 `fq="pre"`, 否则默认是后复权!

### 7.5 ⚠️ skip_paused 参数

| 调用 | 推荐 |
|---|---|
| `attribute_history(...)` | `skip_paused=True` (跳过停牌日, 保持因子稳定) |
| `history(...)` (批量) | `skip_paused=False` (NaN 填充, 便于对齐日期) |

---

## 8. 费用与滑点 (无法完全对齐, 但可接近)

### 8.1 费用对照表

| 费用项 | 本地 (`fees.py`) | 聚宽推荐 (`OrderCost`) |
|---|---|---|
| 买入佣金 | `calc_buy_fee` | `open_commission=对应费率` |
| 卖出佣金 | `calc_sell_fee` | `close_commission=对应费率` |
| 沪市过户费 | `calc_buy_fee` / `calc_sell_fee` 内部 | ❌ 聚宽 API 不支持, 无法对齐 |
| 卖出印花税 | `calc_sell_fee` | `close_tax=对应费率` |
| 最低佣金 | 5 元 | `min_commission=5` |

```python
set_order_cost(OrderCost(
    open_tax=0,
    close_tax=<印花税率>,
    open_commission=<买入佣金率>,
    close_commission=<卖出佣金率>,
    close_today_commission=0,
    min_commission=5
), type="stock")
```

> **费率要与本地 `fees.py` 完全一致**, 否则每年累积差异显著.

### 8.2 滑点对齐

| 项 | 本地 | 聚宽 |
|---|---|---|
| 默认 | 无滑点 | `FixedSlippage(0.0005)` (0.05%) |

**完全对齐**:
```python
set_slippage(FixedSlippage(0))   # 无滑点
```

**保守 (推荐实际跑实盘前用)**:
```python
set_slippage(FixedSlippage(0.0005))   # 保留聚宽默认
```

### 8.3 累计误差估计

| 来源 | 单笔影响 | 一年累计 (假设 N 笔) |
|---|---|---|
| 佣金差 (如有) | 取决于费率差 | 约 N × 单笔差 |
| 沪市过户费 | 取决于费率 | 约 N × 单笔差 |
| 滑点 (0.05% 双向) | 0.1% | 约 N × 0.1% |

⚠️ **滑点通常是最大差异源**, 务必显式设置.


---

## 9. 完整对照检查表

在生成新的聚宽脚本时, 按本检查表逐项验证 (✅ = 必须对齐):

### 9.1 决策时序

- ☐ ✅ `run_daily(daily_handle, time="09:30")` 单一调度 (不要 14:55/09:30 分离)
- ☐ ✅ `attribute_history` / `history` 用默认 (不含当日)
- ☐ ✅ `g.bar_index` 从 1 开始
- ☐ ✅ `if bar_idx == 1: return` 首日跳过
- ☐ ✅ `should_rebalance: bar_idx % freq == 0`

### 9.2 入场逻辑

- ☐ ✅ **`scores = {}` 必须含所有股票 (含持仓)**, 不要过滤持仓 (⚠️ 高坑, 违反"留赢家"意图)
- ☐ ✅ `rank_top_n(scores, target_n, seed=42)` 必须传 seed
- ☐ ✅ `if not top_codes: return` 无候选时持仓不动 (**高坑**)
- ☐ ✅ `target_weights = {c: 1.0 / target_n for c in top_codes}` 等权起步

### 9.3 5 个仓位约束

- ☐ ✅ `enforce_max_single_weight` 软约束 + 缩放归一化
- ☐ ✅ `enforce_industry_concentration` 软约束 + 缩放
- ☐ ✅ `enforce_max_turnover` 不要漏!
- ☐ ✅ **`fill_cash_with_remaining_candidates` 不要漏!** (⚠️ 高坑, 与本地 runner 对齐)
- ☐ ✅ `get_industry(stock_list, date=context.previous_date)` 传历史日期 (**高坑**)
- ☐ ✅ 约束链顺序: single → industry → turnover → fill_cash
- ☐ ⚠️ **3 个 enforce 函数的 re-normalize 仅在 sum > 1 + epsilon (overweight) 时执行**;
      错误实现 `abs(s-1) > epsilon` 会让 cap 失效

### 9.4 出场逻辑

- ☐ ✅ 出场每天检查 (不受 rebalance_freq 限制)
- ☐ ✅ `sorted(exit_w, key=exit_w.get, reverse=True)` 按 weight 降序
- ☐ ✅ 第一个触发就 return (不是 sum)
- ☐ ⚠️ 如想"禁用"信号, 必须 `weight=0` 或**从 exit_weights 删除**, **不要靠小 weight**
- ☐ ⚠️ **spec 里设极小 weight 的信号, 脚本 `should_exit` 必须保留并仍触发**
      (作为最低优先级兜底) — weight 仅决定优先级, 不决定是否启用

### 9.5 持仓状态

- ☐ ✅ `holding_days += 1` 每个交易日累加 (不是 (today - entry_date).days)
- ☐ ✅ `entry_price = (amount + fee) / shares` 含费
- ☐ ✅ `highest_close` 用 T-1 收盘价更新 (下一日 step 1)
- ☐ ✅ `prev_close` 缓存 T-1 收盘价 (出场决策用)
- ☐ ⚠️ **holding_days 1-based (buy 设 1, step 1 +=1 → hd=2)**: 对齐本地 runner P3 修复
      (subjects/subject/backtest/portfolio.py:142). 旧版 buy 设 0 会让 time_stop 晚 1 天触发.

### 9.6 A 股规则

- ☐ ✅ 北交所代码前缀过滤 (`4/8/92xxxx`)
- ☐ ✅ ST 信任 universe 本身已剔除, 不在 09:30 检查 `cd.is_st`
- ☐ ✅ `filter_universe` 不调 `attribute_history` (性能!)
- ☐ ✅ `can_buy_at_open` / `can_sell_at_open` 检查 d.high_limit / d.low_limit (防止卖跌停下废单)
- ☐ ✅ 检查 `order_result.filled` (涨停时 filled=0)
- ☐ ✅ 科创板 (688) 用 `LimitOrderStyle`
- ☐ ⚠️ **科创板 (688) 买入整手 200 股, 其他 100 股** (`lot_size = 200 if '688' else 100`)
- ☐ ⚠️ 科创板卖出限价**也要**加 `_min(limit_price, 9999.99)` 上限, 与买入端对齐

### 9.7 性能

- ☐ ✅ `calc_factors_batch` 用 `history()` 批量
- ☐ ✅ 单股 fallback 仅用于持仓股不在 universe 时
- ☐ ✅ universe 缓存策略 (可选优化)

### 9.8 内置函数 (聚宽环境)

- ☐ ✅ `import builtins; _sum = builtins.sum; _max = builtins.max; _min = builtins.min`
- ☐ ✅ 所有 `sum(d.values())` → `_sum(d.values())`
- ☐ ✅ 所有 `max(a, b)` (2-arg) → `_max(a, b)`
- ☐ ✅ 所有 `min(a, b)` (2-arg) → `_min(a, b)`

### 9.9 费用与滑点

- ☐ ✅ `OrderCost(open_commission=本地费率, close_commission=本地费率)`
- ☐ ✅ `OrderCost(close_tax=本地印花税率)`
- ☐ ✅ `set_slippage(FixedSlippage(0))` 完全对齐 / `FixedSlippage(0.0005)` 保守

### 9.10 复权与数据

- ☐ ✅ `attribute_history(..., fq="pre")` 前复权
- ☐ ✅ `history(..., fq="pre")` 前复权
- ☐ ✅ `attribute_history(..., skip_paused=True)` (单股)
- ☐ ✅ `history(..., skip_paused=False)` (批量, NaN 对齐)

---

## 10. 关键不变量

任何策略对接都必须遵守的约定, 不可改动:

```python
# 这些约定不要改:
- bar_index 从 1 开始 (本地 enumerate(..., 1))
- 首日 (bar_idx=1) 完全跳过交易
- 出场每天做, 入场只在调仓日做
- holding_days 是交易日, 不是日历日; 1-based (buy 设 1, P3 修复)
- entry_price 含买入费用
- rank_top_n seed=42 (保证可复现)
- 5 个仓位约束按顺序链式应用
- get_industry_map 必须传 date 参数
- exit weight == 0 才是真正禁用, weight > 0 都参与触发
- can_buy/sell_at_open 必须检查 d.high_limit / d.low_limit (卖跌停不能下废单)
```

---

## 11. 调试与差异定位

### 11.1 当本地与聚宽差距 > 5% 时, 按顺序排查

1. **第一步**: 对比两边的**首次调仓日**:
   - 本地: bar_idx=freq (即第 freq 个交易日)
   - 聚宽: g.bar_index=freq
   - 若不一致 → 检查首日是否正确跳过 (bar_idx==1)

2. **第二步**: 对比两边的**入场日股票列表**:
   - 同样 seed=42, 同样 scores → 应该选出同样 top N
   - 若不一致 → 检查 entry_score 计算是否一致

3. **第三步**: 对比两边的**出场触发分布**:
   - 应该有相同的出场信号分布
   - 若分布差异大 → 检查 holding_days (交易日 vs 日历日)
   - 若极小 weight 的信号缺失 → 检查 `should_exit` 是否错误地跳过了这些信号
     (正确行为是 weight > 0 都参与触发)

4. **第四步**: 对比**单笔交易的 PnL**:
   - 公式: `(open_px - effective_entry) * shares - sell_fee`
   - 若差异 ≈ 0.05% → 滑点差异 (聚宽 vs 本地)
   - 若差异 ≈ 佣金差 → 检查 OrderCost 费率
   - 若差异 > 0.5% → 检查 entry_price 是否含费

5. **第五步**: 对比**调仓日的仓位约束**:
   - 同样 universe → 应该有同样 industry_map → 同样的 enforce 结果
   - 若不一致 → 检查 get_industry_map 是否传了 date 参数

### 11.2 推荐的 sanity check 日志

```python
def daily_handle(context):
    # ...
    log.info("[%s] bar_idx=%d, universe=%d, scores>0=%d, holdings=%d, %s" % (
             context.current_dt.strftime("%Y-%m-%d"),
             g.bar_index, len(g.universe), len(scores), len(g.holdings),
             "调仓日" if should_rebalance(...) else "持仓维护"))
```

### 11.3 单笔交易诊断日志

```python
# _execute_buy:
log.info(">>> 买入 %s: %d股 @ %.2f, 含费成本=%.4f, 金额=%.0f" %
         (stock, actual_shares, open_px, effective_entry, actual_amount))

# _execute_sell:
log.info(">>> 卖出 %s: %d股 @ %.2f, PnL=%.2f, 持仓=%d交易日, 信号=%s" %
         (stock, shares, open_px, pnl, holding_days, exit_signal))
```

---

## 12. 历史教训汇总 (踩过的坑)

| 编号 | 问题 | 症状 | 修复 |
|---|---|---|---|
| 1 | `sum(d.values())` 被 numpy 覆盖 | `TypeError: dict_values vs int` | 用 `_sum = builtins.sum` |
| 2 | `max(a, b)` 被 numpy 覆盖 | `axis 参数错误` | 用 `_max = builtins.max` |
| 3 | `filter_universe` 用 `cd.paused` | 候选全部被过滤为 paused | 删除 paused 检查 |
| 4 | `can_buy_at_open` 检查 `cd.is_st` | 候选全部无法买入 | 简化为 `return True` |
| 5 | `filter_universe` 调 `attribute_history` | 回测极慢 (小时级) | 删除上市天数检查 |
| 6 | 单股 `attribute_history` | 每天 N+ API 调用 | 用 `history()` 批量 |
| 7 | `scores={}` 时全部清仓 | 弱市变 100% 现金 | `if not top_codes: return` |
| 8 | `get_industry()` 没传 date | 用当前快照而非历史 | 传 `date=previous_date` |
| 9 | `holding_days` 用日历日 | 时间类出场信号触发提前 | 改成交易日 +=1 |
| 10 | `entry_price` 不含费 | PnL 偏乐观 | `(amount + fee) / shares` |
| 11 | exit 极小 weight 误当"禁用" | 低优先级信号被跳过, 兜底失效 | `should_exit` 仅跳过 `weight == 0`, 极小 weight 仍参与触发 |
| 12 | 涨停时 `order` 返回非 None | 错误记录持仓 | 检查 `order.filled > 0` |
| 13 | 14:55 决策 + 09:30 执行 | 使用了 T 日盘中数据 | 改成 09:30 单一调度 |
| 14 | 没设 `fq="pre"` | 默认后复权, 价格异常 | 显式传 `fq="pre"` |
| 15 | 加仓/减仓逻辑 | 本地引擎不支持 | 删除这部分代码 |
| 16 | 科创板 (688) 整手 100 股 | order 被聚宽拒, 无明显报错 | `lot_size = 200 if '688' else 100` |
| 17 | enforce_* re-normalize `abs(s-1) > epsilon` | cap 失效, 持仓超 max_single | 仅 `sum > 1 + epsilon` 时 re-normalize |
| 18 | 科创板卖出限价缺 9999.99 上限 | 极端价时 order 被拒 | `_min(limit_price, 9999.99)` |
| 19 | `set_universe()` 未在 initialize 预填 | 每天 N+ lazy load 慢 | initialize 末尾 `set_universe(stock_list)` |
| 20 | **scores 过滤持仓(`if stock not in g.holdings`)** | 调仓日所有持仓被无差别卖出 | 删掉过滤, scores 含所有股票 |
| 21 | **未调 `fill_cash_with_remaining_candidates`** | industry/turnover 缩放后 cash 沉淀 | 3 enforce 后紧接 fill_cash |
| 22 | **holding_days 旧版用 0-based (buy 设 0)** | time_stop 晚 1 天触发, 与本地 P3 修复不一致 | buy 改设 1, step 1 +=1 (1-based) |
| 23 | **`can_buy/sell_at_open` 极简化 (return True)** | 卖跌停时下废单, 浪费订单且日志噪音大 | 检查 d.high_limit / d.low_limit 提前拦截 |

---

## 附录 A: 一键自检脚本

```python
def self_check():
    """启动前自检 PARAMS 是否符合本规范"""
    p = PARAMS
    issues = []

    # 1. 必填字段
    for key in ["target_holdings", "max_single_weight", "max_industry_concentration",
                "max_turnover_per_rebalance", "rebalance_freq_days",
                "entry_weights", "exit_weights", "tie_break_seed"]:
        if key not in p:
            issues.append(f"PARAMS 缺少必填字段: {key}")

    # 2. tie_break_seed = 42 (保证与本地可复现一致)
    if p.get("tie_break_seed") != 42:
        issues.append("tie_break_seed 应为 42, 与本地 rank_top_n 默认一致")

    # 3. 入场信号 weight > 0
    for sig, w in p.get("entry_weights", {}).items():
        if w <= 0:
            issues.append(f"entry_weights[{sig}] = {w}, 应 > 0")

    # 4. 出场信号 weight 警告
    for sig, w in p.get("exit_weights", {}).items():
        if 0 < w < 1e-6:
            issues.append(f"exit_weights[{sig}] = {w:.2e}, "
                          f"weight 极小但仍会触发, 如想禁用请删除该项或设 weight=0")

    if issues:
        log.warn("=== PARAMS 自检发现 %d 个问题 ===" % len(issues))
        for i in issues:
            log.warn("  - %s" % i)
    else:
        log.info("=== PARAMS 自检通过 ===")
    return len(issues) == 0
```

---

**版本**: 2.0 (通用规则化重写)
**适用范围**: 任何从本地 weight 引擎迁移到聚宽回测的策略
**对齐目标**: 与 `subjects/subject/backtest/runner.py::_run_weight` 行为等价