# 本地 Weight 回测引擎 → 聚宽脚本对接规范

> **目的**: 当一个新策略从本地 weight 模式 (`subjects/subject/backtest/runner.py::_run_weight`) 翻译到聚宽脚本时, 本文档提供逐项对照规则, 避免回测结果出现巨大差距 (>10%) 的常见陷阱.
>
> **参照实现**: `joinQuant/trend_momentum_strategy_1.py` 是已对齐过的标杆.

---

## 0. 摘要 — 一句话原则

> **T-1 严格无前视 + 单一组合管理 + score 加权选股 + 5 个仓位约束链式应用 + 出场每天检查 + 入场只在调仓日**

如果聚宽脚本与本地回测的 `annual_return` / `total_return` 差距 > **5%**, 请**逐项**对照本文档的 9 个章节排查.

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
| 5,10,15,... | 出场 + 调仓 (`bar_idx % freq == 0`) | 同左 |

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

如果策略只有 1 个入场信号 (如 trend_momentum_entry, weight=1.0), 则 score ∈ {0, 1.0}, **所有候选 score 相同, 必须靠 seed shuffle 选股**.

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

**真相**: 即使某个出场信号 `weight = 1e-8` (看起来像"禁用"), **它仍然会被检查并可能触发**.

**示例**: `trend_reversal` (ma_5 < ma_20) 在很多股票上几乎每天成立, 即使 weight=1e-8, 每天都会大量触发出场.

### 3.3 出场信号优先级 (典型趋势策略示例)

| 信号 | 典型 weight | 触发条件 |
|---|---|---|
| rsi_overbought_stop | 3.0 | rsi_14 > 84 (超买止盈) |
| trailing_stop | 0.5 | current_price < highest × (1 - 15%) |
| time_stop | 0.3 | holding_days >= 75 |
| trend_reversal | 1e-8 | ma_5 < ma_20 (**会频繁触发!**) |
| fixed_stop | 1e-8 | current_price < entry × 0.87 |

> 如果想**真正禁用**某个信号, 必须把它从 `exit_weights` 中删除, **不要靠设小 weight**.

### 3.4 持仓不在 universe 时的处理

策略文档要求"所有持仓都要走出场决策", 即使股票被剔出 HS300 也要继续监控:

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
    # 归一化到总和 = 1
    s = sum(out.values())
    if s > 0 and abs(s - 1.0) > 1e-6:
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
    # 只有真正缩放过才归一化
    if any_scaled:
        s = sum(out.values())
        if s > 0 and abs(s - 1.0) > 1e-6:
            out = {k: v / s for k, v in out.items()}
    return out
```

### 4.4 ⚠️ 行业映射必须用历史快照, 不是当前快照

**本地**: `load_industry_map(universe, date_str)` 从 `data-by-day/{date}.csv` 读历史快照.

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

**为什么是高坑?** 同一只股票在不同年代可能属于不同行业 (如某医药股 2019 年属"医药", 2023 年改属"医疗器械"). 用当前快照会导致行业约束错位.

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
    return out
```

### 4.6 ⚠️ 常见漏实现的约束

| 约束 | 默认值 | 是否容易漏 |
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

**聚宽对应**:
```python
# daily_handle step 1 中:
for stock in list(g.holdings.keys()):
    h = g.holdings[stock]
    # ... 更新 highest_close
    h["holding_days"] += 1   # ← 每个交易日 +1
```

⚠️ **错误实现**: `(context.current_dt.date() - entry_date.date()).days` 是日历日, 会比交易日多 ~30% (周末/假日).

