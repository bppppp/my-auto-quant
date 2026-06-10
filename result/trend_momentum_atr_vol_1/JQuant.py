# -*- coding: utf-8 -*-
"""
trend_momentum_atr_vol_1  -  聚宽(JQuant)版本
================================================
策略: 双均线金叉 + ATR 波动率扩张 + 量能放大确认, 打分制入场, 三层止损出场
测试集: 沪深 300 (默认)
调仓:   每 10 个交易日
目标:   年化 22%, 胜率 45%, 盈亏比 3.5, 夏普 1.3, 最大回撤 -15%

API 参考: joinQuant/JQuantAPI.md
"""

# ============================================================
# 0. 导入
# ============================================================
from jqdata import *
import numpy as np
import pandas as pd


# ============================================================
# 1. 参数配置区
# ============================================================
PARAMS = {
    # ---- 标的与基准 ----
    'universe_index':       '000300.XSHG',   # 沪深 300
    'static_universe':      True,            # 启用静态列表 (与本地 weight 回测对齐)

    # ---- 因子窗口 ----
    'ma_short':             10,              # 短期均线
    'ma_long':              30,              # 长期均线
    'atr_period':           14,              # ATR 周期
    'volume_ma_period':     20,              # 量比均线周期

    # ---- 入场阈值 (打分制) ----
    'atr_threshold':        0.08,            # ATR/Close 最低 (波动率扩张)
    'vol_threshold':        2.8,             # 量比最低 (量能放大)
    'min_entry_score':      0,               # 入场过滤阈值, 实际逻辑为 score > min_entry_score
                                            # 0 = 任何入场信号触发即入候选池 (与本地 runner.py:666 一致)

    # ---- 出场阈值 ----
    'fixed_stop_pct':       0.14,            # 固定止损比例
    'trailing_stop_pct':    0.18,            # 移动止损回撤比例
    'max_holding_days':     180,             # 最大持仓天数 (时间止损)

    # ---- 仓位控制 ----
    'target_holdings':          6,           # 目标持仓数量
    'max_single_weight':        0.20,        # 单票最大权重
    'max_industry_concentration': 0.35,      # 行业集中度上限
    'max_turnover_per_rebalance': 0.60,      # 单次调仓换手率上限
    'cash_reserve':             0.02,        # 现金保留比例

    # ---- 调仓频率 ----
    'rebalance_freq_days':  10,              # 调仓间隔交易日数

    # ---- A 股硬约束 ----
    'min_listing_days':     60,              # 最低上市天数
    'resume_trade_wait_days': 5,             # 复牌后等待天数 (停牌后从 before_market_open 起算)
    'lot_size_kechuang':    200,             # 科创板 688xxx 最小手数 (其他股票 100)
}


