# -*- coding: utf-8 -*-
"""
箱体震荡选股策略 (深挖版)
========================================
策略名称: 候选池过滤 + 箱体识别 + 布林带低吸高抛
回测平台: JoinQuant (聚宽)
资金体量: 30万

一、选股池: 硬性过滤 + 财务安全 + 筹码结构
二、趋势判定: 沪深300的20日EMA斜率决定仓位上限
三、箱体识别: 60日振幅、20日EMA走平、布林带宽度
四、买卖点: 触及下轨买, 触及上轨/异常放量卖
"""

from jqdata import *
import numpy as np
import pandas as pd
from datetime import datetime, timedelta


# ============================================================
# 1. 参数配置区
# ============================================================
PARAMS = {
    # ---- 资金与仓位 ----
    "total_capital": 300000,         # 总资金 30万
    "max_holdings": 3,               # 同时最多持有 3 只股票
    "per_stock_value": 30000,        # 单只股票买入 3 万元
    "position_cap_down": 0.30,       # 下跌趋势: 总仓位上限 30%
    "position_cap_sideways": 0.50,   # 震荡/上升: 总仓位上限 50%
    "cash_reserve": 0.02,            # 现金保留
    
    # ---- 基准与股票池 ----
    "benchmark": "000300.XSHG",
    # 候选池: 沪深300 + 创业板 + 科创50 (三大指数合并, 覆盖大中小盘)
    # 注: 聚宽 JQData 中经过验证的指数代码
    "universe_indices": [
        "000300.XSHG",  # 沪深300 (大盘股)
        "399006.XSHE",  # 创业板指 (成长股)
        "000688.XSHG",  # 科创50 (科创板)
    ],
    "universe_index": "000300.XSHG",  # 兼容保留: 从沪深300中初筛 (单指数模式)
    
    # ---- 选股池硬性过滤 (基于2018年回测调整) ----
    "min_listed_days": 60,            # 上市满 60 个交易日 (进一步放宽)
    "min_avg_amount_20d": 5e7,        # 20日均成交额 > 5000万 (放宽到小盘股)
    "min_price": 3.0,                  # 收盘价 > 3 元 (放宽, 容纳低价股)
    "max_turnover_20d": 0.15,          # 20日均换手率 < 15% (大幅放宽)
    "max_margin_ratio": 0.15,          # 融资余额占流通市值 < 15%
    "max_debt_ratio": 0.80,            # 资产负债率 < 80%
    "min_net_profit": 0,               # 归母净利润 > 0 (元)
    
    # ---- 箱体识别 ----
    "max_amp_60d": 0.45,               # 60日振幅 <= 45%
    "min_days_in_band": 15,            # 20日内 >= 15天在布林带内
    "ema_flat_range": 0.01,            # 20日EMA斜率绝对值 < 1%
    "min_boll_width": 0.12,            # 布林带宽度 > 12%
    "boll_period": 20,                 # 布林带周期
    "boll_std": 2,                     # 布林带标准差倍数
    "ema_period": 20,                  # EMA周期
    "ema_slope_lookback": 5,          # EMA斜率回溯天数
    "amp_lookback": 60,                # 振幅计算回溯天数
    
    # ---- 买卖信号 ----
    "rsi_period": 6,                   # RSI 周期
    "rsi_buy_threshold": 30,           # 买入 RSI < 30 (放宽, 增加买入机会)
    "rsi_sell_threshold": 75,           # 卖出 RSI > 75 (收紧, 让超买更强才卖)
    "boll_buy_tolerance": 1.02,        # 收盘价 <= 下轨 * 1.02 (放宽)
    "boll_sell_tolerance": 0.98,       # 收盘价 >= 上轨 * 0.98 (收紧)
    "profit_target": 0.05,             # 止盈 +5% (降低止盈要求, 提高胜率)
    "stop_loss_pct": 0.07,             # 止损 -7% (放宽, 减少误止损)
    "min_holding_days": 3,             # 最小持仓天数 (避免T+1止损)
    "vol_anomaly_mult": 3.0,            # 异常放量倍数 (放宽, 减少假信号)
    "vol_anomaly_lookback": 20,        # 异常放量回溯天数
    "min_volume_ratio": 0.5,            # 缩量下限 (放宽)
    
    # ---- 调度时间 ----
    "refresh_time": "15:00",           # 候选池刷新时间
    "signal_time": "14:50",             # 买卖信号生成时间
    "execute_time": "09:30",           # 执行时间
}