> 如果 `max_holding_days = 75`:
> - 本地 (交易日): ≈ 105 个日历日
> - 日历日版本: 75 个日历日 ≈ 53 个交易日
> - **time_stop 触发时机相差近一倍!**

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
    actual_fee = max(actual_amount * 0.0003, 5)
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
    "holding_days": 0,                  # 持仓交易日 (买入当日=0, 次日=1)
    "shares": actual_shares,            # 持仓股数
    "entry_signals": [...],             # 触发入场的信号列表 (用于统计)
    "prev_close": open_px,              # 上一交易日收盘价 (用于决策)
}
```

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
2. ST 信任 HS300 本身就剔除 (一般不含)
3. 不要在 filter_universe 里调 attribute_history (太慢)

```python
def filter_universe(raw_list, context):
    """简化: 只剔除北交所. HS300 成员稳定, 不做其他过滤."""
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

**聚宽对应**: 聚宽 09:30 时 `d.last_price` 可能为 0, `d.high_limit` 也未必准. 推荐**极简版**:
```python
def can_buy_at_open(d, stock):
    """让 order() 自然处理一切异常, 涨停时 filled=0 自动跳过."""
    return True

def can_sell_at_open(d, stock):
    return True
```

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

**症状**: 300 只 HS300 每天 600+ 次 API 调用, 回测速度从分钟级降到小时级.

**修复**: 用 `history()` 批量获取:
```python
def calc_factors_batch(stock_list, context, n=100):
    """4 次 API 拿所有股票数据, 替代 300×4=1200 次."""
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

**性能对比** (300 只股票, 5 年回测):
| 方法 | API 调用 | 耗时 |
|---|---|---|
| 每股 attribute_history(100) | ~300/天 | 数小时 |
| 批量 history(100) | ~4/天 | 几分钟 |
| **加速比** | **75x** | - |

### 7.3 ⚠️ `get_current_data()` 在 09:30 不可靠

**症状**: `filter_universe` 把 300 只全部判定为 `paused=True`.

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
| 买入佣金 | 万 2.5 | `open_commission=0.00025` |
| 卖出佣金 | 万 2.5 | `close_commission=0.00025` |
| 沪市过户费 | 万 0.1 | ❌ 聚宽 API 不支持, 无法对齐 |
| 卖出印花税 | 千 1 | `close_tax=0.001` |
| 最低佣金 | 5 元 | `min_commission=5` |

```python
set_order_cost(OrderCost(
    open_tax=0,
    close_tax=0.001,
    open_commission=0.00025,        # 万 2.5, 不是聚宽默认的 0.0003!
    close_commission=0.00025,
    close_today_commission=0,
    min_commission=5
), type="stock")
```

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

| 来源 | 单笔影响 | 一年累计 (假设 100 笔) |
|---|---|---|
| 佣金差 (万 0.5) | 0.005% | ~0.5% |
| 沪市过户费 | 0.001% (仅 .SH) | ~0.05% |
| 滑点 (0.05% 双向) | 0.1% | ~10% |

⚠️ **滑点是最大差异源**, 务必显式设置.


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

- ☐ ✅ `scores = {}` 只给非持仓股算 score
- ☐ ✅ `rank_top_n(scores, target_n, seed=42)` 必须传 seed
- ☐ ✅ `if not top_codes: return` 无候选时持仓不动 (**高坑**)
- ☐ ✅ `target_weights = {c: 1.0 / target_n for c in top_codes}` 等权起步

### 9.3 5 个仓位约束

- ☐ ✅ `enforce_max_single_weight` 软约束 + 缩放归一化
- ☐ ✅ `enforce_industry_concentration` 软约束 + 缩放
- ☐ ✅ `enforce_max_turnover` 不要漏!
- ☐ ✅ `get_industry(stock_list, date=context.previous_date)` 传历史日期 (**高坑**)
- ☐ ✅ 约束链顺序: single → industry → turnover

### 9.4 出场逻辑

- ☐ ✅ 出场每天检查 (不受 rebalance_freq 限制)
- ☐ ✅ `sorted(exit_w, key=exit_w.get, reverse=True)` 按 weight 降序
- ☐ ✅ 第一个触发就 return (不是 sum)
- ☐ ⚠️ 如想"禁用"信号, 必须**从 exit_weights 删除**, 不要靠小 weight

### 9.5 持仓状态

- ☐ ✅ `holding_days += 1` 每个交易日累加 (不是 (today - entry_date).days)
- ☐ ✅ `entry_price = (amount + fee) / shares` 含费
- ☐ ✅ `highest_close` 用 T-1 收盘价更新 (下一日 step 1)
- ☐ ✅ `prev_close` 缓存 T-1 收盘价 (出场决策用)

### 9.6 A 股规则

- ☐ ✅ 北交所代码前缀过滤 (`4/8/92xxxx`)
- ☐ ✅ ST 信任 HS300/universe, 不在 09:30 检查 `cd.is_st`
- ☐ ✅ `filter_universe` 不调 `attribute_history` (性能!)
- ☐ ✅ `can_buy_at_open` / `can_sell_at_open` 极简版 (return True)
- ☐ ✅ 检查 `order_result.filled` (涨停时 filled=0)
- ☐ ✅ 科创板 (688) 用 `LimitOrderStyle`

### 9.7 性能

- ☐ ✅ `calc_factors_batch` 用 `history()` 批量
- ☐ ✅ 单股 fallback `calc_factors_t1` 仅用于持仓股不在 universe 时
- ☐ ✅ universe 缓存策略 (可选优化)

### 9.8 内置函数 (聚宽环境)

- ☐ ✅ `import builtins; _sum = builtins.sum; _max = builtins.max; _min = builtins.min`
- ☐ ✅ 所有 `sum(d.values())` → `_sum(d.values())`
- ☐ ✅ 所有 `max(a, b)` (2-arg) → `_max(a, b)`
- ☐ ✅ 所有 `min(a, b)` (2-arg) → `_min(a, b)`

### 9.9 费用与滑点

- ☐ ✅ `OrderCost(open_commission=0.00025, close_commission=0.00025)` (万 2.5)
- ☐ ✅ `OrderCost(close_tax=0.001)` (印花税千 1)
- ☐ ✅ `set_slippage(FixedSlippage(0))` 完全对齐 / `FixedSlippage(0.0005)` 保守

### 9.10 复权与数据

- ☐ ✅ `attribute_history(..., fq="pre")` 前复权
- ☐ ✅ `history(..., fq="pre")` 前复权
- ☐ ✅ `attribute_history(..., skip_paused=True)` (单股)
- ☐ ✅ `history(..., skip_paused=False)` (批量, NaN 对齐)

---

## 10. 标杆参照实现

完整可运行的对齐脚本: `joinQuant/trend_momentum_strategy_1.py`

### 10.1 脚本结构 (10 个章节)

```
1. PARAMS 配置区
   ├─ benchmark / universe_index
   ├─ 因子窗口
   ├─ 入场/出场阈值
   ├─ 5 个仓位约束
   ├─ entry_weights / exit_weights
   └─ tie_break_seed = 42

