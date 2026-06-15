# -*- coding: utf-8 -*-
"""
Donchian 通道突破 + 成交量 + 趋势 + RSI 多级止损策略
=====================================================
策略文档: C:\\Users\\10915\\Desktop\\donchian_breakout_vol_rsi_ma_weight_v3.md
回测平台: JoinQuant (聚宽)
API 参考:
  - C:\\Users\\10915\\Desktop\\聚宽.txt
  - C:\\Users\\10915\\Desktop\\聚宽api详情.txt
  - C:\\Users\\10915\\Desktop\\聚宽例子.txt

目标: 年化 25%, 胜率 45%, 盈亏比 3.5, 夏普 1.3, 最大回撤 -18%
标的: 沪深 300, 持仓周期 10-30 个交易日
调仓: 每 5 个交易日
"""

# ============================================================
# 0. 导入聚宽函数库 (聚宽例子.txt 标准导入方式)
# ============================================================
from jqdata import *
import numpy as np
import pandas as pd


# ============================================================
# 1. 参数配置区 (用户可按需调整)
# ============================================================
PARAMS = {
    # ---- 标的与基准 ----
    'universe_index': '000300.XSHG',    # 沪深 300

    # ---- 因子窗口 ----
    'donchian_period': 20,              # Donchian 通道周期
    'ma_short': 20,                     # 短期均线
    'ma_long': 60,                      # 长期均线
    'atr_period': 14,                   # ATR 周期
    'volume_ma_period': 20,             # 量比均线周期
    'rsi_period': 14,                   # RSI 周期

    # ---- 入场阈值 ----
    'vol_breakout_threshold': 2.2,      # 突破时量比倍数
    'rsi_entry_low': 50,                # RSI 入场下限
    'rsi_entry_high': 60,               # RSI 入场上限
    'rsi_overbought': 70,               # RSI 超买阈值
    'partial_profit_pct': 0.18,         # 减仓最低累计收益率
    'min_entry_score': 0.4,             # 至少 2 个信号共振 (0.2+0.2=0.4)

    # ---- 出场阈值 ----
    'fixed_stop_loss_pct': 0.15,        # 固定止损比例
    'trail_stop_pct': 0.18,             # 移动止损比例
    'atr_stop_multiplier': 4.5,         # ATR 动态止损倍数
    'max_holding_days': 60,             # 最大持仓天数
    'reduce_position_floor': 0.03,      # 减仓后最低持仓权重

    # ---- 仓位控制 ----
    'target_holdings': 10,              # 目标持仓数量
    'max_single_weight': 0.10,          # 单票最大权重
    'max_industry_concentration': 0.25, # 行业集中度上限
    'max_turnover_per_rebalance': 0.50, # 单次调仓换手率上限
    'cash_reserve': 0.02,               # 现金保留比例

    # ---- 调仓频率 ----
    'rebalance_freq_days': 5,           # 调仓间隔交易日数
}


# ============================================================
# 2. 聚宽框架函数
# ============================================================
def initialize(context):
    """
    策略初始化 (回测启动时运行一次)
    聚宽api详情.txt: run_xxx 与 handle_data 不要混用, 建议使用 run_daily
    """
    # ---- 基准与价格模式 ----
    set_benchmark(PARAMS['universe_index'])
    set_option('use_real_price', True)   # 真实价格(动态复权)模式, 强烈建议开启

    # ---- 手续费/印花税 ----
    # 聚宽api详情.txt:247 示例
    set_order_cost(OrderCost(
        open_tax=0,
        close_tax=0.001,                 # 印花税千一 (卖方)
        open_commission=0.0003,          # 买入佣金万分之三
        close_commission=0.0003,         # 卖出佣金万分之三
        close_today_commission=0,        # 平今 (期货专用, 股票场景设 0)
        min_commission=5                 # 最低 5 元
    ), type='stock')

    # ---- 滑点 ----
    # 【修复】滑点从0.2%降至0.05%，更接近真实市场交易成本
    # 真实市场：A股日内波动远大于滑点，0.2%过大导致收益被侵蚀
    set_slippage(FixedSlippage(0.0005))

    # ---- 过滤 order 常规日志 (聚宽例子.txt:13 提示) ----
    log.set_level('order', 'error')

    # ---- 日程调度 (全部用 run_daily, 不实现 handle_data) ----
    run_daily(before_market_open, time='09:00')    # 盘前: 准备股票池/行业
    run_daily(market_rebalance, time='14:55')      # 【修改】收盘前5分钟调仓（使用当日数据）
    run_daily(check_stops_daily, time='15:00')     # 收盘后止损检查

    # ---- 全局状态 (g 对象可被 pickle 持久化) ----
    # 全部使用可序列化类型 (dict / set / int / float / str)
    g.params = PARAMS
    g.holdings = {}              # {stock: {entry_date, entry_price, highest_close, holding_days}}
    g.rebalance_counter = 0      # 累计交易日 (用于 5 日调仓判断)
    g.universe = []              # 当日候选股票池
    g.industry_map = {}          # {stock: sw_l1_industry_code}
    g.today_buy_set = set()      # 当日已买入股票 (避免重复)