def initialize(context):
    """
    策略初始化
    """
    set_benchmark(PARAMS["benchmark"])
    set_option("use_real_price", True)
    
    # 手续费/印花税
    set_order_cost(OrderCost(
        open_tax=0,                  # 买入无印花税
        close_tax=0.001,             # 卖出印花税千一
        open_commission=0.0003,     # 买入佣金万三
        close_commission=0.0003,    # 卖出佣金万三
        close_today_commission=0,
        min_commission=5
    ), type="stock")
    
    set_slippage(FixedSlippage(0.001))  # 0.1%滑点
    log.set_level("order", "error")
    
    # ---- 全局状态 ----
    g.params = PARAMS
    g.candidate_pool = []      # 候选池 (每日刷新)
    g.oscillation_pool = []    # 震荡奶牛池 (在候选池基础上进一步筛选)
    g.holdings = {}            # 持仓: {stock: {entry_price, entry_date, highest_close}}
    g.signal_pending = []     # 次日待执行信号: [(stock, action, reason), ...]
    g.trend_status = "sideways"  # 当前大盘趋势状态
    g.refresh_done = False     # 当日候选池是否已刷新
    g.first_run = True         # 首次运行标志
    
    # ---- 日程调度 ----
    # 15:00 收盘后: 刷新候选池 + 识别震荡奶牛
    run_daily(refresh_pool, time=PARAMS["refresh_time"])
    # 14:50 生成信号 (注意: 必须在刷新之后, 用 run_daily 顺序由函数注册先后决定)
    # 这里交换顺序: 14:50 实际比 15:00 早, 所以先 14:50 用昨日池子
    # 修改方案: 14:50 不刷新池子, 15:00 刷新池子并识别震荡奶牛
    # 但 14:50 需要判断信号, 所以我们改成:
    #  - 14:50 用当日最新数据生成信号 (因为 14:50 后价格波动小, 近似收盘价)
    #  - 15:00 收盘后再刷新候选池 (供明日判断)
    # 实际: 14:50 时 close 字段已近似收盘, 14:50 -> 15:00 半小时
    #  为简化, 我们让 generate_signals 在 15:00 后执行, 此时已收盘
    run_daily(generate_signals, time="15:05")  # 收盘后生成买卖信号
    # 次日 09:30 执行
    run_daily(execute_pending, time=PARAMS["execute_time"])
    
    log.info("=" * 60)
    log.info("=== 箱体震荡选股策略 (深挖版) 初始化完成 ===")
    log.info("总资金: %d | 单股: %d | 最多持仓: %d" % (
             PARAMS["total_capital"], PARAMS["per_stock_value"], PARAMS["max_holdings"]))
    log.info("=" * 60)

    # 首次启动时立即刷新一次候选池 (避免首次信号生成时池子为空)
    # 注意: initialize 中 context 不一定可用, 用 run_daily 替代
    # 实际上, run_daily 注册的函数会在第一个符合时间点执行
    # 所以第一次 15:00 会先 refresh_pool, 第一次 15:05 会 generate_signals

# ============================================================
# 2. 候选池刷新
# ============================================================

