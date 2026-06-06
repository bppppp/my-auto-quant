"""Weight 模式逐笔验证 (从 portfolio.history 反查 entry/exit 日期)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve()
SUBJECTS_DIR = HERE.parents[1]
if str(SUBJECTS_DIR) not in sys.path:
    sys.path.insert(0, str(SUBJECTS_DIR))
os.chdir(SUBJECTS_DIR)

import logging
logging.basicConfig(level=logging.WARNING)

from subject.backtest.runner import BacktestRunner
from subject.backtest.data_loader import load_stock
from subject.backtest.a_share_rules import can_buy, can_sell
from importlib.util import spec_from_file_location, module_from_spec


def load_strategy():
    spec = spec_from_file_location("s", "ma_cross_atr_volume/generated/strategy.py")
    mod = module_from_spec(spec)
    sys.modules["s"] = mod
    spec.loader.exec_module(mod)
    return mod.Strategy(), mod


def main():
    strategy, _ = load_strategy()
    runner = BacktestRunner(
        strategy_name="ma_cross_atr_volume",
        mode="weight",
        start_date="2024-01-01",
        end_date="2024-03-31",
        initial_capital=1_000_000,
        subjects_dir=".",
        test_universe_override=["000001.SZ", "000002.SZ", "600000.SH", "600519.SH", "000333.SZ"],
        max_stocks=5,
    )
    params = runner.params
    weights = runner.weights

    print("=" * 80)
    print("  WEIGHT 模式 - 逐笔验证 (从 portfolio.history 反查 entry/exit 日期)")
    print("=" * 80)

    # 重跑 weight 模式, 但用同一个 runner 拿到 portfolio 的 history
    # 简化: 重跑主循环, 但保存 portfolio.history
    from subject.backtest.data_loader import load_day
    from subject.backtest.universe import exclude_bj, exclude_st
    from subject.backtest.portfolio import Portfolio
    from subject.backtest.signals import rank_top_n
    from subject.backtest.portfolio import (
        enforce_industry_concentration, enforce_max_single_weight,
        enforce_max_turnover, load_industry_map,
    )

    portfolio = Portfolio(initial_capital=1_000_000, cash=1_000_000)
    trading_dates = runner._enumerate_trading_dates()
    target_n = int(params.get("target_holdings", 8))
    freq = int(params.get("rebalance_freq_days", 5))
    max_single = float(params.get("max_single_weight", 0.10))
    max_turnover = float(params.get("max_turnover_per_rebalance", 0.50))

    # 预加载历史
    HISTORY_BUFFER_DAYS = 60
    earliest_needed = pd.Timestamp("2024-01-01") - pd.Timedelta(days=HISTORY_BUFFER_DAYS)
    stock_history = {}
    for code in runner.universe:
        hist = load_stock(code.split(".")[0])
        hist = hist[hist["日期"] >= earliest_needed]
        hist = hist[hist["日期"] <= pd.Timestamp("2024-03-31")]
        hist = hist.sort_values("日期").reset_index(drop=True)
        if len(hist) >= 20:
            stock_history[code] = hist

    all_trades = []
    for bar_idx, date_str in enumerate(trading_dates, 1):
        date = pd.Timestamp(date_str)
        df = load_day(date_str)
        df = exclude_bj(df)
        df = exclude_st(df)
        df = df[df["代码"].isin(set(runner.universe))].copy().reset_index(drop=True)
        if len(df) == 0:
            continue
        day_data = {row["代码"]: row for _, row in df.iterrows()}

        # 算因子 + entry score
        scores = {}
        factors_by_code = {}
        for code, row in day_data.items():
            if code not in stock_history:
                continue
            hist = stock_history[code]
            mask = hist["日期"] <= date
            if not mask.any():
                continue
            idx = hist.index[mask][-1]
            factors = strategy.compute_factors(hist.iloc[:idx+1], params)
            factors_by_code[code] = factors
            try:
                scores[code] = strategy.entry_score(factors, params, weights)
            except Exception:
                scores[code] = 0.0
        prices = {code: float(r["收盘价"]) for code, r in day_data.items()}

        # 出场
        for code in list(portfolio.positions.keys()):
            if code not in day_data or code not in factors_by_code:
                continue
            pos = portfolio.positions[code]
            close = float(day_data[code]["收盘价"])
            portfolio.update_after_bar(code, close)
            factors = factors_by_code[code]
            pos_dict = pos.to_state_dict()
            pos_dict["current_price"] = close
            pos_dict["pnl_pct"] = (close - pos.entry_price) / pos.entry_price if pos.entry_price > 0 else 0.0
            try:
                sig = strategy.should_exit(pos_dict, factors, params, weights)
            except Exception:
                sig = None
            if sig and can_sell(day_data[code]):
                pnl = (close - pos.entry_price) * pos.shares
                entry_date = pos.entry_date
                entry_price = pos.entry_price
                portfolio.sell(code, close, date)
                all_trades.append({
                    "code": code,
                    "entry_date": entry_date,
                    "entry_price": entry_price,
                    "exit_date": date,
                    "exit_price": close,
                    "exit_signal": sig,
                    "pnl": pnl,
                    "holding_days": pos.holding_days,
                    "highest": pos.highest,
                })

        # 调仓
        if bar_idx % freq == 0:
            top_codes = rank_top_n(scores, target_n)
            if top_codes:
                target_weights = {c: 1.0/target_n for c in top_codes}
                target_weights = enforce_max_single_weight(target_weights, max_single)
                try:
                    industry_map = load_industry_map(runner.universe, date_str)
                    target_weights = enforce_industry_concentration(target_weights, industry_map, 0.30)
                except Exception:
                    pass
                current_weights = portfolio.weights(prices)
                target_weights = enforce_max_turnover(current_weights, target_weights, max_turnover)
                tv = portfolio.total_value(prices)
                # 卖出不在 target 的
                for code in list(portfolio.positions.keys()):
                    if code not in target_weights:
                        if code in day_data and can_sell(day_data[code]):
                            pos = portfolio.positions[code]
                            close = float(day_data[code]["收盘价"])
                            pnl = (close - pos.entry_price) * pos.shares
                            entry_date = pos.entry_date
                            entry_price = pos.entry_price
                            portfolio.sell(code, close, date)
                            all_trades.append({
                                "code": code,
                                "entry_date": entry_date,
                                "entry_price": entry_price,
                                "exit_date": date,
                                "exit_price": close,
                                "exit_signal": "rebalance",
                                "pnl": pnl,
                                "holding_days": pos.holding_days,
                                "highest": pos.highest,
                            })
                # 买入
                for code, weight in target_weights.items():
                    if code in portfolio.positions or code not in day_data:
                        continue
                    if not can_buy(day_data[code]):
                        continue
                    close = float(day_data[code]["收盘价"])
                    amount = tv * weight
                    shares = int(amount / close / 100) * 100
                    if shares > 0:
                        portfolio.buy(code, close, shares, date)

    print(f"\n共 {len(all_trades)} 笔 closed trades\n")
    n = 0
    pass_n = 0
    fail_n = 0
    for t in all_trades:
        n += 1
        ed = t["entry_date"].strftime("%Y-%m-%d") if hasattr(t["entry_date"], "strftime") else str(t["entry_date"])
        xd = t["exit_date"].strftime("%Y-%m-%d") if hasattr(t["exit_date"], "strftime") else str(t["exit_date"])
        win = "WIN " if t["pnl"] > 0 else "LOSS"
        print(f"--- Trade #{n}  [{win}]  {t['code']}  {ed}->{xd}  ({t['holding_days']}d)"
              f"  pnl={t['pnl']:+.2f}  signal={t['exit_signal']} ---")
        # entry factors
        hist = load_stock(t["code"].split(".")[0])
        sub = hist[hist["日期"] <= t["entry_date"]].sort_values("日期").reset_index(drop=True)
        if len(sub) < 20:
            print(f"  ENTRY: history<20 [FAIL]")
        else:
            f = strategy.compute_factors(sub, params)
            fv = {k: float(v.iloc[-1]) for k, v in f.items()}
            ma_cross = fv["ma_5"] > fv["ma_20"]
            atr_up = fv["atr_14"] > fv["atr_14_prev"]
            atr_pct = fv["atr_14"] / fv["close"]
            atr_ok = atr_up and atr_pct > params["atr_min_threshold"]
            vol_ok = fv["volume_ratio_20"] > params["volume_breakout_ratio"]
            entry_ok = ma_cross and (atr_ok or vol_ok)
            mark = "PASS" if entry_ok else "FAIL"
            print(f"  ENTRY: ma_cross={ma_cross} atr_ok={atr_ok} vol_ok={vol_ok}"
                  f" -> spec_required={entry_ok} [{mark}]")
            print(f"    factors: close={fv['close']:.3f} ma5={fv['ma_5']:.3f} ma20={fv['ma_20']:.3f}"
                  f" atr14={fv['atr_14']:.4f} atr14_prev={fv['atr_14_prev']:.4f}"
                  f" vol_r20={fv['volume_ratio_20']:.3f}")
        # exit
        sub = hist[hist["日期"] <= t["exit_date"]].sort_values("日期").reset_index(drop=True)
        if len(sub) < 20:
            print(f"  EXIT: history<20 [FAIL]")
        else:
            f = strategy.compute_factors(sub, params)
            fv = {k: float(v.iloc[-1]) for k, v in f.items()}
            sig = t["exit_signal"]
            chosen_ok = False
            detail = ""
            if sig == "ma_death_cross":
                chosen_ok = fv["ma_5"] < fv["ma_20"]
                detail = f"{fv['ma_5']:.3f} < {fv['ma_20']:.3f}"
            elif sig == "trailing_stop":
                thr = t["highest"] * (1 - params["trailing_stop_pct"])
                chosen_ok = fv["close"] < thr
                detail = f"{fv['close']:.3f} < {thr:.3f}  (highest={t['highest']:.3f} * {1-params['trailing_stop_pct']:.3f})"
            elif sig == "fixed_stop":
                thr = t["entry_price"] * (1 - params["fixed_stop_pct"])
                chosen_ok = fv["close"] < thr
                detail = f"{fv['close']:.3f} < {thr:.3f}"
            elif sig == "time_stop":
                chosen_ok = t["holding_days"] >= params["max_holding_days"]
                detail = f"{t['holding_days']} >= {params['max_holding_days']}"
            elif sig == "rebalance":
                chosen_ok = True
                detail = "rebalance out"
            mark = "PASS" if chosen_ok else "FAIL"
            print(f"  EXIT: {sig} -> {detail} [{mark}]")
            print(f"    factors: close={fv['close']:.3f} ma5={fv['ma_5']:.3f} ma20={fv['ma_20']:.3f}"
                  f" highest={t['highest']:.3f} entry={t['entry_price']:.3f}")
        print()
        if chosen_ok and entry_ok:
            pass_n += 1
        else:
            fail_n += 1
    print("=" * 80)
    print(f"WEIGHT 模式总结: 全部通过 {pass_n}/{n} 笔, 失败 {fail_n} 笔")
    print("=" * 80)


if __name__ == "__main__":
    main()
