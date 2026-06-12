# Weight 模式计算逻辑 Bug 分析报告

**分析日期**: 2026-06-12
**分析者**: Claude (systematic-debugging)
**触发问题**: 实测 weight 模式报告结果很差 (donchian_breakout_vol_rsi_ma: 年化 -32.86%)

---

## 0. 修复状态 (2026-06-12 更新)

| Bug | 状态 | 修复位置 |
|:---|:---|:---|
| #1 fill_cash 死代码 | ✅ 已修 | `portfolio.py:344-420` 重写 fill_cash 算法 (新候选平分 leftover) |
| #2 buy 循环 cash drift | ❌ 未修 | `runner.py:1395` 静态 `tv * weight` 仍存在 |
| #3 fill_cash 数学错误 | ✅ 已修 (随 #1 一并) | 同上, 新算法天然 sum ≤ 1 |
| #4 enforce_max_single sum<1 意图 | ✅ 设计意图已实现 | fill_cash 现在能补齐, 不再需要重归一化 |
| #5 turnover blend | ❌ 未修 (架构问题) | 见下文, 影响 1+ 季度级 |

**配套修复**:
- Bug A (P0, 隐藏): rebalance-out 缺 exit_linked → 归因账对不上
  - 修复: `runner.py:1371-1379` 调仓 sell 块补 exit_linked 循环
  - 影响: `_compute_signal_attribution` 的 entry signal pnl 完整, LLM factor_weights 调权数据通路正确
- Bug B (P1, 报告): triggered 被翻倍
  - 修复: `signal_stats.py:25-105` 拆 triggered/exits 字段, 加新列
  - 影响: 报告里"触发次数"数字减半 (从 2N 变 N), 反映真实入场次数

详见 `subjects/subject/backtest/tests/test_bug{1,2,3}_*.py`.

---

## 1. 复现证据

### 1.1 实际报告对比 (donchian_breakout_vol_rsi_ma, 2024-01-01 ~ 2024-12-31)

| 模式 | 年化收益 | 胜率 | 盈亏比 | 夏普 | 最大回撤 | 交易数 |
|---|---:|---:|---:|---:|---:|---:|
| **params** (per-stock) | -3.38% | 44.04% | 1.20 | -0.20 | -39.56% | (per-stock 加总) |
| **weight** (组合) | **-32.86%** | 27.00% | 1.25 | -2.04 | -33.09% | 200 |

weight 模式年化收益是 params 模式的 **10 倍糟糕**, 这是核心异常.

### 1.2 实测跟踪脚本

- `subjects/scripts/test_weight_bug.py`: 4 个核心 bug 验证
- `subjects/scripts/debug_portfolio_growth.py`: portfolio 增长跟踪

---

## 2. 核心 Bug 链 (按严重性排序)

### 🔴 Bug #1 (Critical): `fill_cash_with_remaining_candidates` 在 turnover 触发时是死代码

**位置**: `subjects/subject/backtest/portfolio.py:326-402`

**机制**:
1. `enforce_max_single_weight` 在 max_pct=0.10, target_n=8 时, 8 只股票全部触顶
2. 设计意图 (P3 修复): 保留 sum<1, 让 `fill_cash` 补齐到 1.0
3. 但 `enforce_max_turnover` 之后, target 包含 8 新 + N 旧 = 16+ 个 codes
4. `fill_cash` 内的 `max_n = target_n * 2 = 16` 限制触发, `if len(out) >= max_n: break` 立即 return
5. **5% cash 永远无法投资**

**实测复现** (`debug_portfolio_growth.py`):
```
Rebalance #1: target=10 stocks, sum=1.0, cash=10%
Rebalance #2: target=16 stocks, sum=0.8334, cash=5% (fill_cash 死代码)
Rebalance #3: target=18 stocks, sum=0.8644, cash=5%
...
```

**影响**: 长期 5% cash 沉淀, 等于年化收益白白损失 ~5%.

**修复方向**:
- **方案 A**: 提高 `max_n_multiplier` (默认 2 → 4), 但 portfolio 会更大
- **方案 B**: 改 fill_cash 逻辑, 允许将"过小"权重的现有持仓移除, 腾出位置给 cash-filling 新候选
- **方案 C**: 重构 enforce 链, 让 turnover cap 不要把旧持仓加进 target
- **方案 D (推荐)**: 用 `enforce_max_turnover` 的 output 后, **先**执行 sell not-in-target (不光是 new target, 是 blended target 中需要降低的), 再让 fill_cash 处理真正的新候选