def refresh_pool(context):
    """
    15:00 收盘后刷新候选池, 同时识别震荡奶牛
    一、硬性过滤: ST/上市天数/成交额/价格/换手率/融资/财务
    二、箱体识别: 60日振幅/布林带内天数/EMA走平/带宽

    股票池: 中证2000 + 创业板 + 科创板 (三大指数合并去重)
    """
    log.info("=" * 60)
    log.info("[%s] 刷新候选池 + 识别震荡奶牛" % context.current_dt.strftime("%Y-%m-%d"))

    p = g.params

    # 1. 合并多个指数成分股
    raw = []
    index_counts = {}

    # 优先使用新的多指数配置
    if p.get("universe_indices"):
        for index_code in p["universe_indices"]:
            try:
                stocks = get_index_stocks(index_code, date=context.previous_date)
                if stocks:
                    index_counts[index_code] = len(stocks)
                    for s in stocks:
                        if s not in raw:
                            raw.append(s)
            except Exception as e:
                log.warn("获取指数 %s 成分股失败: %s" % (index_code, str(e)))
        # 性能提示: 中证2000有2000只, 合并后约3000只, 硬性过滤会剔除大部分
        if len(raw) > 1500:
            log.warn("合并池较大 (%d 只), 硬性过滤可能耗时较长, 建议回测周期不要太长" % len(raw))
    else:
        # 兼容旧配置: 单指数
        try:
            raw = list(get_index_stocks(p["universe_index"], date=context.previous_date))
            index_counts[p["universe_index"]] = len(raw)
        except Exception as e:
            log.warn("获取指数成分股失败: %s" % str(e))
            return

    if index_counts:
        log.info("指数成分股: %s" % index_counts)
    log.info("合并去重后: %d 只" % len(raw))
    
    # 2. 硬性过滤
    candidate = hard_filter(raw, context)
    log.info("硬性过滤后: %d 只" % len(candidate))
    g.candidate_pool = candidate
    
    # 3. 箱体识别
    oscillation = box_filter(candidate, context)
    log.info("震荡奶牛池: %d 只" % len(oscillation))
    g.oscillation_pool = oscillation
    g.refresh_done = True

def hard_filter(stock_list, context):
    """
    硬性过滤: 排除 ST/低成交/低价格/高换手/高融资

    【性能优化】使用 history() 批量获取所有股票的数据, 一次API调用代替 385 次
    优化前: 385 只股票 × 5 次 API 调用 = 1925 次请求
    优化后: 3 次 history() 批量调用 (close, money, volume)
    """
    p = g.params
    out = []
    skipped_st = 0
    skipped_listed = 0
    skipped_amount = 0
    skipped_price = 0
    skipped_turnover = 0
    skipped_exception = 0
    skipped_no_data = 0

    if not stock_list:
        return out

    # ---- 批量获取数据 (3 次 API 调用代替 385 次) ----
    need_days = max(p["min_listed_days"], 25)
    try:
        # 1. 批量获取收盘价 (用于价格过滤、上市天数判断)
        df_close = history(need_days, "1d", "close", stock_list,
                          df=True, skip_paused=False, fq="pre")
    except Exception as e:
        log.warn("批量获取收盘价失败: %s" % str(e))
        df_close = None

    try:
        # 2. 批量获取成交额
        df_money = history(25, "1d", "money", stock_list,
                          df=True, skip_paused=False, fq="pre")
    except Exception as e:
        log.warn("批量获取成交额失败: %s" % str(e))
        df_money = None

    if df_close is None or len(df_close) == 0:
        log.warn("批量获取收盘价失败, 回退到原始逐个查询")
        return _hard_filter_legacy(stock_list, context)

    # ---- 3. 批量获取换手率 ----
    try:
        turnover_df = get_valuation(stock_list,
                                 start_date=context.previous_date,
                                 end_date=context.previous_date,
                                 fields=["turnover_ratio"])
    except Exception:
        turnover_df = None

    # ---- 4. 批量获取 ST 状态 ----
    try:
        extras = get_extras("is_st", stock_list,
                           start_date=context.previous_date,
                           end_date=context.previous_date,
                           df=False)
    except Exception:
        extras = None

    # ---- 5. 逐只检查 (内存中计算, 速度极快) ----
    debug_count = 0
    for s in stock_list:
        try:
            # ---- 收盘价 ----
            if s not in df_close.columns:
                skipped_no_data += 1
                continue
            close_series = df_close[s].dropna()
            if len(close_series) < 5:
                skipped_no_data += 1
                continue

            last_close = close_series.iloc[-1]
            if last_close <= 0 or np.isnan(last_close):
                skipped_price += 1
                continue
            if last_close < p["min_price"]:
                skipped_price += 1
                continue

            if debug_count < 3:
                log.info("DEBUG %s: last_close=%.2f" % (s, last_close))
                debug_count += 1

            # ---- 上市天数 ----
            if len(close_series) < p["min_listed_days"]:
                skipped_listed += 1
                continue

            # ---- ST 检查 ----
            if extras and s in extras and len(extras[s]) > 0:
                try:
                    is_st = bool(extras[s][-1])
                    if is_st:
                        skipped_st += 1
                        continue
                except Exception:
                    pass

            # ---- 成交额 ----
            if df_money is not None and s in df_money.columns:
                money_series = df_money[s].dropna()
                if len(money_series) >= 20:
                    avg_amount_20 = money_series.tail(20).mean()
                    if np.isnan(avg_amount_20) or avg_amount_20 < p["min_avg_amount_20d"]:
                        skipped_amount += 1
                        continue

            # ---- 换手率 ----
            if turnover_df is not None and s in turnover_df.index:
                tr = turnover_df.loc[s, "turnover_ratio"]
                if tr is not None and not np.isnan(tr) and tr > p["max_turnover_20d"] * 100:
                    skipped_turnover += 1
                    continue

            out.append(s)
        except Exception as e:
            skipped_exception += 1
            if debug_count < 5:
                log.warn("过滤 %s 异常: %s" % (s, str(e)))
                debug_count += 1
            continue

    log.info("硬性过滤详情: ST=%d, 上市不足=%d, 成交额=%d, 价格=%d, 换手率=%d, 无数据=%d, 异常=%d" % (
             skipped_st, skipped_listed, skipped_amount, skipped_price, skipped_turnover,
             skipped_no_data, skipped_exception))
    return out