2. initialize (单一调度 run_daily 09:30)

3. 因子计算
   ├─ _ema / _atr / _rsi (helpers)
   ├─ calc_factors_t1 (单股 fallback)
   └─ calc_factors_batch (批量主流程)

4. 入场信号
   ├─ get_triggered_signals
   └─ entry_score

5. 出场信号
   ├─ _check_exit_signal
   └─ should_exit (按 weight 降序)

6. 排序与约束
   ├─ rank_top_n (seed=42 + shuffle)
   ├─ enforce_max_single_weight
   ├─ enforce_industry_concentration
   ├─ enforce_max_turnover
   └─ should_rebalance

7. A 股规则
   ├─ _is_bj
   ├─ filter_universe (只剔除北交所)
   ├─ get_industry_map (传 date)
   ├─ can_buy_at_open / can_sell_at_open (return True)

8. daily_handle 主循环 (5 步)
   ├─ step 1: 更新 highest_close + holding_days += 1
   ├─ step 2: 刷新 universe (含 industry)
   ├─ step 3: 算因子 + score
   ├─ step 4: 出场决策 (每天)
   └─ step 5: 调仓 (调仓日)

9. _do_rebalance
   ├─ rank_top_n
   ├─ enforce 链
   ├─ 卖出不在 target 的
   └─ 买入新进的

