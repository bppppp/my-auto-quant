# -*- coding: utf-8 -*-
"""
多因子趋势波段策略 (Multi-Factor Trend Swing)
==============================================
策略名称: multi_factor_trend_swing
策略文档: D:\my-auto-quant\result\multi_factor_trend_swing\multi_factor_trend_swing_final.md
回测平台: JoinQuant (聚宽)

目标: 年化 22%, 胜率 52%, 盈亏比 2.9, 夏普 1.35, 回撤 12%
标的: 沪深 300, 持仓周期 15-30 个交易日
调仓: 每 5 个交易日

因子: MA10/30/60, ATR14, 量比, RSI14, 60日动量
"""

from jqdata import *
import numpy as np
import pandas as pd


# ============================================================
# 1. 参数配置区 (基于策略文档 v1 调优参数)
# ============================================================
PARAMS = {
    # ---- 标的与基准 ----
    "benchmark": "000300.XSHG",   # 基准仍用沪深300
    "universe_source": "static",  # "static" = 使用静态测试集, "index" = 使用HS300动态池
    # 静态测试集 (来自 D:\my-auto-quant\subjects\multi_factor_trend_swing\test_universe\top300.md)
    # 共 300 只, 转换: SH -> XSHG, SZ -> XSHE
    "static_universe": [
        '301638.XSHE', '301662.XSHE', '001400.XSHE', '920116.XSHE', '301551.XSHE',
        '688411.XSHG', '920526.XSHE', '301563.XSHE', '920799.XSHE', '301396.XSHE',
        '920971.XSHE', '300502.XSHE', '603516.XSHG', '000062.XSHE', '688656.XSHG',
        '920171.XSHE', '920576.XSHE', '920493.XSHE', '301611.XSHE', '300757.XSHE',
        '920223.XSHE', '920207.XSHE', '920415.XSHE', '920522.XSHE', '301377.XSHE',
        '001309.XSHE', '300476.XSHE', '688183.XSHG', '001280.XSHE', '301550.XSHE',
        '300548.XSHE', '600105.XSHG', '000833.XSHE', '603929.XSHG', '920204.XSHE',
        '920489.XSHE', '301209.XSHE', '688195.XSHG', '920564.XSHE', '601869.XSHG',
        '603226.XSHG', '300857.XSHE', '002565.XSHE', '603124.XSHG', '920821.XSHE',
        '920000.XSHE', '301489.XSHE', '300475.XSHE', '688519.XSHG', '920505.XSHE',
        '301626.XSHE', '688629.XSHG', '688615.XSHG', '002837.XSHE', '603256.XSHG',
        '301630.XSHE', '002378.XSHE', '301232.XSHE', '301306.XSHE', '920002.XSHE',
        '920274.XSHE', '002290.XSHE', '301629.XSHE', '920765.XSHE', '920510.XSHE',
        '688205.XSHG', '920924.XSHE', '920699.XSHE', '000657.XSHE', '600343.XSHG',
        '300870.XSHE', '002361.XSHE', '920247.XSHE', '002342.XSHE', '920876.XSHE',
        '688679.XSHG', '688710.XSHG', '300342.XSHE', '920541.XSHE', '920249.XSHE',
        '920169.XSHE', '300210.XSHE', '002718.XSHE', '001267.XSHE', '920392.XSHE',
        '603667.XSHG', '003018.XSHE', '301600.XSHE', '301183.XSHE', '603067.XSHG',
        '920046.XSHE', '603052.XSHG', '600673.XSHG', '300390.XSHE', '300720.XSHE',
        '300308.XSHE', '002364.XSHE', '300290.XSHE', '920790.XSHE', '688158.XSHG',
        '300570.XSHE', '920509.XSHE', '002046.XSHE', '603601.XSHG', '002636.XSHE',
        '002272.XSHE', '920239.XSHE', '920184.XSHE', '920227.XSHE', '688257.XSHG',
        '603308.XSHG', '603175.XSHG', '002796.XSHE', '920357.XSHE', '603626.XSHG',
        '920839.XSHE', '300436.XSHE', '605255.XSHG', '920689.XSHE', '002759.XSHE',
        '920953.XSHE', '002611.XSHE', '920273.XSHE', '003041.XSHE', '301128.XSHE',
        '300718.XSHE', '002842.XSHE', '688313.XSHG', '300620.XSHE', '605298.XSHG',
        '920284.XSHE', '605318.XSHG', '002851.XSHE', '301018.XSHE', '920720.XSHE',
        '688661.XSHG', '688167.XSHG', '300836.XSHE', '300153.XSHE', '920122.XSHE',
        '300972.XSHE', '603598.XSHG', '920627.XSHE', '301070.XSHE', '920926.XSHE',
        '301338.XSHE', '300063.XSHE', '920981.XSHE', '300102.XSHE', '600629.XSHG',
        '001896.XSHE', '000426.XSHE', '688530.XSHG', '603119.XSHG', '300058.XSHE',
        '920436.XSHE', '920964.XSHE', '920879.XSHE', '603663.XSHG', '300442.XSHE',
        '301200.XSHE', '920475.XSHE', '920149.XSHE', '301308.XSHE', '605376.XSHG',
        '688041.XSHG', '301362.XSHE', '603038.XSHG', '301389.XSHE', '920834.XSHE',
        '920753.XSHE', '301171.XSHE', '920139.XSHE', '920237.XSHE', '300255.XSHE',
        '300984.XSHE', '920748.XSHE', '603011.XSHG', '000880.XSHE', '920394.XSHE',
        '920454.XSHE', '920174.XSHE', '600301.XSHG', '688800.XSHG', '000688.XSHE',
        '688191.XSHG', '920580.XSHE', '300394.XSHE', '920407.XSHE', '920508.XSHE',
        '300731.XSHE', '920634.XSHE', '600580.XSHG', '603286.XSHG', '002222.XSHE',
        '688316.XSHG', '002980.XSHE', '601138.XSHG', '920179.XSHE', '920346.XSHE',
        '002580.XSHE', '000890.XSHE', '301297.XSHE', '688521.XSHG', '920299.XSHE',
        '688081.XSHG', '001203.XSHE', '603090.XSHG', '300170.XSHE', '603530.XSHG',
        '002384.XSHE', '920396.XSHE', '920553.XSHE', '920221.XSHE', '601020.XSHG',
        '603699.XSHG', '688498.XSHG', '300432.XSHE', '920885.XSHE', '688691.XSHG',
        '300868.XSHE', '920262.XSHE', '301123.XSHE', '301345.XSHE', '920395.XSHE',
        '600331.XSHG', '300067.XSHE', '603200.XSHG', '920873.XSHE', '301196.XSHE',
        '601179.XSHG', '300499.XSHE', '603991.XSHG', '605488.XSHG', '920802.XSHE',
        '688525.XSHG', '920190.XSHE', '920592.XSHE', '301486.XSHE', '301079.XSHE',
        '603920.XSHG', '688233.XSHG', '920021.XSHE', '600396.XSHG', '301571.XSHE',
        '301005.XSHE', '688307.XSHG', '603950.XSHG', '920523.XSHE', '920504.XSHE',
        '603091.XSHG', '600879.XSHG', '600869.XSHG', '300364.XSHE', '688226.XSHG',
        '920075.XSHE', '605117.XSHG', '920212.XSHE', '688258.XSHG', '920455.XSHE',
        '920275.XSHE', '300668.XSHE', '300835.XSHE', '920808.XSHE', '920768.XSHE',
        '920533.XSHE', '000559.XSHE', '688108.XSHG', '301526.XSHE', '301182.XSHE',
        '920810.XSHE', '600539.XSHG', '920663.XSHE', '920751.XSHE', '920403.XSHE',
        '688593.XSHG', '920245.XSHE', '688309.XSHG', '688523.XSHG', '920914.XSHE',
        '603061.XSHG', '920976.XSHE', '002536.XSHE', '300900.XSHE', '301000.XSHE',
        '920438.XSHE', '301228.XSHE', '688308.XSHG', '300652.XSHE', '920870.XSHE',
        '301189.XSHE', '000973.XSHE', '300131.XSHE', '688031.XSHG', '600490.XSHG',
        '301165.XSHE', '300539.XSHE', '603019.XSHG', '600418.XSHG', '920418.XSHE',
    ],
    "universe_index": "000300.XSHG",  # universe_source="index" 时使用
    
    # ---- 因子窗口 ----
    "ma_short": 10,
    "ma_mid": 30,
    "ma_long": 60,
    "atr_period": 14,
    "volume_ma_period": 20,
    "rsi_period": 14,
    "mom_lookback": 60,
    
    # ---- 入场阈值 (v1 调优后) ----
    "atr_threshold": 0.08,           # ATR/close > 0.08
    "vol_threshold": 1.4,            # 量比 > 1.4
    "mom_threshold": 0.12,           # 60日动量 > 12%
    "rsi_upper": 60,                  # RSI(14) < 60
    "entry_score_threshold": 0.5,     # 加权评分 >= 0.5 (要求多头排列0.3 + 至少任一其他)
    
    # ---- 出场阈值 ----
    "fixed_stop_pct": 0.13,          # 固定止损 -13%
    "trailing_stop_pct": 0.09,       # 移动止损 -9%
    "max_holding_days": 45,           # 最大持仓 45 天
    "rsi_overbought": 80,             # RSI > 80 超买卖出
    
    # ---- 仓位控制 ----
    "target_holdings": 12,            # 目标持仓 12 只
    "max_single_weight": 0.10,        # 单票最大 10%
    "max_industry_concentration": 0.30,  # 行业集中度 <= 30%
    "max_turnover_per_rebalance": 0.30,  # 单次换手 <= 30%
    "cash_reserve": 0.02,             # 现金保留 2%
    
    # ---- 调仓频率 ----
    "rebalance_freq_days": 5,
    
    # ---- 调度时间 ----
    "signal_time": "14:55",
    "execute_time": "09:30",
}