def _hard_filter_legacy(stock_list, context):
    """原始逐个查询实现, 作为回退方案"""
    p = g.params
    out = []
    for s in stock_list:
        try:
            hist_min = attribute_history(s, 5, "1d", ["close", "high", "low", "volume"],
                                         skip_paused=True, df=True, fq="pre")
            if hist_min is None or len(hist_min) < 5:
                continue
            last_close = hist_min["close"].iloc[-1]
            if last_close <= 0 or np.isnan(last_close) or last_close < p["min_price"]:
                continue
            out.append(s)
        except Exception:
            continue
    return out

def box_filter(stock_list, context):
    """
    箱体识别: 在候选池中筛选震荡奶牛

    【性能优化】使用 history() 批量获取所有股票数据
    优化前: 300+ 只股票 × 1 次 70天历史查询 = 300+ 次 API 调用
    优化后: 3 次 history() 批量调用 (close, high, low)
    """
    p = g.params
    out = []
    details = {"amp": 0, "in_band": 0, "ema_slope": 0, "boll_width": 0}

    if not stock_list:
        return out

    n = max(p["amp_lookback"], p["ema_period"], p["boll_period"]) + 10

    # ---- 批量获取数据 ----
    try:
        df_close = history(n, "1d", "close", stock_list,
                          df=True, skip_paused=False, fq="pre")
        df_high = history(n, "1d", "high", stock_list,
                         df=True, skip_paused=False, fq="pre")
        df_low = history(n, "1d", "low", stock_list,
                        df=True, skip_paused=False, fq="pre")
    except Exception as e:
        log.warn("箱体识别批量获取数据失败: %s" % str(e))
        return out

    if df_close is None or df_close.empty:
        return out

    # ---- 逐只计算 (内存中运算) ----
    for s in stock_list:
        try:
            if s not in df_close.columns:
                continue

            close = df_close[s].dropna()
            if len(close) < p["amp_lookback"]:
                continue

            high = df_high[s].dropna()
            low = df_low[s].dropna()

            # ---- 1. 60日振幅 ----
            high_60 = high.tail(p["amp_lookback"]).max()
            low_60 = low.tail(p["amp_lookback"]).min()
            if low_60 <= 0:
                continue
            amp_60 = (high_60 - low_60) / low_60
            if amp_60 > p["max_amp_60d"]:
                details["amp"] += 1
                continue

            # ---- 2. 布林带 ----
            mid = close.rolling(p["boll_period"]).mean()
            std = close.rolling(p["boll_period"]).std()
            upper = mid + p["boll_std"] * std
            lower = mid - p["boll_std"] * std

            # 20日内 >= 15天在布林带内
            recent_close = close.tail(20)
            recent_upper = upper.tail(20)
            recent_lower = lower.tail(20)
            in_band = (recent_close <= recent_upper) & (recent_close >= recent_lower)
            in_band_count = in_band.sum()
            if in_band_count < p["min_days_in_band"]:
                details["in_band"] += 1
                continue

            # 布林带宽度 (上轨-下轨)/中轨 > 12%
            mid_last = mid.iloc[-1]
            if mid_last <= 0:
                continue
            boll_width = (upper.iloc[-1] - lower.iloc[-1]) / mid_last
            if boll_width <= p["min_boll_width"]:
                details["boll_width"] += 1
                continue

            # ---- 3. 20日EMA斜率 ----
            ema20 = close.ewm(span=p["ema_period"], adjust=False).mean()
            ema_today = ema20.iloc[-1]
            ema_5d_ago = ema20.iloc[-(p["ema_slope_lookback"] + 1)]
            if np.isnan(ema_today) or np.isnan(ema_5d_ago) or ema_5d_ago == 0:
                continue
            ema_slope = (ema_today - ema_5d_ago) / ema_5d_ago
            if abs(ema_slope) > p["ema_flat_range"]:
                details["ema_slope"] += 1
                continue

            out.append(s)
        except Exception as e:
            details["amp"] += 1
            continue

    log.info("箱体过滤详情: 振幅=%d, 带内天数=%d, EMA斜率=%d, 带宽=%d" % (
             details["amp"], details["in_band"], details["ema_slope"], details["boll_width"]))
    return out

