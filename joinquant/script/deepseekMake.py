# -*- coding: utf-8 -*-
"""
双均线斜率过滤 + 布林带震荡收割策略
==========================================
策略文档: 用户手写 (震荡下跌的A股市场)
回测平台: JoinQuant (聚宽)

适用场景: 震荡下跌的A股市场
资金体量: 30万, 半仓操作
只做多: 沪深300ETF(510300) 或 创业板ETF(159915)
"""

from jqdata import *
import numpy as np
import pandas as pd


# ============================================================
# 1. 参数配置区
# ============================================================
PARAMS = {
    # ---- 标的与基准 ----
    "etf_code": "510300.XSHG",        # 沪深300ETF (默认) / 159915.XSHE 创业板ETF
    "benchmark": "000300.XSHG",       # 基准: 沪深300指数

    # ---- 趋势过滤指数 (测试集: 中证2000 + 创业板 + 科创板) ----
    # 用这些指数的合成趋势判断市场整体方向
    "trend_indices": [
        "932000.XSHG",  # 中证2000 (小盘股)
        "399006.XSHE",  # 创业板指
        "000688.XSHG",  # 科创50
    ],
    "trend_long_only": True,         # 仅做多, 趋势过滤看均线方向
    "trend_buy_threshold": 0.5,      # 至少50%的指数EMA走平/上升才允许开仓
    "trend_sell_threshold": 0.0,     # 任何指数EMA向下即触发清仓 (严格)

    "total_capital": 300000,         # 总资金 30万
    "position_ratio": 0.5,           # 半仓比例
    "min_commission": 5,             # 最低佣金
    "use_real_price": True,           # 真实价格模式
    "ema_period": 20,                 # 20日EMA
    "ema_slope_lookback": 5,         # EMA斜率回溯天数
    "boll_period": 20,                # 布林带周期
    "boll_std": 2,                    # 布林带标准差倍数
    "rsi_period": 6,                  # 6日RSI
    "rsi_buy_threshold": 30,         # 买入RSI阈值
    "rsi_sell_threshold": 75,         # 卖出RSI阈值
    "profit_target": 0.05,            # 止盈 +5%
    "stop_loss_pct": 0.04,            # 止损 -4%
    "boll_buy_tolerance": 1.005,      # 收盘价 <= 下轨 * 1.005 视为触及下轨
    "boll_sell_tolerance": 0.995,     # 收盘价 >= 上轨 * 0.995 视为触及上轨
    "rebalance_time": "14:50",        # 信号观察时间
    "execute_time": "09:30",          # 实际成交时间 (开盘)
}


def initialize(context):
    """
    策略初始化
    """
    set_benchmark(PARAMS["benchmark"])
    set_option("use_real_price", PARAMS["use_real_price"])
    
    # 手续费/印花税 (ETF没有印花税, 佣金万三)
    set_order_cost(OrderCost(
        open_tax=0,                    # 买入无印花税
        close_tax=0,                  # ETF卖出无印花税
        open_commission=0.0003,        # 买入佣金万三
        close_commission=0.0003,       # 卖出佣金万三
        close_today_commission=0,     # 平今 (ETF不适用)
        min_commission=PARAMS["min_commission"]
    ), type="fund")  # ETF是场内基金
    
    set_slippage(FixedSlippage(0.001))  # 0.1%滑点
    log.set_level("order", "error")
    
    # 全局状态
    g.etf_code = PARAMS["etf_code"]
    g.benchmark = PARAMS["benchmark"]
    g.total_capital = PARAMS["total_capital"]
    g.position_ratio = PARAMS["position_ratio"]
    g.params = PARAMS
    
    # 持仓状态
    g.holding_shares = 0          # 当前持仓股数
    g.entry_price = 0             # 入场成本价
    g.entry_date = None           # 入场日期
    g.lowest_close_after_entry = None  # 入场后最低收盘价 (用于动态跟踪止损)
    g.signal_pending = None       # 待执行信号: "buy" / "sell" / None
    g.last_trade_date = None
    
    # 日程调度
    # 14:50 收盘后: 计算所有信号, 设置 g.signal_pending
    run_daily(generate_signal, time=PARAMS["rebalance_time"])
    # 次日 09:30: 执行昨日生成的信号
    run_daily(execute_pending, time=PARAMS["execute_time"])

    log.info("=== 双均线斜率过滤 + 布林带震荡收割 策略初始化完成 ===")
    log.info("标的: %s | 总资金: %d | 半仓: %d" % (g.etf_code, g.total_capital, int(g.total_capital * g.position_ratio)))