10. 执行
    ├─ _execute_buy (含费 entry_price)
    └─ _execute_sell (检查 last_price fallback)
```

### 10.2 关键不变量

```python
# 这些约定不要改:
- bar_index 从 1 开始
- 首日 (bar_idx=1) 完全跳过交易
- 出场每天做, 入场只在调仓日做
- holding_days 是交易日, 不是日历日
- entry_price 含买入费用
- rank_top_n seed=42 (保证可复现)
- 5 个仓位约束按顺序链式应用
- get_industry_map 必须传 date 参数
```

---

## 11. 调试与差异定位

### 11.1 当本地与聚宽差距 > 10% 时, 按顺序排查

1. **第一步**: 对比两边的**首次调仓日**:
   - 本地: bar_idx=5 (即第 5 个交易日)
   - 聚宽: g.bar_index=5
   - 若不一致 → 检查首日是否正确跳过 (bar_idx==1)

2. **第二步**: 对比两边的**入场日股票列表**:
   - 同样 seed=42, 同样 scores → 应该选出同样 top N
   - 若不一致 → 检查 entry_score 计算是否一致

3. **第三步**: 对比两边的**出场触发分布**:
   - 应该有相同的出场信号分布 (rsi_overbought / trailing_stop / time_stop)
   - 若分布差异大 → 检查 holding_days (交易日 vs 日历日)
   - 若 trend_reversal 多 → 检查权重为 1e-8 时是否仍触发 (本地行为)

4. **第四步**: 对比**单笔交易的 PnL**:
   - 公式: `(open_px - effective_entry) * shares - sell_fee`
   - 若差异 ~ 0.05% → 滑点差异 (聚宽 vs 本地)
   - 若差异 ~ 0.03% → 佣金差异 (万 3 vs 万 2.5)
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
| 3 | `filter_universe` 用 `cd.paused` | `300 只全部被过滤为 paused` | 删除 paused 检查 |
| 4 | `can_buy_at_open` 检查 `cd.is_st` | `7 只候选全部无法买入` | 简化为 `return True` |
| 5 | `filter_universe` 调 `attribute_history` | 回测极慢 (小时级) | 删除上市天数检查 |
| 6 | 单股 `attribute_history` | 每天 300+ API 调用 | 用 `history()` 批量 |
| 7 | `scores={}` 时全部清仓 | 弱市变 100% 现金 | `if not top_codes: return` |
| 8 | `get_industry()` 没传 date | 用当前快照而非历史 | 传 `date=previous_date` |
| 9 | `holding_days` 用日历日 | time_stop 触发提前 | 改成交易日 +=1 |
| 10 | `entry_price` 不含费 | PnL 偏乐观 0.03% | `(amount + fee) / shares` |
| 11 | exit weight=1e-8 当"禁用" | trend_reversal 仍频繁触发 | 真要禁用就删除 |
| 12 | 涨停时 `order` 返回非 None | 错误记录持仓 | 检查 `order.filled > 0` |
| 13 | 14:55 决策 + 09:30 执行 | 使用了 T 日盘中数据 | 改成 09:30 单一调度 |
| 14 | 没设 `fq="pre"` | 默认后复权, 价格异常 | 显式传 `fq="pre"` |
| 15 | 加仓/减仓逻辑 | 本地引擎不支持 | 删除这部分代码 |

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
                          f"weight 极小但仍会触发, 如想禁用请删除该项")

    if issues:
        log.warn("=== PARAMS 自检发现 %d 个问题 ===" % len(issues))
        for i in issues:
            log.warn("  - %s" % i)
    else:
        log.info("=== PARAMS 自检通过 ===")
    return len(issues) == 0
```

---

**版本**: 1.0
**创建日期**: 2026-06-14
**参照标杆**: `joinQuant/trend_momentum_strategy_1.py`
**对齐目标**: 与 `subjects/subject/backtest/runner.py::_run_weight` 完全等价