# ============================================================
# 3. 信号生成
# ============================================================

def generate_signals(context):
    """
    15:05 收盘后: 趋势判断 + 扫描持仓(止损/止盈) + 扫描候选池(买入)
    """
    log.info("=" * 60)
    log.info("[%s] 15:05 信号生成" % context.current_dt.strftime("%Y-%m-%d"))
    
    # 1. 大盘趋势判断
    g.trend_status = check_market_trend(context)
    log.info("大盘趋势: %s" % g.trend_status)
    
    # 2. 扫描持仓 (卖出/止损优先)
    pending_sell = scan_holdings(context)
    
    # 3. 检查持仓是否被移除候选池
    for stock in list(g.holdings.keys()):
        if g.candidate_pool and stock not in g.candidate_pool:
            pending_sell.append([stock, "removed", "候选池移除"])
            log.warn("持仓 %s 被移除候选池, 准备清仓" % stock)
    
    # 4. 扫描震荡奶牛 (买入信号)
    pending_buy = []
    if g.trend_status == "sideways" and g.refresh_done:
        position_cap = g.params["position_cap_sideways"]
        current_value = sum([context.portfolio.positions[s].value
                             for s in g.holdings
                             if s in context.portfolio.positions])
        max_total = g.params["total_capital"] * position_cap
        remaining = max_total - current_value
        log.info("当前持仓: %d 只, 占用: %.0f, 上限: %.0f, 剩余: %.0f" % (
                 len(g.holdings), current_value, max_total, remaining))
        
        if len(g.holdings) < g.params["max_holdings"] and remaining > 0:
            pending_buy = scan_oscillation_pool(context, remaining)
    else:
        log.info("下跌趋势, 不开新仓")
    
    # 5. 合并信号 (卖优先, 卖完再买)
    g.signal_pending = pending_sell + pending_buy
    if g.signal_pending:
        log.info("信号汇总: %s" % [s[:2] for s in g.signal_pending])
    else:
        log.info("无信号, 维持当前状态")

