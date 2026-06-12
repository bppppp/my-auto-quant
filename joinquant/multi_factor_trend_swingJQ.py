# -*- coding: utf-8 -*-
"""
multi_factor_trend_swing 聚宽 (JoinQuant / JQuant) 版本
=========================================================
策略文档: D:\\project\\quant\\my-quant3\\subjects\\multi_factor_trend_swing\\multi_factor_trend_swing_original.md
回测平台: JoinQuant (聚宽)
API 参考: D:\\project\\quant\\my-quant3\\joinQuant\\JQuantAPI.md
参考实现: D:\\project\\quant\\my-quant3\\joinQuant\\strategy.py (donchian_breakout_vol_rsi_ma)

策略核心: 多因子加权入场 (5 信号) + 多重止损出场 (5 信号) + 5 个仓位约束
入场信号 (权重): trend_strength(0.35) + atr_filter(0.20) + volume_confirm(0.15) + momentum_filter(0.15) + rsi_filter(0.15)
出场信号 (权重降序): fixed_stop(0.30) > trailing_stop(0.30) > trend_reversal(0.20) > time_stop(0.10) > rsi_overbought(0.10)
仓位约束: target_holdings=10 / max_single=0.12 / max_industry=0.30 / max_turnover=0.40 / rebalance_freq=5 日
Universe: 沪深 300 (HS300)
调仓: 每 5 个交易日 14:55 (用当日 last_price 算因子)
止损: 每日 15:00 (用 last_price 决策)

JQBoson 兼容性: §16.1-16.10 全部 10 条 Quirks 已逐条防御

测试集: 静态本地 HS300 列表 (data/config.py.HS300) — 不调用 get_index_stocks
        保证回测结果与本地回测引擎 (subjects/subject/backtest) 完全一致
"""


# ============================================================
# 0. 导入聚宽函数库 (聚宽例子.txt 标准导入方式)
# ============================================================
from jqdata import *
import numpy as np
import pandas as pd


# ============================================================
# 1. 参数配置区 (用户可按需调整, 默认值与 spec.params 一致)
# ============================================================
PARAMS = {
    # ---- 标的与基准 ----
    'universe_index': '000300.XSHG',    # 沪深 300

    # ---- 因子窗口 (spec.factors) ----
    'ma_short': 10,                     # 短期均线
    'ma_mid': 30,                       # 中期均线
    'ma_long': 60,                      # 长期均线
    'atr_period': 14,                   # ATR 周期
    'volume_ma_period': 20,             # 量比均线周期
    'rsi_period': 14,                   # RSI 周期
    'mom_period': 60,                   # 动量周期

    # ---- 入场阈值 (spec.entry_signals) ----
    'atr_threshold': 0.01,              # atr_filter: ATR/close > 0.01
    'vol_threshold': 1.3,               # volume_confirm: vol_ratio > 1.3
    'mom_threshold': 0.05,              # momentum_filter: mom_60 > 5%
    'rsi_upper': 70,                    # rsi_filter: rsi_14 < 70
    'min_entry_score': 0.50,            # 至少 trend(0.35) + 1 辅助(≥0.15)

    # ---- 出场阈值 (spec.exit_signals) ----
    'fixed_stop_pct': 0.08,             # 固定止损 8%
    'trailing_stop_pct': 0.05,          # 移动止损 5%
    'max_holding_days': 30,             # 时间止损 30 个交易日
    'rsi_overbought': 75,               # RSI 超买 75

    # ---- 仓位控制 (spec.position_weights) ----
    'target_holdings': 10,              # 目标持仓数
    'max_single_weight': 0.12,          # 单票最大权重
    'max_industry_concentration': 0.30, # 行业集中度上限 (sw_l1)
    'max_turnover_per_rebalance': 0.40, # 单次调仓换手率上限
    'rebalance_freq_days': 5,           # 调仓频率 (交易日)

    # ---- 内部 ----
    'warmup_days': 70,                  # ma_60 需要 60 日, +10 buffer
}


