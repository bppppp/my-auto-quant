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
print("深度验证: 因子计算正确性检查")
print("=" * 70)

# 加载数据
from subject.factors._cache import bind_current_code, bind_current_date, bind_factor_cache, reset_current_code, reset_current_date, clear_cache, try_get_cached_factor
from subject.factors import ma, atr, rsi, volume_ratio, donchian_high, donchian_low, mom
from subject.backtest.data_loader.by_stock import load_stock
from subject.backtest.data_loader.by_stock_factor import try_load_stock_factor

clear_cache()

# 加载测试数据
df = load_stock("000001")
df = df.tail(200).reset_index(drop=True)
print(f"\n数据: {len(df)} 行")
print(f"日期: {df['日期'].iloc[0]} ~ {df['日期'].iloc[-1]}")

# 加载预计算因子
factor_df = try_load_stock_factor("000001")
print(f"预计算因子: {len(factor_df)} 行")

# 对齐日期
factor_df = factor_df[(factor_df["日期"] >= df["日期"].min()) & (factor_df["日期"] <= df["日期"].max())].sort_values("日期").reset_index(drop=True)
print(f"对齐后: {len(factor_df)} 行")

# 设置缓存
bind_factor_cache("000001", factor_df)
tok = bind_current_code("000001")

print("\n" + "=" * 70)
print("验证 1: 检查预计算因子 vs 实时计算 (日期精确匹配)")
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

# 取后50个交易日测试 (确保有足够的历史数据)
test_dates = df["日期"].tail(50).tolist()

for name, compute_fn in test_cases:
    errors = 0
    total = 0
    date_matches = 0
    fallbacks = 0
    
    for test_date in test_dates:
        # 获取T-1数据
        idx = df[df["日期"] == test_date].index
        if len(idx) == 0: continue
        idx = idx[0]
        if idx == 0: continue  # 需要至少1天历史
        
        t1_data = df.iloc[:idx+1]
        
        # 实时计算
        real_values = compute_fn(t1_data)
        real_value = real_values.iloc[-1]
        
        # 设置日期
        dtok = bind_current_date(t1_data.iloc[-1]["日期"])
        
        # 尝试从缓存获取
        cached = try_get_cached_factor(name)
        
        if cached is not None and len(cached) == 1:
            # 日期精确匹配
            cached_value = cached.iloc[0]
            date_matches += 1
        elif cached is not None:
            # 回退到iloc
            cached_value = cached.iloc[-1]
            fallbacks += 1
        else:
            cached_value = np.nan
            errors += 1
            continue
        
        total += 1
        
        # 比较
        if pd.notna(real_value) and pd.notna(cached_value):
            diff = abs(float(real_value) - float(cached_value))
            if diff > 0.0001:
                errors += 1
                all_errors.append(f"{name}@{test_date}: real={real_value:.6f}, cached={cached_value:.6f}")
        
        reset_current_date(dtok)
    
    if errors == 0:
        print(f"  [PASS] {name}: {date_matches} exact + {fallbacks} fallback, {total} tested")
    else:
        print(f"  [FAIL] {name}: {errors}/{total} mismatches")

print("\n" + "=" * 70)
print("验证 2: 检查因子函数的 rolling 窗口行为")
print("=" * 70)

# 测试 ma_20: 验证前19个值是NaN，第20个开始有值
test_ma = ma(df["收盘价"], 20)
nan_count = test_ma.isna().sum()
first_valid = test_ma.dropna().iloc[0] if nan_count < len(test_ma) else np.nan
first_valid_idx = test_ma.first_valid_index()
print(f"  ma_20: NaN={nan_count} (期望19), first_valid_idx={first_valid_idx}, first_valid={first_valid:.4f}")

# 测试 atr_14
test_atr = atr(df["最高价"], df["最低价"], df["收盘价"], 14)
nan_count = test_atr.isna().sum()
print(f"  atr_14: NaN={nan_count} (期望14)")

# 测试 rsi_14
test_rsi = rsi(df["收盘价"], 14)
nan_count = test_rsi.isna().sum()
valid_values = test_rsi.dropna()
if len(valid_values) > 0:
    in_range = all((v >= 0 and v <= 100) for v in valid_values)
    print(f"  rsi_14: NaN={nan_count} (期望14), values in [0,100]={in_range}")

print("\n" + "=" * 70)
print("验证 3: 检查预计算因子的数据完整性")
print("=" * 70)

# 检查预计算因子是否有缺失日期
pre_dates = set(factor_df["日期"].tolist())
stock_dates = set(df["日期"].tolist())
common_dates = pre_dates & stock_dates
missing_in_pre = stock_dates - pre_dates
missing_in_stock = pre_dates - stock_dates

print(f"  预计算因子日期数: {len(pre_dates)}")
print(f"  原始数据日期数: {len(stock_dates)}")
print(f"  共同日期数: {len(common_dates)}")
print(f"  预计算缺失的日期: {len(missing_in_pre)}")
print(f"  原始缺失的日期: {len(missing_in_stock)}")

if len(missing_in_pre) == 0:
    print(f"  [PASS] 预计算因子无缺失日期")
else:
    print(f"  [WARN] 预计算因子缺失 {len(missing_in_pre)} 个日期: {sorted(list(missing_in_pre))[:5]}...")

print("\n" + "=" * 70)
print("验证 4: 模拟 runner 的实际使用场景")
print("=" * 70)

# 模拟 _backtest_single_stock 的行为
errors = 0
trades_detected = 0

for i in range(20, len(df)):  # 从第20天开始（有ma20数据）
    bar = df.iloc[i]
    date = bar["日期"]
    
    # T-1数据 = df.iloc[:i]
    t1_data = df.iloc[:i]
    t1_date = t1_data.iloc[-1]["日期"]
    
    # 设置日期
    dtok = bind_current_date(t1_date)
    
    # 计算因子（模拟策略的compute_factors）
    factors = {
        "ma_5": ma(t1_data["收盘价"], 5),
        "ma_20": ma(t1_data["收盘价"], 20),
        "atr_14": atr(t1_data["最高价"], t1_data["最低价"], t1_data["收盘价"], 14),
    }
    
    # 获取因子的最后一个值
    for name, values in factors.items():
        last_val = values.iloc[-1]
        cached = try_get_cached_factor(name)
        
        if cached is not None:
            if len(cached) == 1:
                cached_val = cached.iloc[0]
            else:
                cached_val = cached.iloc[-1]
            
            if pd.notna(last_val) and pd.notna(cached_val):
                diff = abs(float(last_val) - float(cached_val))
                if diff > 0.0001:
                    errors += 1
                    all_errors.append(f"runner_sim@{date}: {name} real={last_val:.6f} cached={cached_val:.6f}")
    
    reset_current_date(dtok)

print(f"  Runner模拟: {len(df)-20} 次迭代, {errors} 个错误")

if errors == 0:
    print("  [PASS] 所有runner模拟测试通过!")
else:
    print(f"  [FAIL] 发现 {errors} 个错误")
    for e in all_errors[:5]:
        print(f"    {e}")

reset_current_code(tok)
clear_cache()

print("\n" + "=" * 70)
print("总结")
print("=" * 70)

if len(all_errors) == 0:
    print("✅ 所有验证通过! 因子计算是正确的。")
else:
    print(f"❌ 发现 {len(all_errors)} 个错误")
    for e in all_errors[:10]:
        print(f"  {e}")
