"""逐笔交易复盘 (v4: params + weight, 含 signal priority 验证)."""
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


def get_factors(strategy, code, date, params):
    """T-1 因子: hist["日期"] < date, 即 date 前一天及之前."""
    hist = load_stock(code.split(".")[0])
    sub = hist[hist["日期"] < date].sort_values("日期").reset_index(drop=True)
    if len(sub) < 20:
        return None
    return strategy.compute_factors(sub, params)


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

        if i == 0:
            prev_close = close
            continue

        factors = strategy.compute_factors(df.iloc[:i], params)

        if pos is not None:
            pos["highest"] = max(pos["highest"], close)
            pos["holding_days"] = (date - pos["entry_date"]).days
            pos_dict = {
                "current_price": prev_close,
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
                    "shares": pos["shares"],
                })
                pos = None
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

    # 期末强制平仓
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
            "shares": pos["shares"],
        })

    return trades


def verify_trade(strategy, params, weights, t):
    """单笔交易核对. 与新模型 (T-1 因子 + T 开盘成交) 一致.

    注: trailing_stop / fixed_stop 的触发价 = T-1 收盘 (策略决策时看到的"当前价")
        而非 T 收盘. 其它信号 (ma_death_cross / time_stop) 与价格无关, 不变.
    """
    out = {"entry": None, "exit": None, "priority": None, "ash_entry": None, "ash_exit": None}

    # ===== ENTRY =====
    f = get_factors(strategy, t["code"], t["entry_date"], params)
    if f is None:
        out["entry"] = (False, "no_factors")
    else:
        fv = {k: float(v.iloc[-1]) for k, v in f.items()}
        ma_cross = fv["ma_5"] > fv["ma_20"]
        atr_up = fv["atr_14"] > fv["atr_14_prev"]
        atr_pct = fv["atr_14"] / fv["close"]
        atr_ok = atr_up and atr_pct > params["atr_min_threshold"]
        vol_ok = fv["volume_ratio_20"] > params["volume_breakout_ratio"]
        entry_ok = ma_cross and (atr_ok or vol_ok)
        out["entry"] = (entry_ok, fv, atr_ok, vol_ok, ma_cross)
    bar = get_bar(t["code"], t["entry_date"])
    if bar is not None:
        # A 股规则: T 开盘成交, 用 T-1 收盘判定一字板
        hist = load_stock(t["code"].split(".")[0])
        sub_signal = hist[hist["日期"] < t["entry_date"]].sort_values("日期").reset_index(drop=True)
        prev_close = float(sub_signal.iloc[-1]["收盘价"]) if len(sub_signal) else 0.0
        cb = can_buy_at_open(bar, prev_close, t["code"])
        out["ash_entry"] = (cb, is_limit_up(bar), bool(bar.get("是否ST", False)),
                            is_one_word_board(bar) and is_limit_up(bar), bar.get("涨幅%"))

    # ===== EXIT + PRIORITY =====
    f = get_factors(strategy, t["code"], t["exit_date"], params)
    if f is None:
        out["exit"] = (False, "no_factors")
    else:
        fv = {k: float(v.iloc[-1]) for k, v in f.items()}
        # T-1 收盘价 (= prev_close) 作为止损决策时的"当前价"
        hist = load_stock(t["code"].split(".")[0])
        sub_signal = hist[hist["日期"] < t["exit_date"]].sort_values("日期").reset_index(drop=True)
        prev_close = float(sub_signal.iloc[-1]["收盘价"]) if len(sub_signal) else 0.0
        # 每个信号都检查 (独立看), 看哪个真的触发了
        all_trig = {}
        all_trig["ma_death_cross"] = fv["ma_5"] < fv["ma_20"]
        # 止损信号决策价 = prev_close (T-1 收盘), 不是 T 收盘 fv["close"]
        all_trig["trailing_stop"] = prev_close < t["highest"] * (1 - params["trailing_stop_pct"])
        all_trig["fixed_stop"] = prev_close < t["entry_price"] * (1 - params["fixed_stop_pct"])
        all_trig["time_stop"] = t["holding_days"] >= params["max_holding_days"]
        # 触发的列表
        triggered = [s for s, v in all_trig.items() if v]
        chosen = t["exit_signal"]
        # end_of_data 是期末强制平仓, 永远算 ok, priority 验证不适用
        if chosen == "end_of_data":
            all_trig["end_of_data"] = True
            out["exit"] = (True, all_trig, fv)
            out["priority"] = (True, [], None)  # 跳过 priority 检查
        else:
            # spec 优先级链: 按 weight 降序
            ew = weights["exit"]
            priority_chain = sorted(ew.keys(), key=ew.get, reverse=True)
            # 在 triggered 中, 优先级最高的就是 chosen
            priority_pick = next((s for s in priority_chain if s in triggered), None)
            priority_ok = (priority_pick == chosen)
            out["exit"] = (all_trig.get(chosen, False), all_trig, fv)
            out["priority"] = (priority_ok, triggered, priority_pick)
    bar = get_bar(t["code"], t["exit_date"])
    if bar is not None:
        # A 股规则: T 开盘成交
        hist = load_stock(t["code"].split(".")[0])
        sub_signal = hist[hist["日期"] < t["exit_date"]].sort_values("日期").reset_index(drop=True)
        prev_close = float(sub_signal.iloc[-1]["收盘价"]) if len(sub_signal) else 0.0
        cs = can_sell_at_open(bar, prev_close, t["code"])
        out["ash_exit"] = (cs, is_limit_down(bar), is_one_word_down(bar), bar.get("涨幅%"))
    return out