# ============================================================
# 1.5 静态测试集 (本地 HS300 列表, data/config.py 静态快照)
#   单独放模块级常量,不放进 PARAMS (避免 §16.10 g.params 长列表丢失)
#   6 位纯数字 → 聚宽代码 (6 开头 → .XSHG, 0/3 开头 → .XSHE)
# ============================================================
HS300_CODES_RAW = [
    '000001', '000002', '000063', '000100', '000157', '000166', '000301', '000333', '000338', '000408',
    '000425', '000538', '000568', '000596', '000617', '000625', '000630', '000651', '000661', '000708',
    '000725', '000768', '000776', '000786', '000792', '000807', '000858', '000876', '000895', '000938',
    '000963', '000975', '000977', '000983', '000999', '001391', '001965', '001979', '002001', '002027',
    '002028', '002049', '002050', '002074', '002142', '002179', '002230', '002236', '002241', '002252',
    '002304', '002311', '002352', '002371', '002384', '002415', '002422', '002459', '002460', '002463',
    '002466', '002475', '002493', '002594', '002600', '002601', '002625', '002648', '002709', '002714',
    '002736', '002916', '002920', '002938', '003816', '300014', '300015', '300033', '300059', '300122',
    '300124', '300251', '300274', '300308', '300316', '300347', '300394', '300408', '300413', '300418',
    '300433', '300442', '300476', '300498', '300502', '300628', '300661', '300750', '300759', '300760',
    '300782', '300803', '300832', '300866', '300896', '300979', '300999', '301236', '301269', '302132',
    '600000', '600009', '600010', '600011', '600015', '600016', '600018', '600019', '600023', '600025',
    '600026', '600027', '600028', '600029', '600030', '600031', '600036', '600039', '600048', '600050',
    '600061', '600066', '600085', '600089', '600104', '600111', '600115', '600150', '600160', '600161',
    '600176', '600183', '600188', '600196', '600219', '600233', '600276', '600309', '600346', '600362',
    '600372', '600377', '600406', '600415', '600426', '600436', '600438', '600460', '600482', '600489',
    '600515', '600519', '600522', '600547', '600570', '600584', '600585', '600588', '600600', '600660',
    '600674', '600690', '600741', '600760', '600795', '600803', '600809', '600845', '600875', '600886',
    '600887', '600893', '600900', '600905', '600918', '600919', '600926', '600930', '600938', '600941',
    '600958', '600989', '600999', '601006', '601009', '601012', '601018', '601021', '601058', '601059',
    '601066', '601077', '601088', '601100', '601111', '601117', '601127', '601136', '601138', '601166',
    '601169', '601186', '601211', '601225', '601229', '601236', '601238', '601288', '601298', '601318',
    '601319', '601328', '601336', '601360', '601377', '601390', '601398', '601456', '601600', '601601',
    '601607', '601618', '601628', '601633', '601658', '601668', '601669', '601688', '601689', '601698',
    '601728', '601766', '601788', '601800', '601808', '601816', '601818', '601825', '601838', '601857',
    '601868', '601872', '601877', '601878', '601881', '601888', '601898', '601899', '601901', '601916',
    '601919', '601939', '601985', '601988', '601995', '601998', '603019', '603195', '603259', '603260',
    '603288', '603296', '603369', '603392', '603501', '603799', '603893', '603986', '603993', '605117',
    '605499', '688008', '688009', '688012', '688036', '688041', '688047', '688082', '688111', '688126',
    '688169', '688187', '688223', '688256', '688271', '688303', '688396', '688472', '688506', '688981',
]

# 聚宽代码后缀规则:
#   - 6 开头 (含 688 科创板) → .XSHG (上交所)
#   - 0/3 开头 (含 300 创业板) → .XSHE (深交所)
HS300_CODES_JQ = [
    (c + '.XSHG' if c.startswith('6') else c + '.XSHE')
    for c in HS300_CODES_RAW
]