# ============================================================
# 1.5 静态 universe 列表 (独立模块级变量,避免 PARAMS 字典过大)
# ============================================================
# 与本地 subject.backtest.universe.HS300_CODES 完全一致
# 转换规则: .SZ → .XSHE, .SH → .XSHG
# 长度: 300
HS300_STATIC = [
    '000001.XSHE', '000002.XSHE', '000063.XSHE', '000100.XSHE', '000157.XSHE', '000166.XSHE',
    '000301.XSHE', '000333.XSHE', '000338.XSHE', '000408.XSHE', '000425.XSHE', '000538.XSHE',
    '000568.XSHE', '000596.XSHE', '000617.XSHE', '000625.XSHE', '000630.XSHE', '000651.XSHE',
    '000661.XSHE', '000708.XSHE', '000725.XSHE', '000768.XSHE', '000776.XSHE', '000786.XSHE',
    '000792.XSHE', '000807.XSHE', '000858.XSHE', '000876.XSHE', '000895.XSHE', '000938.XSHE',
    '000963.XSHE', '000975.XSHE', '000977.XSHE', '000983.XSHE', '000999.XSHE', '001391.XSHE',
    '001965.XSHE', '001979.XSHE', '002001.XSHE', '002027.XSHE', '002028.XSHE', '002049.XSHE',
    '002050.XSHE', '002074.XSHE', '002142.XSHE', '002179.XSHE', '002230.XSHE', '002236.XSHE',
    '002241.XSHE', '002252.XSHE', '002304.XSHE', '002311.XSHE', '002352.XSHE', '002371.XSHE',
    '002384.XSHE', '002415.XSHE', '002422.XSHE', '002459.XSHE', '002460.XSHE', '002463.XSHE',
    '002466.XSHE', '002475.XSHE', '002493.XSHE', '002594.XSHE', '002600.XSHE', '002601.XSHE',
    '002625.XSHE', '002648.XSHE', '002709.XSHE', '002714.XSHE', '002736.XSHE', '002916.XSHE',
    '002920.XSHE', '002938.XSHE', '003816.XSHE', '300014.XSHE', '300015.XSHE', '300033.XSHE',
    '300059.XSHE', '300122.XSHE', '300124.XSHE', '300251.XSHE', '300274.XSHE', '300308.XSHE',
    '300316.XSHE', '300347.XSHE', '300394.XSHE', '300408.XSHE', '300413.XSHE', '300418.XSHE',
    '300433.XSHE', '300442.XSHE', '300476.XSHE', '300498.XSHE', '300502.XSHE', '300628.XSHE',
    '300661.XSHE', '300750.XSHE', '300759.XSHE', '300760.XSHE', '300782.XSHE', '300803.XSHE',
    '300832.XSHE', '300866.XSHE', '300896.XSHE', '300979.XSHE', '300999.XSHE', '301236.XSHE',
    '301269.XSHE', '302132.XSHE', '600000.XSHG', '600009.XSHG', '600010.XSHG', '600011.XSHG',
    '600015.XSHG', '600016.XSHG', '600018.XSHG', '600019.XSHG', '600023.XSHG', '600025.XSHG',
    '600026.XSHG', '600027.XSHG', '600028.XSHG', '600029.XSHG', '600030.XSHG', '600031.XSHG',
    '600036.XSHG', '600039.XSHG', '600048.XSHG', '600050.XSHG', '600061.XSHG', '600066.XSHG',
    '600085.XSHG', '600089.XSHG', '600104.XSHG', '600111.XSHG', '600115.XSHG', '600150.XSHG',
    '600160.XSHG', '600161.XSHG', '600176.XSHG', '600183.XSHG', '600188.XSHG', '600196.XSHG',
    '600219.XSHG', '600233.XSHG', '600276.XSHG', '600309.XSHG', '600346.XSHG', '600362.XSHG',
    '600372.XSHG', '600377.XSHG', '600406.XSHG', '600415.XSHG', '600426.XSHG', '600436.XSHG',
    '600438.XSHG', '600460.XSHG', '600482.XSHG', '600489.XSHG', '600515.XSHG', '600519.XSHG',
    '600522.XSHG', '600547.XSHG', '600570.XSHG', '600584.XSHG', '600585.XSHG', '600588.XSHG',
    '600600.XSHG', '600660.XSHG', '600674.XSHG', '600690.XSHG', '600741.XSHG', '600760.XSHG',
    '600795.XSHG', '600803.XSHG', '600809.XSHG', '600845.XSHG', '600875.XSHG', '600886.XSHG',
    '600887.XSHG', '600893.XSHG', '600900.XSHG', '600905.XSHG', '600918.XSHG', '600919.XSHG',
    '600926.XSHG', '600930.XSHG', '600938.XSHG', '600941.XSHG', '600958.XSHG', '600989.XSHG',
    '600999.XSHG', '601006.XSHG', '601009.XSHG', '601012.XSHG', '601018.XSHG', '601021.XSHG',
    '601058.XSHG', '601059.XSHG', '601066.XSHG', '601077.XSHG', '601088.XSHG', '601100.XSHG',
    '601111.XSHG', '601117.XSHG', '601127.XSHG', '601136.XSHG', '601138.XSHG', '601166.XSHG',
    '601169.XSHG', '601186.XSHG', '601211.XSHG', '601225.XSHG', '601229.XSHG', '601236.XSHG',
    '601238.XSHG', '601288.XSHG', '601298.XSHG', '601318.XSHG', '601319.XSHG', '601328.XSHG',
    '601336.XSHG', '601360.XSHG', '601377.XSHG', '601390.XSHG', '601398.XSHG', '601456.XSHG',
    '601600.XSHG', '601601.XSHG', '601607.XSHG', '601618.XSHG', '601628.XSHG', '601633.XSHG',
    '601658.XSHG', '601668.XSHG', '601669.XSHG', '601688.XSHG', '601689.XSHG', '601698.XSHG',
    '601728.XSHG', '601766.XSHG', '601788.XSHG', '601800.XSHG', '601808.XSHG', '601816.XSHG',
    '601818.XSHG', '601825.XSHG', '601838.XSHG', '601857.XSHG', '601868.XSHG', '601872.XSHG',
    '601877.XSHG', '601878.XSHG', '601881.XSHG', '601888.XSHG', '601898.XSHG', '601899.XSHG',
    '601901.XSHG', '601916.XSHG', '601919.XSHG', '601939.XSHG', '601985.XSHG', '601988.XSHG',
    '601995.XSHG', '601998.XSHG', '603019.XSHG', '603195.XSHG', '603259.XSHG', '603260.XSHG',
    '603288.XSHG', '603296.XSHG', '603369.XSHG', '603392.XSHG', '603501.XSHG', '603799.XSHG',
    '603893.XSHG', '603986.XSHG', '603993.XSHG', '605117.XSHG', '605499.XSHG', '688008.XSHG',
    '688009.XSHG', '688012.XSHG', '688036.XSHG', '688041.XSHG', '688047.XSHG', '688082.XSHG',
    '688111.XSHG', '688126.XSHG', '688169.XSHG', '688187.XSHG', '688223.XSHG', '688256.XSHG',
    '688271.XSHG', '688303.XSHG', '688396.XSHG', '688472.XSHG', '688506.XSHG', '688981.XSHG',
]


