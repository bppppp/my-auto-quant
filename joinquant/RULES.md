# 聚宽 (JoinQuant) 脚本生成规则

> **本文件是入口性规则**,给出生成新聚宽脚本时**必须遵守**的核心约定。
> 详细 API/对接规范/实战踩坑 → 见 [`createBase/`](./createBase/) 下的三份源材料。

---

## 0. 必读源材料 (`createBase/`)

| 文件 | 用途 | 何时查阅 |
|---|---|---|
| `JQuantAPI.md` | 聚宽 API 完整参考 + 16 节 JQBoson 引擎 Quirks + 17 节实战踩坑 | 写新 API 调用前;遇到平台行为异常时 |
| `weight-rules.md` | 本地 weight 引擎 → 聚宽脚本的逐项对接规范 (12 章) | 翻译新策略时;本地 vs 聚宽回测差距 > 5% 时按 §11.1 排查 |
| `template_trend_momentum_strategy_1.py` | 已对齐的标杆实现 (11 章,1030 行) | 新策略直接复制此文件的骨架,只改 PARAMS + 因子 + 信号 |

> 标杆参照:`joinQuant/script/trend_momentum_strategy_1.py` (基于上述模板生成,可在聚宽直接回测)。

---

## 1. 一句话原则

> **T-1 严格无前视 + 单一组合管理 + score 加权选股 + 5 个仓位约束链式应用 + 出场每天检查 + 入场只在调仓日**

如果聚宽脚本与本地 weight 回测 (`subjects/subject/backtest/runner.py::_run_weight`) 的 `annual_return` / `total_return` 差距 > **5%**,按 `createBase/weight-rules.md` §11.1 的 5 步顺序逐项排查。

---

## 2. 新策略存放

**位置:** `joinQuant/script/<strategy_name>.py`

| 命名约定 | 说明 |
|---|---|
| 蛇形命名 | `multi_factor_trend_swing.py`,`donchian_adx_volume_entry_1.py` |
| 数字后缀表示版本 | `xxx_1.py` → `xxx_2.py` 同一策略的不同版本 |
| **必须**与 `subjects/<strategy_name>/` 同名 | 方便对齐本地回测与聚宽回测 |
| 配套文档放 `subjects/<strategy_name>/<strategy_name>_v*.md` | 策略 spec / 调参记录 |

**禁止** 把新策略放在 `joinQuant/` 根目录或 `createBase/` 下。

---

## 3. 脚本结构 (11 章节,严格按此顺序)

直接复制 `createBase/template_trend_momentum_strategy_1.py` 的骨架,只改以下三块:

| 章节 | 内容 | 修改范围 |
|---|---|---|
| 1. PARAMS | 参数配置 | **必须改**:因子窗口/入场阈值/出场阈值/5 仓位约束/entry&exit_weights |
| 3. 因子计算 | `_ema` / `_atr` / `_rsi` / `calc_factors_batch` | **按需改**:加新因子 helper,改 batch 字段 |
| 4. 入场信号 | `get_triggered_signals` / `entry_score` | **必改**:实现新策略的入场逻辑 |
| 5. 出场信号 | `_check_exit_signal` / `should_exit` | **按需改**:加新出场信号 |
| 其它章节 | 2/6/7/8/9/10/11 | **不许改**:已与本地引擎完全等价 |

**PARAMS 必填字段** (少了任一都会导致与本地回测错位):

```python
PARAMS = {
    "benchmark": "000300.XSHG",
    "use_fixed_universe": True,           # 固定股票池,跨期可比
    "universe_index": "000300.XSHG",
    # 因子窗口
    "ma_short": 5, "ma_mid": 20, "ma_long": 60,
    # 5 仓位约束
    "target_holdings": 7,
    "max_single_weight": 0.4,
    "max_industry_concentration": 0.5,
    "max_turnover_per_rebalance": 0.5,    # 极易漏!
    "rebalance_freq_days": 5,
    # 信号权重
    "entry_weights": {"your_entry_signal": 1.0},
    "exit_weights": {"rsi_overbought_stop": 3.0, "trailing_stop": 0.5, ...},
    # tie-break 种子 (保证与本地 rank_top_n 可复现)
    "tie_break_seed": 42,
}
```

---

## 4. 关键 Quirks 速查 (Top 15)

每条都是**真坑**,违反必导致回测异常。完整 25+ 条见 `createBase/JQuantAPI.md` §16-17。

