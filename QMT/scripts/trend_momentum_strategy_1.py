# -*- coding: utf-8 -*-
"""
QMT 策略: trend_momentum_strategy_1
对应本地: subjects/trend_momentum_strategy_1/generated/strategy.py
策略 spec: result/trend_momentum_strategy_1/trend_momentum_strategy_1_final.md
翻译日期: 2026-06-17

=== 策略概述 ===
多指标共振趋势策略: 趋势排列 + 动量确认 + 波动过滤 + 量能验证 + RSI 区间优化。
8 条件 AND 共振入场, 5 个出场信号按 weight 降序优先级触发。
weight 仅决定优先级, 任何 w>0 的信号都会触发。

=== 入场信号 ===
- trend_momentum_entry (weight=1.0): ma_5>ma_20>ma_60 + MACD金叉 + RSI区间 + ATR过滤 + 量比

=== 出场信号 (按 weight 降序) ===
- rsi_overbought_stop (3.0) > trailing_stop (0.5) > time_stop (0.3)
  > trend_reversal (1e-8) > fixed_stop (1e-8)

=== 仓位约束 ===
单票40% -> 行业50% -> 换手50% -> fill_cash, 调仓周期5天, 目标7只
"""

# ============ 1. 导入 ============
import builtins
from typing import Optional
import numpy as np
import pandas as pd

try:
    from xtquant import xtdata
except ImportError:
    xtdata = None

_sum = builtins.sum
_max = builtins.max
_min = builtins.min

# QMT ContextInfo(C) 只读, 自定义状态存模块级 _S
_S = {
    "bar_index": 0,
    "stock_list": [],
    "positions": {},
    "rebalance_freq": 5,
    "target_holdings": 7,
    "period": "1d",
    "account_id": "testaccID",
}

# passorder 是 QMT 策略引擎内置函数
try:
    passorder
except NameError:
    def passorder(opType, orderType, accountId, stockCode, priceType,
                  price, volume, strategyContext, **kwargs):
        print("[MOCK] passorder: %s %s vol=%s" % (
            "BUY" if opType == 23 else "SELL", stockCode, volume))
        return None