# ============================================================
# 2. 策略框架函数
# ============================================================
def initialize(context):
    """
    策略初始化 (回测启动时执行一次)
    聚宽建议: run_xxx 与 handle_data 不要混用, 统一用 run_daily
    """
    # ---- 基准与价格模式 ----
    set_benchmark(PARAMS['universe_index'])
    set_option('use_real_price', True)   # 真实价格(动态复权)模式

    # ---- 手续费/印花税 (万3 + 最低5 + 卖千1) ----
    set_order_cost(OrderCost(
        open_tax=0,
        close_tax=0.001,                 # 印花税千一 (卖方)
        open_commission=0.0003,          # 买入佣金万分之三
        close_commission=0.0003,         # 卖出佣金万分之三
        close_today_commission=0,        # 平今(期货专用, 股票=0)
        min_commission=5                 # 最低 5 元
    ), type='stock')

    # ---- 滑点 ----
    set_slippage(FixedSlippage(0.0005))

    # ---- 过滤 order 常规日志 ----
    log.set_level('order', 'error')

    # ---- 日程调度 ----
    run_daily(before_market_open,    time='09:00')   # 盘前: 准备股票池/行业
    run_daily(market_rebalance,      time='14:50')   # 调仓日: 收盘前 10 分钟
    run_daily(check_stops_daily,     time='15:00')   # 收盘后: 检查出场

    # ---- 全局状态 (g 可被 pickle 持久化) ----
    g.params             = PARAMS
    g.holdings           = {}    # {stock: {entry_date, entry_price, highest_close, holding_days}}
    g.rebalance_counter  = 0     # 累计交易日 (用于 10 日调仓判断)
    g.universe           = []    # 当日候选股票池
    g.industry_map       = {}    # {stock: sw_l1 行业代码}
    g.paused_reentry     = {}    # {stock: resume_wait_days 倒计时}

    # ---- 交易日集合缓存 ----
    # ⚠️ 关键: 统一转 'YYYY-MM-DD' 字符串, 避免 numpy datetime64 单位不一致
    # get_all_trade_days() 返回 [D] 单位, np.datetime64(date) 默认 [us]/[ns] 单位
    # 单位不同时 `in` 比较会永远返回 False, 导致所有回调被守卫拦截 → 零交易
    try:
        _tds = get_all_trade_days()
        g.trade_days_set = set([str(d)[:10] for d in _tds])
        log.info("[初始化] 加载 %d 个交易日, 样例: %s" %
                 (len(g.trade_days_set),
                  sorted(list(g.trade_days_set))[:3]))
    except Exception as e:
        log.warn("[初始化] 交易日加载失败, 守卫放行: %s" % str(e))
        g.trade_days_set = None

    log.info("[初始化] trend_momentum_atr_vol_1 启动完成")
    log.info("[初始化] 回测起止: %s ~ %s, 频率: day" %
             (context.run_params.start_date, context.run_params.end_date))


def _is_trading_day(context):
    """
    判定当前逻辑时间是否为 A 股交易日
    - 回测环境: JQuant 框架只在交易日触发 run_daily, 此函数主要用于**模拟盘防呆**
    - 模拟盘环境: run_daily 会每日触发, 必须跳过周末/节假日
    - 字符串比较 (YYYY-MM-DD) 避免 numpy datetime64 单位不一致问题
    - 安全网: 数据未加载或 set 过小 → 默认放行, 避免策略被全部拦截
    """
    # 安全网: set 未初始化 / 数据太少 → 放行
    if g.trade_days_set is None or len(g.trade_days_set) < 100:
        return True
    today = str(context.current_dt.date())  # 'YYYY-MM-DD'
    return today in g.trade_days_set