### 🟠 Bug #2 (Real): Buy 循环用静态 `tv * weight`, 不考虑累积费用

**位置**: `subjects/subject/backtest/runner.py:1395`

```python
tv = portfolio.total_value(prices)  # PRE-SELL
# ... sells ...
for code, weight in target_weights.items():
    ...
    amount = tv * weight  # 静态, 不考虑前面 buy 累积的 fee
    shares = int(amount / open_px / 100) * 100
    ...
    actual, cost = portfolio.buy(code, open_px, shares, date, ...)
```

**机制**:
- 每次 buy 扣 cash: `cost = shares * open + buy_fee`
- 下一个 buy 仍然用 `amount = tv * weight`, 没扣前面累积的费用
- 最后 1-2 只 buy 会因 cash 不足失败, 留下 cash 沉淀

**实测复现** (`test_weight_bug.py` Test 2):
```
sell 3 只, 5 只新买:
  buy new_0: OK, cost 30,008, cash left 119,820
  buy new_1: OK, cash 89,812
  buy new_2: OK, cash 59,804
  buy new_3: OK, cash 29,796
  buy new_4: FAIL cash 29,796 < cost 30,008
```

**影响**: 单次 rebalance 1-2 只 buy 失败, 留下 cash 沉淀 (~1% per rebalance).

**修复方向**:
- 用 dynamic cash budget: `amount = remaining_cash * (weight / total_remaining_weight)`
- 或: 在买循环前预先扣减 fees 预算

### 🟡 Bug #3 (Latent): `fill_cash_with_remaining_candidates` 数学公式错误

**位置**: `subjects/subject/backtest/portfolio.py:386-388`

```python
n_total = len(out) + 1
# 现有持仓等比缩放, 让出 1/(N+1) 给新候选
for c in out:
    out[c] = out[c] * n_total / (n_total - 1)
out[code] = 1.0 / n_total
```

**机制**:
- 假设 sum(out) = 1.0: scale by (n+1)/n, 新加 1/(n+1)
- sum 变成: 1.0 * (n+1)/n + 1/(n+1) = (n+1)/n + 1/(n+1) ≠ 1
- 当 sum(out) ≠ 1.0 (turnover 触发后), 数学错误更严重

**实测复现** (直接调用, sum=0.5 输入):
```
输入: 8 stocks at 0.0625, sum=0.5
输出: 12 stocks, sum=1.1325
多出 13.25% "凭空创造" 的权重
```

**影响**: 由于 Bug #1 让 fill_cash 退化为死代码, 这个 bug 不会在实际运行中触发. 但如果有人修复 Bug #1 增大 max_n, 这个 bug 会立即显现.

**修复方向**:
- 正确公式: `scale = (n_total - 1) / n_total / current_sum`
- 或: 加新候选后立即 normalize to sum=1.0

### 🟡 Bug #4 (Design): `enforce_max_single_weight` 的 sum<1 设计意图未实现

**位置**: `subjects/subject/backtest/portfolio.py:226-228, 231-233`

```python
else:
    # 全部触顶 → 全部 cap 到 max_pct, 保留 sum < 1
    for k in out:
        out[k] = max_pct
# 归一化: 仅当 sum > 1 时 re-normalize (overweight)
# sum < 1 时保留, 由 fill_cash 补齐
s = sum(out.values())
if s > 1.0 + 1e-6:
    out = {k: v / s for k, v in out.items()}
```

**机制**:
- 8 只 0.125 → cap 到 0.10 → sum=0.80 → 保留 (因为 fill_cash 应该补)
- 但 fill_cash 是死代码, 所以 0.80 永远不会被补到 1.0
- 注释里写"由 fill_cash 补齐"是错的

**影响**: 20% cash 沉淀 (在 max_single 触发但 turnover 不触发的场景).

**修复方向**:
- 重新启用归一化, 或者
- 修复 fill_cash 让它能真正补齐

### 🟢 Bug #5 (Conceptual): `enforce_max_turnover` 输出包含旧持仓, buy/sell 逻辑无法真正降低

**位置**: `subjects/subject/backtest/runner.py:1329-1342, 1360-1379`