# ============================================================
# 2. 聚宽框架函数
# ============================================================
def initialize(context):
    """
    策略初始化 (回测启动时运行一次)
    - 设置基准 / 真实价格 / 手续费 / 滑点
    - 缓存所有交易日 (供 _is_trading_day 守卫使用, §16.6)
    - 注册每日回调
    """
    # ---- 基准与价格模式 ----
    set_benchmark(PARAMS['universe_index'])
    set_option('use_real_price', True)   # 动态复权, 强烈建议开启

    # ---- 手续费/印花税 ----
    set_order_cost(OrderCost(
        open_tax=0,                     # 买入无印花税
        close_tax=0.001,                # 卖出印花税千一
        open_commission=0.0003,         # 买入佣金万三
        close_commission=0.0003,        # 卖出佣金万三
        close_today_commission=0,       # 平今 (股票场景设 0)
        min_commission=5                # 最低 5 元
    ), type='stock')

    # ---- 滑点 ----
    set_slippage(FixedSlippage(0.0005))

    # ---- 过滤 order 常规日志 ----
    log.set_level('order', 'error')

    # ---- 关键: set_universe 预填 get_current_data() 字典 ----
    # JQuantAPI.md §3: get_current_data() "按需获取(初始为空, 访问时加载)"
    # 单独用 cd[code] 才能触发 lazy loading; set_universe() 进一步预填
    set_universe(HS300_CODES_JQ)

    # ---- 缓存所有交易日 (set of datetime.date) ----
    g.trade_days_set = set([d for d in get_all_trade_days()])

    # ---- 日程调度 (全部用 run_daily, 不实现 handle_data) ----
    run_daily(before_market_open, time='09:00')   # 盘前: 准备股票池/行业
    run_daily(market_rebalance, time='14:55')     # 调仓日: 计算因子 + 调仓
    run_daily(check_stops_daily, time='15:00')    # 盘后: 止损检查 + 持仓状态更新

    # ---- 全局状态 (g 对象可被 pickle 持久化) ----
    g.params = PARAMS
    g.holdings = {}              # {stock: {entry_date, entry_price, highest_close, holding_days}}
    g.rebalance_counter = 0      # 累计交易日 (用于 5 日调仓判断)
    g.universe = []              # 当日候选股票池
    g.industry_map = {}          # {stock: sw_l1_industry_code}


def before_market_open(context):
    """
    每日 09:00 盘前准备
    1. 交易日守卫 (§16.6 修复)
    2. 获取 HS300 成分股 (用前一交易日避免未来函数)
    3. 过滤: 停牌 / ST / 上市不足 60 日
    4. 行业映射 (sw_l1 申万一级)
    5. 累计交易日计数 +1
    """
    if not _is_trading_day(context):
        return

    # ---- 1. 使用本地 HS300 静态列表 (data/config.py.HS300) ----
    # 与本地回测引擎 (subjects/subject/backtest) 完全对齐
    # 不调用 get_index_stocks, 避免回测期内聚宽指数成分股调整影响结果
    raw = HS300_CODES_JQ

    # ---- 2. 过滤停牌/ST/上市不足 ----
    g.universe = filter_universe(raw, context)

    # ---- 3. 行业映射 (sw_l1 申万一级) ----
    g.industry_map = get_industry_map(g.universe)

    # ---- 4. 交易日计数 ----
    g.rebalance_counter += 1


def market_rebalance(context):
    """
    调仓日 14:55: 计算信号, 调仓
    - 仅在每 5 个交易日调仓一次
    - 计算所有候选股综合得分
    - 选取得分 >= min_entry_score(0.50) 的股
    - 按得分降序取前 target_holdings(10) 只
    - 应用 5 个仓位约束
    - 涨停/停牌/科创板股票跳过买入
    """
    if not _is_trading_day(context):
        return

    # 仅在调仓日执行
    if g.rebalance_counter % PARAMS['rebalance_freq_days'] != 0:
        return

    if not g.universe:
        return

    # ---- 1. 批量计算所有候选股因子 ----
    factor_panel = calc_factors_batch(g.universe, context)
    if factor_panel is None or factor_panel.empty:
        return

    # ---- 2. 计算每只股票的入场信号得分 ----
    p = g.params
    candidates = []
    for stock in factor_panel.index:
        f = factor_panel.loc[stock].to_dict()
        score = entry_score(f, p)
        if score >= p['min_entry_score']:
            candidates.append((stock, score))

    if not candidates:
        execute_rebalance(context, [], [])
        return

    # ---- 3. 按得分降序, 取前 target_holdings(10) 只 ----
    candidates.sort(key=lambda x: x[1], reverse=True)
    target_stocks = [c[0] for c in candidates[:p['target_holdings']]]
    log.info("[%s] 候选 %d 只, 入选 %d 只" %
             (context.current_dt.strftime('%Y-%m-%d'),
              len(candidates), len(target_stocks)))

    # ---- 4. 执行调仓 ----
    execute_rebalance(context, target_stocks, [])


