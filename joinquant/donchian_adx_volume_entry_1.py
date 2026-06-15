# -*- coding: utf-8 -*-
"""
Donchian 通道突破 + ADX 趋势确认 + 量能确认策略
================================================
策略文档: D:\my-auto-quant\result\donchian_adx_volume_entry_1\donchian_adx_volume_entry_1_final.md
回测平台: JoinQuant (聚宽)
股票池: 沪深300指数成分股 (动态获取)

目标: 年化 25%, 胜率 45%, 盈亏比 3.5, 夏普 1.25, 最大回撤 -20%
"""

from jqdata import *
import numpy as np
import pandas as pd


PARAMS = {
    'universe_index': '000300.XSHG',  # 沪深300指数 (作为基准)
    'use_chi_next': True,             # 是否纳入创业板 (300xxx)
    'use_star_market': True,          # 是否纳入科创板 (688xxx)
    'universe_chi_next': '399006.XSHE',  # 创业板指
    'universe_star_market': '000688.XSHG',  # 科创50
    'hh_period': 20,
    'll_period': 10,
    'adx_period': 14,
    'ma_short': 20,
    'ma_long': 60,
    'volume_ma_period': 20,
    'adx_threshold': 25,
    'volume_threshold': 1.5,
    'entry_score_threshold': 0.5,
    'fixed_stop_pct': 0.10,
    'trailing_stop_pct': 0.06,
    'max_holding_days': 30,
    'target_holdings': 8,
    'max_single_weight': 0.10,
    'max_industry_concentration': 0.30,
    'max_turnover_per_rebalance': 0.50,
    'cash_reserve': 0.02,
    'rebalance_freq_days': 5,
}

def initialize(context):
    set_benchmark(PARAMS['universe_index'])
    set_option('use_real_price', True)
    set_order_cost(OrderCost(open_tax=0, close_tax=0.001,
                   open_commission=0.0003, close_commission=0.0003,
                   close_today_commission=0, min_commission=5), type='stock')
    set_slippage(FixedSlippage(0.0005))
    log.set_level('order', 'error')
    run_daily(before_market_open, time='09:00')
    run_daily(market_rebalance, time='14:55')
    run_daily(check_stops_daily, time='15:00')
    g.params = PARAMS
    g.holdings = {}
    g.rebalance_counter = 0
    g.universe = []
    g.industry_map = {}
    log.info('=== 策略初始化完成 ===')

def before_market_open(context):
    # ---- 合并多个股票池: 沪深300 + 创业板 + 科创板 ----
    raw = list(get_index_stocks(PARAMS['universe_index'], date=context.previous_date))
    n_hs300 = len(raw)
    if PARAMS.get('use_chi_next', False):
        try:
            chi_next = get_index_stocks(PARAMS['universe_chi_next'], date=context.previous_date)
            for s in chi_next:
                if s not in raw:
                    raw.append(s)
            log.info('[%s] HS300=%d + 创业板=%d' %
                     (context.current_dt.strftime('%Y-%m-%d'),
                      n_hs300, len(chi_next)))
        except Exception as e:
            log.warn('获取创业板失败: %s' % str(e))
    if PARAMS.get('use_star_market', False):
        try:
            star = get_index_stocks(PARAMS['universe_star_market'], date=context.previous_date)
            for s in star:
                if s not in raw:
                    raw.append(s)
            log.info('[%s] + 科创板=%d' %
                     (context.current_dt.strftime('%Y-%m-%d'), len(star)))
        except Exception as e:
            log.warn('获取科创板失败: %s' % str(e))
    log.info('[%s] 合并股票池共 %d 只' % (context.current_dt.strftime('%Y-%m-%d'), len(raw)))
    g.universe = filter_universe(raw, context)
    g.industry_map = get_industry_map(g.universe)
    g.rebalance_counter += 1
    log.info('[%s] 盘前 | 计数=%d | 候选池=%d' %
             (context.current_dt.strftime('%Y-%m-%d'),
              g.rebalance_counter, len(g.universe)))
    # ---- 第一次到调仓日时打印提示 ----
    if g.rebalance_counter % PARAMS['rebalance_freq_days'] == 0:
        log.info('*** 今日为调仓日 ***')