def generate_signal(context):
    """
    14:50 收盘后: 计算所有信号
    - 趋势过滤: 下跌趋势则清仓
    - 买入信号: 触及布林下轨 + RSI < 30
    - 卖出信号: 触及布林上轨 / RSI > 75 / 盈利 +5%
    - 止损检查
    """
    log.info("=" * 50)
    log.info("[%s] 14:50 信号生成" % context.current_dt.strftime("%Y-%m-%d"))
    
    # 1. 计算沪深300指数的20日EMA及斜率
    trend_status = check_trend(context)
    log.info("趋势状态: %s" % trend_status)
    
    # 2. 趋势过滤: 如果是下跌趋势, 必须清仓
    if trend_status == "down":
        if g.holding_shares > 0:
            log.warn("下跌趋势: 触发趋势止损, 准备清仓!")
            g.signal_pending = "sell_trend"
        else:
            log.info("下跌趋势: 空仓观望, 不开新仓")
            g.signal_pending = None
        return
    
    # 3. 震荡/上涨趋势: 检查持仓止损条件 (优先)
    if g.holding_shares > 0:
        # 3.1 止损检查
        stop_reason = check_stop_loss(context)
        if stop_reason:
            log.warn("触发止损: 原因=%s, 准备清仓" % stop_reason)
            g.signal_pending = "sell_stop"
            return

        # 3.2 卖出信号检查
        sell_reason = compute_sell_signal(context)
        if sell_reason:
            log.info("触发卖出: 原因=%s, 准备清仓" % sell_reason)
            g.signal_pending = "sell"
            return

        # 3.3 已持仓, 不再加仓, 不触发买入
        log.info("震荡/上涨趋势, 已持仓, 等待卖出信号")
        g.signal_pending = None
        return

    # 4. 空仓 + 震荡/上涨趋势: 检查买入信号
    buy_signal = compute_buy_signal(context)
    if buy_signal:
        log.info("触发买入信号: 准备半仓买入")
        g.signal_pending = "buy"
    else:
        log.info("无买入信号, 继续空仓")
        g.signal_pending = None


def execute_pending(context):
    """
    09:30 开盘: 执行昨日 14:50 生成的信号
    """
    if g.signal_pending is None:
        return
    
    log.info("=" * 50)
    log.info("[%s] 执行信号: %s" % (context.current_dt.strftime("%Y-%m-%d"), g.signal_pending))
    
    if g.signal_pending == "buy":
        do_buy(context)
    elif g.signal_pending in ["sell", "sell_stop", "sell_trend"]:
        do_sell(context, reason=g.signal_pending)
    
    g.signal_pending = None
    g.last_trade_date = context.current_dt

# ============================================================
# 2. 核心信号计算
# ============================================================

def check_trend(context):
    """
    趋势过滤: 计算多个指数的20日EMA斜率
    测试集: 中证2000 + 创业板 + 科创板

    规则:
    - 如果任何指数的EMA向下 (下跌趋势), 立即清仓 (严格)
    - 至少 50% 的指数EMA走平/向上, 才允许开仓
    - 返回: "down" (下跌, 必须清仓) / "sideways" (震荡/上升, 允许开仓)
    """
    p = g.params
    n = p["ema_period"] + p["ema_slope_lookback"] + 10

    up_count = 0
    down_count = 0
    details = []

    for index_code in p["trend_indices"]:
        try:
            df = attribute_history(index_code, n, "1d", ["close"],
                                  skip_paused=True, df=True, fq="pre")
            if df is None or len(df) < p["ema_period"] + p["ema_slope_lookback"]:
                log.warn("指数 %s 数据不足, 视为下跌" % index_code)
                down_count += 1
                details.append("%s: 数据不足" % index_code)
                continue

            close = df["close"]
            ema20 = close.ewm(span=p["ema_period"], adjust=False).mean()
            ema_today = ema20.iloc[-1]
            ema_5d_ago = ema20.iloc[-(p["ema_slope_lookback"] + 1)]

            if np.isnan(ema_today) or np.isnan(ema_5d_ago):
                down_count += 1
                details.append("%s: NaN" % index_code)
                continue

            slope = (ema_today - ema_5d_ago) / ema_5d_ago
            if ema_today < ema_5d_ago:
                down_count += 1
                details.append("%s: 下跌 (斜率=%.4f)" % (index_code, slope))
            else:
                up_count += 1
                details.append("%s: 上升 (斜率=%.4f)" % (index_code, slope))
        except Exception as e:
            log.warn("指数 %s 计算异常: %s" % (index_code, str(e)))
            down_count += 1
            details.append("%s: 异常" % index_code)

    total = up_count + down_count
    if total == 0:
        log.warn("所有指数都计算失败, 默认空仓")
        return "down"

    up_ratio = up_count / total
    log.info("趋势详情: %s | 上升=%d/下降=%d" % (", ".join(details), up_count, down_count))

    # 严格规则: 任何指数下跌就清仓
    if down_count > 0 and p.get("trend_sell_threshold", 0) == 0:
        return "down"

    # 至少 50% 上升才允许开仓
    if up_ratio < p.get("trend_buy_threshold", 0.5):
        return "down"

    return "sideways"