def initialize(context):
    """
    策略初始化
    """
    set_benchmark(PARAMS["universe_index"])
    set_option("use_real_price", True)
    
    # 手续费/印花税
    set_order_cost(OrderCost(
        open_tax=0,
        close_tax=0.001,             # 卖出印花税千一
        open_commission=0.0003,
        close_commission=0.0003,
        close_today_commission=0,
        min_commission=5
    ), type="stock")
    
    set_slippage(FixedSlippage(0.0005))  # 0.05% 滑点
    log.set_level("order", "error")
    
    # ---- 全局状态 ----
    g.params = PARAMS
    g.universe = []              # 候选池
    g.holdings = {}              # 持仓: {stock: {entry_price, entry_date, highest_close, holding_days, score}}
    g.industry_map = {}          # 行业映射
    g.rebalance_counter = 0
    g.signal_pending = []         # 待执行信号
    g.refresh_done = False
    
    # 日程调度
    # 14:55 生成信号, 09:30 执行
    run_daily(refresh_universe, time="09:00")
    run_daily(generate_signals, time=PARAMS["signal_time"])
    run_daily(execute_pending, time=PARAMS["execute_time"])
    
    log.info("=" * 60)
    log.info("=== 多因子趋势波段策略 初始化完成 ===")
    log.info("=" * 60)