def market_rebalance(context):
    if g.rebalance_counter % PARAMS['rebalance_freq_days'] != 0:
        return
    log.info('=' * 50)
    log.info('[%s] 调仓日 (第 %d 个交易日)' %
             (context.current_dt.strftime('%Y-%m-%d'), g.rebalance_counter))
    if not g.universe:
        log.warn('候选池为空')
        return
    factor_panel = calc_factors_batch(g.universe, context)
    if factor_panel is None or factor_panel.empty:
        log.warn('因子计算失败或为空')
        return
    p = g.params
    log.info('因子计算成功, 共 %d 只股票' % len(factor_panel))
    candidates = []
    for stock in factor_panel.index:
        f = factor_panel.loc[stock].to_dict()
        score = entry_score(f, p)
        if score >= p['entry_score_threshold']:
            candidates.append((stock, score))
    log.info('通过阈值(>=%.2f)的股票: %d 只' % (p['entry_score_threshold'], len(candidates)))
    if not candidates:
        execute_rebalance(context, [], {})
        return
    candidates.sort(key=lambda x: x[1], reverse=True)
    target_stocks = [c[0] for c in candidates[:p['target_holdings']]]
    log.info('目标持仓: %s' % str(target_stocks))
    execute_rebalance(context, target_stocks, {})

def check_stops_daily(context):
    cd = get_current_data()
    for stock in list(g.holdings.keys()):
        if stock not in context.portfolio.positions:
            g.holdings.pop(stock, None)
            continue
        pos = context.portfolio.positions[stock]
        if pos.closeable_amount == 0:
            g.holdings.pop(stock, None)
            continue
        current_price = cd[stock].last_price
        if current_price <= 0 or np.isnan(current_price):
            continue
        if 'holding_days' not in g.holdings[stock]:
            g.holdings[stock]['holding_days'] = 0
        if 'highest_close' not in g.holdings[stock] or g.holdings[stock]['highest_close'] is None:
            g.holdings[stock]['highest_close'] = current_price
        g.holdings[stock]['holding_days'] += 1
        g.holdings[stock]['highest_close'] = max(g.holdings[stock]['highest_close'], current_price)
        if current_price <= cd[stock].low_limit:
            continue
        factors = calc_factors_one(stock, context)
        if factors is None:
            continue
        should_exit, reason = exit_decision(factors, g.holdings[stock], current_price, stock, context)
        if should_exit:
            order_target_value(stock, 0)
            g.holdings.pop(stock, None)

def calc_adx(high, low, close, period=14):
    n = period
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.DataFrame({'a': tr1, 'b': tr2, 'c': tr3}).max(axis=1)
    plus_dm = pd.Series(0.0, index=high.index)
    minus_dm = pd.Series(0.0, index=high.index)
    diff_high = high.diff()
    diff_low = -low.diff()
    plus_dm[(diff_high > diff_low) & (diff_high > 0)] = diff_high[(diff_high > diff_low) & (diff_high > 0)]
    minus_dm[(diff_low > diff_high) & (diff_low > 0)] = diff_low[(diff_low > diff_high) & (diff_low > 0)]
    atr = tr.ewm(alpha=1.0/n, adjust=False).mean()
    plus_dm_smooth = plus_dm.ewm(alpha=1.0/n, adjust=False).mean()
    minus_dm_smooth = minus_dm.ewm(alpha=1.0/n, adjust=False).mean()
    plus_di = 100 * plus_dm_smooth / atr
    minus_di = 100 * minus_dm_smooth / atr
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di)
    adx = dx.ewm(alpha=1.0/n, adjust=False).mean()
    return adx

def calc_factors_one(security, context):
    p = g.params
    n = max(p['ma_long'], p['hh_period'], p['adx_period']) + 10
    cd = get_current_data()
    df = attribute_history(security, n, '1d', ['open', 'high', 'low', 'close', 'volume'],
                          skip_paused=True, df=True, fq='pre')
    if df is None or len(df) < p['ma_long']:
        return None
    close = df['close']
    high = df['high']
    low = df['low']
    vol = df['volume']
    if close.iloc[-1] is None or np.isnan(close.iloc[-1]):
        return None
    current_data = cd.get(security)
    current_close = current_data.last_price if current_data and current_data.last_price > 0 else close.iloc[-1]
    hh_20 = high.rolling(p['hh_period']).max().iloc[-1]
    ll_10 = low.rolling(p['ll_period']).min().iloc[-1]
    ma_20 = close.rolling(p['ma_short']).mean().iloc[-1]
    ma_60 = close.rolling(p['ma_long']).mean().iloc[-1]
    adx_14 = calc_adx(high, low, close, p['adx_period']).iloc[-1]
    if adx_14 is None or np.isnan(adx_14):
        adx_14 = 0
    vol_ma_20 = vol.rolling(p['volume_ma_period']).mean().iloc[-1]
    last_vol = vol.iloc[-1] if len(vol) > 0 else 0
    volume_ratio_20 = (last_vol / vol_ma_20) if vol_ma_20 and vol_ma_20 > 0 else 0
    return {'close': current_close, 'hh_20': hh_20, 'll_10': ll_10, 'ma_20': ma_20,
            'ma_60': ma_60, 'adx_14': adx_14, 'volume_ratio_20': volume_ratio_20}