# 本地 HS300 测试集 (296 只, 与本地回测系统完全一致)
HS300 = [
    "000001.SZ","000002.SZ","000063.SZ","000100.SZ","000157.SZ","000166.SZ","000301.SZ","000333.SZ",
    "000338.SZ","000408.SZ","000425.SZ","000538.SZ","000568.SZ","000596.SZ","000617.SZ","000625.SZ",
    "000630.SZ","000651.SZ","000708.SZ","000725.SZ","000768.SZ","000776.SZ","000786.SZ","000807.SZ",
    "000858.SZ","000876.SZ","000895.SZ","000938.SZ","000963.SZ","000975.SZ","000977.SZ","000983.SZ",
    "000999.SZ","001391.SZ","001965.SZ","001979.SZ","002001.SZ","002027.SZ","002028.SZ","002049.SZ",
    "002050.SZ","002074.SZ","002142.SZ","002179.SZ","002230.SZ","002236.SZ","002241.SZ","002252.SZ",
    "002304.SZ","002311.SZ","002352.SZ","002371.SZ","002384.SZ","002415.SZ","002422.SZ","002459.SZ",
    "002460.SZ","002463.SZ","002466.SZ","002475.SZ","002493.SZ","002600.SZ","002601.SZ","002625.SZ",
    "002648.SZ","002709.SZ","002714.SZ","002736.SZ","002916.SZ","002920.SZ","002938.SZ","003816.SZ",
    "300014.SZ","300015.SZ","300033.SZ","300059.SZ","300122.SZ","300124.SZ","300251.SZ","300274.SZ",
    "300308.SZ","300316.SZ","300347.SZ","300394.SZ","300408.SZ","300413.SZ","300418.SZ","300433.SZ",
    "300442.SZ","300476.SZ","300498.SZ","300502.SZ","300661.SZ","300750.SZ","300759.SZ","300760.SZ",
    "300782.SZ","300803.SZ","300832.SZ","300866.SZ","300896.SZ","300979.SZ","300999.SZ","301236.SZ",
    "301269.SZ","302132.SZ",
    "600000.SH","600009.SH","600010.SH","600011.SH","600015.SH","600016.SH","600018.SH","600019.SH",
    "600023.SH","600025.SH","600026.SH","600027.SH","600028.SH","600029.SH","600030.SH","600031.SH",
    "600036.SH","600039.SH","600048.SH","600050.SH","600061.SH","600066.SH","600085.SH","600089.SH",
    "600104.SH","600111.SH","600115.SH","600150.SH","600160.SH","600161.SH","600176.SH","600183.SH",
    "600188.SH","600196.SH","600219.SH","600233.SH","600276.SH","600309.SH","600346.SH","600362.SH",
    "600372.SH","600377.SH","600406.SH","600415.SH","600426.SH","600436.SH","600438.SH","600460.SH",
    "600482.SH","600489.SH","600515.SH","600519.SH","600522.SH","600547.SH","600570.SH","600584.SH",
    "600585.SH","600588.SH","600600.SH","600660.SH","600674.SH","600690.SH","600741.SH","600760.SH",
    "600795.SH","600803.SH","600809.SH","600845.SH","600875.SH","600886.SH","600887.SH","600893.SH",
    "600900.SH","600905.SH","600918.SH","600919.SH","600926.SH","600930.SH","600938.SH","600941.SH",
    "600958.SH","600989.SH","600999.SH","601006.SH","601009.SH","601012.SH","601018.SH","601021.SH",
    "601058.SH","601059.SH","601066.SH","601077.SH","601088.SH","601100.SH","601111.SH","601117.SH",
    "601127.SH","601136.SH","601138.SH","601166.SH","601169.SH","601186.SH","601211.SH","601225.SH",
    "601229.SH","601236.SH","601238.SH","601288.SH","601298.SH","601318.SH","601319.SH","601328.SH",
    "601336.SH","601360.SH","601377.SH","601390.SH","601398.SH","601456.SH","601600.SH","601601.SH",
    "601607.SH","601618.SH","601628.SH","601633.SH","601658.SH","601668.SH","601669.SH","601688.SH",
    "601689.SH","601698.SH","601728.SH","601766.SH","601788.SH","601800.SH","601808.SH","601816.SH",
    "601818.SH","601825.SH","601838.SH","601857.SH","601868.SH","601872.SH","601877.SH","601878.SH",
    "601881.SH","601888.SH","601898.SH","601899.SH","601901.SH","601916.SH","601919.SH","601939.SH",
    "601985.SH","601988.SH","601995.SH","601998.SH","603019.SH","603195.SH","603259.SH","603260.SH",
    "603288.SH","603296.SH","603369.SH","603392.SH","603501.SH","603799.SH","603893.SH","603986.SH",
    "603993.SH","605117.SH","605499.SH","688008.SH","688009.SH","688012.SH","688036.SH","688041.SH",
    "688047.SH","688082.SH","688111.SH","688126.SH","688169.SH","688187.SH","688223.SH","688256.SH",
    "688271.SH","688303.SH","688396.SH","688472.SH","688506.SH","688981.SH",
]

# ============ 2. 策略参数 ============
PARAMS = {
    "ma_short": 5, "ma_mid": 20, "ma_long": 60,
    "rsi_low": 30, "rsi_high": 80, "atr_min": 0.015, "vol_min": 1.0,
    "rsi_overbought": 84, "trailing_stop_pct": 0.15,
    "fixed_stop_pct": 0.13, "max_holding_days": 75,
    "target_holdings": 7, "max_single_stock_weight": 0.4,
    "max_industry_concentration": 0.5,
    "max_turnover_per_rebalance": 0.5, "rebalance_freq_days": 5,
    "entry_weights": {"trend_momentum_entry": 1.0},
    "exit_weights": {
        "rsi_overbought_stop": 3.0, "trailing_stop": 0.5,
        "time_stop": 0.3, "trend_reversal": 1.0e-08, "fixed_stop": 1.0e-08,
    },
    "tie_break_seed": 42,
}