def check_market_trend(context):
    """
    大盘趋势: 沪深300的20日EMA斜率
    """
    p = g.params
    n = p["ema_period"] + p["ema_slope_lookback"] + 10
    df = attribute_history(p["benchmark"], n, "1d", ["close"],
                          skip_paused=True, df=True, fq="pre")
    if df is None or len(df) < p["ema_period"] + p["ema_slope_lookback"]:
        return "down"
    
    ema20 = df["close"].ewm(span=p["ema_period"], adjust=False).mean()
    ema_today = ema20.iloc[-1]
    ema_5d_ago = ema20.iloc[-(p["ema_slope_lookback"] + 1)]
    if np.isnan(ema_today) or np.isnan(ema_5d_ago):
        return "down"
    if ema_today < ema_5d_ago:
        return "down"
    return "sideways"


def compute_rsi(close, period):
    """计算 RSI"""
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.rolling(period).mean().iloc[-1]
    avg_loss = loss.rolling(period).mean().iloc[-1]
    if np.isnan(avg_gain) or np.isnan(avg_loss) or (avg_gain + avg_loss) == 0:
        return 50.0
    return 100 * avg_gain / (avg_gain + avg_loss)


def scan_holdings(context):
    """
    扫描持仓, 返回卖出信号列表

    【优化】增加最小持仓天数保护, 避免 T+1 频繁止损
    """
    p = g.params
    pending = []
    min_hold = p.get("min_holding_days", 3)

    for stock in list(g.holdings.keys()):
        h = g.holdings[stock]
        try:
            n = max(p["boll_period"], p["ema_period"], p["vol_anomaly_lookback"]) + 10
            df = attribute_history(stock, n, "1d",
                                  ["open", "close", "high", "low", "volume"],
                                  skip_paused=True, df=True, fq="pre")
            if df is None or len(df) < p["boll_period"]:
                continue

            close = df["close"]
            last_close = close.iloc[-1]
            if np.isnan(last_close):
                continue

            # 更新入场后最高
            h["highest_close"] = max(h.get("highest_close", h["entry_price"]), last_close)

            # ---- 计算持仓天数 ----
            entry_date = h.get("entry_date")
            if entry_date is not None:
                held_days = (context.current_dt.date() - entry_date.date()).days
            else:
                held_days = 99  # 未知时默认已持仓很久
            in_min_period = held_days < min_hold

            # ---- 计算 pnl ----
            pnl = (last_close - h["entry_price"]) / h["entry_price"]

            # ---- 计算布林 ----
            mid = close.rolling(p["boll_period"]).mean().iloc[-1]
            std = close.rolling(p["boll_period"]).std().iloc[-1]
            upper = mid + p["boll_std"] * std if not np.isnan(mid) and not np.isnan(std) else None
            lower = mid - p["boll_std"] * std if not np.isnan(mid) and not np.isnan(std) else None

            # ---- 1. 触及布林上轨 (持仓未达 min_hold 仍允许) ----
            if upper is not None and last_close >= upper * p["boll_sell_tolerance"]:
                pending.append([stock, "sell", "触及上轨"])
                log.info("%s 触及布林上轨, 准备卖出 (持仓%d日)" % (stock, held_days))
                continue

            # ---- 2. RSI > 70 ----
            rsi = compute_rsi(close, p["rsi_period"])
            if rsi > p["rsi_sell_threshold"]:
                pending.append([stock, "sell", "RSI超买"])
                log.info("%s RSI=%.2f > 75, 准备卖出 (持仓%d日)" % (stock, rsi, held_days))
                continue

            # ---- 3. 止盈 +5% (降低要求) ----
            if pnl >= p["profit_target"]:
                pending.append([stock, "sell", "止盈"])
                log.info("%s 盈利 %.2f%%, 准备止盈 (持仓%d日)" % (stock, pnl * 100, held_days))
                continue

            # ---- 4. 异常放量 + 阴线 ----
            vol_20 = df["volume"].tail(p["vol_anomaly_lookback"]).mean()
            today_vol = df["volume"].iloc[-1]
            if vol_20 > 0 and today_vol > vol_20 * p["vol_anomaly_mult"]:
                if last_close < df["open"].iloc[-1]:
                    pending.append([stock, "sell", "异常放量阴线"])
                    log.info("%s 异常放量+阴线, 准备清仓" % stock)
                    continue

            # ---- 5. 固定止损 (持仓未达 min_hold 暂不执行, 避免 T+1 误止损) ----
            if pnl <= -p["stop_loss_pct"]:
                if in_min_period:
                    log.info("%s 亏损 %.2f%%, 但持仓仅 %d 日 (< %d), 暂不止损" %
                             (stock, pnl * 100, held_days, min_hold))
                else:
                    pending.append([stock, "stop", "固定止损"])
                    log.info("%s 亏损 %.2f%%, 触发止损" % (stock, pnl * 100))
                    continue

            # ---- 6. 个股20日EMA转空 (持仓未达 min_hold 暂不执行) ----
            ema20 = close.ewm(span=p["ema_period"], adjust=False).mean()
            ema_today = ema20.iloc[-1]
            ema_5d_ago = ema20.iloc[-(p["ema_slope_lookback"] + 1)]
            if not np.isnan(ema_today) and not np.isnan(ema_5d_ago):
                if ema_today < ema_5d_ago:
                    if in_min_period:
                        log.info("%s EMA转空, 但持仓仅 %d 日, 暂不执行" % (stock, held_days))
                    else:
                        pending.append([stock, "stop", "个股EMA转空"])
                        log.info("%s 20日EMA转空, 准备离场" % stock)
                        continue

            # ---- 7. 大盘转空 + 个股跌破中轨 (保护性, 无需等 min_hold) ----
            if g.trend_status == "down":
                if not np.isnan(mid) and last_close < mid:
                    pending.append([stock, "stop", "大盘转空+破中轨"])
                    log.info("%s 大盘转空且跌破中轨, 保护性清仓" % stock)
                    continue
        except Exception as e:
            log.warn("扫描 %s 异常: %s" % (stock, str(e)))

    return pending