def print_trade(n, t, v):
    win = "WIN " if t["pnl"] > 0 else "LOSS"
    ed = t["entry_date"].strftime("%Y-%m-%d")
    xd = t["exit_date"].strftime("%Y-%m-%d")
    print(f"--- Trade #{n}  [{win}]  {t['code']}  {ed}->{xd}  ({t['holding_days']}d)"
          f"  pnl={t['pnl']:+.2f}  signal={t['exit_signal']} ---")
    # entry
    if v["entry"][0] is False and isinstance(v["entry"][1], str):
        print(f"  ENTRY: {v['entry'][1]} [FAIL]")
    else:
        ok, fv, atr_ok, vol_ok, ma_cross = v["entry"]
        print(f"  ENTRY: ma_cross={ma_cross} atr_ok={atr_ok} vol_ok={vol_ok}"
              f" -> spec_required={ok} [{'PASS' if ok else 'FAIL'}]")
        print(f"    factors: close={fv['close']:.3f} ma5={fv['ma_5']:.3f} ma20={fv['ma_20']:.3f}"
              f" atr14={fv['atr_14']:.4f} atr14_prev={fv['atr_14_prev']:.4f}"
              f" vol_r20={fv['volume_ratio_20']:.3f}")
    if v["ash_entry"] is not None:
        cb, zt, st, ow, pct = v["ash_entry"]
        flag = "PASS" if cb else "FAIL"
        print(f"  A-share entry: can_buy={cb} (ST={st}, zt={zt}, one_word_zt={ow}, pct={pct}%) [{flag}]")
    # exit
    if v["exit"][0] is False and isinstance(v["exit"][1], str):
        print(f"  EXIT: {v['exit'][1]} [FAIL]")
    else:
        chosen_ok, all_trig, fv = v["exit"]
        print(f"  EXIT: chosen_signal={t['exit_signal']} -> rule_satisfied={chosen_ok}"
              f" [{'PASS' if chosen_ok else 'FAIL'}]")
        print(f"    factors: close={fv['close']:.3f} ma5={fv['ma_5']:.3f} ma20={fv['ma_20']:.3f}"
              f" highest={t['highest']:.3f} entry={t['entry_price']:.3f}")
    # priority
    if v["priority"] is not None:
        pri_ok, triggered, pick = v["priority"]
        chain_str = " > ".join(t["exit_signal"] if s == t["exit_signal"] else f"({s})" for s in triggered)
        print(f"  priority: triggered={triggered}  spec_pick={pick}  matches_chosen={pri_ok}"
              f" [{'PASS' if pri_ok else 'FAIL'}]")
    if v["ash_exit"] is not None:
        cs, dt, ow_dt, pct = v["ash_exit"]
        flag = "PASS" if cs else "FAIL"
        print(f"  A-share exit: can_sell={cs} (dt={dt}, one_word_dt={ow_dt}, pct={pct}%) [{flag}]")
    # pnl
    expected = (t["exit_price"] - t["entry_price"]) * t["shares"]
    if abs(expected - t["pnl"]) < 1.0:
        print(f"  pnl: shares={t['shares']} expected={expected:+.2f} actual={t['pnl']:+.2f} [PASS]")
    else:
        print(f"  pnl: shares={t['shares']} expected={expected:+.2f} actual={t['pnl']:+.2f} [FAIL]")
    print()


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
    print("  PARAMS 模式 - 全量交易明细 + 策略规则 + A 股硬约束 + Signal priority")
    print("=" * 80)
    all_trades = []
    for code in ["000001.SZ", "000002.SZ", "600000.SH", "600519.SH", "000333.SZ"]:
        all_trades.extend(replay_params(strategy, params, weights, code, "2024-01-01", "2024-03-31"))
    print(f"\n共 {len(all_trades)} 笔 closed trades\n")
    n = 0
    pass_n = 0
    fail_n = 0
    for t in all_trades:
        n += 1
        v = verify_trade(strategy, params, weights, t)
        print_trade(n, t, v)
        # 统计
        all_pass = (
            v["entry"] and v["entry"][0] is True
            and v["exit"] and v["exit"][0] is True
            and v["priority"] and v["priority"][0]
            and v["ash_entry"] and v["ash_entry"][0]
            and v["ash_exit"] and v["ash_exit"][0]
        )
        if all_pass:
            pass_n += 1
        else:
            fail_n += 1
    print("=" * 80)
    print(f"PARAMS 模式总结: 全部通过 {pass_n}/{n} 笔, 失败 {fail_n} 笔")
    print("=" * 80)


if __name__ == "__main__":
    main()
