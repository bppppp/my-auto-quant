# 本地策略 -> QMT 脚本翻译规则

> **目的**: 将本地策略翻译为 QMT 可运行的 Python 策略脚本。
> **QMT 版本**: 1.0.1.1, Python 3.6 内置
> **参考**: http://dict.thinktrader.net

---

## 0. 核心原则

1. **逻辑完全一致**：因子公式、入场条件、出场信号、仓位约束与本地 `strategy.py` 逐行对应
2. **QMT 适配**：调度模型（`init`+`handlebar`）、数据获取（`C.get_market_data_ex`）、下单（`passorder`）
3. **Python 3.6 兼容**：无 f-string 嵌套同引号、无 `pd.NA`、无 `:=`、无 dataclass
4. **一份文件自包含**：所有股票代码、参数、辅助函数内联在单个 `.py` 文件中

---

## 1. 文件骨架（可直接复制）

```python
# -*- coding: utf-8 -*-
"""
QMT 策略: <strategy_name>
对应本地: subjects/<strategy_name>/generated/strategy.py
策略 spec: result/<strategy_name>/<strategy_name>_final.md
"""
import builtins
import numpy as np
import pandas as pd

try:
    from xtquant import xtdata
except ImportError:
    xtdata = None

_sum, _max, _min = builtins.sum, builtins.max, builtins.min

# QMT ContextInfo(C) 只读, 所有自定义状态存模块级 _S
_S = {
    "bar_index": 0, "stock_list": [], "positions": {},
    "rebalance_freq": 5, "target_holdings": 7,
    "period": "1d", "account_id": "testaccID",
}

# passorder 是 QMT 内置, 不在 xtquant 中
try:
    passorder
except NameError:
    def passorder(opType, orderType, accountId, stockCode, priceType,
                  price, volume, strategyContext, **kwargs):
        print("[MOCK] %s %s vol=%s" % ("BUY" if opType==23 else "SELL", stockCode, volume))

# === 测试集 (内联) ===
STOCK_LIST = [...]  # 与本地完全一致的股票代码列表

# === 策略参数 (从 .final.md 复制) ===
PARAMS = { ... }

# === 因子函数 ===
def _ema(series, span):
    return series.ewm(span=span, adjust=False).mean()
# ... 其他因子函数从本地 strategy.py 逐字复制 ...

# === 核心策略方法 (翻译自本地 Strategy 类的 3 个方法) ===
def calc_factors(hist_data, params):  # 对应 compute_factors
def calc_entry_score(factors, params, entry_weights):  # 对应 entry_score
def check_exit(position, factors, params, exit_weights):  # 对应 should_exit

# === 仓位约束 (与本地 portfolio.py 完全一致) ===
def rank_top_n, enforce_max_single_weight, enforce_industry_concentration,
     enforce_max_turnover, fill_cash_with_remaining_candidates

# === 数据获取 (QMT 回测模式) ===
def get_history_data(C, code):  # 优先 xtdata.get_local_data, 回退 C.get_market_data_ex
def get_history_data_batch(C, codes):  # 逐只调 get_history_data

# === A 股规则 ===
def can_buy_at_open, can_sell_at_open  # 涨跌停判断, 用 > 和 <

# === 持仓状态 ===
def update_positions_state  # 先 prev_close, 再 current_price, 再 highest, 最后 holding_days

# === 交易执行 ===
def check_and_execute_exits(C, bar_date)  # 每天检查出场
def execute_rebalance(C, target_weights, scores, bar_date)  # 先卖后买
def do_rebalance(C, bar_date)  # 完整调仓流程

# === QMT 生命周期 ===
def init(C):
    C.start = '2023-01-01 00:00:00'   # 必须最先设置
    C.end = '2026-05-01 00:00:00'
    _S["stock_list"] = STOCK_LIST
    C.set_universe(_S["stock_list"])
    # 其他初始化...

def handlebar(C):
    # 过滤回测日期之前的 bar
    # bar_index 计数 + 调仓判断
```

---

## 2. 翻译步骤（按顺序执行）

### 步骤 1: 复制测试集和参数

- 股票列表直接从本地 `subjects/subject/backtest/universe/hs300.py` 导出, 内联到脚本中
- PARAMS 从 `result/<strategy_name>/<strategy_name>_final.md` 的 frontmatter 复制
- `entry_weights` 和 `exit_weights` 直接从 `.final.md` 的 `entry_signals[].weight` / `exit_signals[].weight` 取值