**机制**:
1. `enforce_max_turnover` 把旧持仓 "blend" 进 target (旧 → 0.04, 新 → 0.056)
2. buy/sell 逻辑是二元的: `if code not in target: sell`
3. 旧持仓还在 target (只是 weight 小), 所以不被 sell
4. 但 portfolio 实际持仓的 weight 可能比 target 大很多, 永远不会被 reduce

**影响**:
- 旧持仓不会被主动减仓
- 新持仓会不断加入
- Portfolio 慢慢增长 (虽然被 max_n 限制)
- Turnover cap 的"限速换手"意图未真正实现

**修复方向**:
- 把 buy/sell 逻辑从二元改为按比例调整
- 或: enforce_max_turnover 不把旧持仓加进 target, 而是只输出"实际应增加/减少"的量

---

## 3. Bug 间的相互影响

```
[1] enforce_max_single → sum < 1 (设计意图: fill_cash 补)
       ↓
[2] fill_cash 因为 max_n 死代码, 无法补 → cash 沉淀 5-20%
       ↓
[3] buy 循环用静态 tv*weight, 最后几只 buy 失败 → 额外 1% cash 沉淀
       ↓
[4] portfolio 实际投入资金 < 100%, 拖累年化收益
       ↓
[5] 实际年化收益 < 策略信号应有的年化收益
```

特别地:
- 如果策略本身有正期望 (e.g., ma_cross_atr_volume 年化 240%), cash 沉淀只损失 5%, 实际表现仍可接受
- 如果策略本身是负期望 (e.g., donchian -33% / 年), cash 沉淀会进一步放大损失

---

## 4. 验证清单

| Bug | 测试文件 | 已验证 | 影响 |
|---|---|:---:|---|
| #1 fill_cash 死代码 | debug_portfolio_growth.py: Rebalance #2-5 | ✓ | 5% cash 永久沉淀 |
| #2 buy 循环 cash drift | test_weight_bug.py: Test 2 | ✓ | 1% cash 沉淀/rebalance |
| #3 fill_cash 数学错误 | test_weight_bug.py: Test 3 | ✓ | 潜在, 被 #1 掩盖 |
| #4 enforce_max_single sum<1 | test_weight_bug.py: Test 3 (间接) | ✓ | 20% cash 沉淀 (无 turnover) |
| #5 turnover blend 不被 reduce | debug_portfolio_growth.py | ✓ | 旧持仓无法 reduce |

---

## 5. 修复优先级建议

| 优先级 | Bug | 工作量 | 风险 | 收益 |
|---|:---|:---:|:---:|:---:|
| **P0** | #1 (fill_cash 死代码) | 1-2h | 低 | +5% 年化 |
| P1 | #2 (buy 循环 cash drift) | 1-2h | 中 | +1-2% 年化 |
| P2 | #5 (turnover blend) | 4-6h | 高 | 真正的"组合管理" |
| P3 | #4 (enforce_max_single) | 0.5h | 低 | 修正文档 |
| P3 | #3 (fill_cash 数学) | 0.5h | 低 | 防 latent 风险 |

---

## 6. 附录: 实测 cash 沉淀时序

来自 `debug_portfolio_growth.py` (理想场景, 8 只价格相同的稳定 rebalance):

```
Rebalance #1: target=10 stocks, sum=1.0000 (fill_cash 补齐成功), cash=10%
Rebalance #2: target=16 stocks, sum=0.8334 (fill_cash 死), cash=5%
Rebalance #3: target=18 stocks, sum=0.8644 (fill_cash 死), cash=5%
Rebalance #4: target=18 stocks, sum=0.8644 (fill_cash 死), cash=5%
Rebalance #5: target=18 stocks, sum=0.8644 (fill_cash 死), cash=5%
```

5% 现金沉淀, 等价于:
- 年化收益损失 ~5% (假设 cash 不产生收益)
- 实际表现比"100% 投资策略"差 5%

---

## 7. 用户决策点

需要用户决定:

1. **是否开始 Phase 4 修复?** (建议: 至少修 P0 + P1, ~3-4h)
2. **修复顺序**: 先修 #1 + #3 + #4 (一组, 都是 weight 计算), 再修 #2 (买循环), 最后 #5 (架构)
3. **修复后验证**: 重跑 donchian_breakout_vol_rsi_ma weight 模式, 对比修复前年化 -32.86%
4. **是否更新设计文档**: `subject_structure.md` 里关于 weight 模式的设计意图需要修正