# ============ 3. 因子辅助函数 ============
def _ema(series, span):
    return series.ewm(span=span, adjust=False).mean()

def _ma(series, period):
    return series.rolling(window=period, min_periods=period).mean()

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
    return 100.0 - 100.0 / (1.0 + rs)

def _volume_ratio(volume, period=20):
    return volume / volume.rolling(window=period, min_periods=period).mean()

# ============ 4. 因子计算 ============
def calc_factors(hist_data, params):
    if hist_data.empty or len(hist_data) < 60:
        return None
    close = hist_data["close"]
    high = hist_data["high"]
    low = hist_data["low"]
    volume = hist_data["volume"]
    ema_12 = _ema(close, 12)
    ema_26 = _ema(close, 26)
    macd_line = ema_12 - ema_26
    macd_signal = _ema(macd_line, 9)
    return {
        "close": close, "high": high, "low": low, "volume": volume,
        "ma_5": _ma(close, 5), "ma_20": _ma(close, 20), "ma_60": _ma(close, 60),
        "macd_line": macd_line, "macd_signal": macd_signal,
        "atr_14": _atr(high, low, close, 14),
        "rsi_14": _rsi(close, 14),
        "volume_ratio_20": _volume_ratio(volume, 20),
    }

def get_factor_val(factors, name):
    val = factors.get(name)
    if val is None:
        return None
    if isinstance(val, pd.Series):
        if len(val) == 0:
            return None
        v = val.iloc[-1]
        return None if pd.isna(v) else float(v)
    return None if pd.isna(val) else float(val)

# ============ 5. 入场信号 ============
def calc_entry_score(factors, params, entry_weights):
    score = 0.0
    vals = {}
    for name in ["ma_5", "ma_20", "ma_60", "macd_line", "macd_signal",
                 "rsi_14", "atr_14", "close", "volume_ratio_20"]:
        vals[name] = get_factor_val(factors, name)
        if vals[name] is None:
            return 0.0

    if (vals["ma_5"] > vals["ma_20"]
            and vals["ma_20"] > vals["ma_60"]
            and vals["macd_line"] > vals["macd_signal"]
            and vals["rsi_14"] > params["rsi_low"]
            and vals["rsi_14"] < params["rsi_high"]
            and (vals["atr_14"] / vals["close"]) > params["atr_min"]
            and vals["volume_ratio_20"] > params["vol_min"]):
        score += entry_weights.get("trend_momentum_entry", 0)
    return score

# ============ 6. 出场信号 ============
def check_exit(position, factors, params, exit_weights):
    cp = position.get("current_price", 0)
    ep = position.get("entry_price", 0)
    hi = position.get("highest", 0)
    hd = position.get("holding_days", 0)

    for sig in sorted(exit_weights, key=exit_weights.get, reverse=True):
        w = exit_weights.get(sig, 0)
        if w <= 0:
            continue

        if sig == "rsi_overbought_stop":
            rsi = get_factor_val(factors, "rsi_14")
            if rsi is not None and rsi > params["rsi_overbought"]:
                return "rsi_overbought_stop"
        elif sig == "trailing_stop":
            if hi > 0 and cp < hi * (1 - params["trailing_stop_pct"]):
                return "trailing_stop"
        elif sig == "time_stop":
            if hd >= params["max_holding_days"]:
                return "time_stop"
        elif sig == "trend_reversal":
            m5 = get_factor_val(factors, "ma_5")
            m20 = get_factor_val(factors, "ma_20")
            if m5 is not None and m20 is not None and m5 < m20:
                return "trend_reversal"
        elif sig == "fixed_stop":
            if ep > 0 and cp < ep * (1 - params["fixed_stop_pct"]):
                return "fixed_stop"
    return None

# ============ 7. 选股与仓位约束 ============
def rank_top_n(scores, top_n, seed=42):
    positives = [(k, v) for k, v in scores.items() if v > 0]
    if not positives:
        return []
    positives.sort(key=lambda x: (-x[1], x[0]))
    top = positives[:top_n]
    result = [k for k, _ in top]
    if seed is not None and len(result) > 1:
        all_scores = set(v for _, v in top)
        if len(all_scores) == 1:
            import random
            rng = random.Random(seed)
            rng.shuffle(result)
    return result

