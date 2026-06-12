"""逐笔交易复盘验证 (v3: 干净 ASCII 输出)."""
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
from subject.backtest.a_share_rules import (
    can_buy, can_buy_at_open, can_sell, can_sell_at_open,
    is_limit_up, is_limit_down, is_one_word_board, is_one_word_down,
)
from importlib.util import spec_from_file_location, module_from_spec


def load_strategy():
    spec = spec_from_file_location("s", "ma_cross_atr_volume/generated/strategy.py")
    mod = module_from_spec(spec)
    sys.modules["s"] = mod
    spec.loader.exec_module(mod)
    return mod.Strategy(), mod


def get_bar(code, date):
    hist = load_stock(code.split(".")[0])
    sub = hist[hist["日期"] == date]
    if len(sub) == 0:
        return None
    return sub.iloc[0]


def get_factors_at(strategy, code, date, params):
    hist = load_stock(code.split(".")[0])
    hist = hist[hist["日期"] <= date].sort_values("日期").reset_index(drop=True)
    if len(hist) < 20:
        return None
    return strategy.compute_factors(hist, params)


def replay_params(strategy, params, weights, code, start, end):
    """回放 params 模式单只股的回测. 与 runner._backtest_single_stock 保持一致:

    - T-1 因子 (df.iloc[:i], 不含今天)
    - T 开盘成交 (用 open, 不是 close)
    - Day 0 跳过 (无 T-1 数据, 不交易)
    - 期末强制平仓 (用 last close 估算 PnL, signal='end_of_data')
    """
    df = load_stock(code.split(".")[0])
    df = df[df["日期"] >= pd.Timestamp(start)]
    df = df[df["日期"] <= pd.Timestamp(end)]
    df = df.sort_values("日期").reset_index(drop=True)
    if len(df) < 20:
        return []
    per_stock_capital = 1_000_000 * params.get("max_single_weight", 0.10)
    pos = None
    trades = []
    prev_close = None
    for i in range(len(df)):
        bar = df.iloc[i]
        date = bar["日期"]
        open_px = float(bar["开盘价"])
        close = float(bar["收盘价"])

        # Day 0: 无 T-1 数据, 跳过交易
        if i == 0:
            prev_close = close
            continue

        # T-1 因子
        factors = strategy.compute_factors(df.iloc[:i], params)

        # 出场 → at T open
        if pos is not None:
            pos["highest"] = max(pos["highest"], close)
            pos["holding_days"] = (date - pos["entry_date"]).days
            pos_dict = {
                "current_price": prev_close,  # 决策时看到的"当前价" = T-1 收盘
                "entry_price": pos["entry_price"],
                "highest": pos["highest"],
                "holding_days": pos["holding_days"],
            }
            sig = strategy.should_exit(pos_dict, factors, params, weights)
            if sig and can_sell_at_open(bar, prev_close, code):
                trades.append({
                    "code": code,
                    "entry_date": pos["entry_date"],
                    "entry_price": pos["entry_price"],
                    "exit_date": date,
                    "exit_price": open_px,
                    "exit_signal": sig,
                    "pnl": (open_px - pos["entry_price"]) * pos["shares"],
                    "holding_days": pos["holding_days"],
                    "highest": pos["highest"],
                })
                pos = None

        # 入场 → at T open
        if pos is None:
            score = strategy.entry_score(factors, params, weights)
            if score > 0 and can_buy_at_open(bar, prev_close, code):
                shares = int(per_stock_capital / open_px / 100) * 100
                if shares > 0:
                    pos = {
                        "entry_date": date,
                        "entry_price": open_px,
                        "shares": shares,
                        "highest": open_px,
                    }

        prev_close = close

    # 期末强制平仓 (与 runner 一致: 用 last close 估算)
    if pos is not None:
        last_close = float(df.iloc[-1]["收盘价"])
        trades.append({
            "code": code,
            "entry_date": pos["entry_date"],
            "entry_price": pos["entry_price"],
            "exit_date": df.iloc[-1]["日期"],
            "exit_price": last_close,
            "exit_signal": "end_of_data",
            "pnl": (last_close - pos["entry_price"]) * pos["shares"],
            "holding_days": pos["holding_days"],
            "highest": pos["highest"],
        })

    return trades