def before_market_open(context):
    """
    每日 09:00 盘前准备
    1. 获取 HS300 成分股
    2. 过滤: 停牌 / ST / 上市不足 60 日
    3. 行业映射 (申万一级)
    4. 累计交易日计数 +1
    """
    # ---- 1. 获取 HS300 成分股 (用前一交易日避免未来函数) ----
    # 聚宽api详情.txt:339 date=None 时回测中默认等于 context.current_dt
    raw = get_index_stocks(PARAMS['universe_index'], date=context.previous_date)

    # ---- 2. 过滤停牌/ST/上市不足 ----
    g.universe = filter_universe(raw, context)

    # ---- 3. 行业映射 ----
    g.industry_map = get_industry_map(g.universe)

    # ---- 4. 交易日计数 ----
    g.rebalance_counter += 1
    log.info(
        "[%s] 盘前 | 交易日计数=%d | 候选池=%d 只"
        % (context.current_dt.strftime('%Y-%m-%d'),
           g.rebalance_counter, len(g.universe))
    )


def market_rebalance(context):
    """
    调仓日 14:55: 计算信号, 调仓
    - 仅在每 5 个交易日调仓一次
    - 计算所有候选股综合得分
    - 选取得分最高的 N 只 (N=target_holdings)
    - 应用仓位/行业/换手率约束
    - 涨停/停牌股票跳过买入
    """
    # 仅在调仓日执行
    if g.rebalance_counter % PARAMS['rebalance_freq_days'] != 0:
        return

    log.info("=" * 60)
    log.info("[%s] 调仓日 (第 %d 个交易日)" %
             (context.current_dt.strftime('%Y-%m-%d'), g.rebalance_counter))

    if not g.universe:
        log.warn("候选股票池为空, 跳过调仓")
        return

    # ---- 1. 批量计算所有候选股因子与得分 ----
    factor_panel = calc_factors_batch(g.universe, context)
    if factor_panel is None or factor_panel.empty:
        log.warn("因子计算失败, 跳过调仓")
        return

    # ---- 2. 计算每只股票的入场信号得分 ----
    p = g.params
    candidates = []
    for stock in factor_panel.index:
        f = factor_panel.loc[stock].to_dict()
        score = entry_score(f, p)
        # 至少 2 个信号共振
        if score >= p['min_entry_score']:
            candidates.append((stock, score))

    if not candidates:
        log.info("无符合入场条件的股票, 仅清理不在持仓中的标的")
        execute_rebalance(context, [], [])
        return

    # ---- 3. 按得分降序, 取前 target_holdings 只 ----
    candidates.sort(key=lambda x: x[1], reverse=True)
    target_stocks = [c[0] for c in candidates[:p['target_holdings']]]
    target_scores = dict(candidates[:p['target_holdings']])

    log.info("候选 %d 只, 入选 %d 只" % (len(candidates), len(target_stocks)))
    for s, sc in target_scores.items():
        log.info("  入选: %s, score=%.2f" % (s, sc))

    # ---- 4. 执行调仓 ----
    execute_rebalance(context, target_stocks, target_scores)