| # | Quirk | 修复 |
|---|---|---|
| 1 | `from jqdata import *` 后 `sum(d.values())` 返回 dict_values | 文件顶部 `import builtins; _sum = builtins.sum` |
| 2 | `max(a, b)` 被 numpy 覆盖,把 b 当 axis | `_max = builtins.max`,`min` 同理 |
| 3 | `cd.get(s)` 不会触发 lazy loading | 用 `cd[s] + try/except KeyError`,并 `set_universe(stock_list)` 预填 |
| 4 | `cd.high_limit` 可能为 0,`last_price >= 0` 恒真 | 比较前加 `> 0` 守卫 |
| 5 | 科创板 (688) 市价单需保护限价 | `if stock.startswith("688"): order(s, shares, LimitOrderStyle(px*1.005))` |
| 6 | `order()` 涨停时返回 Order 但 `filled=0` | 下单后**必须** `if order_result.filled == 0: return` |
| 7 | `order_target_value` 偶尔内部推算数量为 0 | 改用 `order(stock, delta_shares)`,自己算股数 |
| 8 | `g.params` 长列表/嵌套 dict 丢键 | PARAMS 中**只放标量**,长列表放独立模块级常量 |
| 9 | 09:30 时 `cd.paused` / `cd.is_st` 不可靠 | `filter_universe` 只做北交所代码前缀过滤,其他交给 order 结果 |
| 10 | `attribute_history` 每股调用 300+ API | 用 `history(n, '1d', 'close', stock_list, df=True)` 批量 (75x 加速) |
| 11 | `attribute_history(...)` 默认 `skip_paused=True` 太严 | 批量 `history()` 用 `skip_paused=False` (NaN 对齐) |
| 12 | 14:55 决策 + 09:30 执行 = 用了 T 日盘中数据 | **统一** `run_daily(daily_handle, time="09:30")` 单一调度 |
| 13 | `get_fundamentals` 不传 date 会引入未来函数 | `get_fundamentals(q, date=context.previous_date)` |
| 14 | `get_industry()` 默认当前快照,跨年错位 | `get_industry(stock_list, date=context.previous_date)` |
| 15 | Python 3.6 不支持 `list[str]` / `X \| Y` 注解 | 全部用无注解,或加 `from __future__ import annotations` |
| 16 | **科创板 (688) 买入整手 200 股,不是 100** | `lot_size = 200 if '688' else 100` |
| 17 | **3 个 enforce 函数 `abs(s-1)>1e-6` 归一化** → cap 失效 | 仅 `s > 1.0 + 1e-6` (overweight) 时 re-normalize |
| 18 | **科创板卖出限价缺 9999.99 上限** | `_min(limit_price, 9999.99)` 对齐买入端 |
| 19 | **`.final.md` 设 weight=1e-8 "禁用" 信号,脚本仍触发** | `should_exit` 跳过 `weight < 1e-6` 的信号 |
| 20 | **scores 过滤持仓(`if stock not in g.holdings`)** | 调仓日所有持仓被卖光 | 删过滤,scores 含所有股票 |
| 21 | **未调 `fill_cash_with_remaining_candidates`** | industry/turnover 缩放后 cash 沉淀 | 3 enforce 后紧接 fill_cash |

**额外诡异坑**:`np.isnan(合法正数)` 在 JQBoson 引擎下**会返回 True**!改用 `np.isfinite` 末尾验证 (见 `JQuantAPI.md` §17.1.2)。

---

## 5. 自检 Checklist (生成新脚本时必走一遍)

每条对应一个会出**静默错误**的高频坑,缺一个回测结果就可能偏差 > 10%。

### 5.1 决策时序
- [ ] `run_daily(daily_handle, time="09:30")` 单一调度 (没有 14:55 决策)
- [ ] `g.bar_index` 从 1 开始,`if bar_idx == 1: return`
- [ ] `should_rebalance: bar_idx % freq == 0`

### 5.2 入场
- [ ] `rank_top_n(scores, target_n, seed=42)` 传 seed
- [ ] **`if not top_codes: return`** 无候选时持仓不动 (⚠️ 高坑:弱市全部清仓变现金)
- [ ] `target_weights = {c: 1.0 / target_n for c in top_codes}` 等权起步
- [ ] **`scores = {}` 必须含所有股票(含持仓)** (⚠️ 高坑:过滤持仓会"卖光持仓",违反"留赢家"意图)

### 5.3 5 个仓位约束 (按顺序)
- [ ] `enforce_max_single_weight(0.4)` 软约束 + 缩放归一化
- [ ] `enforce_industry_concentration(0.5)` 软约束
- [ ] **`enforce_max_turnover(0.5)`** 极易漏,实盘风格脚本常缺
- [ ] **`fill_cash_with_remaining_candidates`** 补齐 industry/turnover 留下的 cash 沉淀 (⚠️ 高坑)
- [ ] `get_industry_map(stock_list, date=context.previous_date)` 传历史日期 (⚠️ 高坑)
- [ ] 约束链顺序: single → industry → turnover → fill_cash
- [ ] **3 个 enforce 函数的 re-normalize 仅在 `s > 1.0 + 1e-6` 时执行** (⚠️ 高坑)