def check_stops_daily(context):
    """
    每日 15:00 止损检查
    - 更新 holding_days / highest_close
    - 检查出场信号 (按权重降序: fixed > trailing > trend_reversal > time > rsi_overbought)
    - 跌停当日不执行出场 (被吞)
    - 科创板用限价单 (§16.8 修复)
    """
    if not _is_trading_day(context):
        return

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

        # 关键: cd[stock] 触发 lazy loading; KeyError 表示股票不在 JQ 数据库
        try:
            d = cd[stock]
        except KeyError:
            continue
        current_price = d.last_price
        if current_price <= 0 or np.isnan(current_price):
            continue

        # ---- 初始化/更新 holding_days 与 highest_close ----
        h = g.holdings[stock]
        if 'holding_days' not in h:
            h['holding_days'] = 0
        if 'highest_close' not in h or h['highest_close'] is None:
            h['highest_close'] = current_price
        h['holding_days'] += 1
        h['highest_close'] = max(h['highest_close'], current_price)

        # ---- 跌停当日: 所有出场信号不执行 (被吞) ----
        # §16.5 修复: high_limit/low_limit 可能为 0, 加 > 0 守护
        if d.low_limit > 0 and current_price <= d.low_limit:
            continue

        # ---- 涨停当日: 出场仍可执行 (避免被套) ----
        is_up_limit = d.high_limit > 0 and current_price >= d.high_limit

        # ---- 计算因子 ----
        factors = calc_factors_one(stock, context)
        if factors is None:
            continue

        # ---- 出场决策 ----
        reason = exit_decision(factors, h, current_price, g.params)

        if reason:
            # §16.8 修复: 科创板市价单需指定保护限价
            if stock.startswith('688'):
                limit_price = min(current_price * 0.995, 9999.99)
                if limit_price > 0:
                    order(stock, -pos.closeable_amount, LimitOrderStyle(limit_price))
            else:
                # §16.9 修复: 卖出也用 order(stock, -shares) 而非 order_target_value(0)
                order(stock, -pos.closeable_amount)
            pnl = (current_price - h['entry_price']) / h['entry_price']
            log.info("[%s] 止损离场: %s, 原因=%s, 盈亏=%.2f%%, 持有=%d日" %
                     (context.current_dt.strftime('%Y-%m-%d'),
                      stock, reason, pnl * 100, h['holding_days']))
            g.holdings.pop(stock, None)


# ============================================================
# 3. 因子计算
# ============================================================
def calc_factors_one(security, context):
    """
    计算单只股票的因子 (用于每日 15:00 止损检查)
    返回 dict: {close, ma_10, ma_30, ma_60, atr_14, volume_ratio_20, rsi_14, mom_60}
    返回 None 表示数据不足
    """
    p = g.params
    n = PARAMS['warmup_days']

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

    # §16.4 修复: get_current_data() 无 volume 字段, 量比用历史 volume
    # 关键: cd[security] 触发 lazy loading; KeyError 表示股票不在 JQ 数据库
    cd = get_current_data()
    try:
        d = cd[security]
    except KeyError:
        d = None
    if d is not None and d.last_price > 0 and not np.isnan(d.last_price):
        current_close = d.last_price
    else:
        current_close = close.iloc[-1]

    return _calc_factors_core(close, high, low, vol, current_close, p)