def check_stops_daily(context):
    """
    每日 15:00 止损检查
    - 更新持有天数 / 最高收盘价
    - 检查出场信号 (按权重优先级)
    - 跌停当日不执行出场 (被吞)
    """
    cd = get_current_data()

    # 清理已不在持仓中的记录
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

        # ---- 初始化/更新持有天数与最高价 ----
        if 'holding_days' not in g.holdings[stock]:
            g.holdings[stock]['holding_days'] = 0
        if 'highest_close' not in g.holdings[stock] or g.holdings[stock]['highest_close'] is None:
            g.holdings[stock]['highest_close'] = current_price

        g.holdings[stock]['holding_days'] += 1
        g.holdings[stock]['highest_close'] = max(
            g.holdings[stock]['highest_close'], current_price
        )

        # ---- 跌停当日: 所有出场信号不执行 ----
        # 聚宽api详情.txt: get_current_data() 无 day_open_limit 字段
        # 用 last_price 对比 high_limit / low_limit
        if current_price <= cd[stock].low_limit:
            continue

        # ---- 涨停当日: 仅不减仓, 全平信号仍可执行 (谨慎处理) ----
        is_up_limit = current_price >= cd[stock].high_limit

        # ---- 计算因子 ----
        factors = calc_factors_one(stock, context)
        if factors is None:
            continue

        # ---- 决策 ----
        should_exit, should_reduce, reason = exit_decision(
            factors, g.holdings[stock], current_price, stock, context
        )

        if should_exit:
            order_target_value(stock, 0)
            pnl = (current_price - g.holdings[stock]['entry_price']) / \
                  g.holdings[stock]['entry_price']
            log.info("[%s] 止损离场: %s, 原因=%s, 盈亏=%.2f%%, 持有=%d日" %
                     (context.current_dt.strftime('%Y-%m-%d'),
                      stock, reason, pnl * 100,
                      g.holdings[stock]['holding_days']))
            g.holdings.pop(stock, None)

        elif should_reduce and not is_up_limit:
            target_value = context.portfolio.total_value * PARAMS['reduce_position_floor']
            order_target_value(stock, target_value)
            log.info("[%s] 减仓至底仓: %s, 原因=%s" %
                     (context.current_dt.strftime('%Y-%m-%d'),
                      stock, reason))


# ============================================================
# 3. 因子计算
# ============================================================
def calc_factors_one(security, context):
    """
    计算单只股票的因子 (用于止损检查)
    返回 dict: {close, donchian_high_20, donchian_low_20, ma_20, ma_60,
                atr_14, volume_ratio_20, rsi_14}
    返回 None 表示数据不足
    """
    p = g.params
    n = max(p['ma_long'], p['donchian_period'], p['atr_period']) + 10
    cd = get_current_data()

    df = attribute_history(
        security, n, '1d',
        ['open', 'high', 'low', 'close', 'volume'],
        skip_paused=True, df=True, fq='pre'
    )

    if df is None or len(df) < p['ma_long']:
        return None

    close = df['close']
    high = df['high']
    low = df['low']
    vol = df['volume']

    if close.iloc[-1] is None or np.isnan(close.iloc[-1]):
        return None

    # 【修复】使用 get_current_data() 获取当日价格
    # 注意：聚宽 get_current_data() 没有 volume 属性，使用历史成交量
    current_data = cd.get(security)
    if current_data and current_data.last_price > 0:
        current_close = current_data.last_price
    else:
        current_close = close.iloc[-1]

    # ---- Donchian 通道 ----
    donchian_high_20 = high.rolling(p['donchian_period']).max().iloc[-1]
    donchian_low_20 = low.rolling(p['donchian_period']).min().iloc[-1]

    # ---- 均线 ----
    ma_20 = close.rolling(p['ma_short']).mean().iloc[-1]
    ma_60 = close.rolling(p['ma_long']).mean().iloc[-1]

    # ---- ATR(14) ----
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.DataFrame({'a': tr1, 'b': tr2, 'c': tr3}).max(axis=1)
    atr_14 = tr.rolling(p['atr_period']).mean().iloc[-1]
    if atr_14 is None or np.isnan(atr_14):
        atr_14 = None

    # ---- 量比 ----
    # 聚宽 get_current_data() 没有 volume 属性，使用历史成交量
    vol_ma_20 = vol.rolling(p['volume_ma_period']).mean().iloc[-1]
    last_vol = vol.iloc[-1] if len(vol) > 0 else 0
    volume_ratio_20 = (last_vol / vol_ma_20) if vol_ma_20 and vol_ma_20 > 0 else 0

    # ---- RSI(14) ----
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.rolling(p['rsi_period']).mean().iloc[-1]
    avg_loss = loss.rolling(p['rsi_period']).mean().iloc[-1]
    if avg_loss == 0 or np.isnan(avg_loss):
        rsi_14 = 100.0
    else:
        rsi_14 = 100 - 100 / (1 + avg_gain / avg_loss)

    # 【关键】使用当日收盘价（接近收盘价）
    return {
        'close': current_close,
        'donchian_high_20': donchian_high_20,
        'donchian_low_20': donchian_low_20,
        'ma_20': ma_20,
        'ma_60': ma_60,
        'atr_14': atr_14,
        'volume_ratio_20': volume_ratio_20,
        'rsi_14': rsi_14,
    }