def main():
    strategy, _ = load_strategy()
    runner = BacktestRunner(
        strategy_name="ma_cross_atr_volume",
        mode="params",
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
    print("  PARAMS 模式 - 全量交易明细 (Q1 2024, 5 只股)")
    print("=" * 80)

    all_trades = []
    for code in ["000001.SZ", "000002.SZ", "600000.SH", "600519.SH", "000333.SZ"]:
        all_trades.extend(replay_params(strategy, params, weights, code, "2024-01-01", "2024-03-31"))

    print(f"\n共 {len(all_trades)} 笔 closed trades\n")

    for n, t in enumerate(all_trades, 1):
        win = t["pnl"] > 0
        mark = "WIN " if win else "LOSS"
        ed = t["entry_date"].strftime("%Y-%m-%d")
        xd = t["exit_date"].strftime("%Y-%m-%d")
        print(f"--- Trade #{n}  [{mark}]  {t['code']} ---")
        print(f"  period: {ed} -> {xd}  ({t['holding_days']} days)")
        print(f"  price : entry={t['entry_price']:.2f}  exit={t['exit_price']:.2f}"
              f"  high={t['highest']:.2f}  pnl={t['pnl']:+.2f}")

        # === ENTRY verification ===
        # 决策信号来自 T-1 因子, 成交在 T 开盘. entry_date = T.
        print(f"  [ENTRY @ {ed}]  (signal: T-1 factors, fill: T open)")
        hist = load_stock(t["code"].split(".")[0])
        # T-1 因子 = entry_date 前一天 (即 hist["日期"] < entry_date)
        sub_signal = hist[hist["日期"] < t["entry_date"]].sort_values("日期").reset_index(drop=True)
        if len(sub_signal) < 20:
            print(f"    [FAIL] T-1 history < 20")
        else:
            f = strategy.compute_factors(sub_signal, params)
            fv = {k: float(v.iloc[-1]) for k, v in f.items()}
            print(f"    T-1 factors: close={fv['close']:.3f}  ma_5={fv['ma_5']:.3f}  ma_20={fv['ma_20']:.3f}"
                  f"  atr_14={fv['atr_14']:.4f}  atr_14_prev={fv['atr_14_prev']:.4f}"
                  f"  vol_r20={fv['volume_ratio_20']:.3f}")
            ma_cross = fv["ma_5"] > fv["ma_20"]
            atr_up = fv["atr_14"] > fv["atr_14_prev"]
            atr_pct = fv["atr_14"] / fv["close"]
            atr_ok = atr_up and atr_pct > params["atr_min_threshold"]
            vol_ok = fv["volume_ratio_20"] > params["volume_breakout_ratio"]
            entry_ok = ma_cross and (atr_ok or vol_ok)
            print(f"    [OK]  ma_5 > ma_20: {fv['ma_5']:.3f} > {fv['ma_20']:.3f}")
            print(f"    [OK]  atr_14 > atr_14_prev: {fv['atr_14']:.4f} > {fv['atr_14_prev']:.4f}")
            print(f"    [OK]  atr_14/close > {params['atr_min_threshold']}: {atr_pct:.4f} > {params['atr_min_threshold']}")
            print(f"    [OK]  vol_r20 > {params['volume_breakout_ratio']}: {fv['volume_ratio_20']:.3f} > {params['volume_breakout_ratio']}")
            print(f"    -> entry spec (ma_cross + (atr_ok or vol_ok)) = {entry_ok} [PASS]" if entry_ok
                  else f"    -> entry spec FAILED [FAIL]")
            # A 股规则 (T 开盘, 用 T-1 收盘价判定一字板)
            bar = get_bar(t["code"], t["entry_date"])
            prev_close = float(sub_signal.iloc[-1]["收盘价"])  # T-1 收盘
            cb = can_buy_at_open(bar, prev_close, t["code"])
            print(f"    A-share @ open: can_buy={cb}  (ST={bool(bar.get('是否ST', False))}, "
                  f"open={float(bar['开盘价']):.2f}, prev_close={prev_close:.2f}, "
                  f"pct={bar.get('涨幅%')}%)")
            if not cb:
                print(f"    -> [FAIL] A-share rule violated at entry!")
        print()

        # === EXIT verification ===
        # 决策信号来自 T-1 因子, 成交在 T 开盘. exit_date = T.
        print(f"  [EXIT @ {xd}  signal={t['exit_signal']}]  (signal: T-1 factors, fill: T open)")
        sub_signal = hist[hist["日期"] < t["exit_date"]].sort_values("日期").reset_index(drop=True)
        if len(sub_signal) < 20:
            print(f"    [FAIL] T-1 history < 20")
        else:
            f = strategy.compute_factors(sub_signal, params)
            fv = {k: float(v.iloc[-1]) for k, v in f.items()}
            prev_close = float(sub_signal.iloc[-1]["收盘价"])  # T-1 收盘 (策略看到的"当前价")
            print(f"    T-1 factors: close={fv['close']:.3f}  ma_5={fv['ma_5']:.3f}  ma_20={fv['ma_20']:.3f}"
                  f"  highest={t['highest']:.3f}  entry={t['entry_price']:.3f}")
            sig = t["exit_signal"]
            ok = False
            detail = ""
            # 注: trailing/fixed_stop 决策用的是 T-1 收盘价 (= prev_close), 不是 T 收盘价
            if sig == "ma_death_cross":
                ok = fv["ma_5"] < fv["ma_20"]
                detail = f"{fv['ma_5']:.3f} < {fv['ma_20']:.3f}"
            elif sig == "trailing_stop":
                thr = t["highest"] * (1 - params["trailing_stop_pct"])
                ok = prev_close < thr
                detail = f"prev_close {prev_close:.3f} < thr {thr:.3f}  (highest={t['highest']:.3f} * {1-params['trailing_stop_pct']:.3f})"
            elif sig == "fixed_stop":
                thr = t["entry_price"] * (1 - params["fixed_stop_pct"])
                ok = prev_close < thr
                detail = f"prev_close {prev_close:.3f} < thr {thr:.3f}  (entry={t['entry_price']:.3f} * {1-params['fixed_stop_pct']:.3f})"
            elif sig == "time_stop":
                ok = t["holding_days"] >= params["max_holding_days"]
                detail = f"{t['holding_days']} >= {params['max_holding_days']}"
            elif sig == "end_of_data":
                # 期末强制平仓, 永远 PASS
                ok = True
                detail = "end_of_data: 期末强制平仓, 无信号"
            mark2 = "[OK]  " if ok else "[FAIL]"
            print(f"    {mark2} {sig} rule: {detail}")
            # A 股规则 (T 开盘, 用 T-1 收盘价判定一字板)
            bar = get_bar(t["code"], t["exit_date"])
            cs = can_sell_at_open(bar, prev_close, t["code"])
            print(f"    A-share @ open: can_sell={cs}  (open={float(bar['开盘价']):.2f}, "
                  f"prev_close={prev_close:.2f}, pct={bar.get('涨幅%')}%)")
            if not cs:
                print(f"    -> [FAIL] A-share rule violated at exit (should be swallowed)!")
        print()

        # === pnl formula check ===
        shares = (100_000 // (t["entry_price"] * 100)) * 100
        expected = (t["exit_price"] - t["entry_price"]) * shares
        if abs(expected - t["pnl"]) < 1.0:
            print(f"  pnl formula: shares={shares}, expected={expected:+.2f}, actual={t['pnl']:+.2f} [PASS]")
        else:
            print(f"  pnl formula: shares={shares}, expected={expected:+.2f}, actual={t['pnl']:+.2f}, diff={abs(expected-t['pnl']):.2f} [FAIL]")
        print()


if __name__ == "__main__":
    main()
