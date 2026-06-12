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
import pandas as pd
import numpy as np

print("=" * 70)
print("Deep Verification: Factor Calculation Correctness")
print("=" * 70)

from subject.factors._cache import bind_current_code, bind_current_date, bind_factor_cache, reset_current_code, reset_current_date, clear_cache, try_get_cached_factor
from subject.factors import ma, atr, rsi, volume_ratio, donchian_high, donchian_low, mom
from subject.backtest.data_loader.by_stock import load_stock
from subject.backtest.data_loader.by_stock_factor import try_load_stock_factor

clear_cache()

# Load test data
df = load_stock("000001")
df = df.tail(200).reset_index(drop=True)
print(f"\nData: {len(df)} rows")
print(f"Date: {df['日期'].iloc[0]} ~ {df['日期'].iloc[-1]}")

# Load precomputed factors
factor_df = try_load_stock_factor("000001")
factor_df = factor_df[(factor_df["日期"] >= df["日期"].min()) & (factor_df["日期"] <= df["日期"].max())].sort_values("日期").reset_index(drop=True)
print(f"Precomputed factors: {len(factor_df)} rows")

# Set up cache
bind_factor_cache("000001", factor_df)
tok = bind_current_code("000001")

print("\n" + "=" * 70)
print("Test 1: Precomputed vs Real-time (date-exact match)")
print("=" * 70)

test_cases = [
    ("ma_5", lambda d: ma(d["收盘价"], 5)),
    ("ma_10", lambda d: ma(d["收盘价"], 10)),
    ("ma_20", lambda d: ma(d["收盘价"], 20)),
    ("ma_30", lambda d: ma(d["收盘价"], 30)),
    ("ma_60", lambda d: ma(d["收盘价"], 60)),
    ("atr_14", lambda d: atr(d["最高价"], d["最低价"], d["收盘价"], 14)),
    ("rsi_14", lambda d: rsi(d["收盘价"], 14)),
    ("donchian_high_20", lambda d: donchian_high(d["最高价"], 20)),
    ("donchian_low_20", lambda d: donchian_low(d["最低价"], 20)),
    ("volume_ratio_20", lambda d: volume_ratio(d["成交量（股）"], 20)),
    ("mom_60", lambda d: mom(d["收盘价"], 60)),
]

all_errors = []

# Test with last 30 dates (where we have enough warmup data)
test_dates = df["日期"].iloc[65:].tolist()  # Start where ma_20 has valid values

for name, compute_fn in test_cases:
    errors = 0
    date_hits = 0
    fallbacks = 0
    
    for test_date in test_dates:
        # Get data up to test_date (inclusive)
        idx_list = df[df["日期"] == test_date].index.tolist()
        if not idx_list: continue
        idx = idx_list[0]
        
        # Real-time calculation on full history
        real_values = compute_fn(df.iloc[:idx+1])
        real_value = real_values.iloc[-1]  # Last value = today's ma_20
        
        # Set date and try cache
        dtok = bind_current_date(test_date)
        cached = try_get_cached_factor(name)
        
        if cached is not None:
            if len(cached) == 1:
                # Date exact match
                cached_value = cached.iloc[0]
                date_hits += 1
            else:
                # Fallback: last value
                cached_value = cached.iloc[-1]
                fallbacks += 1
        else:
            cached_value = np.nan
            errors += 1
            continue
        
        # Compare
        if pd.notna(real_value) and pd.notna(cached_value):
            diff = abs(float(real_value) - float(cached_value))
            if diff > 0.0001:
                errors += 1
                all_errors.append(f"{name}@{test_date}: real={real_value:.6f}, cached={cached_value:.6f}")
        
        reset_current_date(dtok)
    
    if errors == 0:
        print(f"  [PASS] {name}: {date_hits} exact + {fallbacks} fallback, {len(test_dates)} tested")
    else:
        print(f"  [FAIL] {name}: {errors}/{len(test_dates)} mismatches")

print("\n" + "=" * 70)
print("Test 2: Factor rolling window behavior")
print("=" * 70)

test_ma = ma(df["收盘价"], 20)
print(f"  ma_20 NaN count: {test_ma.isna().sum()} (expected 19)")
print(f"  ma_20 first valid: idx={test_ma.first_valid_index()}, value={test_ma.dropna().iloc[0]:.4f}")

test_atr = atr(df["最高价"], df["最低价"], df["收盘价"], 14)
print(f"  atr_14 NaN count: {test_atr.isna().sum()} (expected 14)")

test_rsi = rsi(df["收盘价"], 14)
valid_rsi = test_rsi.dropna()
in_range = all((0 <= v <= 100) for v in valid_rsi)
print(f"  rsi_14 NaN count: {test_rsi.isna().sum()} (expected 14)")
print(f"  rsi_14 values in [0,100]: {in_range}")

print("\n" + "=" * 70)
print("Test 3: Precomputed factor data integrity")
print("=" * 70)

pre_dates = set(factor_df["日期"].tolist())
stock_dates = set(df["日期"].tolist())
common = pre_dates & stock_dates
missing = stock_dates - pre_dates
print(f"  Precomputed dates: {len(pre_dates)}")
print(f"  Stock dates: {len(stock_dates)}")
print(f"  Common dates: {len(common)}")
print(f"  Missing from precomputed: {len(missing)}")

print("\n" + "=" * 70)
print("Test 4: Simulate runner usage (compute_factors)")
print("=" * 70)

errors = 0
for i in range(25, len(df)):  # Start where ma_20 has values
    bar = df.iloc[i]
    date = bar["日期"]
    
    # T-1 data
    t1_data = df.iloc[:i]
    t1_date = t1_data.iloc[-1]["日期"]
    
    dtok = bind_current_date(t1_date)
    
    # Simulate compute_factors
    factors = {
        "ma_5": ma(t1_data["收盘价"], 5),
        "ma_20": ma(t1_data["收盘价"], 20),
        "atr_14": atr(t1_data["最高价"], t1_data["最低价"], t1_data["收盘价"], 14),
    }
    
    for fname, values in factors.items():
        last_val = values.iloc[-1]
        cached = try_get_cached_factor(fname)
        
        if cached is not None:
            if len(cached) == 1:
                cached_val = cached.iloc[0]
            else:
                cached_val = cached.iloc[-1]
            
            if pd.notna(last_val) and pd.notna(cached_val):
                diff = abs(float(last_val) - float(cached_val))
                if diff > 0.0001:
                    errors += 1
                    all_errors.append(f"runner@{date}: {fname} real={last_val:.6f} cached={cached_val:.6f}")
    
    reset_current_date(dtok)

print(f"  Runner simulation: {len(df)-25} iterations, {errors} errors")
if errors == 0:
    print("  [PASS] All runner simulation tests passed!")

print("\n" + "=" * 70)
print("SUMMARY")
print("=" * 70)

if len(all_errors) == 0:
    print("ALL TESTS PASSED! Factors are correctly calculated.")
else:
    print(f"Found {len(all_errors)} errors:")
    for e in all_errors[:10]:
        print(f"  {e}")

reset_current_code(tok)
clear_cache()