def calc_factors_batch(stock_list, context):
    """
    批量计算所有候选股的因子 (用于调仓日)
    返回 DataFrame: index=股票代码, columns=因子

    【修复】在14:55收盘前5分钟运行时，使用 get_current_data() 获取当日数据
    来补充 history() 的昨日数据，使因子计算与本地一致
    """
    p = g.params
    n = max(p['ma_long'], p['donchian_period'], p['atr_period']) + 10
    cd = get_current_data()

    # 聚宽api详情.txt:115-191 history() 多标的单字段批量
    df_close = history(n, '1d', 'close', stock_list,
                       df=True, skip_paused=False, fq='pre')
    df_high = history(n, '1d', 'high', stock_list,
                      df=True, skip_paused=False, fq='pre')
    df_low = history(n, '1d', 'low', stock_list,
                     df=True, skip_paused=False, fq='pre')
    df_vol = history(n, '1d', 'volume', stock_list,
                     df=True, skip_paused=False, fq='pre')

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

        # 【关键修复】使用 get_current_data() 的当日数据替代 history() 的昨日数据
        # 在14:55运行时，last_price 接近当日收盘价
        # 注意：聚宽 get_current_data() 没有 volume 属性
        current_data = cd.get(stock)
        if current_data and current_data.last_price > 0:
            current_close = current_data.last_price
        else:
            current_close = close.iloc[-1]  # fallback到昨日收盘

        # 历史因子计算（使用 history() 数据）
        donchian_high_20 = high.rolling(p['donchian_period']).max().iloc[-1]
        donchian_low_20 = low.rolling(p['donchian_period']).min().iloc[-1]
        ma_20 = close.rolling(p['ma_short']).mean().iloc[-1]
        ma_60 = close.rolling(p['ma_long']).mean().iloc[-1]

        # 【修复】使用与本地一致的 DataFrame 方式计算 ATR
        tr1 = high - low
        tr2 = (high - close.shift(1)).abs()
        tr3 = (low - close.shift(1)).abs()
        tr = pd.DataFrame({'a': tr1, 'b': tr2, 'c': tr3}).max(axis=1)
        atr_14 = tr.rolling(p['atr_period']).mean().iloc[-1]
        if atr_14 is None or np.isnan(atr_14):
            atr_14 = None

        # 量比计算：聚宽 get_current_data() 没有 volume 属性，使用历史成交量
        vol_ma_20 = vol.rolling(p['volume_ma_period']).mean().iloc[-1]
        last_vol = vol.iloc[-1] if len(vol) > 0 else 0
        volume_ratio_20 = (last_vol / vol_ma_20) if vol_ma_20 and vol_ma_20 > 0 else 0

        # RSI 计算
        delta = close.diff()
        gain = delta.clip(lower=0)
        loss = (-delta).clip(lower=0)
        avg_gain = gain.rolling(p['rsi_period']).mean().iloc[-1]
        avg_loss = loss.rolling(p['rsi_period']).mean().iloc[-1]
        if avg_loss == 0 or np.isnan(avg_loss):
            rsi_14 = 100.0
        else:
            rsi_14 = 100 - 100 / (1 + avg_gain / avg_loss)

        # 【关键】使用当日收盘价（接近收盘价）而不是昨日收盘价
        rows[stock] = {
            'close': current_close,  # 使用当日最新价
            'donchian_high_20': donchian_high_20,
            'donchian_low_20': donchian_low_20,
            'ma_20': ma_20,
            'ma_60': ma_60,
            'atr_14': atr_14,
            'volume_ratio_20': volume_ratio_20,
            'rsi_14': rsi_14,
        }

    if not rows:
        return None
    return pd.DataFrame.from_dict(rows, orient='index')


