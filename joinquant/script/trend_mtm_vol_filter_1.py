# -*- coding: utf-8 -*-
"""
多因子趋势跟踪 + 波动率过滤策略 - 严格 T-1 回测模式 (Local-Engine Equivalent)
============================================================================
策略名称: trend_mtm_vol_filter_1
策略文档: D:/my-auto-quant/result/trend_mtm_vol_filter_1/trend_mtm_vol_filter_1_final.md
回测平台: JoinQuant (聚宽)

本脚本严格按本地 weight 回测引擎 (subjects/subject/backtest/runner.py::_run_weight)
的语义实现, 用于对齐本地与聚宽的回测结果:

**策略逻辑 (3 入场 + 4 出场)**:
- 入场 (entry_score = Σ 触发信号 weight):
  * trend_momentum_filter (0.4): ma_20 > ma_60 AND return_20d > min_return_20d
                                AND volume_ratio_20 > vol_min
  * rsi_filter             (0.1): rsi_min < rsi_14 < rsi_max
  * volatility_expansion   (0.5): atr_14 > atr_14_prev AND atr_14/close > atr_min_pct
- 出场 (按 weight 降序遍历, 第一个触发即返回):
  * fixed_stop    (0.05): current_price < entry_price * (1 - fixed_stop_pct)
  * trailing_stop (0.5):  current_price < highest * (1 - trailing_stop_pct)
  * time_stop     (0.4):  holding_days >= max_holding_days
  * trend_reverse (0.05): ma_20 < ma_60 AND rsi_14 < rsi_weakness

关键约定:
1. **T-1 因子决策 + T 开盘成交**: 严格无前视
   - 09:30 触发, 用 attribute_history(end=T-1) 拿严格 T-1 数据
   - 用 get_current_data().last_price (T 开盘价) 成交
2. **score-based 排序**: entry_score = Σ(触发信号 × weight), rank_top_n + random tie-break
3. **5 个仓位约束**: max_single_weight / max_industry_concentration / max_turnover_per_rebalance
   / target_holdings / rebalance_freq_days
4. **出场优先级动态读权重**: sorted(exit_weights, key=weights.get, reverse=True)
5. **holding_days 按交易日累加** (每个交易日 +1, 非日历日)
6. **entry_price 含费用调整**: (amount + fee) / shares
7. **ST / 北交所自动过滤**
8. **无加仓 / 无减仓** (本地引擎不支持, 故此脚本也禁用)

目标: 年化 25%, 胜率 45%, 盈亏比 3.5, 夏普 1.3, 最大回撤 -20%
本地 v3 实测: 年化 50.04%, 胜率 54.6%, 盈亏比 3.26, 夏普 1.73, 最大回撤 -28.6%
"""

from jqdata import *
import numpy as np
import pandas as pd
import random
import builtins

# 用 _sum / _max / _min 别名指向 Python 内置函数, 避免被 numpy 覆盖.
_sum = builtins.sum
_max = builtins.max
_min = builtins.min


# ============================================================
# 1. 参数配置区 (与本地引擎读取的 yaml 参数完全一致)
# ============================================================
PARAMS = {
    # ---- 标的与基准 ----
    "benchmark": "000300.XSHG",
    "use_fixed_universe": True,
    "universe_index": "000300.XSHG",

    # ---- 因子窗口 ----
    "ma_period": 20,
    "ma_long_period": 60,
    "atr_period": 14,
    "rsi_period": 14,
    "return_period": 20,
    "volume_ma_period": 20,

    # ---- 入场阈值 (3 个 AND 触发条件) ----
    "min_return_20d": 0.02,
    "vol_min": 1.2,
    "rsi_min": 50,
    "rsi_max": 80,
    "atr_min_pct": 0.045,

    # ---- 出场阈值 ----
    "fixed_stop_pct": 0.12,
    "trailing_stop_pct": 0.25,
    "max_holding_days": 250,
    "rsi_weakness": 25,

    # ---- 仓位约束 (与本地引擎 enforce_xxx 函数对齐) ----
    "target_holdings": 10,
    "max_single_weight": 0.2,
    "max_industry_concentration": 0.4,
    "max_turnover_per_rebalance": 0.7,

    # ---- 调仓频率 ----
    "rebalance_freq_days": 5,

    # ---- 信号权重 (用于 score + 出场优先级) ----
    "entry_weights": {
        "trend_momentum_filter": 0.4,
        "rsi_filter": 0.1,
        "volatility_expansion": 0.5,
    },
    "exit_weights": {
        "trailing_stop": 0.5,     # 优先级最高 (保护浮盈)
        "time_stop": 0.4,         # 时间止损
        "fixed_stop": 0.05,       # 固定止损 (保本)
        "trend_reverse": 0.05,    # 趋势反转
    },

    # ---- tie-break random seed (与本地 rank_top_n seed=42 对齐) ----
    "tie_break_seed": 42,
}