### 5.4 出场
- [ ] 出场**每天**检查 (不受 rebalance_freq 限制)
- [ ] `sorted(exit_w, key=exit_w.get, reverse=True)` 按 weight 降序
- [ ] 第一个触发就 return (短路,**不**是 sum)
- [ ] 想"禁用"信号 → **二选一**:
  - `should_exit` 跳过 `weight < 1e-6` 的信号 (推荐,保留 spec 原值)
  - 从 `exit_weights` 删除该键 (1e-8 仍会触发!)

### 5.5 持仓状态
- [ ] `holding_days += 1` 按**交易日**累加,**不**是 `(today - entry_date).days`
- [ ] `entry_price = (amount + fee) / shares` 含费
- [ ] `highest_close` 在下一日 step 1 用 T-1 close 更新
- [ ] **holding_days 0-based (buy 设 0, step 1 +=1)** — 与本地 runner 对齐,不要改 1-based

### 5.6 A 股规则
- [ ] 北交所代码前缀过滤 (`4/8/92` 开头)
- [ ] `filter_universe` 不调 `attribute_history` (性能!)
- [ ] `can_buy_at_open` / `can_sell_at_open` 极简 `return True`
- [ ] `_execute_buy` 检查 `order_result.filled > 0`
- [ ] 科创板 (688) 买入用 `LimitOrderStyle`,卖出也用限价
- [ ] **科创板 (688) 整手 200 股** (`lot_size = 200 if '688' else 100`,⚠️ 高坑)
- [ ] 科创板卖出限价**也要** `_min(limit_price, 9999.99)` 上限

### 5.7 性能
- [ ] `calc_factors_batch` 用 `history()` 批量 (不要 300 次 `attribute_history`)
- [ ] `set_universe(stock_list)` 在 `initialize` 中预填

### 5.8 内置函数 (聚宽环境)
- [ ] 文件顶部 `import builtins; _sum/_max/_min = builtins.sum/max/min`
- [ ] 所有 `sum(d.values())` → `_sum(d.values())`
- [ ] 所有 2-arg `max(a, b)` / `min(a, b)` → `_max(a, b)` / `_min(a, b)`

### 5.9 费用与滑点
- [ ] `OrderCost(open_commission=0.00025, close_commission=0.00025, close_tax=0.001)`
- [ ] `set_slippage(FixedSlippage(0))` 完全对齐 / `FixedSlippage(0.0005)` 保守
- [ ] 沪市过户费聚宽不支持,无法对齐 (单笔影响 ~0.001%)

### 5.10 复权与数据
- [ ] `attribute_history(..., fq="pre")` 显式前复权
- [ ] `history(..., fq="pre")` 显式前复权

---

## 6. 调试流程 (本地 vs 聚宽差距 > 5% 时)

按 `createBase/weight-rules.md` §11.1 顺序排查:

1. 对比**首次调仓日** (应为 bar_idx=5)
2. 对比**入场日股票列表** (应一致,否则 entry_score 有差)
3. 对比**出场触发分布** (看 holding_days + 1e-8 weight 触发)
4. 对比**单笔 PnL** (~0.05% 差 = 滑点;~0.03% = 佣金;> 0.5% = entry_price 不含费)
5. 对比**调仓日仓位约束** (应一致,否则 industry_map 没用历史日期)

加诊断日志的模板见 `weight-rules.md` §11.2-11.3。

---

## 7. 一键自检脚本 (复制到策略文件末尾)

```python
def self_check():
    """启动前自检 PARAMS, 触发 0 笔交易或差距大时优先看这里"""
    p = PARAMS
    issues = []
    for key in ["target_holdings", "max_single_weight", "max_industry_concentration",
                "max_turnover_per_rebalance", "rebalance_freq_days",
                "entry_weights", "exit_weights", "tie_break_seed"]:
        if key not in p:
            issues.append(f"PARAMS 缺少必填字段: {key}")
    if p.get("tie_break_seed") != 42:
        issues.append("tie_break_seed 应为 42")
    for sig, w in p.get("entry_weights", {}).items():
        if w <= 0:
            issues.append(f"entry_weights[{sig}] = {w}, 应 > 0")
    for sig, w in p.get("exit_weights", {}).items():
        if 0 < w < 1e-6:
            issues.append(
                f"exit_weights[{sig}] = {w:.2e}, weight 极小 — "
                f"确认 should_exit 已实现 'weight < 1e-6 跳过' 逻辑 (否则该信号仍会触发)"
            )
    if issues:
        log.warn("=== PARAMS 自检发现 %d 个问题 ===" % len(issues))
        for i in issues: log.warn("  - " + i)
    else:
        log.info("=== PARAMS 自检通过 ===")
    return len(issues) == 0
```

在 `initialize(context)` 末尾加 `self_check()` 即可。

---

## 8. 版本与维护

- **版本**: 1.0
- **创建日期**: 2026-06-15
- **对应聚宽引擎**: JQBoson (Python 3.6)
- **对齐目标**: `subjects/subject/backtest/runner.py::_run_weight`
- **如 createBase 下的源文档更新**: 本文件只在结构/速查层面同步,详细 API/案例以源文档为准

---