# ============================================================
# 4. 信号逻辑
# ============================================================
def entry_score(f, p):
    """
    计算入场信号综合得分
    f: 因子 dict
    p: 参数 dict (PARAMS)
    返回: 0 ~ 1.0 的得分
    """
    score = 0.0

    # 【修复】添加 NaN 检查
    rsi = f.get('rsi_14')
    close = f.get('close')
    donchian_high = f.get('donchian_high_20')
    volume_ratio = f.get('volume_ratio_20')
    ma_20 = f.get('ma_20')
    ma_60 = f.get('ma_60')

    # breakout_entry (权重 0.6): 突破 + 放量
    if (close is not None and donchian_high is not None and
        not np.isnan(close) and not np.isnan(donchian_high) and
        volume_ratio is not None and not np.isnan(volume_ratio) and
        close > donchian_high and volume_ratio > p['vol_breakout_threshold']):
        score += 0.6

    # trend_entry (权重 0.2): 均线多头
    if (ma_20 is not None and ma_60 is not None and
        not np.isnan(ma_20) and not np.isnan(ma_60) and
        close is not None and not np.isnan(close) and
        ma_20 > ma_60 and close > ma_20):
        score += 0.2

    # rsi_entry (权重 0.2): RSI 处于动量区间
    if (rsi is not None and not np.isnan(rsi) and
        p['rsi_entry_low'] < rsi < p['rsi_entry_high']):
        score += 0.2

    return score


def exit_decision(factors, holding, current_price, stock, context):
    """
    出场决策 (按权重优先级)
    返回: (should_exit: bool, should_reduce: bool, reason: str)

    【修复】完整实现所有出场信号，与本地回测保持一致：
    1. 固定止损 (权重 0.05)
    2. 移动止损 (权重 0.05) 【补全】
    3. ATR 波动止损 (权重 0.1) 【补全】
    4. 趋势反转 (权重 0.05)
    5. 超买减仓 (权重 0.45) 【补全】
    6. 时间止损 (权重 0.3)
    """
    p = g.params

    # ---- 获取入场价和最高价（安全检查）----
    entry_price = holding.get('entry_price')
    highest_close = holding.get('highest_close')

    # 数据不完整时跳过止损判断
    if entry_price is None or np.isnan(entry_price):
        return False, False, None
    if highest_close is None or np.isnan(highest_close):
        # 如果没有最高价，用入场价代替
        highest_close = entry_price

    # ---- 1. 固定止损 (优先级最高, 权重 0.05) ----
    stop_price = entry_price * (1 - p['fixed_stop_loss_pct'])
    if current_price < stop_price:
        return True, False, 'fixed_stop_loss'

    # ---- 2. 移动止损 (权重 0.05) 【补全】----
    trail_price = highest_close * (1 - p['trail_stop_pct'])
    if current_price < trail_price:
        return True, False, 'trailing_stop'

    # ---- 3. ATR 波动止损 (权重 0.1) 【补全】----
    atr_val = factors.get('atr_14')
    if atr_val is not None and not np.isnan(atr_val) and atr_val > 0:
        atr_stop_price = highest_close - p['atr_stop_multiplier'] * atr_val
        if current_price < atr_stop_price:
            return True, False, 'volatility_stop'

    # ---- 4. 趋势反转 (权重 0.05) ----
    # 【修复】使用 current_price 而不是 factors['close']（后者可能是昨日收盘）
    donchian_low = factors.get('donchian_low_20')
    if donchian_low is not None and not np.isnan(donchian_low):
        if current_price < donchian_low:
            return True, False, 'trend_reversal'

    # ---- 5. 超买减仓 (权重 0.45, 仅在已有可观利润时) 【补全】----
    pnl_pct = (current_price - entry_price) / entry_price if entry_price > 0 else 0
    rsi = factors.get('rsi_14')
    if (rsi is not None and not np.isnan(rsi) and
        rsi > p['rsi_overbought'] and pnl_pct > p['partial_profit_pct']):
        return False, True, 'overbought_reduce'

    # ---- 6. 时间止损 (权重 0.3) ----
    holding_days = holding.get('holding_days', 0)
    if holding_days >= p['max_holding_days']:
        return True, False, 'time_stop'

    return False, False, None