def enforce_max_single_weight(weights, max_w):
    if max_w <= 0 or max_w >= 1:
        return weights
    out, excess = {}, 0.0
    for code, w in weights.items():
        if w > max_w:
            excess += w - max_w
            out[code] = max_w
        else:
            out[code] = w
    if excess > 1e-6:
        others = {k: v for k, v in out.items() if v < max_w - 1e-6}
        ot = _sum(others.values())
        if ot > 1e-6:
            for k in others:
                out[k] *= (ot + excess) / ot
        else:
            for k in out:
                out[k] = max_w
    s = _sum(out.values())
    if s > 1.0 + 1e-6:
        out = {k: v / s for k, v in out.items()}
    return out

def get_industry_map(codes, bar_date=""):
    if xtdata is None:
        return {}
    m = {}
    for code in codes:
        try:
            d = xtdata.get_instrument_detail(code)
            if d:
                m[code] = d.get("Industry", "u")
        except Exception:
            m[code] = "u"
    return m

def enforce_industry_concentration(weights, industry_map, max_pct):
    if max_pct <= 0 or max_pct >= 1 or not industry_map:
        return weights
    it = {}
    for code, w in weights.items():
        ind = industry_map.get(code, "u")
        it[ind] = it.get(ind, 0.0) + w
    scale = {ind: (max_pct / t if t > max_pct else 1.0) for ind, t in it.items()}
    out, any_scaled = {}, False
    for code, w in weights.items():
        ind = industry_map.get(code, "u")
        out[code] = w * scale[ind]
        if scale[ind] < 1.0 - 1e-6:
            any_scaled = True
    if any_scaled:
        s = _sum(out.values())
        if s > 1.0 + 1e-6:
            out = {k: v / s for k, v in out.items()}
    return out

def enforce_max_turnover(current_weights, target_weights, max_turnover):
    if max_turnover <= 0 or max_turnover >= 1:
        return target_weights
    all_c = set(target_weights) | set(current_weights)
    turnover = _sum(abs(target_weights.get(c, 0) - current_weights.get(c, 0))
                    for c in all_c) / 2.0
    if turnover <= max_turnover:
        return target_weights
    scale = max_turnover / turnover if turnover > 1e-6 else 1.0
    out = {}
    for c in all_c:
        cur = current_weights.get(c, 0.0)
        tgt = target_weights.get(c, 0.0)
        out[c] = cur + (tgt - cur) * scale
    s = _sum(out.values())
    if s > 1.0 + 1e-6:
        out = {k: v / s for k, v in out.items()}
    return out

def fill_cash_with_remaining_candidates(
    target_weights, scores, target_n, max_single,
    industry_map=None, max_industry=1.0, cash_threshold=0.01, max_n_multiplier=2.0,
):
    if not scores or not target_weights:
        return target_weights
    leftover = 1.0 - _sum(target_weights.values())
    if leftover < cash_threshold:
        return target_weights
    in_target = set(target_weights.keys())
    candidates = sorted(
        [(c, s) for c, s in scores.items() if c not in in_target and s > 0],
        key=lambda x: x[1], reverse=True)
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
            ind = industry_map.get(code, "u")
            cit = _sum(w for c, w in out.items() if industry_map.get(c, "u") == ind)
            ir = max_industry - cit
            if ir <= 0:
                continue
            if new_w > ir:
                new_w = ir
        if new_w < cash_threshold:
            continue
        out[code] = new_w
    return out

def compute_current_weights(positions_state, total_value):
    w = {}
    for code, pos in positions_state.items():
        if pos.get("shares", 0) > 0 and pos.get("current_price", 0) > 0:
            w[code] = pos["shares"] * pos["current_price"] / total_value if total_value > 0 else 0
    return w