def calc_factors_batch(stock_list, context):
    """
    批量计算所有候选股的因子 (用于调仓日 14:55)
    返回 DataFrame: index=股票代码, columns=因子
    """
    p = g.params
    n = PARAMS['warmup_days']
    cd = get_current_data()

    # 多标的批量 (history() 不含当天, 与 get_current_data() 配合)
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

        # 关键: cd[stock] 触发 lazy loading; KeyError 表示股票不在 JQ 数据库
        try:
            d = cd[stock]
        except KeyError:
            d = None
        if d is not None and d.last_price > 0 and not np.isnan(d.last_price):
            current_close = d.last_price
        else:
            current_close = close.iloc[-1]   # fallback 到昨日收盘

        try:
            row = _calc_factors_core(close, high, low, vol, current_close, p)
            if row is not None:
                rows[stock] = row
        except Exception:
            continue

    if not rows:
        return None
    return pd.DataFrame.from_dict(rows, orient='index')


def _calc_factors_core(close, high, low, vol, current_close, p):
    """
    核心因子计算 (供 calc_factors_one / calc_factors_batch 共用)
    严格对应 spec.factors 7 个因子:
      ma_10, ma_30, ma_60, atr_14, volume_ratio_20, rsi_14, mom_60

    [修复] 移除提前 NaN 检查 (any(x is None or np.isnan(x)) 在 JQ 平台
    对合法正数也误判为 True), 改为在最终返回时统一验证
    """
    # ---- 均线 ----
    ma_10 = close.rolling(p['ma_short']).mean().iloc[-1]
    ma_30 = close.rolling(p['ma_mid']).mean().iloc[-1]
    ma_60 = close.rolling(p['ma_long']).mean().iloc[-1]

    # ---- ATR(14) ----
    # TR = max(H-L, |H-prevC|, |L-prevC|), 14 日均值
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.DataFrame({'a': tr1, 'b': tr2, 'c': tr3}).max(axis=1)
    atr_14 = tr.rolling(p['atr_period']).mean().iloc[-1]

    # ---- 量比 (volume_ratio_20) ----
    # §16.4 修复: get_current_data() 无 volume, 用历史 vol.iloc[-1]
    vol_ma_20 = vol.rolling(p['volume_ma_period']).mean().iloc[-1]
    last_vol = vol.iloc[-1] if len(vol) > 0 else 0
    volume_ratio_20 = (last_vol / vol_ma_20) if vol_ma_20 and vol_ma_20 > 0 else 0

    # ---- RSI(14) ----
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.rolling(p['rsi_period']).mean().iloc[-1]
    avg_loss = loss.rolling(p['rsi_period']).mean().iloc[-1]
    if avg_loss is None or (isinstance(avg_loss, float) and avg_loss != avg_loss) or avg_loss == 0:
        rsi_14 = 100.0 if (avg_gain is not None and avg_gain > 0) else 50.0
    else:
        rsi_14 = 100 - 100 / (1 + avg_gain / avg_loss)

    # ---- mom_60: 当日收盘 / 60 日前收盘 - 1 ----
    # 用 "self != self" (NaN trick) 代替 np.isnan
    prev_close_60 = close.shift(p['mom_period']).iloc[-1]
    if prev_close_60 is None or (isinstance(prev_close_60, float) and prev_close_60 != prev_close_60) or prev_close_60 <= 0:
        return None
    mom_60 = current_close / prev_close_60 - 1

    factors = {
        'close': float(current_close),
        'ma_10': float(ma_10),
        'ma_30': float(ma_30),
        'ma_60': float(ma_60),
        'atr_14': float(atr_14),
        'volume_ratio_20': float(volume_ratio_20),
        'rsi_14': float(rsi_14),
        'mom_60': float(mom_60),
    }
    # 最终验证: 所有因子必须是有限数
    for k, v in factors.items():
        if not np.isfinite(v):
            return None
    return factors