def before_market_open(context):
    """
    每日 09:00 盘前准备
    0. 非交易日守卫 (模拟盘防呆)
    1. 获取 HS300 成分股 (静态列表,与本地 weight 回测对齐)
    2. 过滤: 停牌 / ST / 上市不足 60 日
    3. 行业映射 (申万一级)
    4. 复牌等待倒计时递减
    5. 当日停牌的股票加入复牌等待
    6. 累计交易日计数

    修改记录:
    - 原版用 get_index_stocks('000300.XSHG', date) 动态拉取成分股
      → 每次调仓日 universe 可能不同 (聚宽 HS300 实际 2021~2025 多次调整)
      → 导致本地对比困难
    - 现改用 PARAMS['hs300_codes'] 静态 300 只列表
      → 与本地 subject.backtest.universe.HS300_CODES 完全一致
      → universe 切片差异从对比中消除
    """
    # ---- 0. 非交易日守卫 (模拟盘防呆) ----
    if not _is_trading_day(context):
        return
    # ---- 1. 获取 HS300 成分股 ----
    # 静态模式: 用模块级 HS300_STATIC (与本地对齐, 避免 get_index_stocks 动态切片)
    # 动态模式: 用 get_index_stocks(...) (聚宽 API, 不同时点成分股不同)
    if PARAMS.get('static_universe', False):
        raw = list(HS300_STATIC)
    else:
        raw = get_index_stocks(PARAMS['universe_index'], date=context.previous_date)

    # ---- 2. 过滤停牌 / ST / 上市不足 ----
    g.universe = filter_universe(raw, context)

    # ---- 3. 行业映射 ----
    g.industry_map = get_industry_map(g.universe)

    # ---- 4. 复牌等待倒计时递减 ----
    for s in list(g.paused_reentry.keys()):
        g.paused_reentry[s] -= 1
        if g.paused_reentry[s] <= 0:
            g.paused_reentry.pop(s, None)

    # ---- 5. 当日停牌的股票加入复牌等待 (每交易日扫描一次) ----
    cd0 = get_current_data()
    for s in g.universe:
        try:
            if cd0[s].paused and s not in g.paused_reentry:
                g.paused_reentry[s] = PARAMS['resume_trade_wait_days']
        except Exception:
            # 个股退市/退市整理期/异常 → 跳过
            pass

    # ---- 6. 交易日计数 ----
    g.rebalance_counter += 1
    log.info("[%s] 盘前 | 交易日计数=%d | 候选池=%d 只" %
             (context.current_dt.strftime('%Y-%m-%d'),
              g.rebalance_counter, len(g.universe)))


def market_rebalance(context):
    """
    调仓日 14:50: 计算信号, 调仓
    - 仅在每 rebalance_freq_days 个交易日调仓一次
      (注意: 首日 counter=1, 首次 rebalance 在第 rebalance_freq_days 个交易日)
    - 计算所有候选股综合得分 (三信号加权)
    - 选取得分 >= min_entry_score 的股票, 按得分降序取前 target_holdings 只
    - 应用仓位 / 行业 / 换手率约束
    - 涨停 / 停牌股票跳过买入
    - 已持仓且仍在目标的: order_target_value 自动调仓到目标 (不追加)
    - 已持仓但不在目标: 清仓 (跌停/停牌则顺延)
    """
    # ---- 0. 非交易日守卫 (模拟盘防呆) ----
    if not _is_trading_day(context):
        return

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
    # 本地回测 (runner.py:666) 实际过滤条件是 `score > 0`, 不是 `score >= min_entry_score`
    # min_entry_score 在 spec YAML 中仅作为调参文档, 实际入场只需任意一个入场信号触发
    # 然后按 score 降序排, 取前 target_holdings 只
    p = g.params
    candidates = []
    for stock in factor_panel.index:
        f = factor_panel.loc[stock].to_dict()
        score = entry_score(f, p)
        if score > 0:    # 任何入场信号触发即入候选池
            candidates.append((stock, score))

    if not candidates:
        log.info("无符合入场条件的股票, 清仓不在目标中的持仓")
        execute_rebalance(context, [])
        return

    # ---- 3. 按得分降序, 取前 target_holdings 只 ----
    candidates.sort(key=lambda x: x[1], reverse=True)
    target_stocks = [c[0] for c in candidates[:p['target_holdings']]]

    log.info("候选 %d 只 (score > 0), 入选 top %d 只" %
             (len(candidates), len(target_stocks)))
    for s, sc in candidates[:p['target_holdings']]:
        log.info("  入选: %s, score=%.2f" % (s, sc))

    # ---- 4. 执行调仓 ----
    execute_rebalance(context, target_stocks)