def refresh_universe(context):
    """
    09:00 盘前: 刷新候选池
    根据 universe_source 选择: 静态测试集 或 HS300动态池

    注意: 这里只刷新股票池, 不递增 rebalance_counter
    调仓判断统一在 generate_signals (14:55) 中进行
    """
    p = g.params
    if p.get("universe_source", "static") == "static":
        # 使用静态测试集 (top300.md)
        raw = list(p.get("static_universe", []))
        log.info("[%s] 使用静态测试集: %d 只" %
                 (context.current_dt.strftime("%Y-%m-%d"), len(raw)))
    else:
        # 使用 HS300 动态池
        raw = get_index_stocks(p["universe_index"], date=context.previous_date)
        log.info("[%s] HS300 成分股: %d" %
                 (context.current_dt.strftime("%Y-%m-%d"), len(raw)))

    g.universe = filter_universe(raw, context)
    g.industry_map = get_industry_map(g.universe)
    g.refresh_done = True
    log.info("[%s] 候选池: %d" %
             (context.current_dt.strftime("%Y-%m-%d"), len(g.universe)))

# ============================================================
# 2. 因子计算
# ============================================================

def calc_factors(stock, n=70):
    """
    计算单只股票的多因子 (用于信号生成)
    返回 dict 或 None
    """
    p = g.params
    try:
        df = attribute_history(stock, n, "1d",
                              ["open", "close", "high", "low", "volume"],
                              skip_paused=True, df=True, fq="pre")
        if df is None or len(df) < p["ma_long"]:
            return None
        
        close = df["close"]
        high = df["high"]
        low = df["low"]
        vol = df["volume"]
        last_close = close.iloc[-1]
        if last_close <= 0 or np.isnan(last_close):
            return None
        
        # ---- MA10/30/60 ----
        ma_10 = close.tail(p["ma_short"]).mean()
        ma_30 = close.tail(p["ma_mid"]).mean()
        ma_60 = close.tail(p["ma_long"]).mean()
        
        # ---- ATR(14) ----
        tr1 = high - low
        tr2 = (high - close.shift(1)).abs()
        tr3 = (low - close.shift(1)).abs()
        tr = pd.DataFrame({"a": tr1, "b": tr2, "c": tr3}).max(axis=1)
        atr_14 = tr.tail(p["atr_period"]).mean()
        
        # ---- 量比 ----
        vol_ma_20 = vol.tail(p["volume_ma_period"]).mean()
        volume_ratio_20 = vol.iloc[-1] / vol_ma_20 if vol_ma_20 > 0 else 0
        
        # ---- RSI(14) ----
        delta = close.diff()
        gain = delta.clip(lower=0)
        loss = (-delta).clip(lower=0)
        avg_gain = gain.tail(p["rsi_period"]).mean()
        avg_loss = loss.tail(p["rsi_period"]).mean()
        if avg_loss == 0 or np.isnan(avg_loss):
            rsi_14 = 100.0
        else:
            rsi_14 = 100 - 100 / (1 + avg_gain / avg_loss)
        
        # ---- 60日动量 ----
        if len(close) >= p["mom_lookback"] + 1:
            mom_60 = close.iloc[-1] / close.iloc[-(p["mom_lookback"] + 1)] - 1
        else:
            mom_60 = 0
        
        return {
            "close": last_close,
            "ma_10": ma_10,
            "ma_30": ma_30,
            "ma_60": ma_60,
            "atr_14": atr_14,
            "volume_ratio_20": volume_ratio_20,
            "rsi_14": rsi_14,
            "mom_60": mom_60,
        }
    except Exception as e:
        log.warn("计算 %s 因子异常: %s" % (stock, str(e)))
        return None