# ============ 8. 数据获取 ============
def _fields_to_df(fields_dict):
    if fields_dict is None:
        return None
    if isinstance(fields_dict, pd.DataFrame):
        return None if fields_dict.empty else fields_dict
    if isinstance(fields_dict, dict):
        if len(fields_dict) == 0:
            return None
        dfs = []
        for field, df in fields_dict.items():
            if isinstance(df, pd.DataFrame):
                s = df.iloc[:, 0] if df.shape[1] == 1 else df.squeeze()
                s.name = str(field).lower()
                dfs.append(s)
            elif isinstance(df, pd.Series):
                s = df.copy()
                s.name = str(field).lower()
                dfs.append(s)
        if len(dfs) == 0:
            return None
        result = pd.concat(dfs, axis=1)
        return None if result.empty else result
    return None

def _bar_date_str(C):
    try:
        ts = C.get_bar_timetag(C.barpos)
        return timetag_to_datetime(ts, '%Y%m%d%H%M%S')
    except Exception:
        return "20230101000000"

def _bar_date_str_at(C, barpos):
    try:
        ts = C.get_bar_timetag(barpos)
        return timetag_to_datetime(ts, '%Y%m%d%H%M%S')
    except Exception:
        return ""

def get_history_data(C, code, period="1d", lookback=100):
    """优先用 xtdata 本地数据 (快), 回退 C.get_market_data_ex (慢)"""
    fields = ["open", "high", "low", "close", "volume", "amount"]
    # 方案 1: xtdata.get_local_data (本地缓存直读, 最快)
    if xtdata is not None:
        try:
            data = xtdata.get_local_data(
                field_list=fields, stock_list=[code], period=period,
                start_time="", end_time="", count=lookback)
            if isinstance(data, dict) and code in data:
                df = _fields_to_df(data[code])
                if df is not None and not df.empty:
                    df.columns = [str(c).lower() for c in df.columns]
                    return df
        except Exception:
            pass
        try:
            data = xtdata.get_market_data_ex(
                field_list=fields, stock_list=[code], period=period,
                start_time="", end_time="", count=lookback)
            if isinstance(data, dict) and code in data:
                df = _fields_to_df(data[code])
                if df is not None and not df.empty:
                    df.columns = [str(c).lower() for c in df.columns]
                    return df
        except Exception:
            pass
    # 方案 2: C.get_market_data_ex (必须 subscribe=False)
    if C is not None and hasattr(C, 'get_market_data_ex'):
        try:
            bar_dt = _bar_date_str(C)
            data = C.get_market_data_ex(
                fields, [code], period=period, end_time=bar_dt, count=lookback,
                subscribe=False)
            if isinstance(data, dict) and code in data:
                df = _fields_to_df(data[code])
                if df is not None and not df.empty:
                    df.columns = [str(c).lower() for c in df.columns]
                    return df
        except Exception:
            pass
    return None

def get_history_data_batch(C, codes, period="1d", lookback=100):
    """批量获取"""
    result = {}
    total = len(codes)
    for i, code in enumerate(codes):
        if i % 100 == 0 and i > 0:
            print("[DATA] %s/%s stocks..." % (i, total))
        df = get_history_data(C, code, period, lookback)
        if df is not None and not df.empty:
            result[code] = df
    return result

def get_current_tick_price(code, C=None):
    if xtdata is not None:
        try:
            tick = xtdata.get_full_tick([code])
            if code in tick and tick[code]:
                lp = tick[code].get("lastPrice", 0)
                if lp and lp > 0:
                    return float(lp)
        except Exception:
            pass
    hist = get_history_data(C, code, "1d", lookback=1)
    if hist is not None and not hist.empty:
        return float(hist["close"].iloc[-1])
    return 0.0

# ============ 9. A 股规则 ============
def is_bj_stock(code):
    bare = code.split(".")[0] if "." in code else code
    return bare.startswith(("4", "8", "92"))

def can_buy_at_open(code, open_price, prev_close):
    if prev_close <= 0 or open_price <= 0:
        return False
    if code.startswith("688") or code.startswith("30"):
        lpct = 0.20
    elif code.startswith(("4", "8", "92")):
        lpct = 0.30
    else:
        lpct = 0.10
    return not (open_price > prev_close * (1 + lpct) - 0.01)