def scan_oscillation_pool(context, remaining_budget):
    """
    扫描震荡奶牛池, 返回买入信号列表
    买入条件: 触及下轨 + RSI < 35 + 缩量
    """
    p = g.params
    pending = []
    per_stock = p["per_stock_value"]
    buy_capacity = min(int(remaining_budget / per_stock), p["max_holdings"] - len(g.holdings))

    if buy_capacity <= 0:
        return pending

    log.info("扫描震荡奶牛: %d 只, 可买入 %d 只" % (len(g.oscillation_pool), buy_capacity))

    # 按得分排序 (布林带偏离度)
    candidates = []
    for stock in g.oscillation_pool:
        if stock in g.holdings:
            continue
        try:
            n = max(p["boll_period"], p["rsi_period"]) + 10
            df = attribute_history(stock, n, "1d",
                                  ["open", "close", "high", "low", "volume"],
                                  skip_paused=True, df=True, fq="pre")
            if df is None or len(df) < p["boll_period"]:
                continue

            close = df["close"]
            last_close = close.iloc[-1]
            if np.isnan(last_close):
                continue

            # 布林带
            mid = close.rolling(p["boll_period"]).mean().iloc[-1]
            std = close.rolling(p["boll_period"]).std().iloc[-1]
            if np.isnan(mid) or np.isnan(std):
                continue
            lower = mid - p["boll_std"] * std

            # 触及下轨
            if last_close > lower * p["boll_buy_tolerance"]:
                continue

            # RSI
            rsi = compute_rsi(close, p["rsi_period"])
            if rsi >= p["rsi_buy_threshold"]:
                continue

            # 缩量: 当日成交量 > 5日均量 * 0.7
            vol_5 = df["volume"].tail(5).mean()
            today_vol = df["volume"].iloc[-1]
            if vol_5 <= 0 or today_vol < vol_5 * p["min_volume_ratio"]:
                continue

            # 得分: 距下轨的距离 (越近越好)
            score = abs(last_close - lower) / lower
            candidates.append((stock, score, rsi, last_close, lower))

        except Exception as e:
            log.warn("扫描 %s 异常: %s" % (stock, str(e)))
            continue

    # 按得分升序 (最接近下轨的优先)
    candidates.sort(key=lambda x: x[1])

    for stock, score, rsi, last_close, lower in candidates[:buy_capacity]:
        pending.append([stock, "buy", "触及下轨+RSI=%.1f" % rsi])
        log.info("%s 买入信号: 收盘=%.3f, 下轨=%.3f, RSI=%.1f" %
                 (stock, last_close, lower, rsi))

    return pending


