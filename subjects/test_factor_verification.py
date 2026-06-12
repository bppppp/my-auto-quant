#!/usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import annotations
import os, sys
from pathlib import Path
_HERE = Path(__file__).resolve()
_SUBJECTS = _HERE.parent
_PROJECT = _SUBJECTS.parent
for p in [_SUBJECTS, _PROJECT]:
    if str(p) not in sys.path: sys.path.insert(0, str(p))
import logging, argparse
import pandas as pd
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger(__name__)

def load_stock_test(code):
    from subject.backtest.data_loader.by_stock import load_stock
    return load_stock(code).tail(500).reset_index(drop=True)

def load_factor_test(code):
    from subject.backtest.data_loader.by_stock_factor import try_load_stock_factor
    return try_load_stock_factor(code)

def test_round1(df, code):
    from subject.factors import ma, atr, rsi, donchian_high, donchian_low, volume_ratio, mom
    from subject.backtest.data_loader.by_stock_factor import try_load_stock_factor
    res = {"passed": 0, "failed": 0, "warnings": [], "details": []}
    factor_df = try_load_stock_factor(code)
    test_df = df.tail(200).reset_index(drop=True)
    col_map = {"ma_5": "ma_5", "ma_10": "ma_10", "ma_20": "ma_20", "ma_30": "ma_30", "ma_60": "ma_60", "atr_14": "atr_14", "rsi_14": "rsi_14", "donchian_high_20": "donchian_high_20", "donchian_low_20": "donchian_low_20", "volume_ratio_20": "volume_ratio_20", "mom_60": "mom_60"}
    cases = [("ma_5", lambda: ma(test_df["收盘价"], 5)), ("ma_10", lambda: ma(test_df["收盘价"], 10)), ("ma_20", lambda: ma(test_df["收盘价"], 20)), ("ma_30", lambda: ma(test_df["收盘价"], 30)), ("ma_60", lambda: ma(test_df["收盘价"], 60)), ("atr_14", lambda: atr(test_df["最高价"], test_df["最低价"], test_df["收盘价"], 14)), ("rsi_14", lambda: rsi(test_df["收盘价"], 14)), ("donchian_high_20", lambda: donchian_high(test_df["最高价"], 20)), ("donchian_low_20", lambda: donchian_low(test_df["最低价"], 20)), ("volume_ratio_20", lambda: volume_ratio(test_df["成交量（股）"], 20)), ("mom_60", lambda: mom(test_df["收盘价"], 60))]
    for name, fn in cases:
        try:
            computed = fn()
            if factor_df is not None and col_map.get(name) in factor_df.columns:
                common = set(test_df["日期"]) & set(factor_df["日期"])
                if len(common) < 50: res["warnings"].append(f"{name}: <50 dates"); continue
                diffs = []
                for d in list(common)[:100]:
                    it = test_df[test_df["日期"] == d].index
                    ip = factor_df[factor_df["日期"] == d].index
                    if len(it) > 0 and len(ip) > 0:
                        v1, v2 = computed.iloc[it[0]], factor_df[col_map[name]].iloc[ip[0]]
                        if pd.notna(v1) and pd.notna(v2): diffs.append(abs(float(v1) - float(v2)))
                md = max(diffs) if diffs else 0
                if md < 0.001: res["passed"] += 1; res["details"].append(f"  [PASS] {name}: diff={md:.6f}")
                else: res["failed"] += 1; res["warnings"].append(f"  [FAIL] {name}: diff={md:.6f}"); res["details"].append(f"  [FAIL] {name}: diff={md:.6f}")
            else: res["passed"] += 1; res["details"].append(f"  [PASS] {name}: OK")
        except Exception as e: res["failed"] += 1; res["details"].append(f"  [FAIL] {name}: {str(e)}")
    return res