def check_stops_daily(context):
    """
    每日 15:00 收盘后止损检查
    - 更新持有天数与最高收盘价
    - 按优先级链: 固定止损 > 移动止损 > 时间止损 > 均线死叉
    - 跌停当日不执行出场 (被吞), 顺延到下一可交易日
    """
    # ---- 0. 非交易日守卫 (模拟盘防呆) ----
    if not _is_trading_day(context):
        return

    cd = get_current_data()

    for stock in list(g.holdings.keys()):
        # 清理已不在持仓中的记录
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
        h = g.holdings[stock]
        h['holding_days'] = h.get('holding_days', 0) + 1
        h['highest_close'] = max(h.get('highest_close', current_price), current_price)

        # ---- 跌停当日: 所有出场信号不执行 (被吞) ----
        # low_limit 异常为 0 时跳过此检查, 避免永远吞掉信号
        if cd[stock].low_limit > 0 and current_price <= cd[stock].low_limit:
            log.info("[%s] 跌停被吞: %s" %
                     (context.current_dt.strftime('%Y-%m-%d'), stock))
            continue

        # ---- 计算因子 (供均线死叉判断) ----
        factors = calc_factors_one(stock, context)
        if factors is None:
            continue

        # ---- 出场决策 (按优先级) ----
        should_exit, reason = exit_decision(factors, h, current_price)
        if should_exit:
            # 用 order(stock, -closeable) 而非 order_target_value, 绕过 JQuant 内部 0 数量 bug
            pos = context.portfolio.positions[stock]
            sell_amount = -pos.closeable_amount
            if sell_amount < 0:
                order(stock, sell_amount)
            pnl = (current_price - h['entry_price']) / h['entry_price']
            log.info("[%s] 离场: %s, 原因=%s, 盈亏=%.2f%%, 持有=%d日, 卖%d股" %
                     (context.current_dt.strftime('%Y-%m-%d'),
                      stock, reason, pnl * 100, h['holding_days'], -sell_amount))
            g.holdings.pop(stock, None)


# ============================================================
# 3. 因子计算
# ============================================================
def calc_factors_one(security, context):
    """
    计算单只股票的因子 (用于止损检查)
    返回 dict: {close, ma_10, ma_30, atr_14, volume_ratio_20}
    返回 None 表示数据不足

    修改: 改用 history() 替代 attribute_history()
    - 原 attribute_history: 返回的 DataFrame 不含当天 (因为 14:50 时今天 bar 还在累积)
    - 现 history(n, '1d', fq='pre'): 含当天, 跟本地 hist.iloc[:idx+1] 对齐
    """
    p = g.params
    n = max(p['ma_long'], p['atr_period'], p['volume_ma_period']) + 10
    cd = get_current_data()

    # 改用 history() 含当天 (跟本地 hist 对齐)
    # 注: calc_factors_batch 用 history() 已经一致, 这里也改成 history() 保持一致
    df = history(
        n, '1d',
        ['open', 'high', 'low', 'close', 'volume'],
        security, df=True, skip_paused=True, fq='pre'
    )

    if df is None or len(df) < p['ma_long']:
        return None

    close = df['close']
    high  = df['high']
    low   = df['low']
    vol   = df['volume']

    if np.isnan(close.iloc[-1]):
        return None

    # ---- 当日 close 用 14:50 价 (cd.last_price, 即 get_current_data().last_price) ----
    # 注: history() 返回的 close.iloc[-1] 是昨日 (14:50 时今天 close 还没出)
    #     而入场信号算 ma_10/ma_30 用的是昨日及之前, 跟 history() 一致
    #     但 current_close 用 14:50 盘中价 (跟本地 hist.iloc[-1] 含当天 close 对齐)
    current_data = cd.get(security)
    current_close = (current_data.last_price
                     if (current_data and current_data.last_price > 0)
                     else close.iloc[-1])

    # ---- MA(10) / MA(30) (基于 history() 的 close Series, 不含当天) ----
    ma_10 = close.rolling(p['ma_short']).mean().iloc[-1]
    ma_30 = close.rolling(p['ma_long']).mean().iloc[-1]

    # ---- ATR(14): 真实波幅的滚动均值 ----
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low  - close.shift(1)).abs()
    tr  = pd.DataFrame({'a': tr1, 'b': tr2, 'c': tr3}).max(axis=1)
    atr_14 = tr.rolling(p['atr_period']).mean().iloc[-1]
    if atr_14 is None or np.isnan(atr_14):
        atr_14 = None

    # ---- 量比(20): 当日成交量 / 20 日均量 ----
    # history() 不含当天, vol.iloc[-1] 是昨日 vol
    # 用 cd 取不到 vol 字段, 所以 vol_ratio 用昨日 vol, 1 日滞后
    vol_ma_20      = vol.rolling(p['volume_ma_period']).mean().iloc[-1]
    last_vol       = vol.iloc[-1] if len(vol) > 0 else 0
    volume_ratio_20 = (last_vol / vol_ma_20) if (vol_ma_20 and vol_ma_20 > 0) else 0

    return {
        'close':           current_close,
        'ma_10':           ma_10,
        'ma_30':           ma_30,
        'atr_14':          atr_14,
        'volume_ratio_20': volume_ratio_20,
    }