def execute_pending(context):
    """
    09:30 开盘: 执行昨日 15:05 生成的信号
    """
    if not g.signal_pending:
        return

    log.info("=" * 60)
    log.info("[%s] 09:30 执行信号 (共 %d 条)" %
             (context.current_dt.strftime("%Y-%m-%d"), len(g.signal_pending)))

    for signal in g.signal_pending:
        stock, action, reason = signal[0], signal[1], signal[2]
        if action == "buy":
            do_buy(context, stock, reason)
        elif action in ["sell", "stop", "removed"]:
            do_sell(context, stock, reason)

    g.signal_pending = []
    g.refresh_done = False  # 重置刷新标志


def do_buy(context, stock, reason):
    """执行买入"""
    if stock in g.holdings:
        return

    p = g.params
    target_value = p["per_stock_value"]
    available_cash = context.portfolio.available_cash
    actual_value = min(target_value, available_cash * 0.95)
    if actual_value < 1000:
        log.warn("可用资金不足, 放弃买入 %s" % stock)
        return

    # 获取开盘价
    cd = get_current_data()
    d = cd.get(stock)
    if d is not None and d.last_price > 0:
        open_price = d.last_price
    else:
        try:
            df = attribute_history(stock, 1, "1d", ["close"],
                                  skip_paused=True, df=True, fq="pre")
            open_price = df["close"].iloc[-1] if df is not None and len(df) > 0 else 0
        except Exception:
            open_price = 0

    if open_price <= 0 or np.isnan(open_price):
        log.warn("价格异常, 放弃买入 %s" % stock)
        return

    shares = int(actual_value // open_price // 100 * 100)
    if shares < 100:
        log.warn("资金不足以买1手, 放弃 %s" % stock)
        return

    # 科创板需要限价单
    if stock.startswith("688"):
        limit_price = min(open_price * 1.005, 9999.99)
        order_result = order(stock, shares, LimitOrderStyle(limit_price))
    else:
        order_result = order_value(stock, shares * open_price)

    if order_result is None:
        log.warn("下单失败: %s" % stock)
        return

    g.holdings[stock] = {
        "entry_price": open_price,
        "entry_date": context.current_dt,
        "highest_close": open_price,
        "shares": shares,
        "reason": reason,
    }
    log.info(">>> 买入 %s: %d股, 开盘价=%.3f, 金额=%.0f, 原因=%s" %
             (stock, shares, open_price, shares * open_price, reason))


def do_sell(context, stock, reason):
    """执行卖出"""
    if stock not in g.holdings:
        return

    h = g.holdings[stock]
    shares = h.get("shares", 0)
    if shares <= 0:
        # 尝试从 context.portfolio 获取
        if stock in context.portfolio.positions:
            shares = context.portfolio.positions[stock].closeable_amount
        if shares <= 0:
            log.warn("无可卖股数: %s" % stock)
            del g.holdings[stock]
            return

    # 科创板限价单
    if stock.startswith("688"):
        cd = get_current_data()
        d = cd.get(stock)
        cur_price = d.last_price if d and d.last_price > 0 else h["entry_price"]
        limit_price = max(cur_price * 0.995, 0.01)
        if limit_price >= 10000:
            limit_price = 9999.99
        order_result = order(stock, -shares, LimitOrderStyle(limit_price))
    else:
        order_result = order_target_value(stock, 0)

    if order_result is None:
        log.warn("清仓下单失败: %s" % stock)
        return

    # 记录收益
    cd = get_current_data()
    d = cd.get(stock)
    current_price = d.last_price if d and d.last_price > 0 else h["entry_price"]
    pnl = (current_price - h["entry_price"]) / h["entry_price"] * 100

    log.info(">>> 卖出 %s: %d股, 价=%.3f, 盈亏=%.2f%%, 原因=%s" %
             (stock, shares, current_price, pnl, reason))

    del g.holdings[stock]