def entry_score(f, p):
    """
    入场信号综合得分 (加权评分制)
    trend_strength: 0.3 (多头排列)
    atr_filter: 0.15 (波动过滤)
    volume_confirm: 0.1 (量能确认)
    momentum_filter: 0.25 (动量)
    rsi_filter: 0.2 (RSI不超买)
    """
    score = 0.0
    close = f.get("close")
    ma_10 = f.get("ma_10")
    ma_30 = f.get("ma_30")
    ma_60 = f.get("ma_60")
    atr_14 = f.get("atr_14")
    volume_ratio = f.get("volume_ratio_20")
    rsi_14 = f.get("rsi_14")
    mom_60 = f.get("mom_60")
    
    # 1. 多头排列 (0.3)
    if ma_10 > ma_30 > ma_60:
        score += 0.3
    
    # 2. ATR 波动过滤 (0.15): atr/close > 阈值
    if close > 0 and atr_14 > 0 and not np.isnan(atr_14):
        if atr_14 / close > p["atr_threshold"]:
            score += 0.15
    
    # 3. 量能确认 (0.1): volume_ratio > 1.4
    if volume_ratio > p["vol_threshold"]:
        score += 0.1
    
    # 4. 动量 (0.25): mom_60 > 12%
    if mom_60 > p["mom_threshold"]:
        score += 0.25
    
    # 5. RSI 不超买 (0.2): rsi_14 < 60
    if rsi_14 < p["rsi_upper"]:
        score += 0.2
    
    return score