def test_round2(df, code):
    from subject.factors._cache import bind_current_code, bind_current_date, bind_factor_cache, reset_current_code, reset_current_date, clear_cache, try_get_cached_factor
    res = {"passed": 0, "failed": 0, "warnings": [], "details": []}
    clear_cache()
    tdf = df.tail(50).reset_index(drop=True)
    fd_dates = pd.to_datetime(tdf["日期"]).values
    fd = pd.DataFrame({"日期": fd_dates, "ma_20": tdf["收盘价"].rolling(20).mean().values})
    fd = fd.set_index("日期")
    c6 = code.split(".")[0]
    bind_factor_cache(c6, fd)
    tok = bind_current_code(c6)
    try:
        # Expected behavior:
        # - Date in cache + value not NaN -> return single-element Series with correct date
        # - Date in cache + value is NaN -> fall through to fallback (return full Series)
        # - Date NOT in cache -> fall through to fallback (return full Series)
        exact_match = 0
        fallback = 0
        wrong_date = 0
        for _, r in tdf.iterrows():
            dt = pd.to_datetime(r["日期"])
            dtok = bind_current_date(dt)
            try:
                x = try_get_cached_factor("ma_20")
                if x is None:
                    wrong_date += 1  # Should not happen
                elif len(x) == 1 and x.index[0] == dt:
                    exact_match += 1  # Correct single-element match
                else:
                    fallback += 1  # Full Series fallback (expected for NaN values)
            finally: reset_current_date(dtok)
        total = exact_match + fallback + wrong_date
        # For ma_20 with window=20, first 19 values are NaN, so fallback is expected for those
        expected_fallback = 19  # First 19 rows have NaN ma_20
        if exact_match == (50 - expected_fallback) and fallback == expected_fallback:
            res["passed"] += 1; res["details"].append(f"  [PASS] Date match: {exact_match} exact + {fallback} fallback (expected for NaN)")
        else:
            res["failed"] += 1; res["details"].append(f"  [FAIL] exact={exact_match}, fallback={fallback}, expected: exact={50-expected_fallback}, fallback={expected_fallback}")
        # Test non-existent date: when date not in cache and length=None, fallback returns full series
        fake_dt = pd.Timestamp("2099-12-31")
        dtok = bind_current_date(fake_dt)
        try:
            x = try_get_cached_factor("ma_20")
            # With length=None, fallback returns full series (not None)
            # This is expected behavior - we don't reject queries just because date isn't in cache
            if x is not None and len(x) == 50: res["passed"] += 1
            else: res["failed"] += 1
        finally: reset_current_date(dtok)
    finally: reset_current_code(tok); clear_cache()
    res["details"].append(f"  Round2: {res['passed']}p/{res['failed']}f")
    return res

def test_round3(df, code):
    from subject.factors import ma, atr, rsi, volume_ratio, mom
    res = {"passed": 0, "failed": 0, "warnings": [], "details": []}
    tdf = df.tail(100).reset_index(drop=True)
    for n, v, e in [("ma_20", ma(tdf["收盘价"], 20), 19), ("atr_14", atr(tdf["最高价"], tdf["最低价"], tdf["收盘价"], 14), 13), ("rsi_14", rsi(tdf["收盘价"], 14), 14), ("mom_60", mom(tdf["收盘价"], 60), 60), ("vol_r20", volume_ratio(tdf["成交量（股）"], 20), 19)]:
        nc = v.isna().sum()
        if nc == e: res["passed"] += 1; res["details"].append(f"  [PASS] {n}: NaN={nc}")
        else: res["failed"] += 1; res["warnings"].append(f"  [FAIL] {n}: expected {e}, got {nc}"); res["details"].append(f"  [FAIL] {n}: NaN={nc}")
    res["details"].append(f"  Round3: {res['passed']}p/{res['failed']}f")
    return res