def calc_factors_batch(stock_list, context):
    """
    批量计算所有候选股的因子 (用于调仓日)
    返回 DataFrame: index=股票代码, columns=因子
    """
    p = g.params
    n = max(p['ma_long'], p['atr_period'], p['volume_ma_period']) + 10
    cd = get_current_data()

    # 多标的批量取历史行情
    df_close = history(n, '1d', 'close',  stock_list, df=True, skip_paused=False, fq='pre')
    df_high  = history(n, '1d', 'high',   stock_list, df=True, skip_paused=False, fq='pre')
    df_low   = history(n, '1d', 'low',    stock_list, df=True, skip_paused=False, fq='pre')
    df_vol   = history(n, '1d', 'volume', stock_list, df=True, skip_paused=False, fq='pre')

    if df_close is None or df_close.empty:
        return None

    rows = {}
    for stock in stock_list:
        try:
            close = df_close[stock]
            high  = df_high[stock]
            low   = df_low[stock]
            vol   = df_vol[stock]
        except KeyError:
            continue

        if close is None or len(close.dropna()) < p['ma_long']:
            continue
        if np.isnan(close.iloc[-1]):
            continue

        # 当日价格用 14:50 价 (cd.last_price, get_current_data().last_price)
        # history() 拿到的 close.iloc[-1] 是昨日, 不用作 current_close
        current_data = cd.get(stock)
        current_close = (current_data.last_price
                         if (current_data and current_data.last_price > 0)
                         else close.iloc[-1])

        # ---- MA / ATR / 量比 ----
        ma_10 = close.rolling(p['ma_short']).mean().iloc[-1]
        ma_30 = close.rolling(p['ma_long']).mean().iloc[-1]

        tr1 = high - low
        tr2 = (high - close.shift(1)).abs()
        tr3 = (low  - close.shift(1)).abs()
        tr  = pd.DataFrame({'a': tr1, 'b': tr2, 'c': tr3}).max(axis=1)
        atr_14 = tr.rolling(p['atr_period']).mean().iloc[-1]
        if atr_14 is None or np.isnan(atr_14):
            atr_14 = None

        vol_ma_20       = vol.rolling(p['volume_ma_period']).mean().iloc[-1]
        last_vol        = vol.iloc[-1] if len(vol) > 0 else 0
        volume_ratio_20 = (last_vol / vol_ma_20) if (vol_ma_20 and vol_ma_20 > 0) else 0

        rows[stock] = {
            'close':           current_close,
            'ma_10':           ma_10,
            'ma_30':           ma_30,
            'atr_14':          atr_14,
            'volume_ratio_20': volume_ratio_20,
        }

    if not rows:
        return None
    return pd.DataFrame.from_dict(rows, orient='index')


# ============================================================
# 4. 信号逻辑
# ============================================================
def entry_score(f, p):
    """
    入场信号打分 (权重求和)
    f: 因子 dict
    p: 参数 dict
    返回: 0 ~ 1.0 的加权得分

    信号:
      - ma_golden_cross (0.50):  MA(10) > MA(30)
      - atr_expand      (0.15):  ATR(14) / close > atr_threshold
      - volume_confirm  (0.35):  volume_ratio_20 > vol_threshold
    """
    score = 0.0
    close           = f.get('close')
    ma_10           = f.get('ma_10')
    ma_30           = f.get('ma_30')
    atr_14          = f.get('atr_14')
    volume_ratio_20 = f.get('volume_ratio_20')

    def _ok(x):
        return x is not None and not (isinstance(x, float) and np.isnan(x))

    # ---- 1. 均线金叉 (权重 0.50) ----
    if _ok(ma_10) and _ok(ma_30) and _ok(close) and ma_10 > ma_30:
        score += 0.50

    # ---- 2. ATR 波动率扩张 (权重 0.15) ----
    if _ok(atr_14) and _ok(close) and close > 0:
        atr_ratio = atr_14 / close
        if atr_ratio > p['atr_threshold']:
            score += 0.15

    # ---- 3. 量能放大 (权重 0.35) ----
    if _ok(volume_ratio_20) and volume_ratio_20 > p['vol_threshold']:
        score += 0.35

    return score


def exit_decision(factors, holding, current_price):
    """
    出场决策 (按优先级链, 满足任一即触发)
    返回: (should_exit: bool, reason: str or None)

    优先级: 固定止损 > 移动止损 > 时间止损 > 均线死叉
    """
    p = g.params

    entry_price   = holding.get('entry_price')
    highest_close = holding.get('highest_close', entry_price)
    holding_days  = holding.get('holding_days', 0)

    if entry_price is None or np.isnan(entry_price) or entry_price <= 0:
        return False, None
    if highest_close is None or np.isnan(highest_close):
        highest_close = entry_price

    # ---- 1. 固定止损 (权重 0.02) ----
    stop_price = entry_price * (1 - p['fixed_stop_pct'])
    if current_price < stop_price:
        return True, 'fixed_stop'

    # ---- 2. 移动止损 (权重 0.12) ----
    trail_price = highest_close * (1 - p['trailing_stop_pct'])
    if current_price < trail_price:
        return True, 'trailing_stop'

    # ---- 3. 时间止损 (权重 0.06) ----
    if holding_days >= p['max_holding_days']:
        return True, 'time_stop'

    # ---- 4. 均线死叉 (权重 0.80) ----
    ma_10 = factors.get('ma_10')
    ma_30 = factors.get('ma_30')
    if (ma_10 is not None and ma_30 is not None
            and not np.isnan(ma_10) and not np.isnan(ma_30)
            and ma_10 < ma_30):
        return True, 'ma_death_cross'

    return False, None