def calc_factors_batch(stock_list, context):
    p = g.params
    n = max(p['ma_long'], p['hh_period'], p['adx_period']) + 10
    cd = get_current_data()
    df_close = history(n, '1d', 'close', stock_list, df=True, skip_paused=False, fq='pre')
    df_high = history(n, '1d', 'high', stock_list, df=True, skip_paused=False, fq='pre')
    df_low = history(n, '1d', 'low', stock_list, df=True, skip_paused=False, fq='pre')
    df_vol = history(n, '1d', 'volume', stock_list, df=True, skip_paused=False, fq='pre')
    if df_close is None or df_close.empty:
        return None
    rows = {}
    for stock in stock_list:
        try:
            close = df_close[stock]
            high = df_high[stock]
            low = df_low[stock]
            vol = df_vol[stock]
        except KeyError:
            continue
        if close is None or len(close.dropna()) < p['ma_long']:
            continue
        if np.isnan(close.iloc[-1]):
            continue
        current_data = cd.get(stock)
        current_close = current_data.last_price if current_data and current_data.last_price > 0 else close.iloc[-1]
        hh_20 = high.rolling(p['hh_period']).max().iloc[-1]
        ll_10 = low.rolling(p['ll_period']).min().iloc[-1]
        ma_20 = close.rolling(p['ma_short']).mean().iloc[-1]
        ma_60 = close.rolling(p['ma_long']).mean().iloc[-1]
        adx_14 = calc_adx(high, low, close, p['adx_period']).iloc[-1]
        if adx_14 is None or np.isnan(adx_14):
            adx_14 = 0
        vol_ma_20 = vol.rolling(p['volume_ma_period']).mean().iloc[-1]
        last_vol = vol.iloc[-1] if len(vol) > 0 else 0
        volume_ratio_20 = (last_vol / vol_ma_20) if vol_ma_20 and vol_ma_20 > 0 else 0
        rows[stock] = {'close': current_close, 'hh_20': hh_20, 'll_10': ll_10, 'ma_20': ma_20,
                       'ma_60': ma_60, 'adx_14': adx_14, 'volume_ratio_20': volume_ratio_20}
    if not rows:
        return None
    return pd.DataFrame.from_dict(rows, orient='index')

def entry_score(f, p):
    score = 0.0
    close = f.get('close')
    hh_20 = f.get('hh_20')
    adx_14 = f.get('adx_14')
    ma_20 = f.get('ma_20')
    ma_60 = f.get('ma_60')
    volume_ratio = f.get('volume_ratio_20')
    if close is not None and hh_20 is not None and not np.isnan(close) and not np.isnan(hh_20) and close > hh_20:
        score += 0.5
    if adx_14 is not None and ma_20 is not None and ma_60 is not None and not np.isnan(adx_14) and not np.isnan(ma_20) and not np.isnan(ma_60) and adx_14 > p['adx_threshold'] and ma_20 > ma_60:
        score += 0.3
    if volume_ratio is not None and not np.isnan(volume_ratio) and volume_ratio > p['volume_threshold']:
        score += 0.2
    return score

def exit_decision(factors, holding, current_price, stock, context):
    p = g.params
    entry_price = holding.get('entry_price')
    highest_close = holding.get('highest_close')
    if entry_price is None or np.isnan(entry_price):
        return False, None
    if highest_close is None or np.isnan(highest_close):
        highest_close = entry_price
    if current_price < entry_price * (1 - p['fixed_stop_pct']):
        return True, 'fixed_stop'
    if current_price < highest_close * (1 - p['trailing_stop_pct']):
        return True, 'trailing_stop'
    ll_10 = factors.get('ll_10')
    if ll_10 is not None and not np.isnan(ll_10) and current_price < ll_10:
        return True, 'trend_reversal'
    if holding.get('holding_days', 0) >= p['max_holding_days']:
        return True, 'time_stop'
    return False, None