def test_round4(df, code):
    from subject.factors._cache import bind_current_code, bind_current_date, bind_factor_cache, reset_current_code, reset_current_date, clear_cache, try_get_cached_factor, _current_code, _current_date
    res = {"passed": 0, "failed": 0, "warnings": [], "details": []}
    clear_cache()
    tdf = df.tail(50).reset_index(drop=True)
    fd = pd.DataFrame({"日期": tdf["日期"].values, "ma_20": tdf["收盘价"].rolling(20).mean().values}).set_index("日期")
    c6 = code.split(".")[0]
    bind_factor_cache(c6, fd)
    tok = bind_current_code(c6)
    try:
        x = try_get_cached_factor("ma_20")
        if x is not None and len(x) > 0: res["passed"] += 1; res["details"].append("  [PASS] Cache")
        else: res["failed"] += 1; res["details"].append("  [FAIL] Cache")
    finally: reset_current_code(tok)
    tok = bind_current_code(c6); dtok = bind_current_date(tdf["日期"].iloc[-1])
    try:
        if _current_code.get() == c6 and _current_date.get() == tdf["日期"].iloc[-1]: res["passed"] += 1; res["details"].append("  [PASS] CtxVar")
        else: res["failed"] += 1; res["details"].append("  [FAIL] CtxVar")
    finally: reset_current_date(dtok); reset_current_code(tok)
    if _current_code.get() is None: res["passed"] += 1; res["details"].append("  [PASS] Reset")
    else: res["failed"] += 1; res["details"].append("  [FAIL] Reset")
    bind_factor_cache(c6, fd); tok = bind_current_code(c6)
    try:
        x = try_get_cached_factor("ma_20", length=len(fd)+100)
        if x is None: res["passed"] += 1; res["details"].append("  [PASS] Len")
        else: res["failed"] += 1; res["details"].append("  [FAIL] Len")
    finally: reset_current_code(tok)
    clear_cache()
    res["details"].append(f"  Round4: {res['passed']}p/{res['failed']}f")
    return res

def test_round5(df, code):
    from subject.factors._cache import bind_current_code, bind_current_date, bind_factor_cache, reset_current_code, reset_current_date, clear_cache
    from subject.backtest.data_loader.by_stock_factor import try_load_stock_factor
    from subject.factors import ma, atr
    res = {"passed": 0, "failed": 0, "warnings": [], "details": []}
    clear_cache()
    tdf = df.tail(100).reset_index(drop=True)
    c6 = code.split(".")[0]
    fd = try_load_stock_factor(c6)
    if fd is not None: fd = fd[(fd["日期"] >= tdf["日期"].min()) & (fd["日期"] <= tdf["日期"].max())].sort_values("日期").reset_index(drop=True)
    bind_factor_cache(c6, fd)
    tok = bind_current_code(c6)
    try:
        errs = []
        for i in range(20, min(50, len(tdf))):
            d = tdf.iloc[i-1]["日期"]
            dtok = bind_current_date(d)
            try:
                for n, v in {"ma_20": ma(tdf.iloc[:i]["收盘价"], 20), "atr_14": atr(tdf.iloc[:i]["最高价"], tdf.iloc[:i]["最低价"], tdf.iloc[:i]["收盘价"], 14)}.items():
                    if len(v) > 0 and pd.isna(v.iloc[-1]): errs.append(f"i={i}: {n} NaN")
            except Exception as e: errs.append(f"i={i}: {str(e)}")
            finally: reset_current_date(dtok)
        if len(errs) == 0: res["passed"] += 1; res["details"].append("  [PASS] Backtest OK")
        else: res["failed"] += 1; res["warnings"].extend(errs); res["details"].append(f"  [FAIL] {len(errs)} errors")
    finally: reset_current_code(tok); clear_cache()
    res["details"].append(f"  Round5: {res['passed']}p/{res['failed']}f")
    return res

def run_tests(code):
    logger.info(f"Factor verification: {code}")
    df = load_stock_test(code)
    logger.info(f"  Data: {len(df)} rows")
    fd = load_factor_test(code)
    logger.info(f"  Precomputed: {len(fd) if fd is not None else 'none'} rows")
    ar = {}
    for n, fn in [("Round1", test_round1), ("Round2", test_round2), ("Round3", test_round3), ("Round4", test_round4), ("Round5", test_round5)]:
        logger.info(f"\n=== {n} ===")
        ar[n.lower()] = fn(df, code)
        for d in ar[n.lower()]["details"]: logger.info(d)
        for w in ar[n.lower()]["warnings"]: logger.warning(w)
    tp = sum(r["passed"] for r in ar.values())
    tf = sum(r["failed"] for r in ar.values())
    logger.info(f"\nSummary: passed={tp}, failed={tf}")
    logger.info("[SUCCESS] All passed!" if tf == 0 else f"[FAIL] {tf} failed")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--code", default="000001")
    args = parser.parse_args()
    os.chdir(_PROJECT)
    run_tests(args.code)