### 步骤 2: 复制因子辅助函数

- `_ema`, `_ma`, `_atr`, `_rsi`, `_mom`, `_volume_ratio` 从本地 `strategy.py` **逐字复制**
- 不要自己重写, 不要从 `subject.factors` import（QMT 中不可用）

### 步骤 3: 翻译 `compute_factors` -> `calc_factors`

```python
def calc_factors(hist_data, params):
    # 本地列名: 中文 -> QMT 列名: 英文小写
    close = hist_data["close"]    # 本地: df["收盘价"]
    high = hist_data["high"]      # 本地: df["最高价"]
    low = hist_data["low"]        # 本地: df["最低价"]
    volume = hist_data["volume"]  # 本地: df["成交量（股）"]
    # ... 因子计算逻辑与本地完全一致 ...
    return {"close": close, "ma_5": _ma(close, 5), ...}  # 返回 {name: Series}
```

### 步骤 4: 翻译 `entry_score` -> `calc_entry_score`

```python
def calc_entry_score(factors, params, entry_weights):
    # 用 get_factor_val() 提取 iloc[-1] 标量
    # 用 Python 'and' 连接（标量比较）
    score = 0.0
    if (get_factor_val(factors, "ma_5") > get_factor_val(factors, "ma_20")
            and ...):
        score += entry_weights.get("<signal_name>", 0)
    return score
```

### 步骤 5: 翻译 `should_exit` -> `check_exit`

```python
def check_exit(position, factors, params, exit_weights):
    for sig in sorted(exit_weights, key=exit_weights.get, reverse=True):
        if exit_weights.get(sig, 0) <= 0:  # 仅跳过 w<=0, w>0 都触发
            continue
        if sig == "xxx":
            if <trigger条件>:   # 与本地 .final.md 的 trigger 对应
                return sig
    return None
```

### 步骤 6: 复制仓位约束

`rank_top_n`, `enforce_max_single_weight`, `enforce_industry_concentration`, `enforce_max_turnover`, `fill_cash_with_remaining_candidates` 从本地 `portfolio.py` 复制公式, 与本地完全一致。

### 步骤 7: 实现交易执行

```python
# 每天执行
def check_and_execute_exits(C, bar_date):
    for stock, pos in _S["positions"]:
        exit_sig = check_exit(pos, factors, PARAMS, exit_weights)
        if exit_sig:
            passorder(24, 1101, _S["account_id"], stock, 5, -1, -shares, C)

# 调仓日执行 (先卖后买)
def execute_rebalance(C, target_weights, scores, bar_date):
    # 1. 卖出不在目标的
    for code in cur_codes - tgt_codes:
        passorder(24, ...)
    # 2. 买入新目标 (用可用现金, 不是总资产)
    avail = total_value - 持仓市值
    for code in tgt_codes - cur_codes:
        passorder(23, ...)
```

### 步骤 8: 实现 `init` + `handlebar`

```python
def init(C):
    C.start = '2023-01-01 00:00:00'  # 必须最先设置!
    C.end = '2026-05-01 00:00:00'
    _S["stock_list"] = STOCK_LIST
    C.set_universe(_S["stock_list"])
    C.set_account("testaccID")

def handlebar(C):
    # 日期获取: timetag_to_datetime(C.get_bar_timetag(C.barpos), '%Y%m%d%H%M%S')
    # C.barpos 是索引, 不是时间戳!
    bar_date = _bar_date_str(C)

    # 过滤回测日期之前的 bar (QMT 遍历主图全部历史 K 线)
    if bar_date < "20230101":
        return

    _S["bar_index"] += 1
    if _S["bar_index"] == 1:
        return  # 首日跳过

    update_positions_state(...)
    check_and_execute_exits(...)

    if _S["bar_index"] % _S["rebalance_freq"] != 0:
        return

    do_rebalance(...)
```

---

## 3. Python 3.6 兼容规则

| 禁止 | 原因 | 替代 |
|---|---|---|
| `f"...{_S["key"]}..."` | 内层 `"` 提前终止 f-string | `"%s" % _S["key"]` |
| `pd.NA` | pandas 1.0+ 才支持 | `np.nan` |
| `:=` (walrus) | Python 3.8+ | 普通赋值 |
| `@dataclass` | Python 3.7+ | 普通 dict |
| `list[str]` 类型注解 | Python 3.9+ | `from __future__ import annotations` 或去掉 |

---

## 4. QMT 特有注意事项