def exit_decision(factors, holding, current_price, stock):
    """
    出场决策 (按权重优先级)
    1. 固定止损 (0.05) - 价格 < 入场价 * (1 - 13%)
    2. 移动止损 (0.45) - 价格 < 最高价 * (1 - 9%)
    3. 趋势反转 (0.0) - ma_10 < ma_30
    4. 时间止损 (0.4) - 持仓 >= 45 天
    5. RSI 超买 (0.1) - RSI > 80
    返回: (should_exit, reason)
    """
    p = g.params
    entry_price = holding.get("entry_price")
    highest_close = holding.get("highest_close", entry_price)
    holding_days = holding.get("holding_days", 0)
    
    if entry_price is None or np.isnan(entry_price):
        return False, None
    if highest_close is None or np.isnan(highest_close):
        highest_close = entry_price
    
    ma_10 = factors.get("ma_10")
    ma_30 = factors.get("ma_30")
    rsi_14 = factors.get("rsi_14")
    
    # 1. 固定止损
    if current_price < entry_price * (1 - p["fixed_stop_pct"]):
        return True, "fixed_stop"
    
    # 2. 移动止损
    if current_price < highest_close * (1 - p["trailing_stop_pct"]):
        return True, "trailing_stop"
    
    # 3. 趋势反转
    if ma_10 is not None and ma_30 is not None and not np.isnan(ma_10) and not np.isnan(ma_30):
        if ma_10 < ma_30:
            return True, "trend_reversal"
    
    # 4. 时间止损
    if holding_days >= p["max_holding_days"]:
        return True, "time_stop"
    
    # 5. RSI 超买
    if rsi_14 is not None and not np.isnan(rsi_14):
        if rsi_14 > p["rsi_overbought"]:
            return True, "rsi_overbought"
    
    return False, None

# ============================================================
# 3. 信号生成
# ============================================================

def generate_signals(context):
    """
    14:55 收盘后: 生成信号
    - 每 5 个交易日 (调仓日): 扫描候选池找入场 + 扫描持仓
    - 其他交易日: 只扫描持仓 (不新开仓, 但允许卖出)
    """
    p = g.params
    g.rebalance_counter += 1
    is_rebalance = (g.rebalance_counter % p["rebalance_freq_days"] == 0)

    log.info("=" * 60)
    log.info("[%s] 计数=%d, %s" % (
             context.current_dt.strftime("%Y-%m-%d"),
             g.rebalance_counter,
             "调仓日" if is_rebalance else "持仓维护"))

    # 1. 每天扫描持仓 (更新状态 + 卖出信号)
    pending_sell = scan_holdings(context)

    # 2. 调仓日才扫描入场
    pending_buy = []
    if is_rebalance and g.refresh_done:
        pending_buy = scan_entry_signals(context)
    elif not is_rebalance:
        log.info("非调仓日, 不开新仓")

    # 3. 合并信号 (卖优先)
    g.signal_pending = pending_sell + pending_buy
    if g.signal_pending:
        log.info("信号汇总: %d 条 (卖=%d, 买=%d)" % (
                 len(g.signal_pending), len(pending_sell), len(pending_buy)))
    else:
        log.info("无信号, 维持当前状态")