def compute_buy_signal(context):
    """
    计算买入信号
    条件: 收盘价 <= 布林下轨 * 1.005 AND RSI(6) < 30
    返回: True / False
    """
    p = g.params
    n = max(p["boll_period"], p["rsi_period"]) + 10
    
    df = attribute_history(g.etf_code, n, "1d",
                          ["open", "close"],
                          skip_paused=True, df=True, fq="pre")
    if df is None or len(df) < p["boll_period"]:
        return False
    
    close = df["close"]
    last_close = close.iloc[-1]
    
    if np.isnan(last_close):
        return False
    
    # ---- 布林带 ----
    mid = close.rolling(p["boll_period"]).mean().iloc[-1]
    std = close.rolling(p["boll_period"]).std().iloc[-1]
    if np.isnan(mid) or np.isnan(std):
        return False
    lower = mid - p["boll_std"] * std
    upper = mid + p["boll_std"] * std
    
    # ---- RSI(6) ----
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.rolling(p["rsi_period"]).mean().iloc[-1]
    avg_loss = loss.rolling(p["rsi_period"]).mean().iloc[-1]
    if np.isnan(avg_gain) or np.isnan(avg_loss) or (avg_gain + avg_loss) == 0:
        return False
    rsi = 100 * avg_gain / (avg_gain + avg_loss)
    
    # ---- 条件: 收盘价 <= 下轨 * 1.005 且 RSI < 30 ----
    buy_cond1 = last_close <= lower * p["boll_buy_tolerance"]
    buy_cond2 = rsi < p["rsi_buy_threshold"]
    
    if buy_cond1 and buy_cond2:
        log.info("买入条件: 收盘价=%.3f, 下轨=%.3f (容差=%.3f), RSI=%.2f" % (
                 last_close, lower, lower * p["boll_buy_tolerance"], rsi))
        return True
    return False

def compute_sell_signal(context):
    """
    计算卖出信号
    满足任一条件: 
      1. 收盘价 >= 上轨 * 0.995
      2. RSI > 75
      3. 浮动盈利 >= +5%
    返回: 卖出原因字符串 或 None
    """
    if g.holding_shares == 0 or g.entry_price <= 0:
        return None
    
    p = g.params
    n = max(p["boll_period"], p["rsi_period"]) + 10
    
    df = attribute_history(g.etf_code, n, "1d",
                          ["open", "close"],
                          skip_paused=True, df=True, fq="pre")
    if df is None or len(df) < p["boll_period"]:
        return None
    
    close = df["close"]
    last_close = close.iloc[-1]
    if np.isnan(last_close):
        return None
    
    # ---- 布林带 ----
    mid = close.rolling(p["boll_period"]).mean().iloc[-1]
    std = close.rolling(p["boll_period"]).std().iloc[-1]
    if np.isnan(mid) or np.isnan(std):
        return None
    upper = mid + p["boll_std"] * std
    
    # ---- RSI ----
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.rolling(p["rsi_period"]).mean().iloc[-1]
    avg_loss = loss.rolling(p["rsi_period"]).mean().iloc[-1]
    if np.isnan(avg_gain) or np.isnan(avg_loss) or (avg_gain + avg_loss) == 0:
        return None
    rsi = 100 * avg_gain / (avg_gain + avg_loss)
    
    # ---- 条件1: 收盘价 >= 上轨 * 0.995 ----
    if last_close >= upper * p["boll_sell_tolerance"]:
        log.info("卖出条件(上轨): 收盘价=%.3f, 上轨=%.3f" % (last_close, upper))
        return "upper_band"
    
    # ---- 条件2: RSI > 75 ----
    if rsi > p["rsi_sell_threshold"]:
        log.info("卖出条件(RSI): RSI=%.2f" % rsi)
        return "rsi_overbought"
    
    # ---- 条件3: 浮动盈利 >= +5% ----
    pnl_pct = (last_close - g.entry_price) / g.entry_price
    if pnl_pct >= p["profit_target"]:
        log.info("卖出条件(止盈): 盈亏=%.2f%%" % pnl_pct * 100)
        return "profit_target"
    
    return None