def can_sell_at_open(code, open_price, prev_close):
    if prev_close <= 0 or open_price <= 0:
        return False
    if code.startswith("688") or code.startswith("30"):
        lpct = 0.20
    elif code.startswith(("4", "8", "92")):
        lpct = 0.30
    else:
        lpct = 0.10
    return not (open_price < prev_close * (1 - lpct) + 0.01)

# ============ 10. 持仓状态 ============
def update_positions_state(positions_state, C=None):
    for code, pos in list(positions_state.items()):
        hist = get_history_data(C, code, "1d", lookback=2)
        if hist is None or len(hist) < 1:
            continue
        t1_close = float(hist["close"].iloc[-1])
        pos["prev_close"] = pos.get("current_price", t1_close)
        pos["current_price"] = t1_close
        if t1_close > pos.get("highest", 0):
            pos["highest"] = t1_close
        pos["holding_days"] += 1

# ============ 11. 交易执行 ============
def check_and_execute_exits(C, bar_date):
    for code, pos in list(_S["positions"].items()):
        if pos.get("holding_days", 0) < 1:
            continue
        hist = get_history_data(C, code, "1d", lookback=100)
        if hist is None:
            continue
        factors = calc_factors(hist, PARAMS)
        if factors is None:
            continue
        open_price = get_current_tick_price(code, C)
        if open_price <= 0:
            continue
        if not can_sell_at_open(code, open_price, pos.get("current_price", 0)):
            continue
        exit_sig = check_exit(pos, factors, PARAMS, PARAMS.get("exit_weights", {}))
        if exit_sig is not None:
            shares = pos.get("shares", 0)
            if shares > 0:
                lp = _min(_max(open_price * 0.995, 0.01), 9999.99)
                if code.startswith("688"):
                    passorder(24, 1101, _S["account_id"], code, 5, lp, -shares, C)
                else:
                    passorder(24, 1101, _S["account_id"], code, 5, -1, -shares, C)
                print("[EXIT] %s %s %s: %s股 hd=%s" % (
                    bar_date, code, exit_sig, shares, pos.get("holding_days", 0)))
                del _S["positions"][code]