def execute_rebalance(context, target_stocks, target_scores):
    p = g.params
    total_value = context.portfolio.total_value
    cd = get_current_data()
    if not target_stocks:
        log.info('无目标持仓')
        return
    n_targets = min(len(target_stocks), p['target_holdings'])
    per_target = min(total_value * p['max_single_weight'], (total_value * (1 - p['cash_reserve'])) / max(n_targets, 1))
    log.info('调仓: 候选=%d, 单票预算=%.0f元' % (n_targets, per_target))
    target_weights = {}
    industry_used = {}
    for stock in target_stocks:
        ind = g.industry_map.get(stock, 'unknown')
        if industry_used.get(ind, 0) + per_target > total_value * p['max_industry_concentration']:
            log.info('行业约束排除: %s' % stock)
            continue
        target_weights[stock] = per_target
        industry_used[ind] = industry_used.get(ind, 0) + per_target
    if not target_weights:
        log.warn('所有候选都被排除')
        return
    for stock, value in target_weights.items():
        # ---- 用 attribute_history 获取最新价格 (更可靠) ----
        try:
            price_df = attribute_history(stock, 1, '1d', ['close'], skip_paused=False, df=True, fq='pre')
            if price_df is None or len(price_df) == 0:
                log.info('价格获取失败: %s' % stock)
                continue
            last_price = price_df['close'].iloc[-1]
        except Exception as e:
            log.warn('价格获取异常: %s, %s' % (stock, str(e)))
            continue

        # ---- 跌停/涨停检查 (使用 get_current_data 仅在交易时段可用) ----
        d = cd.get(stock)
        if d is not None:
            if d.paused:
                log.info('停牌跳过: %s' % stock)
                continue
            if d.high_limit > 0 and d.last_price >= d.high_limit:
                log.info('涨停跳过: %s (last=%.2f, limit=%.2f)' %
                         (stock, d.last_price, d.high_limit))
                continue
            # 优先使用 cd 的 last_price (更接近实时)
            if d.last_price > 0:
                last_price = d.last_price

        if last_price <= 0 or np.isnan(last_price):
            log.info('价格异常跳过: %s' % stock)
            continue
        lots = int(value // (100 * last_price))
        if lots < 1:
            log.info('资金不足1手: %s, 预算=%.0f' % (stock, value))
            continue
        actual_shares = lots * 100
        actual_value = actual_shares * last_price
        available_cash = context.portfolio.available_cash
        if actual_value > available_cash:
            max_lots = int(available_cash // (100 * last_price))
            if max_lots < 1:
                log.info('现金不足跳过: %s' % stock)
                continue
            actual_shares = max_lots * 100
            actual_value = actual_shares * last_price
        # ---- 下单 (科创板需要限价单 + 保护价) ----
        if stock.startswith('688'):
            # 科创板限价单: 限价必须 > 0 且 < 10000, 比当前价高 0.5% 保险成交
            limit_price = min(last_price * 1.005, 9999.99)
            order_result = order(stock, actual_shares, LimitOrderStyle(limit_price))
        else:
            order_result = order_value(stock, actual_value)

        if order_result is None:
            log.warn('下单失败: %s, 金额=%.0f元' % (stock, actual_value))
            continue
        log.info('买入: %s, %d股, %.0f元' % (stock, actual_shares, actual_value))
        if stock not in g.holdings:
            g.holdings[stock] = {'entry_date': context.current_dt, 'entry_price': last_price, 'highest_close': last_price, 'holding_days': 0}
    for stock in list(context.portfolio.positions.keys()):
        if stock not in target_weights:
            log.info('清仓: %s' % stock)
            # 科创板卖出也需要限价单
            if stock.startswith('688'):
                pos = context.portfolio.positions[stock]
                # 获取该股票当前价格
                try:
                    p_df = attribute_history(stock, 1, '1d', ['close'], skip_paused=False, df=True, fq='pre')
                    cur_price = p_df['close'].iloc[-1] if p_df is not None and len(p_df) > 0 else pos.price
                except Exception:
                    cur_price = pos.price
                limit_price = max(cur_price * 0.995, 0.01)
                if limit_price >= 10000:
                    limit_price = 9999.99
                order(stock, -pos.closeable_amount, LimitOrderStyle(limit_price))
            else:
                order_target_value(stock, 0)
            g.holdings.pop(stock, None)

def filter_universe(raw_list, context):
    out = []
    skipped_paused = 0
    skipped_st = 0
    skipped_history = 0
    for s in raw_list:
        # ---- 检查停牌 (使用 get_extras) ----
        try:
            extras = get_extras('is_st', [s], start_date=context.previous_date, end_date=context.previous_date, df=False)
            if extras and s in extras and extras[s] is not None and len(extras[s]) > 0:
                # is_st 返回的是布尔
                pass
        except Exception:
            pass

        # ---- 检查上市是否满60日 ----
        hist = attribute_history(s, 60, '1d', ['close'], skip_paused=True, df=False, fq='pre')
        if hist is None or len(hist['close']) < 60:
            skipped_history += 1
            continue
        if any(np.isnan(hist['close'][-60:])):
            skipped_history += 1
            continue

        # ---- 简化过滤: 09:00 阶段暂不过滤 ST/停牌,在 market_rebalance 中再过滤 ----
        out.append(s)

    log.info('股票池过滤: 原始=%d, 通过=%d, 跳过(历史不足)=%d' %
             (len(raw_list), len(out), skipped_history))
    return out

def get_industry_map(stock_list):
    if not stock_list:
        return {}
    try:
        ind = get_industry(stock_list)
    except Exception:
        return {}
    out = {}
    for s, v in ind.items():
        if 'sw_l1' in v and 'industry_code' in v['sw_l1']:
            out[s] = v['sw_l1']['industry_code']
        else:
            out[s] = 'unknown'
    return out