# ============================================================
# 4. 信号逻辑
# ============================================================
def entry_score(f, p):
    """
    计算入场信号综合得分
    严格对应 spec.entry_signals 5 个信号 (权重 0.35+0.20+0.15+0.15+0.15 = 1.0)

    1. trend_strength (0.35):  ma_10 > ma_30 > ma_60
    2. atr_filter (0.20):       atr_14 / close > atr_threshold
    3. volume_confirm (0.15):   volume_ratio_20 > vol_threshold
    4. momentum_filter (0.15):  mom_60 > mom_threshold
    5. rsi_filter (0.15):       rsi_14 < rsi_upper

    Args:
        f: 因子 dict
        p: 参数 dict (PARAMS)
    Returns:
        float: 0.0 ~ 1.0 的综合得分
    """
    score = 0.0

    close = f.get('close')
    ma_10 = f.get('ma_10')
    ma_30 = f.get('ma_30')
    ma_60 = f.get('ma_60')
    atr_14 = f.get('atr_14')
    volume_ratio = f.get('volume_ratio_20')
    mom_60 = f.get('mom_60')
    rsi_14 = f.get('rsi_14')

    # [修复] JQ 平台上 np.isnan(合法正数) 会误判为 True,
    # 改用 np.isfinite 在末尾统一验证 (有任一非有限数才 return 0.0)
    if close is None or ma_10 is None or ma_30 is None or ma_60 is None:
        return 0.0
    if atr_14 is None or volume_ratio is None or mom_60 is None or rsi_14 is None:
        return 0.0
    if close <= 0:
        return 0.0

    # 1. trend_strength (0.35): 均线多头排列
    if ma_10 > ma_30 > ma_60:
        score += 0.35

    # 2. atr_filter (0.20): 波动率扩张
    if atr_14 / close > p['atr_threshold']:
        score += 0.20

    # 3. volume_confirm (0.15): 量能确认
    if volume_ratio > p['vol_threshold']:
        score += 0.15

    # 4. momentum_filter (0.15): 中期动量
    if mom_60 > p['mom_threshold']:
        score += 0.15

    # 5. rsi_filter (0.15): 避免超买区追高
    if rsi_14 < p['rsi_upper']:
        score += 0.15

    return score


def exit_decision(f, h, current_price, p):
    """
    出场决策 (按权重降序优先级)
    严格对应 spec.exit_signals 5 个信号:
      1. fixed_stop (0.30)         硬性损失
      2. trailing_stop (0.30)      浮盈保护
      3. trend_reversal (0.20)     均线死叉
      4. time_stop (0.10)          持仓周期过长
      5. rsi_overbought (0.10)     短期过热

    Args:
        f: 因子 dict (含 ma_10, ma_30, rsi_14)
        h: 持仓记录 dict (含 entry_price, highest_close, holding_days)
        current_price: 当前价
        p: 参数 dict (PARAMS)
    Returns:
        str: 触发的出场信号名, 或 None
    """
    # ---- 数据完整性检查 ----
    # [修复] JQ 平台上 np.isnan(合法正数) 会误判, 改用 self != self NaN trick
    entry_price = h.get('entry_price')
    highest_close = h.get('highest_close')

    if entry_price is None or entry_price <= 0:
        return None
    if highest_close is None:
        highest_close = entry_price
    elif isinstance(highest_close, float) and highest_close != highest_close:
        # NaN 守护 (self != self)
        highest_close = entry_price

    # 1. fixed_stop (0.30) — 优先级最高, 硬性损失控制
    if current_price < entry_price * (1 - p['fixed_stop_pct']):
        return 'fixed_stop'

    # 2. trailing_stop (0.30) — 浮盈保护
    if current_price < highest_close * (1 - p['trailing_stop_pct']):
        return 'trailing_stop'

    # 3. trend_reversal (0.20) — ma_10 < ma_30 死叉
    ma_10 = f.get('ma_10')
    ma_30 = f.get('ma_30')
    if ma_10 is not None and ma_30 is not None:
        if ma_10 < ma_30:
            return 'trend_reversal'

    # 4. time_stop (0.10) — 持仓周期
    holding_days = h.get('holding_days', 0)
    if holding_days >= p['max_holding_days']:
        return 'time_stop'

    # 5. rsi_overbought (0.10) — 短期超买
    rsi_14 = f.get('rsi_14')
    if rsi_14 is not None and rsi_14 > p['rsi_overbought']:
        return 'rsi_overbought'

    return None