def scan_holdings(context):
    """
    扫描所有持仓, 返回卖出信号
    """
    p = g.params
    pending = []
    
    for stock in list(g.holdings.keys()):
        h = g.holdings[stock]
        if stock not in context.portfolio.positions:
            del g.holdings[stock]
            continue
        
        try:
            factors = calc_factors(stock, n=70)
            if factors is None:
                continue
            
            current_price = factors["close"]
            h["highest_close"] = max(h.get("highest_close", h["entry_price"]), current_price)
            
            # 更新持仓天数
            entry_date = h.get("entry_date")
            if entry_date is not None:
                held_days = (context.current_dt.date() - entry_date.date()).days
            else:
                held_days = 0
            h["holding_days"] = held_days
            
            should_exit, reason = exit_decision(factors, h, current_price, stock)
            if should_exit:
                pending.append([stock, "sell", reason, current_price])
                pnl = (current_price - h["entry_price"]) / h["entry_price"] * 100
                log.info("%s 离场: %s, 盈亏=%.2f%%, 持仓=%d日" % (
                         stock, reason, pnl, held_days))
        except Exception as e:
            log.warn("扫描持仓 %s 异常: %s" % (stock, str(e)))
    
    return pending

def scan_entry_signals(context):
    """
    扫描候选池, 找入场信号
    """
    p = g.params
    pending = []
    
    if not g.universe:
        return pending
    
    # 计算所有候选股的因子和得分
    scored = []
    for stock in g.universe:
        if stock in g.holdings:
            continue  # 已持仓跳过
        factors = calc_factors(stock, n=70)
        if factors is None:
            continue
        score = entry_score(factors, p)
        if score >= p["entry_score_threshold"]:
            scored.append((stock, score, factors["close"]))
    
    log.info("候选池 %d 只, 通过信号阈值(>=%.2f)的有 %d 只" % (
             len(g.universe), p["entry_score_threshold"], len(scored)))
    
    # 按得分降序
    scored.sort(key=lambda x: x[1], reverse=True)
    
    # 取前 target_holdings 个, 加上已持仓 = 总不超过 target_holdings * 1.5
    available = p["target_holdings"] - len(g.holdings)
    if available <= 0:
        log.info("已满仓, 不开新仓")
        return pending
    
    candidates = scored[:available]
    log.info("调仓: 候选 %d, 可开仓 %d" % (len(candidates), available))
    
    for stock, score, price in candidates:
        pending.append([stock, "buy", "信号触发(score=%.2f)" % score, price])
        log.info("%s 入场信号: 价=%.2f, score=%.2f" % (stock, price, score))
    
    return pending

# ============================================================
# 4. 交易执行
# ============================================================

def execute_pending(context):
    """
    09:30 开盘: 执行昨日 14:55 生成的信号
    """
    if not g.signal_pending:
        return
    
    log.info("=" * 60)
    log.info("[%s] 09:30 执行 %d 条信号" % (
             context.current_dt.strftime("%Y-%m-%d"), len(g.signal_pending)))
    
    for sig in g.signal_pending:
        stock, action = sig[0], sig[1]
        if action == "buy":
            reason = sig[2] if len(sig) > 2 else ""
            do_buy(context, stock, reason)
        elif action in ["sell", "stop", "trend", "time"]:
            reason = sig[2] if len(sig) > 2 else "sell"
            do_sell(context, stock, reason)
    
    g.signal_pending = []
    g.refresh_done = False