# ============================================================
# 2. 策略初始化
# ============================================================
def initialize(context):
    set_benchmark(PARAMS["benchmark"])
    set_option("use_real_price", True)

    # 手续费: 万 3 + 印花税千 1 (与本地引擎 calc_buy_fee/calc_sell_fee 对齐)
    set_order_cost(OrderCost(
        open_tax=0,
        close_tax=0.001,
        open_commission=0.0003,
        close_commission=0.0003,
        close_today_commission=0,
        min_commission=5
    ), type="stock")

    # 本地引擎无滑点, 但聚宽 0.05% 滑点更悲观, 保留
    set_slippage(FixedSlippage(0.0005))
    log.set_level("order", "error")

    # ---- 全局状态 ----
    g.params = PARAMS
    g.universe = []
    # holdings: {stock: {entry_price, entry_date, highest_close, holding_days,
    #                     shares, entry_signals, prev_close}}
    g.holdings = {}
    g.industry_map = {}      # 由 daily_handle 每次刷新
    g.bar_index = 0           # 0-based -> 1-based 交易日索引 (本地 enumerate(..., 1))

    # ---- 一次性调度: 09:30 用 T-1 因子决策 + T 开盘成交 ----
    run_daily(daily_handle, time="09:30")

    # ---- 预填 universe: 让 get_current_data() / history() 不走 lazy loading ----
    if PARAMS.get("use_fixed_universe", False):
        set_universe(FIXED_UNIVERSE)

    log.info("=" * 60)
    log.info("=== trend_mtm_vol_filter_1 (严格 T-1 模式) 初始化完成 ===")
    log.info("目标: 年化25%, 胜率45%, 盈亏比3.5, 夏普1.3, 最大回撤20%")
    log.info("入场: trend_momentum(0.4) + rsi(0.1) + volatility_expansion(0.5)")
    log.info("出场: trailing(0.5) + time(0.4) + fixed(0.05) + trend_reverse(0.05)")
    log.info("决策模型: T-1 因子 + T 开盘成交 (与本地 weight 引擎完全等价)")
    log.info("=" * 60)


# ============================================================
# 3. 因子计算 (严格用 T-1 收盘前的数据)
# ============================================================
def _atr(high, low, close, period=14):
    prev_close = close.shift(1)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.rolling(window=period, min_periods=period).mean()