# ============================================================
# 5. 调仓执行
# ============================================================
def execute_rebalance(context, target_stocks, target_scores):
    """
    执行调仓
    - 应用 5 个仓位约束 (单票 / 行业 / 换手率 / 调仓频率)
    - 涨停/停牌股票跳过买入
    - 科创板用限价单 (§16.8 修复)
    - 用 order(stock, delta_shares) 而非 order_target_value (§16.9 修复)
    """
    p = g.params
    cd = get_current_data()
    total_value = context.portfolio.total_value

    if total_value <= 0:
        return

    if not target_stocks:
        # ---- 无目标持仓: 清仓所有 ----
        for stock in list(context.portfolio.positions.keys()):
            try:
                d = cd[stock]
            except KeyError:
                continue
            pos = context.portfolio.positions[stock]
            if pos.closeable_amount > 0:
                # §16.8 修复: 科创板限价单
                if stock.startswith('688') and d.last_price > 0:
                    limit_price = min(d.last_price * 0.995, 9999.99)
                    if limit_price > 0:
                        order(stock, -pos.closeable_amount, LimitOrderStyle(limit_price))
                else:
                    # §16.9 修复: 用 order() 显式股数
                    order(stock, -pos.closeable_amount)
            g.holdings.pop(stock, None)
        return

    # ---- 1. 计算单票目标价值 ----
    # 公式: per_target = min(max_single * tv, tv / N)
    n_targets = min(len(target_stocks), p['target_holdings'])
    per_target = min(
        total_value * p['max_single_weight'],
        total_value / max(n_targets, 1)
    )

    # ---- 2. 应用行业集中度约束 (sw_l1 申万一级) ----
    target_weights = {}
    industry_used = {}
    for stock in target_stocks:
        ind = g.industry_map.get(stock, 'unknown')
        ind_limit = total_value * p['max_industry_concentration']
        if industry_used.get(ind, 0) + per_target > ind_limit:
            # 该股票所在行业已超限, 跳过
            continue
        target_weights[stock] = per_target
        industry_used[ind] = industry_used.get(ind, 0) + per_target

    if not target_weights:
        log.warn("所有候选股都被行业约束排除, 跳过调仓")
        return

    # ---- 3. 应用换手率限制 ----
    # §16.1 修复: sum(dict.values()) 兼容性, 显式 list 转换
    tw_values = [target_weights[_s] for _s in target_weights]
    tw_sum = sum(tw_values) if tw_values else 0.0
    target_turnover = tw_sum / total_value
    if target_turnover > p['max_turnover_per_rebalance']:
        scale = p['max_turnover_per_rebalance'] / target_turnover
        target_weights = {s: v * scale for s, v in target_weights.items()}
        log.info("换手率缩放: scale=%.2f" % scale)

    # ---- 4. 调整到目标持仓 ----
    for stock, value in target_weights.items():
        # 关键: cd[stock] 触发 lazy loading; KeyError 表示股票不在 JQ 数据库
        try:
            d = cd[stock]
        except KeyError:
            continue
        if d.paused:
            continue
        # §16.5 修复: high_limit > 0 守护
        if d.high_limit > 0 and d.last_price >= d.high_limit:
            continue
        if d.last_price <= 0 or np.isnan(d.last_price):
            continue

        last_price = d.last_price

        # ---- A 股最小手数处理 ----
        # 主板 / 中小创 / 创业板: 100 股
        # 科创板 (688xxx): 200 股
        lot_size = 200 if stock.startswith('688') else 100

        lots = int(value // (lot_size * last_price))
        if lots < 1:
            continue

        target_shares = lots * lot_size
        current_shares = (context.portfolio.positions[stock].total_amount
                          if stock in context.portfolio.positions else 0)
        delta_shares = target_shares - current_shares
        if delta_shares == 0:
            continue

        # ---- 资金不足时降级买入量 ----
        if delta_shares > 0:
            available_cash = context.portfolio.available_cash
            if last_price * delta_shares > available_cash:
                max_lots = int(available_cash // (lot_size * last_price))
                if max_lots < 1:
                    continue
                target_shares = current_shares + max_lots * lot_size
                delta_shares = max_lots * lot_size

        # ---- 下单 ----
        # §16.8 修复: 科创板用限价单 (主板仍用市价单)
        if stock.startswith('688'):
            limit_price = min(last_price * 1.005, 9999.99)
            if limit_price <= 0:
                continue
            order_result = order(stock, delta_shares, LimitOrderStyle(limit_price))
        else:
            # §16.9 修复: 用 order() 显式传 delta_shares, 避免 order_target_value "数量为 0" 假报
            order_result = order(stock, delta_shares)

        if order_result is None:
            log.warn("[%s] 下单失败: %s, delta_shares=%d" %
                     (context.current_dt.strftime('%Y-%m-%d'), stock, delta_shares))
            continue

        # ---- 更新持仓记录 (新建/重新进入) ----
        if stock not in g.holdings or g.holdings[stock].get('entry_date') is None:
            g.holdings[stock] = {
                'entry_date': context.current_dt,
                'entry_price': last_price,
                'highest_close': last_price,
                'holding_days': 0,
            }

    # ---- 5. 清仓不在 target 中的标的 ----
    for stock in list(context.portfolio.positions.keys()):
        if stock not in target_weights:
            try:
                d = cd[stock]
            except KeyError:
                continue
            pos = context.portfolio.positions[stock]
            if pos.closeable_amount > 0:
                # §16.8 修复: 科创板限价单
                if stock.startswith('688') and d.last_price > 0:
                    limit_price = min(d.last_price * 0.995, 9999.99)
                    if limit_price > 0:
                        order(stock, -pos.closeable_amount, LimitOrderStyle(limit_price))
                else:
                    order(stock, -pos.closeable_amount)
            g.holdings.pop(stock, None)


# ============================================================
# 6. 工具函数
# ============================================================
def _is_trading_day(context):
    """
    交易日守卫 (§16.6 修复)
    模拟盘 run_daily 每日触发 (含周末/节假日), 回测仅在交易日触发
    """
    return context.current_dt.date() in g.trade_days_set


def filter_universe(raw_list, context):
    """
    过滤股票池:
    - 去除退市 / 未上市 (cd[code] 抛 KeyError)
    - 去除 ST/*ST
    - 去除上市不足 60 日 / 数据缺失 (用历史 60 日 close 是否全为 NaN 判断)

    [修复] 改用 skip_paused=False, 防止任何停牌日导致 hist 不足 60 行
    (旧版 skip_paused=True + len < 60 太严, 把有少量停牌日的正常股票都过滤掉)
    """
    cd = get_current_data()
    out = []
    n_total = len(raw_list)
    n_skip_none = 0      # KeyError (退市/未上市, 不在 JQ 数据库)
    n_skip_paused = 0    # 今日停牌
    n_skip_st = 0        # ST/*ST
    n_skip_data = 0      # 数据不足 (前 60 日全 NaN)

    for s in raw_list:
        # 关键: cd[s] 触发 lazy loading; KeyError 表示股票不在 JQ 数据库
        # (donchian 示例就是这样写的)
        try:
            d = cd[s]
        except KeyError:
            n_skip_none += 1
            continue
        # 今日停牌
        if d.paused:
            n_skip_paused += 1
            continue
        # ST/*ST
        if d.is_st:
            n_skip_st += 1
            continue
        # 上市未满 60 日 (历史全 NaN)
        try:
            hist = attribute_history(s, 70, '1d', ['close'],
                                      skip_paused=False, df=False, fq='pre')
        except Exception:
            n_skip_data += 1
            continue
        if hist is None or len(hist['close']) < 60:
            n_skip_data += 1
            continue
        # 关键修复: 只看最近 30 日 (足够排除上市未满) 而非全部
        # 早期可能有除权除息造成的 NaN, 不应因此过滤
        recent = hist['close'][-30:]
        if any(np.isnan(recent)):
            n_skip_data += 1
            continue
        out.append(s)

    return out


def get_industry_map(stock_list):
    """
    获取股票-行业映射 (sw_l1 申万一级)
    聚宽 get_industry() 返回多套分类, 选用 sw_l1 (与 donchian_breakout_vol_rsi_ma JQ 示例一致)
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