def execute_rebalance(C, target_weights, scores, bar_date):
    try:
        total_value = C.portfolio.total_value if hasattr(C, 'portfolio') else 1000000
    except Exception:
        total_value = 1000000
    cur_codes = set(_S["positions"].keys())
    tgt_codes = set(target_weights.keys())

    for code in list(cur_codes - tgt_codes):
        pos = _S["positions"][code]
        shares = pos.get("shares", 0)
        if shares <= 0:
            del _S["positions"][code]
            continue
        op = get_current_tick_price(code, C)
        if op <= 0:
            continue
        if not can_sell_at_open(code, op, pos.get("current_price", 0)):
            continue
        lp = _min(_max(op * 0.995, 0.01), 9999.99)
        if code.startswith("688"):
            passorder(24, 1101, _S["account_id"], code, 5, lp, -shares, C)
        else:
            passorder(24, 1101, _S["account_id"], code, 5, -1, -shares, C)
        print("[SELL] %s %s: %s股" % (bar_date, code, shares))
        del _S["positions"][code]

    pos_val = sum(p.get("shares", 0) * p.get("current_price", 0)
                  for p in _S["positions"].values())
    avail = max(total_value - pos_val, 0)
    new_codes = [c for c in tgt_codes - cur_codes]
    tw_new = sum(target_weights.get(c, 0) for c in new_codes) if new_codes else 1.0
    if tw_new < 0.01:
        tw_new = 1.0

    for code in new_codes:
        op = get_current_tick_price(code, C)
        if op <= 0:
            continue
        h2 = get_history_data(C, code, "1d", lookback=2)
        prv = float(h2["close"].iloc[-1]) if h2 is not None and len(h2) >= 1 else op
        if not can_buy_at_open(code, op, prv):
            continue
        target_val = avail * (target_weights.get(code, 0) / tw_new)
        bs = int(target_val / op)
        lot = 200 if code.startswith("688") else 100
        bs = (bs // lot) * lot
        if bs < lot:
            continue
        if code.startswith("688"):
            passorder(23, 1101, _S["account_id"], code, 5, _min(op * 1.005, 9999.99), bs, C)
        else:
            passorder(23, 1101, _S["account_id"], code, 5, -1, bs, C)
        fee = _max(op * bs * 0.00025, 5)
        ep_eff = (op * bs + fee) / bs
        _S["positions"][code] = {
            "shares": bs, "entry_price": ep_eff, "entry_date": bar_date,
            "highest": op, "holding_days": 1, "current_price": op,
            "prev_close": prv, "weight": target_weights[code],
        }
        print("[BUY] %s %s: %s股 @~%.2f cost=%.4f" % (bar_date, code, bs, op, ep_eff))

def do_rebalance(C, bar_date):
    scores, n_data, n_fac = {}, 0, 0
    all_hist = get_history_data_batch(C, _S["stock_list"], "1d", lookback=100)
    if not all_hist:
        for code in _S["stock_list"]:
            h = get_history_data(C, code, "1d", lookback=100)
            if h is not None:
                all_hist[code] = h
    total_stocks = len(_S["stock_list"])
    for i, code in enumerate(_S["stock_list"]):
        if i % 50 == 0 and i > 0:
            print("[REBALANCE] %s: processing %s/%s stocks..." % (bar_date, i, total_stocks))
        hist = all_hist.get(code)
        if hist is None:
            continue
        n_data += 1
        factors = calc_factors(hist, PARAMS)
        if factors is None:
            continue
        n_fac += 1
        score = calc_entry_score(factors, PARAMS, PARAMS.get("entry_weights", {}))
        if score > 0:
            scores[code] = score

    print("[REBALANCE] %s: bar=%s u=%s data=%s fac=%s s>0=%s pos=%s" % (
        bar_date, _S["bar_index"], len(_S["stock_list"]),
        n_data, n_fac, len(scores), len(_S["positions"])))

    if n_data == 0:
        print("[REBALANCE] WARN: no data")

    tn = PARAMS.get("target_holdings", 7)
    top = rank_top_n(scores, tn, seed=PARAMS.get("tie_break_seed", 42))
    if not top:
        print("[REBALANCE] %s: no candidates (pos=%s)" % (bar_date, len(_S["positions"])))
        return

    tw = {c: 1.0 / len(top) for c in top}
    tw = enforce_max_single_weight(tw, PARAMS.get("max_single_stock_weight", 0.4))
    im = get_industry_map(_S["stock_list"], bar_date)
    tw = enforce_industry_concentration(tw, im, PARAMS.get("max_industry_concentration", 0.5))
    try:
        tv = C.portfolio.total_value if hasattr(C, 'portfolio') else 1000000
    except Exception:
        tv = 1000000
    cw = compute_current_weights(_S["positions"], tv)
    tw = enforce_max_turnover(cw, tw, PARAMS.get("max_turnover_per_rebalance", 0.5))
    tw = fill_cash_with_remaining_candidates(
        tw, scores, tn, PARAMS.get("max_single_stock_weight", 0.4),
        industry_map=im, max_industry=PARAMS.get("max_industry_concentration", 0.5))
    execute_rebalance(C, tw, scores, bar_date)
    print("[REBALANCE] %s: done target=%s tw=%.1f%% pos=%s" % (
        bar_date, len(tw), _sum(tw.values()) * 100, len(_S["positions"])))

# ============ 12. 参数自检 ============
def self_check():
    p = PARAMS
    issues = []
    for key in ["target_holdings", "max_single_stock_weight",
                "max_industry_concentration", "max_turnover_per_rebalance",
                "rebalance_freq_days", "entry_weights", "exit_weights", "tie_break_seed"]:
        if key not in p:
            issues.append("PARAMS missing: %s" % key)
    if p.get("tie_break_seed") != 42:
        issues.append("tie_break_seed should be 42")
    for sig, w in p.get("entry_weights", {}).items():
        if w <= 0:
            issues.append("entry_weights[%s]=%s should >0" % (sig, w))
    for sig, w in p.get("exit_weights", {}).items():
        if w <= 0:
            issues.append("exit_weights[%s]=%s (disabled)" % (sig, w))
        elif w < 1e-6:
            print("[SELF_CHECK] note: exit_weights[%s]=%.1e triggers at lowest priority" % (sig, w))
    if issues:
        print("[SELF_CHECK] %s issues:" % len(issues))
        for i in issues:
            print("  - %s" % i)
        return False
    print("[SELF_CHECK] PARAMS OK")
    return True

# ============ 13. QMT 生命周期 ============
def init(C):
    print("[init] ====== init() called ======")

    # 回测日期 — 必须最先设置 (否则可能不生效)
    C.start = '2023-01-01 00:00:00'
    C.end = '2026-05-01 00:00:00'

    self_check()

    _S["bar_index"] = 0
    _S["rebalance_freq"] = PARAMS.get("rebalance_freq_days", 5)
    _S["target_holdings"] = PARAMS.get("target_holdings", 7)
    _S["positions"] = {}
    _S["period"] = "1d"
    try:
        C.set_account("testaccID")
    except Exception:
        pass

    _S["stock_list"] = HS300
    C.set_universe(_S["stock_list"])

    # 找到 2023/01/01 对应的 barpos (避免 handlebar 每 bar 调慢速 API)
    _S["start_barpos"] = 0
    for _test_bp in range(C.barpos, min(C.barpos + 3000, C.time_tick_size or 3000)):
        _dt = _bar_date_str_at(C, _test_bp)
        if _dt and _dt[:8] >= "20230101":
            _S["start_barpos"] = _test_bp
            print("[init] start_barpos=%s (date=%s)" % (_test_bp, _dt[:8]))
            break

    # 只在首次运行时预下载数据 (已有缓存则跳过)
    if xtdata is not None:
        _c0 = _S["stock_list"][0]
        _test = xtdata.get_local_data(["close"], [_c0], "1d", "", "", count=1)
        _has = False
        if isinstance(_test, dict) and _c0 in _test and _test[_c0] is not None:
            _v = _test[_c0]
            _has = not (hasattr(_v, 'empty') and _v.empty)
        if _has:
            print("[init] xtdata cache OK, skip download")
        else:
            print("[init] pre-downloading xtdata cache for %s stocks..." % len(_S["stock_list"]))
            for i, code in enumerate(_S["stock_list"]):
                if i % 50 == 0:
                    print("[init] download %s/%s..." % (i, len(_S["stock_list"])))
                try:
                    xtdata.download_history_data(code, "1d", "20230101", "")
                except Exception:
                    pass
            print("[init] download done")

    print("[init] === QMT init complete: %s stocks, period=%s, rebalance=%sd, target=%s ===" % (
        len(_S["stock_list"]), str(C.period), _S["rebalance_freq"], _S["target_holdings"]))

def handlebar(C):
    # 跳过 2023 年之前的 bar (直接用 barpos 数值, 不调慢速 API)
    # barpos=1595 约对应 2023/01/01 (基于主图数据从 2018 年开始)
    if C.barpos < 1595:
        if C.barpos % 500 == 0:
            print("[pre-2023] barpos=%s skipping..." % C.barpos)
        return

    # 用 QMT 标准 API 获取真正的 bar 日期
    bar_date = _bar_date_str(C)
    if len(bar_date) >= 8:
        bar_date = bar_date[:8]

    _S["bar_index"] += 1

    if _S["bar_index"] == 1:
        print("[handlebar] barpos=%s period=%s: day 1 start" % (C.barpos, str(C.period)))
        return

    if _S["bar_index"] <= 5:
        print("[handlebar] %s bar=%s" % (bar_date, _S["bar_index"]))

    update_positions_state(_S["positions"], C)
    check_and_execute_exits(C, bar_date)

    if _S["bar_index"] % _S["rebalance_freq"] != 0:
        if _S["bar_index"] % 20 == 0:
            print("[handlebar] %s: bar=%s pos=%s" % (
                bar_date, _S["bar_index"], len(_S["positions"])))
        return

    do_rebalance(C, bar_date)