# ============================================================
# 5. 调仓执行
# ============================================================
def execute_rebalance(context, target_stocks):
    """
    执行调仓
    - 应用单票/行业/换手率约束
    - 涨停/停牌股票跳过买入
    - A 股 100 股手数处理
    - 更新 g.holdings 记录
    """
    p = g.params
    total_value = context.portfolio.total_value
    cd = get_current_data()

    if total_value <= 0:
        log.warn("总资产 <= 0, 跳过调仓")
        return

    # ---- 1. 计算单票目标价值 ----
    n_targets  = min(len(target_stocks), p['target_holdings'])
    if n_targets <= 0:
        # 清仓所有持仓 (用 order(stock, -closeable) 而非 order_target_value)
        for stock in list(context.portfolio.positions.keys()):
            pos = context.portfolio.positions[stock]
            sell_amount = -pos.closeable_amount
            if sell_amount == 0:
                continue
            sell_order = order(stock, sell_amount)
            if sell_order is not None:
                g.holdings.pop(stock, None)
                log.info("清仓 (无目标): %s, %d股" % (stock, -sell_amount))
        return

    per_target = min(
        total_value * p['max_single_weight'],
        (total_value * (1 - p['cash_reserve'])) / n_targets
    )

    # ---- 2. 应用行业集中度约束 ----
    target_weights = {}
    industry_used  = {}    # {industry: value}
    for stock in target_stocks:
        ind = g.industry_map.get(stock, 'unknown')
        if industry_used.get(ind, 0) + per_target > \
                total_value * p['max_industry_concentration']:
            log.info("行业约束剔除: %s (行业=%s)" % (stock, ind))
            continue
        target_weights[stock] = per_target
        industry_used[ind] = industry_used.get(ind, 0) + per_target

    if not target_weights:
        log.warn("所有候选都被行业约束排除, 跳过调仓")
        return

    # ---- 3. 应用换手率限制 ----
    # 【JQuant 兼容写法】聚宽 Python 3.6 环境下 sum(dict.values()) 不会归约, 直接返回 dict_values
    # 防御式: 显式 list 转换 + 守卫 total_value
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
    available_cash = context.portfolio.available_cash
    for stock, value in target_weights.items():
        # 4.0 异常守护: 个股可能已退市/退市整理期 → cd[stock] 抛 KeyError
        if stock not in cd:
            log.warn("跳过 (无实时数据): %s" % stock)
            continue
        d = cd[stock]

        # 4.1 价格有效性优先判断
        last_price = d.last_price
        if last_price <= 0 or np.isnan(last_price):
            log.info("跳过 (价格异常): %s" % stock)
            continue

        # 4.2 停牌 / 复牌等待
        if d.paused:
            g.paused_reentry[stock] = p['resume_trade_wait_days']
            log.info("跳过 (停牌): %s" % stock)
            continue
        if stock in g.paused_reentry:
            log.info("跳过 (复牌等待): %s, 剩余=%d日" %
                     (stock, g.paused_reentry[stock]))
            continue

        # 4.3 涨停不买 (high_limit 异常为 0 时跳过此检查)
        if d.high_limit > 0 and last_price >= d.high_limit:
            log.info("跳过 (涨停): %s" % stock)
            continue

        # 4.4 科创板 (688xxx) 200 股最小手数, 其他 100 股
        lot_size = p['lot_size_kechuang'] if stock.startswith('688') else 100

        # 4.5 目标股数 (自己算, 不依赖 JQuant 内部)
        target_shares = int(value // (lot_size * last_price)) * lot_size
        if target_shares < lot_size:
            log.info("跳过 (资金不足1手): %s, 需要>=%.0f元" %
                     (stock, lot_size * last_price))
            continue

        # 4.6 资金不足时降档
        if target_shares * last_price > available_cash:
            max_shares = int(available_cash // (lot_size * last_price)) * lot_size
            if max_shares < lot_size:
                log.info("跳过 (现金不足): %s" % stock)
                continue
            target_shares = max_shares
            log.info("降档买入: %s, %d股" % (stock, target_shares))

        # 4.7 已有持仓 → 算 delta
        current_pos = context.portfolio.positions.get(stock)
        current_shares = current_pos.total_amount if current_pos else 0
        # T+1: closeable_amount 可能 < total_amount (今日买入部分不能卖)
        # 但买入不受 T+1 限制, 只需确保不超 target
        delta_shares = target_shares - current_shares
        if delta_shares == 0:
            log.info("无需调仓 (已达标): %s, 当前=%d股" %
                     (stock, current_shares))
            continue
        if delta_shares < 0:
            # 减仓: 不能超 closeable_amount (T+1 限制今日买入不能卖)
            closeable = current_pos.closeable_amount if current_pos else 0
            if -delta_shares > closeable:
                delta_shares = -closeable
                log.info("减仓受 T+1 限制: %s, 仅减 %d股" %
                         (stock, -delta_shares))
            if delta_shares == 0:
                continue

        # 4.8 【关键修复】用 order(stock, shares) 下精确股数, 绕过 JQuant 内部计算
        # 原因: order_target_value(order_value) 在 JQuant 内部有 "下单数量为0" 的 bug
        #       即使 _value=25584 / 100 股明明够买 58 lots, 偶尔会被判 0
        #       改用 order() 直接传股数, JQuant 不再做任何内部推算
        # 科创板 (688xxx) 特殊处理: 市价单需要保护限价, 必须用限价单
        # 限价 = last_price * 1.005 (略高, 确保能成交), 上限 < 10000 元
        if stock.startswith('688'):
            limit_price = min(last_price * 1.005, 9999.99)
            order_result = order(stock, delta_shares, LimitOrderStyle(limit_price))
        else:
            order_result = order(stock, delta_shares)
        if order_result is None:
            log.warn("下单失败: %s, delta=%d股" % (stock, delta_shares))
            continue
        actual_value = abs(delta_shares) * last_price
        available_cash -= actual_value

        # 4.9 记录 / 更新持仓
        # 关键: 已存在持仓时, **不重置** entry_price / holding_days / highest_close
        # 否则会丢失成本基线和持仓天数, 破坏出场信号
        if stock not in g.holdings or g.holdings[stock].get('entry_price') is None:
            g.holdings[stock] = {
                'entry_date':    context.current_dt,
                'entry_price':   last_price,
                'highest_close': last_price,
                'holding_days':  0,
            }
        else:
            # 已持仓的股票: 保留旧 entry_price, 但**新** high 价要更新
            old = g.holdings[stock]
            old['highest_close'] = max(
                old.get('highest_close', last_price), last_price
            )

    # ---- 5. 清仓不在目标中的标的 ----
    # 注意: 即使停牌/跌停, 仍尝试下单卖出
    #   - 聚宽订单在不可成交时**自动挂单**, 股票复牌/打开跌停时自动撮合
    #   - 这样可以避免次日再调仓时再发现, 缩短资金占用周期
    for stock in list(context.portfolio.positions.keys()):
        if stock in target_weights:
            continue
        if stock not in cd:
            continue
        d = cd[stock]
        # 标记原因, 但仍然下单
        reason = ''
        if d.paused:
            reason = '(停牌挂单)'
        elif d.low_limit > 0 and d.last_price <= d.low_limit:
            reason = '(跌停挂单)'

        # 用 order(stock, -shares) 卖可卖的全部, 绕过 JQuant 内部计算
        pos = context.portfolio.positions[stock]
        sell_amount = -pos.closeable_amount
        if sell_amount == 0:
            # closeable=0 但 total>0: 全部是今日买入 (T+1) → 跳过
            log.info("清仓顺延 (T+1 锁定) %s: %s" % (reason, stock))
            continue
        sell_order = order(stock, sell_amount)
        if sell_order is not None:
            g.holdings.pop(stock, None)
            log.info("清仓 (不在目标) %s: %s, %d股" %
                     (reason, stock, -sell_amount))
        else:
            log.info("清仓失败 (待次日) %s: %s" % (reason, stock))

    log.info("调仓完成: 目标 %d 只, 总价值=%.0f" %
             (len(target_weights), sum([target_weights[_s] for _s in target_weights])))


# ============================================================
# 6. 工具函数
# ============================================================
def filter_universe(raw_list, context):
    """
    过滤股票池:
    - 去除停牌股
    - 去除 ST/*ST
    - 去除上市不足 min_listing_days 日
    - 个股退市/退市整理期/异常 → 跳过
    """
    cd = get_current_data()
    out = []
    for s in raw_list:
        try:
            if cd[s].paused:
                continue
            if cd[s].is_st:
                continue
        except Exception:
            # 个股退市/数据缺失 → 跳过
            continue
        # 上市未满 min_listing_days
        hist = attribute_history(s, PARAMS['min_listing_days'], '1d',
                                 ['close'], skip_paused=True, df=False, fq='pre')
        if hist is None or len(hist['close']) < PARAMS['min_listing_days']:
            continue
        if any(np.isnan(hist['close'][-PARAMS['min_listing_days']:])):
            continue
        out.append(s)
    return out


def get_industry_map(stock_list):
    """
    获取股票-行业映射 (申万一级 sw_l1)
    失败时返回空 dict
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