def check_stop_loss(context):
    """
    检查止损条件
    1. 价格止损: 收盘价 < 入场后最低收盘价
    2. 固定比例止损: 浮动亏损 <= -4%
    3. 趋势止损: 已在 before_market_open 中处理
    返回: 止损原因 或 None
    """
    if g.holding_shares == 0 or g.entry_price <= 0:
        return None
    
    p = g.params
    n = 30  # 看最近30天足够
    df = attribute_history(g.etf_code, n, "1d", ["close"],
                          skip_paused=True, df=True, fq="pre")
    if df is None or len(df) < 5:
        return None
    
    close = df["close"]
    last_close = close.iloc[-1]
    if np.isnan(last_close):
        return None
    
    # ---- 1. 更新入场后最低收盘价 ----
    if g.lowest_close_after_entry is None or np.isnan(g.lowest_close_after_entry):
        g.lowest_close_after_entry = g.entry_price
    g.lowest_close_after_entry = min(g.lowest_close_after_entry, last_close)
    
    # ---- 2. 价格止损: 收盘价 < 入场后最低收盘价 ----
    if last_close < g.lowest_close_after_entry:
        # 注意: 这是动态止损, 创新低即止损
        log.info("止损(动态低点): 当前=%.3f, 历史最低=%.3f" % (
                 last_close, g.lowest_close_after_entry))
        g.lowest_close_after_entry = last_close  # 更新
        return "price_stop"
    
    # ---- 3. 固定比例止损: 浮动亏损 <= -4% ----
    pnl_pct = (last_close - g.entry_price) / g.entry_price
    if pnl_pct <= -p["stop_loss_pct"]:
        log.info("止损(固定比例): 盈亏=%.2f%%" % pnl_pct * 100)
        return "pct_stop"
    
    return None

# ============================================================
# 3. 交易执行
# ============================================================

def do_buy(context):
    """
    执行买入: 半仓下单
    """
    p = g.params
    target_value = g.total_capital * p["position_ratio"]
    
    # 优先用 context.portfolio.available_cash 的50% (避免超用)
    available_cash = context.portfolio.available_cash
    actual_value = min(target_value, available_cash * 0.95)
    if actual_value < 1000:
        log.warn("可用资金不足, 放弃本次买入")
        return
    
    # 尝试获取开盘价
    cd = get_current_data()
    d = cd.get(g.etf_code)
    if d is not None and d.last_price > 0:
        open_price = d.last_price
    else:
        # fallback: 用昨日收盘价
        df = attribute_history(g.etf_code, 1, "1d", ["close"],
                              skip_paused=True, df=True, fq="pre")
        if df is None or len(df) == 0:
            log.warn("无法获取价格, 放弃买入")
            return
        open_price = df["close"].iloc[-1]
    
    if open_price <= 0 or np.isnan(open_price):
        log.warn("价格异常, 放弃买入")
        return
    
    # 计算可买股数 (ETF是100的整数倍)
    shares = int(actual_value // open_price // 100 * 100)
    if shares < 100:
        log.warn("资金不足以买1手(100股), 放弃")
        return
    
    # 下单
    order_result = order(g.etf_code, shares)
    if order_result is None:
        log.warn("下单失败")
        return
    
    # 更新状态
    g.holding_shares = shares
    g.entry_price = open_price
    g.entry_date = context.current_dt
    g.lowest_close_after_entry = open_price
    g.signal_pending = None
    
    log.info(">>> 买入成功: %d股, 开盘价=%.3f, 总金额=%.0f元" % (
             shares, open_price, shares * open_price))


def do_sell(context, reason="manual"):
    """
    执行卖出: 全数清仓
    """
    if g.holding_shares <= 0:
        return

    # 全数卖出
    order_result = order(g.etf_code, -g.holding_shares)
    if order_result is None:
        log.warn("清仓下单失败")
        return

    # 记录收益
    cd = get_current_data()
    d = cd.get(g.etf_code)
    current_price = d.last_price if d and d.last_price > 0 else g.entry_price
    pnl = (current_price - g.entry_price) / g.entry_price * 100

    log.info(">>> 卖出成功: 原因=%s, 卖出价=%.3f, 盈亏=%.2f%%" % (
             reason, current_price, pnl))

    # 清理状态
    g.holding_shares = 0
    g.entry_price = 0
    g.entry_date = None
    g.lowest_close_after_entry = None
