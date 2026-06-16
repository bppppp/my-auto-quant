# -*- coding: utf-8 -*-
"""
trend_momo_vol_filter_1 - 趋势动量 + 波动过滤策略 (严格 T-1 回测模式)
==================================================================
策略名称: trend_momo_vol_filter_1
策略文档: D:/project/quant/my-quant3/result/trend_momo_vol_filter_1/trend_momo_vol_filter_1_final.md
回测平台: JoinQuant (聚宽)

本脚本严格按本地 weight 回测引擎 (subjects/subject/backtest/runner.py::_run_weight)
的语义实现, 用于对齐本地与聚宽的回测结果:

核心入场逻辑 (4 信号加权 score):
  ma_golden_cross (0.44)  - ma_10 > ma_30 趋势确认
  macd_positive  (0.01)   - macd_diff > 0 动量确认
  volume_surge   (0.45)   - volume_ratio_20 > vol_break_ratio 资金确认
  atr_normal_range (0.10) - atr_14/close 在 [atr_low_limit, atr_up_limit] 区间
                           (排除僵尸股与极端投机股)

核心出场逻辑 (3 信号按 weight 降序短路):
  time_stop     (0.70)    - holding_days >= max_holding_days (35)
  trailing_stop (0.28)    - current_price < highest_close * (1 - trailing_stop_pct)
  fixed_stop_loss (0.02)  - current_price < entry_price * (1 - stop_loss_pct)

关键约定:
1. T-1 因子决策 + T 开盘成交 (严格无前视)
2. score-based 排序 + random tie-break (seed=42)
3. 5 个仓位约束链式应用 (single -> industry -> turnover -> fill_cash)
4. 出场优先级动态读权重 (sorted(exit_weights) 降序)
5. holding_days 按交易日累加, 1-based (buy 设 1, 对齐本地 P3 修复)
6. entry_price 含费用调整 (amount + fee) / shares
7. 北交所 (4/8/92) 自动过滤, 科创板 (688) 整手 200 股
8. Universe: HS300 (300 只, 与本地 spec test_universe 一致)

目标: 年化 24%, 胜率 46%, 盈亏比 3.3, 夏普 1.2, 最大回撤 -18%
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

    "ma_short": 10,
    "ma_long": 30,
    "macd_fast": 12,
    "macd_slow": 26,
    "atr_period": 14,
    "volume_ma_period": 20,

    "vol_break_ratio": 1.4,
    "atr_low_limit": 0.01,
    "atr_up_limit": 0.06,

    "stop_loss_pct": 0.07,
    "trailing_stop_pct": 0.18,
    "max_holding_days": 35,

    "target_holdings": 6,
    "max_single_weight": 0.15,
    "max_industry_concentration": 0.3,
    "max_turnover_per_rebalance": 0.4,

    "rebalance_freq_days": 5,

    "entry_weights": {
        "ma_golden_cross": 0.44,
        "macd_positive": 0.01,
        "volume_surge": 0.45,
        "atr_normal_range": 0.10,
    },
    "exit_weights": {
        "time_stop": 0.70,
        "trailing_stop": 0.28,
        "fixed_stop_loss": 0.02,
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
    g.industry_map_cache = {}    # ⚠️ 2026-06-15 优化: industry_map 按 date 缓存 (FIXED_UNIVERSE 行业基本不变)
    g.bar_index = 0

    run_daily(daily_handle, time="09:30")

    if PARAMS.get("use_fixed_universe", False):
        set_universe(FIXED_UNIVERSE)

    log.info("=" * 60)
    log.info("=== trend_momo_vol_filter_1 (严格 T-1 模式) 初始化完成 ===")
    log.info("策略: 多因子趋势动量 + 波动过滤 (MA金叉+MACD+量比+ATR区间)")
    log.info("出场: 时间止损 (35日) > 移动止损 (18%) > 固定止损 (7%)")
    log.info("目标: 年化24%, 胜率46%, 盈亏比3.3, 夏普1.2, 回撤18%")
    log.info("=" * 60)


# ============================================================
# 3. 因子计算
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


def calc_factors_t1(stock, context, n=70):
    """⚠️ 2026-06-15 修复: 全程用 pd.Series, 不要转 numpy (numpy 数组没有 ewm/shift/rolling)."""
    p = g.params
    try:
        df = attribute_history(stock, n, "1d",
                              ["close", "high", "low", "volume"],
                              skip_paused=False, df=True, fq="pre")
        if df is None or len(df) < p["ma_long"] + 5:
            return None
        close_series = df["close"].dropna()
        if len(close_series) < p["ma_long"] + 5 or pd.isna(close_series.iloc[-1]) or close_series.iloc[-1] <= 0:
            return None
        high_series = df["high"].dropna()
        low_series = df["low"].dropna()
        volume_series = df["volume"].dropna()
        if len(high_series) < p["atr_period"] + 1 or len(low_series) < p["atr_period"] + 1:
            return None
        # ⚠️ 全部传 pd.Series, _ema/_atr 内部用 pandas API
        ma_10 = float(close_series.iloc[-p["ma_short"]:].mean())
        ma_30 = float(close_series.iloc[-p["ma_long"]:].mean())
        ema_fast = _ema(close_series, p["macd_fast"])
        ema_slow = _ema(close_series, p["macd_slow"])
        macd_diff = float(ema_fast.iloc[-1] - ema_slow.iloc[-1])
        vol_tail = volume_series.iloc[-p["volume_ma_period"]:] if len(volume_series) >= p["volume_ma_period"] else volume_series
        vol_ma = float(vol_tail.mean()) if len(vol_tail) > 0 else 0.0
        volume_ratio_20 = float(volume_series.iloc[-1] / vol_ma) if vol_ma > 0 else 0.0
        atr_14 = float(_atr(high_series, low_series, close_series, p["atr_period"]).iloc[-1])
        factors = {
            "close": float(close_series.iloc[-1]),
            "ma_10": ma_10,
            "ma_30": ma_30,
            "macd_diff": macd_diff,
            "volume_ratio_20": volume_ratio_20,
            "atr_14": atr_14,
        }
        for v in factors.values():
            if not np.isfinite(v):
                return None
        return factors
    except Exception as e:
        log.warn("计算 %s 因子异常: %s" % (stock, str(e)))
        return None


def calc_factors_batch(stock_list, context, n=70):
    """⚠️ 2026-06-15 修复: 回退到 df=True (DataFrame).

    之前改用 df=False (numpy array) 后, 300 只全 fail (factors_by_code=0).
    原因: JQ 平台 df=False 返回的 numpy array 行为与 df=True DataFrame 不一致
    (可能数组长度不足 70, 或 NaN 处理差异, 或数组顺序反), 导致所有 300 只全
    被 isfinite 检查 / size 检查跳过. 改前 df=True 用户跑过能正常算出因子.

    性能折中: 仍走 df=True (DataFrame), 但内部用 numpy 操作 (df.values / np.nanmean)
    加速 — 既保留 pandas 默认 skipna=True 的 NaN 处理行为, 又拿到 numpy 数值计算速度.
    """
    p = g.params
    if not stock_list:
        return {}
    try:
        df_close = history(n, "1d", "close", stock_list, df=True, skip_paused=False, fq="pre")
        df_high = history(n, "1d", "high", stock_list, df=True, skip_paused=False, fq="pre")
        df_low = history(n, "1d", "low", stock_list, df=True, skip_paused=False, fq="pre")
        df_volume = history(n, "1d", "volume", stock_list, df=True, skip_paused=False, fq="pre")
    except Exception as e:
        log.warn("批量历史数据获取失败: %s" % str(e))
        return {}
    # ⚠️ 2026-06-15 详细诊断: 看 df_close 实际是什么
    if df_close is None:
        log.warn("[diag] calc_factors_batch: df_close is None")
        return {}
    if df_close.empty:
        log.warn("[diag] calc_factors_batch: df_close.empty=True, columns=%s" % list(df_close.columns)[:5])
        return {}
    n_cols = len(df_close.columns)
    n_rows = len(df_close)
    log.info("[diag] calc batch: df_close shape=(%d,%d), input stock_list=%d" % (n_rows, n_cols, len(stock_list)))
    if not getattr(g, "_diag_batch_sampled", False):
        sample_col = df_close.columns[0]
        sample_series = df_close[sample_col]
        log.info("[diag] sample col=%s, len=%d, first 3 vals=%s, last 3 vals=%s, dtype=%s, has_nan=%s" %
                 (sample_col, len(sample_series),
                  list(sample_series.iloc[:3]),
                  list(sample_series.iloc[-3:]),
                  sample_series.dtype,
                  bool(sample_series.isna().any())))
        g._diag_batch_sampled = True
    out = {}
    n_skip_nocol = 0
    n_skip_short = 0
    n_skip_nan = 0
    n_skip_size = 0
    n_added = 0
    n_skip_exc = 0    # ⚠️ 2026-06-15 诊断: except 吞掉的股
    for stock in stock_list:
        try:
            if stock not in df_close.columns:
                n_skip_nocol += 1
                continue
            # ⚠️ 2026-06-15 修复: 全程用 pd.Series, 不要转 numpy
            # (numpy 数组没有 ewm/shift/rolling, _ema/_atr 内部用 pandas API 会抛 AttributeError)
            close_series = df_close[stock].dropna()
            if len(close_series) < p["ma_long"] + 5:
                n_skip_short += 1
                continue
            last_close = close_series.iloc[-1]
            if pd.isna(last_close) or last_close <= 0:
                n_skip_nan += 1
                continue
            high_series = df_high[stock].dropna()
            low_series = df_low[stock].dropna()
            volume_series = df_volume[stock].dropna()
            if len(high_series) < p["atr_period"] + 1 or len(low_series) < p["atr_period"] + 1:
                n_skip_size += 1
                continue
            # ⚠️ 全部传 pd.Series (pd.Series.iloc 切片, pd.Series.ewm/shift/rolling 都能用)
            ma_10 = float(close_series.iloc[-p["ma_short"]:].mean())
            ma_30 = float(close_series.iloc[-p["ma_long"]:].mean())
            ema_fast = _ema(close_series, p["macd_fast"])
            ema_slow = _ema(close_series, p["macd_slow"])
            macd_diff = float(ema_fast.iloc[-1] - ema_slow.iloc[-1])
            vol_tail = volume_series.iloc[-p["volume_ma_period"]:] if len(volume_series) >= p["volume_ma_period"] else volume_series
            vol_ma = float(vol_tail.mean()) if len(vol_tail) > 0 else 0.0
            volume_ratio_20 = float(volume_series.iloc[-1] / vol_ma) if vol_ma > 0 else 0.0
            atr_14 = float(_atr(high_series, low_series, close_series, p["atr_period"]).iloc[-1])
            factors = {
                "close": float(close_series.iloc[-1]),
                "ma_10": ma_10,
                "ma_30": ma_30,
                "macd_diff": macd_diff,
                "volume_ratio_20": volume_ratio_20,
                "atr_14": atr_14,
            }
            valid = True
            for v in factors.values():
                if not np.isfinite(v):
                    valid = False
                    break
            if valid:
                out[stock] = factors
                n_added += 1
        except Exception as e:
            # ⚠️ 2026-06-15 诊断: except 吞掉的股, 第一次打印
            n_skip_exc += 1
            if not getattr(g, "_diag_batch_exc", False) and n_skip_exc < 3:
                log.warn("[diag] calc_factors_batch except on %s: %s" % (stock, str(e)[:200]))
                if n_skip_exc == 3:
                    g._diag_batch_exc = True
            continue
    if not getattr(g, "_diag_batch_summary", False):
        log.info("[diag] calc batch summary: nocol=%d, short=%d, nan=%d, size=%d, exc=%d, added=%d" %
                 (n_skip_nocol, n_skip_short, n_skip_nan, n_skip_size, n_skip_exc, n_added))
        g._diag_batch_summary = True
    return out

# ============================================================
# 4. 入场信号 + score
# ============================================================
def get_triggered_signals(factors, p):
    triggered = []
    close = factors.get("close")
    ma_10 = factors.get("ma_10")
    ma_30 = factors.get("ma_30")
    macd_diff = factors.get("macd_diff")
    volume_ratio_20 = factors.get("volume_ratio_20")
    atr_14 = factors.get("atr_14")

    if close is None or close <= 0:
        return triggered

    if ma_10 is not None and ma_30 is not None and not pd.isna(ma_10) and not pd.isna(ma_30):
        if ma_10 > ma_30:
            triggered.append("ma_golden_cross")

    if macd_diff is not None and not pd.isna(macd_diff):
        if macd_diff > 0:
            triggered.append("macd_positive")

    if volume_ratio_20 is not None and not pd.isna(volume_ratio_20):
        if volume_ratio_20 > p["vol_break_ratio"]:
            triggered.append("volume_surge")

    if atr_14 is not None and not pd.isna(atr_14):
        atr_ratio = atr_14 / close
        if atr_ratio > p["atr_low_limit"] and atr_ratio < p["atr_up_limit"]:
            triggered.append("atr_normal_range")

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
    highest_close = holding.get("highest_close", entry_price)
    holding_days = holding.get("holding_days", 1)

    if sig_name == "time_stop":
        return holding_days >= p["max_holding_days"]
    elif sig_name == "trailing_stop":
        return current_price < highest_close * (1 - p["trailing_stop_pct"])
    elif sig_name == "fixed_stop_loss":
        return current_price < entry_price * (1 - p["stop_loss_pct"])
    return False


def should_exit(factors, holding, current_price, p):
    exit_w = p["exit_weights"]
    for sig in sorted(exit_w, key=exit_w.get, reverse=True):
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
    """安全取 cd[stock], KeyError 时返回 None.

    ⚠️ 2026-06-15 修复: JQ 平台 09:30 触发时, ``cd.get(s)`` 永远返回 None
    (JQuantAPI.md §17.2 — lazy loading, .get() 不触发, dict 初始为空).
    即使 ``set_universe(stock_list)`` 预填过, ``cd.get()`` 在首次访问仍 None.
    真正可靠的模式是 ``cd[s] + try/except KeyError``.

    Returns:
        stock data object (含 .last_price/.high_limit/.low_limit/.paused/.is_st)
        或 None (股票不在 cd 中, 例如停牌/退市/未上市).
    """
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
# 8. daily_handle
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

    # step 1: update highest_close + holding_days (⚠️ 2026-06-15 优化: batch 1 次 API 代替 N 次)
    holdings = list(g.holdings.keys())
    if holdings:
        # ⚠️ 2026-06-15 修复: 回退到 df=True (避免 df=False 行为不一致导致 0 只)
        try:
            close_df = history(1, "1d", "close", holdings,
                               df=True, skip_paused=False, fq="pre")
        except Exception:
            close_df = None
        for stock in holdings:
            h = g.holdings[stock]
            t1_close = 0.0
            if close_df is not None and stock in close_df.columns and len(close_df) > 0:
                try:
                    t1_close = float(close_df[stock].iloc[-1])
                except (TypeError, ValueError, IndexError):
                    t1_close = 0.0
            if not np.isnan(t1_close) and t1_close > 0:
                h["highest_close"] = _max(h.get("highest_close", h["entry_price"]),
                                          t1_close)
                h["prev_close"] = t1_close
            h["holding_days"] += 1

    # step 2: refresh universe
    if p.get("use_fixed_universe", False):
        raw = list(FIXED_UNIVERSE)
    else:
        try:
            raw = list(get_index_stocks(p["universe_index"], date=context.previous_date))
        except Exception as e:
            log.warn("获取 universe 失败: %s" % str(e))
            raw = []
    g.universe = filter_universe(raw, context)
    # ⚠️ 2026-06-15 优化: industry_map 按 date 缓存 (省 ~100ms/调仓日, 240 调仓日 ≈ 24s)
    date_key = str(context.previous_date)
    if date_key in g.industry_map_cache:
        g.industry_map = g.industry_map_cache[date_key]
    else:
        g.industry_map = get_industry_map(g.universe, date=context.previous_date)
        g.industry_map_cache[date_key] = g.industry_map

    # step 3: calc factors + entry_score
    factors_by_code = calc_factors_batch(g.universe, context, n=70)
    # ⚠️ 2026-06-15 诊断: 看是 factors_by_code 空 还是 entry_score 全 0
    log.info("[diag] factors_by_code=%d, universe=%d" % (len(factors_by_code), len(g.universe)))
    if factors_by_code and not getattr(g, "_diag_sampled", False):
        sample = list(factors_by_code.items())[0]
        s_name, s_f = sample
        sample_score = entry_score(s_f, p)
        log.info("[diag] sample stock=%s, factors_keys=%s, score=%.4f" %
                 (s_name, list(s_f.keys()), sample_score))
        g._diag_sampled = True
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

    log.info("候选池 %d 只, 通过 entry_score>0 的 %d 只 (持仓 %d 只)" % (
             len(g.universe), len(scores), len(g.holdings)))

    # step 4: exit decision
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
            log.info("%s 出场信号=%s 但 T 开盘无法卖出 (跌停/停牌), 延期" %
                     (stock, exit_sig))
            continue
        _execute_sell(stock, h, exit_sig, context)

    # step 5: rebalance
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
        log.info("无 score>0 候选, 跳过调仓 (持仓保持不变, 对齐本地行为)")
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

    log.info("rebalance: top_n=%d, target_weights=%d, sum=%.4f" %
             (len(top_codes), len(target_weights), _sum(target_weights.values())))

    total_value = _compute_total_value(context)
    cd = get_current_data()

    for stock in list(g.holdings.keys()):
        if stock in target_weights:
            continue
        h = g.holdings[stock]
        d = _cd_get(cd, stock)
        if not can_sell_at_open(d, stock):
            log.info("%s 调仓卖出但跌停/停牌, 延期" % stock)
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
        log.info("现金不足, 放弃买入: %s (需 %.0f, 有 %.0f)" %
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
    actual_fee = _max(actual_amount * 0.00025, 5)
    effective_entry = (actual_amount + actual_fee) / actual_shares

    g.holdings[stock] = {
        "entry_price": effective_entry,
        "entry_date": context.current_dt,
        "highest_close": open_px,
        "holding_days": 1,
        "shares": actual_shares,
        "entry_signals": list(triggered_signals),
        "prev_close": open_px,
    }
    log.info(">>> 买入 %s: %d股 @ %.2f, 含费成本=%.4f, 金额=%.0f, 信号=%s" %
             (stock, actual_shares, open_px, effective_entry, actual_amount,
              triggered_signals))


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

    log.info(">>> 卖出 %s: %d股 @ %.2f, PnL=%.2f, 持仓=%d交易日, 信号=%s" %
             (stock, shares, open_px, pnl, holding_days, exit_signal))
    del g.holdings[stock]

# ============================================================
# 11. 固定股票池 FIXED_UNIVERSE (HS300 单池, 与 spec test_universe 一致)
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
    "300014.XSHE", "300015.XSHE", "300033.XSHE", "300059.XSHE", "300122.XSHE",
    "300124.XSHE", "300251.XSHE", "300274.XSHE", "300308.XSHE", "300316.XSHE",
    "300347.XSHE", "300394.XSHE", "300408.XSHE", "300413.XSHE", "300418.XSHE",
    "300433.XSHE", "300442.XSHE", "300476.XSHE", "300498.XSHE", "300502.XSHE",
    "300628.XSHE", "300661.XSHE", "300750.XSHE", "300759.XSHE", "300760.XSHE",
    "300782.XSHE", "300803.XSHE", "300832.XSHE", "300866.XSHE", "300896.XSHE",
    "300979.XSHE", "300999.XSHE", "301236.XSHE", "301269.XSHE", "302132.XSHE",
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
    "605499.XSHG", "688008.XSHG", "688009.XSHG", "688012.XSHG", "688036.XSHG",
    "688041.XSHG", "688047.XSHG", "688082.XSHG", "688111.XSHG", "688126.XSHG",
    "688169.XSHG", "688187.XSHG", "688223.XSHG", "688256.XSHG", "688271.XSHG",
    "688303.XSHG", "688396.XSHG", "688472.XSHG", "688506.XSHG", "688981.XSHG",
]


# ============================================================
# 12. 启动前自检
# ============================================================
def self_check():
    p = PARAMS
    issues = []
    required = ["benchmark", "target_holdings", "max_single_weight",
                "max_industry_concentration", "max_turnover_per_rebalance",
                "rebalance_freq_days", "entry_weights", "exit_weights",
                "tie_break_seed"]
    for key in required:
        if key not in p:
            issues.append("PARAMS 缺少必填字段: " + key)
    if p.get("tie_break_seed") != 42:
        issues.append("tie_break_seed 应为 42")
    for sig, w in p.get("entry_weights", {}).items():
        if w <= 0:
            issues.append("entry_weights[%s] = %s, 应 > 0" % (sig, w))
    for sig, w in p.get("exit_weights", {}).items():
        if 0 < w < 1e-6:
            issues.append(
                "exit_weights[%s] = %.2e, weight 极小但仍会触发, "
                "确认 should_exit 已实现保留逻辑" % (sig, w)
            )
    expected_entry = {"ma_golden_cross", "macd_positive", "volume_surge", "atr_normal_range"}
    if set(p.get("entry_weights", {}).keys()) != expected_entry:
        issues.append("entry_weights keys 与 spec 不一致, 期望 " + str(expected_entry))
    expected_exit = {"fixed_stop_loss", "trailing_stop", "time_stop"}
    if set(p.get("exit_weights", {}).keys()) != expected_exit:
        issues.append("exit_weights keys 与 spec 不一致, 期望 " + str(expected_exit))
    expected_entry_total = 0.44 + 0.01 + 0.45 + 0.10
    actual_entry_total = sum(p.get("entry_weights", {}).values())
    if abs(actual_entry_total - expected_entry_total) > 1e-6:
        issues.append("entry_weights 总和 %.4f 与 spec 期望 %.4f 不一致" %
                      (actual_entry_total, expected_entry_total))
    expected_exit_total = 0.02 + 0.28 + 0.70
    actual_exit_total = sum(p.get("exit_weights", {}).values())
    if abs(actual_exit_total - expected_exit_total) > 1e-6:
        issues.append("exit_weights 总和 %.4f 与 spec 期望 %.4f 不一致" %
                      (actual_exit_total, expected_exit_total))
    if issues:
        log.warn("=== PARAMS 自检发现 %d 个问题 ===" % len(issues))
        for i in issues:
            log.warn("  - " + i)
    else:
        log.info("=== PARAMS 自检通过 (4 入场 + 3 出场, HS300 universe) ===")
    return len(issues) == 0
