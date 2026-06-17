# -*- coding: utf-8 -*-
"""
双均线+突破+量+RSI+波动率 多信号共振波段策略 (聚宽 JQ 回测脚本)
================================================================
策略名称: dma_breakout_vol_rsi_1
策略文档: D:/my-auto-quant/result/dma_breakout_vol_rsi_1/dma_breakout_vol_rsi_1_final.md
回测平台: JoinQuant (聚宽) — JQBoson 引擎 (Python 3.6)
对齐目标: subjects/subject/backtest/runner.py::_run_weight

本脚本严格按本地 weight 回测引擎语义实现. 关键约定:
1. T-1 因子决策 + T 开盘成交 (严格无前视, 09:30 单一调度)
2. 多信号加权 score 排序 (5 个入场信号 AND 全部触发 = 总分 1.0)
3. 5 个仓位约束链式应用: single → industry → turnover → fill_cash
4. 出场按 weight 降序遍历, 第一个触发即 return (短路)
5. holding_days 按交易日累加, 1-based (对齐本地 P3 修复)
6. entry_price 含费用: (amount + fee) / shares
7. 北交所代码前缀过滤, 科创板 200 股整手, 涨跌停单 filled 检查
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
    "benchmark": "000300.XSHG",
    "use_fixed_universe": True,
    "universe_index": "000300.XSHG",

    "ma_short": 5,
    "ma_mid": 20,
    "high_period": 20,
    "rsi_period": 14,
    "volume_ma_period": 20,
    "atr_period": 14,

    "vol_breakout_ratio": 1.5,
    "rsi_min": 30,
    "rsi_max": 70,
    "min_atr_ratio": 0.015,

    "trail_stop_pct": 0.06,
    "fixed_stop_pct": 0.08,
    "max_hold_days": 30,

    "target_holdings": 10,
    "max_single_weight": 0.1,
    "max_industry_concentration": 0.3,
    "max_turnover_per_rebalance": 0.4,

    "rebalance_freq_days": 5,

    "entry_weights": {
        "ma_trend_bull": 0.3,
        "price_breakout": 0.25,
        "volume_surge": 0.15,
        "rsi_healthy": 0.15,
        "volatility_active": 0.15,
    },

    "exit_weights": {
        "ma_trend_bear": 0.3,
        "trailing_stop": 0.25,
        "fixed_stop": 0.25,
        "time_stop": 0.2,
    },

    "tie_break_seed": 42,
}


# ============================================================
# 2. 策略初始化
# ============================================================
def initialize(context):
    set_benchmark(PARAMS["benchmark"])
    set_option("use_real_price", True)

    set_order_cost(OrderCost(
        open_tax=0,
        close_tax=0.001,
        open_commission=0.00025,
        close_commission=0.00025,
        close_today_commission=0,
        min_commission=5
    ), type="stock")

    set_slippage(FixedSlippage(0))
    log.set_level("order", "error")

    g.params = PARAMS
    g.universe = []
    g.holdings = {}
    g.industry_map = {}
    g.bar_index = 0

    run_daily(daily_handle, time="09:30")

    if PARAMS.get("use_fixed_universe", False):
        set_universe(FIXED_UNIVERSE)

    log.info("=" * 60)
    log.info("=== dma_breakout_vol_rsi_1 (严格 T-1 模式) 初始化完成 ===")
    log.info("策略: 双均线多头 + 突破20日高 + 量放大 + RSI健康 + 波动率活跃")
    log.info("目标: 年化26%, 胜率45%, 盈亏比3.5, 夏普1.5, 最大回撤20%")
    log.info("=" * 60)


# ============================================================
# 3. 因子计算 (严格用 T-1 收盘前的数据)
# ============================================================
def _ema(series, span):
    return series.ewm(span=span, adjust=False).mean()


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
    return rsi.fillna(50.0)


def _build_factors_dict(close, high, low, volume, last_close, p):
    """根据行情序列构造因子 dict (末尾用 np.isfinite 验证)."""
    ma_5 = close.tail(p["ma_short"]).mean()
    ma_20 = close.tail(p["ma_mid"]).mean()
    high_20 = close.tail(p["high_period"]).max()

    atr_series = _atr(high, low, close, p["atr_period"])
    atr_14 = atr_series.iloc[-1]

    rsi_series = _rsi(close, p["rsi_period"])
    rsi_14 = rsi_series.iloc[-1]

    vol_ma_20 = volume.tail(p["volume_ma_period"]).mean()
    if vol_ma_20 is None or pd.isna(vol_ma_20) or vol_ma_20 <= 0:
        vol_ratio = 0.0
    else:
        vol_today = volume.iloc[-1]
        if vol_today is None or pd.isna(vol_today):
            vol_ratio = 0.0
        else:
            vol_ratio = float(vol_today) / float(vol_ma_20)

    factors = {
        "close": float(last_close) if last_close is not None else 0.0,
        "ma_5": float(ma_5) if ma_5 is not None and not pd.isna(ma_5) else 0.0,
        "ma_20": float(ma_20) if ma_20 is not None and not pd.isna(ma_20) else 0.0,
        "high_20": float(high_20) if high_20 is not None and not pd.isna(high_20) else 0.0,
        "atr_14": float(atr_14) if atr_14 is not None and not pd.isna(atr_14) else 0.0,
        "rsi_14": float(rsi_14) if rsi_14 is not None and not pd.isna(rsi_14) else 50.0,
        "vol_ratio": float(vol_ratio) if vol_ratio is not None and not pd.isna(vol_ratio) else 0.0,
    }
    for k, v in factors.items():
        if not np.isfinite(v):
            return None
    return factors


def calc_factors_t1(stock, context, n=70):
    """单股 fallback 因子计算."""
    p = g.params
    try:
        df = attribute_history(stock, n, "1d",
                              ["open", "close", "high", "low", "volume"],
                              skip_paused=False, df=True, fq="pre")
        if df is None or len(df) < p["ma_mid"]:
            return None

        close = df["close"]
        high = df["high"]
        low = df["low"]
        volume = df["volume"]

        valid_close = close.dropna()
        if len(valid_close) < p["ma_mid"]:
            return None

        last_close = close.iloc[-1]
        if last_close is None or pd.isna(last_close) or last_close <= 0:
            return None

        return _build_factors_dict(close, high, low, volume, last_close, p)
    except Exception as e:
        log.warn("计算 %s 因子异常: %s" % (stock, str(e)))
        return None


def calc_factors_batch(stock_list, context, n=70):
    """批量计算所有股票的 T-1 因子 (用 history() 一次性获取)."""
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
        log.warn("批量历史数据获取失败: %s" % str(e))
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
            if len(valid_close) < p["ma_mid"]:
                continue

            last_close = close.iloc[-1]
            if last_close is None or pd.isna(last_close) or last_close <= 0:
                continue

            d = _build_factors_dict(close, high, low, volume, last_close, p)
            if d is not None:
                out[stock] = d
        except Exception:
            continue

    return out


# ============================================================
# 4. 入场信号 + score (5 信号 AND 全部触发 = 总分 1.0)
# ============================================================
def get_triggered_signals(factors, p):
    triggered = []
    close = factors.get("close")
    ma_5 = factors.get("ma_5")
    ma_20 = factors.get("ma_20")
    high_20 = factors.get("high_20")
    rsi_14 = factors.get("rsi_14")
    atr_14 = factors.get("atr_14")
    vol_ratio = factors.get("vol_ratio")

    if close is None or close <= 0:
        return triggered

    if (ma_5 is not None and ma_20 is not None
            and not pd.isna(ma_5) and not pd.isna(ma_20)
            and ma_5 > ma_20 and close > ma_20):
        triggered.append("ma_trend_bull")

    if (high_20 is not None and not pd.isna(high_20) and close > high_20):
        triggered.append("price_breakout")

    if (vol_ratio is not None and not pd.isna(vol_ratio)
            and vol_ratio > p["vol_breakout_ratio"]):
        triggered.append("volume_surge")

    if (rsi_14 is not None and not pd.isna(rsi_14)
            and p["rsi_min"] < rsi_14 < p["rsi_max"]):
        triggered.append("rsi_healthy")

    if (atr_14 is not None and not pd.isna(atr_14)
            and atr_14 / close > p["min_atr_ratio"]):
        triggered.append("volatility_active")

    return triggered


def entry_score(factors, p):
    triggered = get_triggered_signals(factors, p)
    score = 0.0
    for sig in triggered:
        score += float(p["entry_weights"].get(sig, 0.0))
    return score


# ============================================================
# 5. 出场信号
# ============================================================
def _check_exit_signal(sig_name, factors, holding, current_price, p):
    entry_price = holding["entry_price"]
    holding_days = holding.get("holding_days", 0)

    if sig_name == "ma_trend_bear":
        ma_5 = factors.get("ma_5")
        ma_20 = factors.get("ma_20")
        if (ma_5 is not None and ma_20 is not None
                and not pd.isna(ma_5) and not pd.isna(ma_20)):
            return ma_5 < ma_20
        return False
    elif sig_name == "trailing_stop":
        high_20 = factors.get("high_20")
        if high_20 is None or pd.isna(high_20) or high_20 <= 0:
            return False
        return current_price < high_20 * (1 - p["trail_stop_pct"])
    elif sig_name == "fixed_stop":
        return current_price < entry_price * (1 - p["fixed_stop_pct"])
    elif sig_name == "time_stop":
        return holding_days >= p["max_hold_days"]
    return False


def should_exit(factors, holding, current_price, p):
    exit_w = p["exit_weights"]
    active_sigs = [s for s, w in exit_w.items() if w > 0]
    for sig in sorted(active_sigs, key=exit_w.get, reverse=True):
        if _check_exit_signal(sig, factors, holding, current_price, p):
            return sig
    return None


# ============================================================
# 6. 排序与仓位约束
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
# 7. A 股规则
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
    if d is None:
        return False
    if d.high_limit > 0 and d.last_price is not None and d.last_price > 0:
        if d.last_price >= d.high_limit - 0.01:
            return False
    return True


def can_sell_at_open(d, stock):
    if d is None:
        return False
    if d.low_limit > 0 and d.last_price is not None and d.last_price > 0:
        if d.last_price <= d.low_limit + 0.01:
            return False
    return True


# ============================================================
# 8. 主循环 daily_handle
# ============================================================
def daily_handle(context):
    p = g.params
    g.bar_index += 1
    bar_idx = g.bar_index

    log.info("[%s] bar_idx=%d (%s)" % (
             context.current_dt.strftime("%Y-%m-%d"), bar_idx,
             "首日(跳过)" if bar_idx == 1 else (
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

    # step 2: 刷新 universe
    if p.get("use_fixed_universe", False):
        raw = list(FIXED_UNIVERSE)
    else:
        try:
            raw = list(get_index_stocks(p["universe_index"], date=context.previous_date))
        except Exception as e:
            log.warn("获取 universe 失败: %s" % str(e))
            raw = []
    g.universe = filter_universe(raw, context)
    g.industry_map = get_industry_map(g.universe, date=context.previous_date)

    # step 3: 批量算因子 + entry_score
    factors_by_code = calc_factors_batch(g.universe, context, n=70)
    scores = {}
    for stock, f in factors_by_code.items():
        s = entry_score(f, p)
        if s > 0:
            scores[stock] = s

    for stock in list(g.holdings.keys()):
        if stock not in factors_by_code:
            f = calc_factors_t1(stock, context, n=70)
            if f is not None:
                factors_by_code[stock] = f
                s = entry_score(f, p)
                if s > 0:
                    scores[stock] = s

    log.info("候选 %d, score>0 %d, 持仓 %d" %
             (len(g.universe), len(scores), len(g.holdings)))

    # step 4: 出场决策
    cd = get_current_data()
    for stock in list(g.holdings.keys()):
        if stock not in factors_by_code:
            continue
        h = g.holdings[stock]
        f = factors_by_code[stock]
        prev_close = h.get("prev_close") or f.get("close", 0)
        if prev_close is None or prev_close <= 0:
            continue
        exit_sig = should_exit(f, h, prev_close, p)
        if exit_sig is None:
            continue
        d = _cd_get(cd, stock)
        if not can_sell_at_open(d, stock):
            log.info("%s 出场信号=%s 但 T 开盘无法卖出" % (stock, exit_sig))
            continue
        _execute_sell(stock, h, exit_sig, context)

    # step 5: 调仓
    if should_rebalance(bar_idx, p["rebalance_freq_days"]):
        _do_rebalance(scores, factors_by_code, context)


# ============================================================
# 9. 调仓
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
        log.warn("fill_cash 失败: %s" % str(e))

    log.info("rebalance: top_n=%d, weights=%d, sum=%.4f" %
             (len(top_codes), len(target_weights), _sum(target_weights.values())))

    total_value = _compute_total_value(context)
    cd = get_current_data()

    for stock in list(g.holdings.keys()):
        if stock in target_weights:
            continue
        h = g.holdings[stock]
        d = _cd_get(cd, stock)
        if not can_sell_at_open(d, stock):
            log.info("%s 调仓卖出但跌停/停牌" % stock)
            continue
        _execute_sell(stock, h, "rebalance_out", context)

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
# 10. 买卖执行
# ============================================================
def _execute_buy(stock, open_px, shares, triggered_signals, context):
    if shares < 100:
        return
    if stock in g.holdings:
        return

    amount = open_px * shares
    fee = _max(amount * 0.00025, 5)
    total_cost = amount + fee

    if total_cost > context.portfolio.available_cash:
        log.info("现金不足, 放弃买入: %s" % stock)
        return

    if stock.startswith("688"):
        limit_price = _min(open_px * 1.005, 9999.99)
        order_result = order(stock, shares, LimitOrderStyle(limit_price))
    else:
        order_result = order(stock, shares)

    if order_result is None:
        log.info("下单失败: %s" % stock)
        return

    filled_shares = getattr(order_result, "filled", 0)
    if filled_shares == 0:
        log.info("下单未成交: %s" % stock)
        return

    actual_shares = int(filled_shares)
    actual_amount = open_px * actual_shares
    actual_fee = _max(actual_amount * 0.00025, 5)
    effective_entry = (actual_amount + actual_fee) / actual_shares

    g.holdings[stock] = {
        "entry_price": effective_entry,
        "entry_date": context.current_dt,
        "highest_close": open_px,
        "holding_days": 1,  # 1-based (P3 修复)
        "shares": actual_shares,
        "entry_signals": list(triggered_signals),
        "prev_close": open_px,
    }
    log.info(">>> 买入 %s: %d股 @ %.2f, 含费=%.4f" %
             (stock, actual_shares, open_px, effective_entry))


def _execute_sell(stock, holding, exit_signal, context):
    cd = get_current_data()
    d = _cd_get(cd, stock)

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
        order_result = order(stock, -shares)

    if order_result is None:
        log.warn("清仓下单失败: %s" % stock)
        return

    sell_amount = open_px * shares
    sell_fee = _max(sell_amount * 0.00025, 5) + sell_amount * 0.001
    pnl = (open_px - entry_price) * shares - sell_fee

    log.info(">>> 卖出 %s: %d股 @ %.2f, PnL=%.2f, 持仓=%d日, 信号=%s" %
             (stock, shares, open_px, pnl, holding_days, exit_signal))
    del g.holdings[stock]


# ============================================================
# 11. self_check
# ============================================================
def self_check():
    p = PARAMS
    issues = []
    for key in ["target_holdings", "max_single_weight", "max_industry_concentration",
                "max_turnover_per_rebalance", "rebalance_freq_days",
                "entry_weights", "exit_weights", "tie_break_seed"]:
        if key not in p:
            issues.append("PARAMS 缺少: " + key)
    if p.get("tie_break_seed") != 42:
        issues.append("tie_break_seed 应为 42")
    for sig, w in p.get("entry_weights", {}).items():
        if w <= 0:
            issues.append("entry_weights[%s] = %s, 应 > 0" % (sig, w))
    for sig, w in p.get("exit_weights", {}).items():
        if 0 < w < 1e-6:
            issues.append("exit_weights[%s] = %.2e, weight 极小" % (sig, w))
    for sig in ["ma_trend_bull", "price_breakout", "volume_surge", "rsi_healthy", "volatility_active"]:
        if sig not in p.get("entry_weights", {}):
            issues.append("entry 缺 spec 信号: " + sig)
    for sig in ["ma_trend_bear", "trailing_stop", "fixed_stop", "time_stop"]:
        if sig not in p.get("exit_weights", {}):
            issues.append("exit 缺 spec 信号: " + sig)
    if issues:
        log.warn("=== PARAMS 自检 %d 个问题 ===" % len(issues))
        for i in issues: log.warn("  - " + str(i))
    else:
        log.info("=== PARAMS 自检通过 ===")
    return len(issues) == 0


# ============================================================
# 12. 固定股票池 FIXED_UNIVERSE (HS300)
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
    "300015.XSHE", "300033.XSHE", "300059.XSHE", "300122.XSHE", "300124.XSHE",
    "300142.XSHE", "300144.XSHE", "300223.XSHE", "300251.XSHE", "300316.XSHE",
    "300347.XSHE", "300408.XSHE", "300413.XSHE", "300433.XSHE", "300442.XSHE",
    "300450.XSHE", "300498.XSHE", "300601.XSHE", "300628.XSHE", "300661.XSHE",
    "300674.XSHE", "300677.XSHE", "300750.XSHE", "300751.XSHE", "300759.XSHE",
    "300760.XSHE", "300782.XSHE", "300866.XSHE", "300896.XSHE", "300979.XSHE",
    "300999.XSHE", "301236.XSHE", "301269.XSHE",
    "600000.XSHG", "600009.XSHG", "600010.XSHG", "600011.XSHG", "600015.XSHG",
    "600016.XSHG", "600018.XSHG", "600019.XSHG", "600023.XSHG", "600025.XSHG",
    "600028.XSHG", "600029.XSHG", "600030.XSHG", "600031.XSHG", "600036.XSHG",
    "600048.XSHG", "600050.XSHG", "600061.XSHG", "600085.XSHG", "600089.XSHG",
    "600104.XSHG", "600111.XSHG", "600150.XSHG", "600188.XSHG", "600196.XSHG",
    "600276.XSHG", "600309.XSHG", "600346.XSHG", "600362.XSHG", "600406.XSHG",
    "600436.XSHG", "600438.XSHG", "600519.XSHG", "600522.XSHG", "600547.XSHG",
    "600570.XSHG", "600584.XSHG", "600585.XSHG", "600588.XSHG", "600600.XSHG",
    "600660.XSHG", "600690.XSHG", "600741.XSHG", "600795.XSHG", "600809.XSHG",
    "600886.XSHG", "600887.XSHG", "600893.XSHG", "600900.XSHG", "600905.XSHG",
    "600918.XSHG", "600926.XSHG", "600941.XSHG", "600958.XSHG", "600989.XSHG",
    "600999.XSHG", "601006.XSHG", "601009.XSHG", "601012.XSHG", "601018.XSHG",
    "601021.XSHG", "601066.XSHG", "601088.XSHG", "601100.XSHG", "601111.XSHG",
    "601138.XSHG", "601166.XSHG", "601186.XSHG", "601211.XSHG", "601225.XSHG",
    "601229.XSHG", "601288.XSHG", "601318.XSHG", "601319.XSHG", "601328.XSHG",
    "601336.XSHG", "601360.XSHG", "601377.XSHG", "601390.XSHG", "601398.XSHG",
    "601600.XSHG", "601601.XSHG", "601607.XSHG", "601618.XSHG", "601628.XSHG",
    "601633.XSHG", "601658.XSHG", "601668.XSHG", "601669.XSHG", "601688.XSHG",
    "601689.XSHG", "601698.XSHG", "601728.XSHG", "601766.XSHG", "601788.XSHG",
    "601800.XSHG", "601808.XSHG", "601816.XSHG", "601818.XSHG", "601825.XSHG",
    "601838.XSHG", "601857.XSHG", "601868.XSHG", "601872.XSHG", "601877.XSHG",
    "601878.XSHG", "601881.XSHG", "601888.XSHG", "601898.XSHG", "601899.XSHG",
    "601901.XSHG", "601916.XSHG", "601919.XSHG", "601939.XSHG", "601985.XSHG",
    "601988.XSHG", "601995.XSHG", "601998.XSHG", "603019.XSHG", "603195.XSHG",
    "603259.XSHG", "603288.XSHG", "603369.XSHG", "603501.XSHG", "603799.XSHG",
    "603893.XSHG", "603986.XSHG", "603993.XSHG", "605117.XSHG", "605499.XSHG",
    "688008.XSHG", "688009.XSHG", "688012.XSHG", "688027.XSHG", "688036.XSHG",
    "688041.XSHG", "688065.XSHG", "688099.XSHG", "688111.XSHG", "688126.XSHG",
    "688169.XSHG", "688187.XSHG", "688188.XSHG", "688223.XSHG", "688271.XSHG",
    "688303.XSHG", "688349.XSHG", "688361.XSHG", "688396.XSHG", "688472.XSHG",
    "688506.XSHG", "688521.XSHG", "688538.XSHG", "688599.XSHG", "688617.XSHG",
    "688728.XSHG", "688777.XSHG", "688981.XSHG",
]