def do_buy(context, stock, reason=""):
    """
    执行买入: 根据目标持仓数量 + 单票权重, 计算股数
    """
    p = g.params
    if stock in g.holdings:
        return

    total_value = context.portfolio.total_value
    max_per_stock = total_value * p["max_single_weight"]
    target_count = p["target_holdings"]
    per_target = (total_value * (1 - p["cash_reserve"])) / max(target_count, 1)

    target_value = min(max_per_stock, per_target)

    # 应用行业集中度约束: 计算同行业已持仓总价值
    ind = g.industry_map.get(stock, "unknown")
    industry_value = 0
    cd = get_current_data()
    for s in g.holdings:
        if g.industry_map.get(s, "unknown") != ind:
            continue
        d_s = cd.get(s)
        if d_s is not None and d_s.last_price > 0:
            industry_value += g.holdings[s].get("shares", 0) * d_s.last_price
        else:
            industry_value += g.holdings[s].get("shares", 0) * g.holdings[s].get("entry_price", 0)

    if industry_value + target_value > total_value * p["max_industry_concentration"]:
        log.info("行业约束排除: %s (行业=%s, 行业已用=%.0f)" %
                 (stock, ind, industry_value))
        return

    # 获取开盘价
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
        log.warn("价格异常: %s" % stock)
        return

    # 计算可买股数 (100 股整数倍)
    available_cash = context.portfolio.available_cash
    actual_value = min(target_value, available_cash * 0.95)
    if actual_value < 1000:
        log.warn("资金不足, 放弃 %s" % stock)
        return

    shares = int(actual_value // open_price // 100 * 100)
    if shares < 100:
        log.warn("资金不足以买1手: %s, 需要>=%.0f" % (stock, open_price * 100))
        return

    # 科创板需限价单
    if stock.startswith("688"):
        limit_price = min(open_price * 1.005, 9999.99)
        order_result = order(stock, shares, LimitOrderStyle(limit_price))
    else:
        order_result = order_value(stock, shares * open_price)

    if order_result is None:
        log.warn("下单失败: %s" % stock)
        return

    # 更新状态
    g.holdings[stock] = {
        "entry_price": open_price,
        "entry_date": context.current_dt,
        "highest_close": open_price,
        "holding_days": 0,
        "shares": shares,
        "reason": reason,
    }
    log.info(">>> 买入 %s: %d股, 开盘价=%.2f, 金额=%.0f" % (
             stock, shares, open_price, shares * open_price))

def do_sell(context, stock, reason=""):
    """
    执行卖出: 全数清仓该股
    """
    if stock not in g.holdings:
        return
    h = g.holdings[stock]
    shares = h.get("shares", 0)
    if shares <= 0 and stock in context.portfolio.positions:
        shares = context.portfolio.positions[stock].closeable_amount
    if shares <= 0:
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
    
    cd = get_current_data()
    d = cd.get(stock)
    current_price = d.last_price if d and d.last_price > 0 else h["entry_price"]
    pnl = (current_price - h["entry_price"]) / h["entry_price"] * 100
    held = h.get("holding_days", 0)
    log.info(">>> 卖出 %s: %d股, 价=%.2f, 盈亏=%.2f%%, 持仓=%d日, 原因=%s" % (
             stock, shares, current_price, pnl, held, reason))
    del g.holdings[stock]

# ============================================================
# 5. 工具函数
# ============================================================

def filter_universe(raw_list, context):
    """
    过滤候选池: 排除停牌 + 上市不足 60 日 + 收盘价异常
    """
    out = []
    for s in raw_list:
        try:
            hist = attribute_history(s, 60, "1d", ["close"],
                                    skip_paused=True, df=True, fq="pre")
            if hist is None or len(hist) < 60:
                continue
            close = hist["close"].iloc[-1]
            if np.isnan(close) or close <= 0:
                continue
            out.append(s)
        except Exception:
            continue
    return out


def get_industry_map(stock_list):
    """
    获取股票-行业映射 (申万一级 sw_l1)
    """
    if not stock_list:
        return {}
    try:
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