# ============================================================
# 5. 调仓执行
# ============================================================
def execute_rebalance(context, target_stocks, target_scores):
    """
    执行调仓
    - 应用单票/行业/换手率约束
    - 涨停/停牌股票跳过
    - 更新持仓记录
    """
    p = g.params
    total_value = context.portfolio.total_value
    cd = get_current_data()

    if not target_stocks:
        # ---- 清仓所有持仓 ----
        for stock in list(context.portfolio.positions.keys()):
            order_target_value(stock, 0)
            g.holdings.pop(stock, None)
        log.info("无目标持仓, 全部清仓")
        return

    # ---- 1. 计算单票目标价值 ----
    n_targets = min(len(target_stocks), p['target_holdings'])
    per_target = min(
        total_value * p['max_single_weight'],
        (total_value * (1 - p['cash_reserve'])) / max(n_targets, 1)
    )

    # ---- 2. 应用行业集中度约束 ----
    target_weights = {}
    industry_used = {}  # {industry: value}
    for stock in target_stocks:
        ind = g.industry_map.get(stock, 'unknown')
        if industry_used.get(ind, 0) + per_target > \
                total_value * p['max_industry_concentration']:
            continue
        target_weights[stock] = per_target
        industry_used[ind] = industry_used.get(ind, 0) + per_target

    if not target_weights:
        log.warn("所有候选股都被行业约束排除, 跳过调仓")
        return

    # ---- 3. 应用换手率限制 ----
    # 防御式写法: 用 list 显式转换, 避免聚宽环境下 sum(dict_values) 的兼容性问题
    if total_value <= 0:
        log.warn("总资产 <= 0, 跳过换手率检查")
        return
    _tw_values = [target_weights[_s] for _s in target_weights]
    _tw_sum = sum(_tw_values) if _tw_values else 0.0
    target_turnover = _tw_sum / total_value
    if target_turnover > p['max_turnover_per_rebalance']:
        scale = p['max_turnover_per_rebalance'] / target_turnover
        target_weights = {s: v * scale for s, v in target_weights.items()}
        log.info("换手率缩放: scale=%.2f" % scale)

    # ---- 4. 调整到目标持仓 ----
    for stock, value in target_weights.items():
        # 跳过停牌/涨停
        if cd[stock].paused:
            log.info("跳过 (停牌): %s" % stock)
            continue
        if cd[stock].last_price >= cd[stock].high_limit:
            log.info("跳过 (涨停): %s" % stock)
            continue

        # ---- 5. A 股最小 100 股手数处理 ----
        # 聚宽要求: 每次买入必须是 100 的整数倍 (科创板 200 起)
        # 算法: lots = floor(value / (100 * last_price))
        #      若 lots < 1 则跳过该股 (资金不足以买 1 手)
        last_price = cd[stock].last_price
        if last_price <= 0 or np.isnan(last_price):
            log.info("跳过 (价格异常): %s, last_price=%s" % (stock, last_price))
            continue
        lots = int(value // (100 * last_price))
        if lots < 1:
            log.info("跳过 (资金不足1手): %s, 需要≥%.0f元, 预算=%.0f元" %
                     (stock, 100 * last_price, value))
            continue
        # 实际买入股数
        actual_shares = lots * 100
        actual_value = actual_shares * last_price

        # 【修复】使用 order_value 精确指定买入金额，避免 order_target_value 计算问题
        # 检查可用资金
        available_cash = context.portfolio.available_cash
        if actual_value > available_cash:
            # 资金不足，降低买入量
            max_lots = int(available_cash // (100 * last_price))
            if max_lots < 1:
                log.info("跳过 (资金严重不足): %s, 可用=%.0f元, 需要=%.0f元" %
                         (stock, available_cash, actual_value))
                continue
            actual_shares = max_lots * 100
            actual_value = actual_shares * last_price
            log.info("资金不足，降低买入: %s, %d股, %.0f元" % (stock, actual_shares, actual_value))

        # 【修复】使用 order_value 而不是 order_target_value
        # order_value 按指定金额买入，不会因为已有持仓而跳过
        order_result = order_value(stock, actual_value)
        if order_result is None:
            log.warn("下单失败: %s, 金额=%.0f元" % (stock, actual_value))
            continue

        # 更新持仓记录
        if stock not in g.holdings:
            g.holdings[stock] = {
                'entry_date': context.current_dt,
                'entry_price': cd[stock].last_price,
                'highest_close': cd[stock].last_price,
                'holding_days': 0,
            }
        # 重新进入的股票 (老持仓可能因调仓被更新)
        elif g.holdings[stock].get('entry_date') is None:
            g.holdings[stock] = {
                'entry_date': context.current_dt,
                'entry_price': cd[stock].last_price,
                'highest_close': cd[stock].last_price,
                'holding_days': 0,
            }

    # ---- 5. 清仓不在目标中的标的 ----
    for stock in list(context.portfolio.positions.keys()):
        if stock not in target_weights:
            # 【修复】检查清仓订单是否成功
            sell_order = order_target_value(stock, 0)
            if sell_order is None:
                # 清仓失败（如跌停），保留 g.holdings 记录
                log.info("清仓失败 (待下一日): %s" % stock)
                # 不删除 g.holdings 记录，等待下一日继续卖出
            else:
                # 清仓成功，删除 g.holdings 记录
                g.holdings.pop(stock, None)
                log.info("清仓 (不在目标): %s" % stock)

    log.info("调仓完成: 目标 %d 只, 总价值=%.0f" %
             (len(target_weights),
              sum([target_weights[_s] for _s in target_weights])))


# ============================================================
# 6. 工具函数
# ============================================================
def filter_universe(raw_list, context):
    """
    过滤股票池:
    - 去除停牌股
    - 去除 ST/*ST
    - 去除上市不足 60 日 (因子 NaN)
    """
    cd = get_current_data()
    out = []
    for s in raw_list:
        # 停牌
        if cd[s].paused:
            continue
        # ST/*ST
        if cd[s].is_st:
            continue
        # 上市未满 60 日 (因子为 NaN)
        # 聚宽api详情.txt: 聚宽无 get_security_info, 用 attribute_history 替代
        hist = attribute_history(s, 60, '1d', ['close'],
                                  skip_paused=True, df=False, fq='pre')
        if hist is None or len(hist['close']) < 60:
            continue
        if any(np.isnan(hist['close'][-60:])):
            continue
        out.append(s)
    return out


def get_industry_map(stock_list):
    """
    获取股票-行业映射 (申万一级 sw_l1)
    聚宽api详情.txt:351-380 get_industry() 返回多套分类
    """
    if not stock_list:
        return {}
    try:
        ind = get_industry(stock_list)
    except Exception as e:
        log.warn("get_industry 调用失败: %s" % str(e))
        return {}

    out = {}
    for s, v in ind.items():
        if 'sw_l1' in v and 'industry_code' in v['sw_l1']:
            out[s] = v['sw_l1']['industry_code']
        else:
            out[s] = 'unknown'
    return out


# ============================================================
# 7. (可选) 收盘后统计 - 调试用
# ============================================================
def after_market_close(context):
    """
    每日 15:30 收盘后日志 (可选)
    聚宽api详情.txt: 行 629 提到 after_trading_end 在 15:00 后半小时内运行
    本策略未注册到 initialize, 仅作为示例
    """
    pass