| # | 规则 | 原因 |
|---|---|---|
| 1 | 状态用 `_S` dict, 不用 `C.xxx = value` | ContextInfo 只读 |
| 2 | `xtdata` 用 `try/except ImportError` 导入 | QMT 路径可能不在 sys.path |
| 3 | `passorder` 用 `try: passorder`, 不从 xtquant import | passorder 是 QMT C 扩展内置 |
| 4 | 保存 `_sum/_max/_min = builtins.sum/max/min` | QMT 可能覆盖内置函数 |
| 5 | `C.start/C.end` 在 `init` 最开头设置 | 否则可能不生效 |
| 6 | `C.barpos` 是索引, 不是时间戳 | 用 `C.get_bar_timetag(C.barpos)` 获取时间 |
| 7 | 回测不用 `C.run_time` | QMT 自动发现 `handlebar` |
| 8 | `C.set_universe()` 注册股票池 | QMT 标准接口 |
| 9 | 不用 `C.accID`, 用 `_S["account_id"]` | C.accID 可能不存在 |
| 10 | `C.get_market_data_ex` 传 `subscribe=False` | 避免订阅行情导致卡死 |
| 11 | 不依赖 `C.is_last_bar()` | 部分版本不工作 |
| 12 | 不用 `download_history_data_batch/batch2` | API 各版本不兼容 |
| 13 | `get_market_data_ex` 返回 `{code: {field: DataFrame}}` | 需要 `_fields_to_df` 转换 |
| 14 | QMT 回测遍历主图全部历史 K 线 | handlebar 开头过滤日期 |
| 15 | 主图数据不要太长（只保留回测期） | 否则回测极慢 |
| 16 | 买入金额用可用现金, 不是总资产 | 卖出后重新计算 avail |
| 17 | 科创板 (688) 200 股整手, 必须限价 | lot_size, LimitOrderStyle |
| 18 | 涨跌停用 `>` 和 `<`, 不用 `>=` `<=` | 对齐本地 `open_px > limit_up - epsilon` |
| 19 | `holding_days = 1` (1-based) | 对齐本地 P3 修复 |
| 20 | `entry_price = (amount + fee) / shares` | 含费 |

---

## 5. 数据获取优先级

```python
def get_history_data(C, code):
    # 1. xtdata.get_local_data (本地缓存, 最快)
    if xtdata is not None:
        data = xtdata.get_local_data(fields, [code], ...)
    
    # 2. xtdata.get_market_data_ex (本地缓存回退)
        data = xtdata.get_market_data_ex(fields, [code], ...)
    
    # 3. C.get_market_data_ex(subscribe=False) (QMT 回测引擎)
    if C is not None:
        data = C.get_market_data_ex(fields, [code], subscribe=False, ...)
```

> **注意**: QMT 回测中最快的数据路径是 `C.get_market_data_ex(subscribe=False)`，但前提是主图数据不要太长。`xtdata.get_local_data` 需要先下载 xtdata 缓存。

---

## 6. 出场信号权重规则

```
weight 仅决定检查顺序, 不决定是否启用
- w > 0: 参与触发 (包括 1e-08)
- w <= 0: 真正禁用
- 按 sorted(weights, key=weights.get, reverse=True) 降序遍历
- 第一个触发就 return
```

---

## 7. 生成后自检清单

- [ ] Python 3.6 兼容（无 f-string 嵌套同引号、无 pd.NA、无 dataclass）
- [ ] 状态用 `_S` dict, 不设 `C.xxx = value`
- [ ] `passorder` 用 `try: passorder` 检测
- [ ] `_sum/_max/_min` 用 builtins 别名
- [ ] `C.start/C.end` 在 `init` 最开头
- [ ] `C.barpos` 不当地时间戳用
- [ ] `subscribe=False` 在 `C.get_market_data_ex` 中
- [ ] 入场用 `get_factor_val()` + Python `and`
- [ ] 出场 `w <= 0` 跳过, 任何 `w > 0` 触发
- [ ] 先卖后买, 买入用可用现金
- [ ] 科创板 200 股整手 + 限价单
- [ ] 涨跌停判断 `>` `<`, 不是 `>=` `<=`
- [ ] `holding_days = 1`, `entry_price` 含费
- [ ] handlebar 开头过滤回测日期前 bar
- [ ] 一份文件自包含（股票列表内联）

---

**版本**: 4.0 | **日期**: 2026-06-17 | **基于**: QMT 1.0.1.1 完整实测 + trend_momentum_strategy_1 翻译验证