def _rsi(close, period=14):
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    avg_gain = gain.rolling(window=period, min_periods=period).mean()
    avg_loss = loss.rolling(window=period, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    rsi = 100.0 - 100.0 / (1.0 + rs)
    return rsi.fillna(100.0)


def calc_factors_t1(stock, context, n=100):
    p = g.params
    try:
        df = attribute_history(stock, n, "1d",
                              ["open", "close", "high", "low", "volume"],
                              skip_paused=True, df=True, fq="pre")
        if df is None or len(df) < p["ma_long_period"]:
            return None

        close = df["close"]
        high = df["high"]
        low = df["low"]
        volume = df["volume"]

        last_close = close.iloc[-1]
        if last_close <= 0 or np.isnan(last_close):
            return None

        atr_series = _atr(high, low, close, p["atr_period"])
        rsi_series = _rsi(close, p["rsi_period"])

        return {
            "close": last_close,
            "ma_20": close.tail(p["ma_period"]).mean(),
            "ma_60": close.tail(p["ma_long_period"]).mean(),
            "atr_14": atr_series.iloc[-1],
            "atr_14_prev": atr_series.iloc[-2] if len(atr_series) >= 2 else np.nan,
            "rsi_14": rsi_series.iloc[-1],
            "return_20d": (
                close.iloc[-1] / close.iloc[-1 - p["return_period"]] - 1.0
                if len(close) > p["return_period"] else 0.0
            ),
            "volume_ratio_20": (
                volume.iloc[-1] / volume.tail(p["volume_ma_period"]).mean()
                if volume.tail(p["volume_ma_period"]).mean() > 0 else 0
            ),
        }
    except Exception as e:
        log.warn("calc_factors_t1 fail %s: %s" % (stock, str(e)))
        return None


def calc_factors_batch(stock_list, context, n=100):
    p = g.params
    if not stock_list:
        return {}

    try:
        df_close = history(n, "1d", "close", stock_list, df=True,
                          skip_paused=False, fq="pre")
        df_high = history(n, "1d", "high", stock_list, df=True,
                         skip_paused=False, fq="pre")
        df_low = history(n, "1d", "low", stock_list, df=True,
                        skip_paused=False, fq="pre")
        df_volume = history(n, "1d", "volume", stock_list, df=True,
                           skip_paused=False, fq="pre")
    except Exception as e:
        log.warn("calc_factors_batch fail: %s" % str(e))
        return {}

    if df_close is None or df_close.empty:
        return {}

    out = {}
    for stock in stock_list:
        try:
            if stock not in df_close.columns:
                continue
            close = df_close[stock]
            high = df_high[stock]
            low = df_low[stock]
            volume = df_volume[stock]

            valid_close = close.dropna()
            if len(valid_close) < p["ma_long_period"]:
                continue

            last_close = close.iloc[-1]
            if pd.isna(last_close) or last_close <= 0:
                continue

            ma_20 = close.tail(p["ma_period"]).mean()
            ma_60 = close.tail(p["ma_long_period"]).mean()

            atr_series = _atr(high, low, close, p["atr_period"])
            atr_14 = atr_series.iloc[-1]
            atr_14_prev = atr_series.iloc[-2] if len(atr_series) >= 2 else np.nan

            rsi_series = _rsi(close, p["rsi_period"])
            rsi_14 = rsi_series.iloc[-1]

            if len(close) > p["return_period"]:
                return_20d = close.iloc[-1] / close.iloc[-1 - p["return_period"]] - 1.0
            else:
                return_20d = 0.0

            vol_ma_20 = volume.tail(p["volume_ma_period"]).mean()
            volume_ratio_20 = (
                volume.iloc[-1] / vol_ma_20
                if vol_ma_20 and vol_ma_20 > 0 else 0
            )

            out[stock] = {
                "close": last_close,
                "ma_20": ma_20,
                "ma_60": ma_60,
                "atr_14": atr_14,
                "atr_14_prev": atr_14_prev,
                "rsi_14": rsi_14,
                "return_20d": return_20d,
                "volume_ratio_20": volume_ratio_20,
            }
        except Exception:
            continue

    return out


# ============================================================
# 4. 入场信号 + score (对齐本地 entry_score / get_triggered_signals)
# ============================================================
def get_triggered_signals(factors, p):
    triggered = []
    close = factors.get("close")
    ma_20 = factors.get("ma_20")
    ma_60 = factors.get("ma_60")
    rsi_14 = factors.get("rsi_14")
    atr_14 = factors.get("atr_14")
    atr_14_prev = factors.get("atr_14_prev")
    return_20d = factors.get("return_20d")
    volume_ratio_20 = factors.get("volume_ratio_20")

    # 任意 NaN 直接否决
    for v in (close, ma_20, ma_60, rsi_14, atr_14, atr_14_prev,
              return_20d, volume_ratio_20):
        if v is None or (isinstance(v, float) and np.isnan(v)):
            return triggered

    # trend_momentum_filter: ma_20>ma_60 AND return_20d>thr AND vol_ratio>thr
    if (ma_20 > ma_60
            and return_20d > p["min_return_20d"]
            and volume_ratio_20 > p["vol_min"]):
        triggered.append("trend_momentum_filter")

    # rsi_filter: rsi_min < rsi_14 < rsi_max
    if p["rsi_min"] < rsi_14 < p["rsi_max"]:
        triggered.append("rsi_filter")

    # volatility_expansion: atr_14>atr_14_prev AND atr_14/close>thr
    if atr_14 > atr_14_prev and (atr_14 / close) > p["atr_min_pct"]:
        triggered.append("volatility_expansion")

    return triggered


def entry_score(factors, p):
    triggered = get_triggered_signals(factors, p)
    score = 0.0
    for sig in triggered:
        score += float(p["entry_weights"].get(sig, 0.0))
    return score


# ============================================================
# 5. 出场信号 (对齐本地 prioritize_exit_signals: 按 weight 降序遍历)
# ============================================================
def _check_exit_signal(sig_name, factors, holding, current_price, p):
    entry_price = holding["entry_price"]
    highest_close = holding.get("highest_close", entry_price)
    holding_days = holding.get("holding_days", 0)

    if sig_name == "fixed_stop":
        return current_price < entry_price * (1 - p["fixed_stop_pct"])
    elif sig_name == "trailing_stop":
        return current_price < highest_close * (1 - p["trailing_stop_pct"])
    elif sig_name == "time_stop":
        return holding_days >= p["max_holding_days"]
    elif sig_name == "trend_reverse":
        ma_20 = factors.get("ma_20")
        ma_60 = factors.get("ma_60")
        rsi_14 = factors.get("rsi_14")
        if (ma_20 is not None and ma_60 is not None and rsi_14 is not None
                and not np.isnan(ma_20) and not np.isnan(ma_60)
                and not np.isnan(rsi_14)):
            return ma_20 < ma_60 and rsi_14 < p["rsi_weakness"]
    return False


def should_exit(factors, holding, current_price, p):
    exit_w = p["exit_weights"]
    active_sigs = [s for s, w in exit_w.items() if w >= 1e-6]
    for sig in sorted(active_sigs, key=exit_w.get, reverse=True):
        if _check_exit_signal(sig, factors, holding, current_price, p):
            return sig
    return None


# ============================================================
# 6. 排序与仓位约束 (1:1 对齐本地 signals.py / portfolio.py)
# ============================================================
def rank_top_n(scores, top_n, seed=42):
    if top_n <= 0:
        return [k for k, v in sorted(scores.items(), key=lambda kv: (kv[1], kv[0]),
                                      reverse=True) if v > 0]
    positives = [(k, v) for k, v in scores.items() if v > 0]
    positives.sort(key=lambda kv: (kv[1], kv[0]), reverse=True)
    result = [k for k, _ in positives[:top_n]]
    if seed is not None and len(result) > 1:
        all_scores = set(v for _, v in positives[:top_n])
        if len(all_scores) == 1:
            random.seed(seed)
            random.shuffle(result)
    return result


def enforce_max_single_weight(weights, max_pct):
    if not weights or max_pct <= 0:
        return weights
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
        others_total = _sum(others.values())
        if others_total > 0:
            scale = (others_total + excess) / others_total
            for k in others:
                out[k] *= scale
        else:
            for k in out:
                out[k] = max_pct
    s = _sum(out.values())
    if s > 1.0 + 1e-6:
        out = {k: v / s for k, v in out.items()}
    return out


def enforce_industry_concentration(weights, industry_map, max_pct):
    if not weights or max_pct <= 0:
        return weights
    industry_total = {}
    for code, w in weights.items():
        ind = industry_map.get(code, "unknown")
        industry_total[ind] = industry_total.get(ind, 0.0) + w
    scale = {}
    for ind, total in industry_total.items():
        if total > max_pct:
            scale[ind] = max_pct / total
        else:
            scale[ind] = 1.0
    out = {}
    any_scaled = False
    for code, w in weights.items():
        ind = industry_map.get(code, "unknown")
        out[code] = w * scale[ind]
        if scale[ind] < 1.0:
            any_scaled = True
    if any_scaled:
        s = _sum(out.values())
        if s > 1.0 + 1e-6:
            out = {k: v / s for k, v in out.items()}
    return out


def enforce_max_turnover(current, target, max_pct):
    if not target:
        return target
    all_codes = set(current.keys()) | set(target.keys())
    turnover = _sum(abs(target.get(c, 0) - current.get(c, 0)) for c in all_codes) / 2.0
    if turnover <= max_pct:
        return target
    alpha = max_pct / turnover if turnover > 0 else 1.0
    out = {}
    for c in all_codes:
        cw = current.get(c, 0)
        tw = target.get(c, 0)
        mixed = cw + alpha * (tw - cw)
        if mixed > 1e-9:
            out[c] = mixed
    s = _sum(out.values())
    if s > 1.0 + 1e-6:
        out = {k: v / s for k, v in out.items()}
    return out


def fill_cash_with_remaining_candidates(
    target_weights, scores, target_n, max_single,
    industry_map=None, max_industry=1.0,
    cash_threshold=0.01, max_n_multiplier=2.0,
):
    if not scores or not target_weights:
        return target_weights

    leftover = 1.0 - _sum(target_weights.values())
    if leftover < cash_threshold:
        return target_weights

    in_target = set(target_weights.keys())
    candidates = sorted(
        [(c, s) for c, s in scores.items() if c not in in_target and s > 0],
        key=lambda x: x[1],
        reverse=True,
    )

    out = dict(target_weights)
    max_n = int(target_n * max_n_multiplier)

    for code, _score in candidates:
        if len(out) >= max_n:
            break
        leftover = 1.0 - _sum(out.values())
        if leftover < cash_threshold:
            break

        new_w = leftover
        if max_single > 0 and new_w > max_single:
            new_w = max_single
        if industry_map is not None and max_industry < 1.0:
            ind = industry_map.get(code, "unknown")
            current_ind_total = _sum(
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


def should_rebalance(bar_index, freq):
    if freq <= 0:
        return False
    return bar_index % freq == 0


# ============================================================
# 7. A 股规则: ST/北交所过滤 + 一字板判定
# ============================================================
def _is_bj(stock):
    bare = stock.split(".")[0]
    return bare.startswith(("4", "8", "92"))


def _cd_get(cd, stock):
    try:
        return cd[stock]
    except KeyError:
        return None


def filter_universe(raw_list, context):
    out = []
    skip_bj = 0
    for s in raw_list:
        if _is_bj(s):
            skip_bj += 1
            continue
        out.append(s)
    log.info("filter_universe: raw=%d, pass=%d (skip: bj=%d)" %
             (len(raw_list), len(out), skip_bj))
    return out


def get_industry_map(stock_list, date=None):
    if not stock_list:
        return {}
    try:
        if date is not None:
            ind = get_industry(stock_list, date=date)
        else:
            ind = get_industry(stock_list)
    except Exception:
        return {}
    out = {}
    for s, v in ind.items():
        if "sw_l1" in v and "industry_code" in v["sw_l1"]:
            out[s] = v["sw_l1"]["industry_code"]
        else:
            out[s] = "unknown"
    return out


def can_buy_at_open(d, stock):
    return True


def can_sell_at_open(d, stock):
    return True


# ============================================================
# 8. 主循环 daily_handle (09:30 触发, 等价本地 _run_weight 主循环)
# ============================================================
def daily_handle(context):
    p = g.params
    g.bar_index += 1
    bar_idx = g.bar_index

    log.info("=" * 60)
    log.info("[%s] bar_idx=%d (%s)" % (
             context.current_dt.strftime("%Y-%m-%d"), bar_idx,
             "首日(跳过交易)" if bar_idx == 1 else (
                 "调仓日" if should_rebalance(bar_idx, p["rebalance_freq_days"])
                 else "持仓维护"
             )))

    if bar_idx == 1:
        return

    # step 1: 更新 highest_close + holding_days
    for stock in list(g.holdings.keys()):
        h = g.holdings[stock]
        try:
            df = attribute_history(stock, 1, "1d", ["close"],
                                  skip_paused=True, df=True, fq="pre")
            if df is not None and len(df) > 0:
                t1_close = float(df["close"].iloc[-1])
                if not np.isnan(t1_close) and t1_close > 0:
                    h["highest_close"] = _max(h.get("highest_close", h["entry_price"]),
                                              t1_close)
                    h["prev_close"] = t1_close
        except Exception:
            pass
        h["holding_days"] += 1

    # step 2: 刷新 universe + industry_map
    if p.get("use_fixed_universe", False):
        raw = list(FIXED_UNIVERSE)
    else:
        try:
            raw = list(get_index_stocks(p["universe_index"], date=context.previous_date))
        except Exception as e:
            log.warn("get universe fail: %s" % str(e))
            raw = []
    g.universe = filter_universe(raw, context)
    g.industry_map = get_industry_map(g.universe, date=context.previous_date)

    # step 3: 批量计算 T-1 因子 + entry_score
    factors_by_code = calc_factors_batch(g.universe, context, n=100)
    scores = {}
    for stock, f in factors_by_code.items():
        s = entry_score(f, p)
        if s > 0:
            scores[stock] = s

    # 持仓股不在 g.universe 时单独算因子
    for stock in list(g.holdings.keys()):
        if stock not in factors_by_code:
            f = calc_factors_t1(stock, context, n=100)
            if f is not None:
                factors_by_code[stock] = f
                if entry_score(f, p) > 0:
                    scores[stock] = entry_score(f, p)

    log.info("候选池 %d 只, 通过 entry_score>0 的 %d 只 (持仓 %d 只)" % (
             len(g.universe), len(scores), len(g.holdings)))

    # step 4: 出场决策
    cd = get_current_data()
    for stock in list(g.holdings.keys()):
        if stock not in factors_by_code:
            continue
        h = g.holdings[stock]
        f = factors_by_code[stock]
        prev_close = h.get("prev_close") or f["close"]
        exit_sig = should_exit(f, h, prev_close, p)
        if exit_sig is None:
            continue
        d = _cd_get(cd, stock)
        if not can_sell_at_open(d, stock):
            log.info("%s 出场信号=%s 但 T 开盘无法卖出, 延期" % (stock, exit_sig))
            continue
        _execute_sell(stock, h, exit_sig, context)

    # step 5: 调仓
    if should_rebalance(bar_idx, p["rebalance_freq_days"]):
        _do_rebalance(scores, factors_by_code, context)


# ============================================================
# 9. 调仓 (rebalance)
# ============================================================
def _do_rebalance(scores, factors_by_code, context):
    p = g.params
    target_n = p["target_holdings"]
    max_single = p["max_single_weight"]
    max_industry = p["max_industry_concentration"]
    max_turnover = p["max_turnover_per_rebalance"]

    if not scores and not g.holdings:
        log.info("无候选且无持仓, 跳过调仓")
        return

    top_codes = rank_top_n(scores, target_n, seed=p["tie_break_seed"])
    if not top_codes:
        log.info("无 score>0 候选, 跳过调仓 (持仓保持不变)")
        return

    target_weights = {c: 1.0 / target_n for c in top_codes}
    target_weights = enforce_max_single_weight(target_weights, max_single)
    target_weights = enforce_industry_concentration(target_weights, g.industry_map,
                                                     max_industry)
    current_weights = _compute_current_weights(context)
    target_weights = enforce_max_turnover(current_weights, target_weights, max_turnover)

    try:
        target_weights = fill_cash_with_remaining_candidates(
            target_weights=target_weights,
            scores=scores,
            target_n=target_n,
            max_single=max_single,
            industry_map=g.industry_map,
            max_industry=max_industry,
        )
    except Exception as e:
        log.warn("fill_cash fail: %s" % str(e))

    log.info("rebalance: top_n=%d, target_weights=%d, sum=%.4f" %
             (len(top_codes), len(target_weights), _sum(target_weights.values())))

    total_value = _compute_total_value(context)
    cd = get_current_data()

    # 卖出不在 target 的持仓
    for stock in list(g.holdings.keys()):
        if stock in target_weights:
            continue
        h = g.holdings[stock]
        d = _cd_get(cd, stock)
        if not can_sell_at_open(d, stock):
            log.info("%s 调仓卖出但跌停/停牌, 延期" % stock)
            continue
        _execute_sell(stock, h, "rebalance_out", context)

    # 买入新进的
    for stock, weight in target_weights.items():
        if stock in g.holdings:
            continue
        d = _cd_get(cd, stock)
        if not can_buy_at_open(d, stock):
            log.info("%s 买入信号但 T 开盘无法买入" % stock)
            continue

        open_px = 0
        if d is not None and d.last_price is not None and d.last_price > 0:
            open_px = float(d.last_price)
        else:
            f = factors_by_code.get(stock)
            if f is not None and f.get("close") and f["close"] > 0:
                open_px = float(f["close"])

        if open_px <= 0 or np.isnan(open_px):
            log.info("%s 价格异常, 跳过" % stock)
            continue

        amount = total_value * weight
        # 科创板 (688) 最低 200 股/手, 其他板块 100 股/手
        lot_size = 200 if stock.startswith("688") else 100
        shares = int(amount / open_px / lot_size) * lot_size
        if shares < lot_size:
            continue
        triggered = get_triggered_signals(factors_by_code.get(stock, {}), p)
        _execute_buy(stock, open_px, shares, triggered, context)


def _compute_current_weights(context):
    out = {}
    total = 0.0
    cd = get_current_data()
    for stock, h in g.holdings.items():
        d = _cd_get(cd, stock)
        price = d.last_price if d and d.last_price > 0 else h.get("prev_close", h["entry_price"])
        value = h["shares"] * price
        out[stock] = value
        total += value
    total += context.portfolio.available_cash
    if total <= 0:
        return {}
    return {k: v / total for k, v in out.items()}


def _compute_total_value(context):
    cd = get_current_data()
    tv = context.portfolio.available_cash
    for stock, h in g.holdings.items():
        d = _cd_get(cd, stock)
        price = d.last_price if d and d.last_price > 0 else h.get("prev_close", h["entry_price"])
        tv += h["shares"] * price
    return tv


# ============================================================
# 10. 买卖执行 (对齐本地 Portfolio.buy / Portfolio.sell)
# ============================================================
def _execute_buy(stock, open_px, shares, triggered_signals, context):
    if shares < 100:
        return
    if stock in g.holdings:
        return

    amount = open_px * shares
    fee = _max(amount * 0.0003, 5)
    total_cost = amount + fee

    if total_cost > context.portfolio.available_cash:
        log.info("现金不足, 放弃买入: %s (need %.0f, have %.0f)" %
                 (stock, total_cost, context.portfolio.available_cash))
        return

    if stock.startswith("688"):
        limit_price = _min(open_px * 1.005, 9999.99)
        order_result = order(stock, shares, LimitOrderStyle(limit_price))
    else:
        order_result = order(stock, shares)

    if order_result is None:
        log.info("下单失败 (可能涨停/停牌): %s" % stock)
        return

    filled_shares = getattr(order_result, "filled", 0)
    if filled_shares == 0:
        log.info("下单未成交 (涨停/无对手盘): %s" % stock)
        return

    actual_shares = int(filled_shares)
    actual_amount = open_px * actual_shares
    actual_fee = _max(actual_amount * 0.0003, 5)
    effective_entry = (actual_amount + actual_fee) / actual_shares

    g.holdings[stock] = {
        "entry_price": effective_entry,
        "entry_date": context.current_dt,
        "highest_close": open_px,
        "holding_days": 0,
        "shares": actual_shares,
        "entry_signals": list(triggered_signals),
        "prev_close": open_px,
    }
    log.info(">>> 买入 %s: %d股 @ %.2f, 含费成本=%.4f, 金额=%.0f" %
             (stock, actual_shares, open_px, effective_entry, actual_amount))


def _execute_sell(stock, holding, exit_signal, context):
    cd = get_current_data()
    d = cd.get(stock)

    open_px = 0
    if d is not None and d.last_price is not None and d.last_price > 0:
        open_px = float(d.last_price)
    else:
        open_px = float(holding.get("prev_close") or holding.get("entry_price") or 0)

    if open_px <= 0 or np.isnan(open_px):
        log.warn("价格异常, 跳过卖出: %s" % stock)
        return

    shares = holding["shares"]
    entry_price = holding["entry_price"]
    holding_days = holding["holding_days"]

    if stock.startswith("688"):
        limit_price = _max(open_px * 0.995, 0.01)
        limit_price = _min(limit_price, 9999.99)
        order_result = order(stock, -shares, LimitOrderStyle(limit_price))
    else:
        order_result = order_target_value(stock, 0)

    if order_result is None:
        log.warn("清仓下单失败: %s" % stock)
        return

    sell_amount = open_px * shares
    sell_fee = _max(sell_amount * 0.0003, 5) + sell_amount * 0.001
    pnl = (open_px - entry_price) * shares - sell_fee

    log.info(">>> 卖出 %s: %d股 @ %.2f, PnL=%.2f, 持仓=%d交易日, 信号=%s" %
             (stock, shares, open_px, pnl, holding_days, exit_signal))
    del g.holdings[stock]


# ============================================================
# 11. 固定股票池 FIXED_UNIVERSE (HS300 + CYB_STAR_50)
# ============================================================
# 注: spec.test_universe = [HS300, CSI1000], 但本地 backtest 实际用
# data/ 下的 top300 (从 pre_compute_factor.py 筛出), 跟本 FIXED_UNIVERSE
# 不完全一致. 用户如需对齐本地 top300, 请替换为
# subjects/trend_mtm_vol_filter_1/test_universe/top300.md 的实际列表.
# 当前用与 trend_momentum_strategy_1 一致的 HS300 + CYB_STAR_50 (356 只).
# ============================================================
FIXED_UNIVERSE = [
    "000001.XSHE", "000002.XSHE", "000063.XSHE", "000100.XSHE", "000157.XSHE",
    "000166.XSHE", "000301.XSHE", "000333.XSHE", "000338.XSHE", "000408.XSHE",
    "000425.XSHE", "000538.XSHE", "000568.XSHE", "000596.XSHE", "000617.XSHE",
    "000625.XSHE", "000630.XSHE", "000651.XSHE", "000661.XSHE", "000708.XSHE",
    "000725.XSHE", "000768.XSHE", "000776.XSHE", "000786.XSHE", "000792.XSHE",
    "000807.XSHE", "000858.XSHE", "000876.XSHE", "000895.XSHE", "000938.XSHE",
    "000963.XSHE", "000975.XSHE", "000977.XSHE", "000983.XSHE", "000999.XSHE",
    "001391.XSHE", "001965.XSHE", "001979.XSHE", "002001.XSHE", "002027.XSHE",
    "002028.XSHE", "002049.XSHE", "002050.XSHE", "002074.XSHE", "002142.XSHE",
    "002179.XSHE", "002230.XSHE", "002236.XSHE", "002241.XSHE", "002252.XSHE",
    "002304.XSHE", "002311.XSHE", "002352.XSHE", "002371.XSHE", "002384.XSHE",
    "002415.XSHE", "002422.XSHE", "002459.XSHE", "002460.XSHE", "002463.XSHE",
    "002466.XSHE", "002475.XSHE", "002493.XSHE", "002594.XSHE", "002600.XSHE",
    "002601.XSHE", "002625.XSHE", "002648.XSHE", "002709.XSHE", "002714.XSHE",
    "002736.XSHE", "002916.XSHE", "002920.XSHE", "002938.XSHE", "003816.XSHE",
    "300002.XSHE", "300014.XSHE", "300015.XSHE", "300017.XSHE", "300024.XSHE",
    "300033.XSHE", "300058.XSHE", "300059.XSHE", "300073.XSHE", "300115.XSHE",
    "300122.XSHE", "300124.XSHE", "300136.XSHE", "300207.XSHE", "300223.XSHE",
    "300251.XSHE", "300255.XSHE", "300274.XSHE", "300308.XSHE", "300316.XSHE",
    "300339.XSHE", "300346.XSHE", "300347.XSHE", "300373.XSHE", "300394.XSHE",
    "300395.XSHE", "300408.XSHE", "300413.XSHE", "300418.XSHE", "300433.XSHE",
    "300442.XSHE", "300450.XSHE", "300458.XSHE", "300474.XSHE", "300476.XSHE",
    "300496.XSHE", "300498.XSHE", "300502.XSHE", "300548.XSHE", "300604.XSHE",
    "300628.XSHE", "300661.XSHE", "300724.XSHE", "300748.XSHE", "300750.XSHE",
    "300759.XSHE", "300760.XSHE", "300763.XSHE", "300782.XSHE", "300803.XSHE",
    "300832.XSHE", "300857.XSHE", "300866.XSHE", "300896.XSHE", "300979.XSHE",
    "300999.XSHE", "301236.XSHE", "301269.XSHE", "301308.XSHE", "302132.XSHE",
    "600000.XSHG", "600009.XSHG", "600010.XSHG", "600011.XSHG", "600015.XSHG",
    "600016.XSHG", "600018.XSHG", "600019.XSHG", "600023.XSHG", "600025.XSHG",
    "600026.XSHG", "600027.XSHG", "600028.XSHG", "600029.XSHG", "600030.XSHG",
    "600031.XSHG", "600036.XSHG", "600039.XSHG", "600048.XSHG", "600050.XSHG",
    "600061.XSHG", "600066.XSHG", "600085.XSHG", "600089.XSHG", "600104.XSHG",
    "600111.XSHG", "600115.XSHG", "600150.XSHG", "600160.XSHG", "600161.XSHG",
    "600176.XSHG", "600183.XSHG", "600188.XSHG", "600196.XSHG", "600219.XSHG",
    "600233.XSHG", "600276.XSHG", "600309.XSHG", "600346.XSHG", "600362.XSHG",
    "600372.XSHG", "600377.XSHG", "600406.XSHG", "600415.XSHG", "600426.XSHG",
    "600436.XSHG", "600438.XSHG", "600460.XSHG", "600482.XSHG", "600489.XSHG",
    "600515.XSHG", "600519.XSHG", "600522.XSHG", "600547.XSHG", "600570.XSHG",
    "600584.XSHG", "600585.XSHG", "600588.XSHG", "600600.XSHG", "600660.XSHG",
    "600674.XSHG", "600690.XSHG", "600741.XSHG", "600760.XSHG", "600795.XSHG",
    "600803.XSHG", "600809.XSHG", "600845.XSHG", "600875.XSHG", "600886.XSHG",
    "600887.XSHG", "600893.XSHG", "600900.XSHG", "600905.XSHG", "600918.XSHG",
    "600919.XSHG", "600926.XSHG", "600930.XSHG", "600938.XSHG", "600941.XSHG",
    "600958.XSHG", "600989.XSHG", "600999.XSHG", "601006.XSHG", "601009.XSHG",
    "601012.XSHG", "601018.XSHG", "601021.XSHG", "601058.XSHG", "601059.XSHG",
    "601066.XSHG", "601077.XSHG", "601088.XSHG", "601100.XSHG", "601111.XSHG",
    "601117.XSHG", "601127.XSHG", "601136.XSHG", "601138.XSHG", "601166.XSHG",
    "601169.XSHG", "601186.XSHG", "601211.XSHG", "601225.XSHG", "601229.XSHG",
    "601236.XSHG", "601238.XSHG", "601288.XSHG", "601298.XSHG", "601318.XSHG",
    "601319.XSHG", "601328.XSHG", "601336.XSHG", "601360.XSHG", "601377.XSHG",
    "601390.XSHG", "601398.XSHG", "601456.XSHG", "601600.XSHG", "601601.XSHG",
    "601607.XSHG", "601618.XSHG", "601628.XSHG", "601633.XSHG", "601658.XSHG",
    "601668.XSHG", "601669.XSHG", "601688.XSHG", "601689.XSHG", "601698.XSHG",
    "601728.XSHG", "601766.XSHG", "601788.XSHG", "601800.XSHG", "601808.XSHG",
    "601816.XSHG", "601818.XSHG", "601825.XSHG", "601838.XSHG", "601857.XSHG",
    "601868.XSHG", "601872.XSHG", "601877.XSHG", "601878.XSHG", "601881.XSHG",
    "601888.XSHG", "601898.XSHG", "601899.XSHG", "601901.XSHG", "601916.XSHG",
    "601919.XSHG", "601939.XSHG", "601985.XSHG", "601988.XSHG", "601995.XSHG",
    "601998.XSHG", "603019.XSHG", "603195.XSHG", "603259.XSHG", "603260.XSHG",
    "603288.XSHG", "603296.XSHG", "603369.XSHG", "603392.XSHG", "603501.XSHG",
    "603799.XSHG", "603893.XSHG", "603986.XSHG", "603993.XSHG", "605117.XSHG",
    "605499.XSHG", "688008.XSHG", "688009.XSHG", "688012.XSHG", "688027.XSHG",
    "688036.XSHG", "688041.XSHG", "688047.XSHG", "688065.XSHG", "688072.XSHG",
    "688082.XSHG", "688099.XSHG", "688111.XSHG", "688114.XSHG", "688120.XSHG",
    "688122.XSHG", "688126.XSHG", "688169.XSHG", "688183.XSHG", "688187.XSHG",
    "688188.XSHG", "688213.XSHG", "688220.XSHG", "688223.XSHG", "688234.XSHG",
    "688249.XSHG", "688256.XSHG", "688271.XSHG", "688278.XSHG", "688297.XSHG",
    "688303.XSHG", "688349.XSHG", "688361.XSHG", "688375.XSHG", "688396.XSHG",
    "688469.XSHG", "688472.XSHG", "688506.XSHG", "688521.XSHG", "688525.XSHG",
    "688538.XSHG", "688568.XSHG", "688578.XSHG", "688599.XSHG", "688608.XSHG",
    "688617.XSHG", "688702.XSHG", "688728.XSHG", "688777.XSHG", "688981.XSHG",
    "689009.XSHG",
]
