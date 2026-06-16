# baostock 数据集生成方案

> 用 baostock 前复权 (qfq) 数据生成 HS300 + CSI1000 + CYB_STAR_50 的 by-day 和 by-stock 数据集, 跟本地 weight 回测引擎的格式完全对齐。
>
> **用途**: 替换现有 `data/data-by-day/` 和 `data/data-by-stock/` 里的"金玥数据" (前复权行为异常, 跟 JQ 数据差异巨大), 改用 baostock 前复权 (跟 JQ 前复权 MAE 仅 0.6 元, 几乎一致)。

---

## 一、目标与规模

| 项 | 数值 |
|---|---|
| 股票池 | HS300 (300) + CSI1000 (1000) + CYB_STAR_50 (100) 去重 |
| **总股票数** | **1355 只** |
| 日期范围 | 2018-01-01 ~ 2026-05-31 (留 2 年 buffer 给 ma_60) |
| **生成目录** | `data/data-by-stock-bs/` 和 `data/data-by-day-bs/` (不复盖现有) |
| **磁盘需求** | by-stock 400 MB + by-day 1.2 GB = **1.6 GB** |

---

## 二、实测性能 (2026-06-16)

前 10 只股票, 单进程, baostock 前复权 (adjustflag=3):

| 指标 | 值 |
|---|---|
| 总耗时 | 57.7 秒 |
| 平均 | 5.77 秒/只 (首只握手 14.6s 拉高均值, 后续 4.4s) |
| 最快 | 3.78 秒 |
| 最慢 | 14.63 秒 (首只) |
| 成功率 | 10/10 = 100% |
| 数据范围 | 2020-01-02 ~ 2026-05-29 (1550 行, 6.4 年) |
| 限流迹象 | **无**, 10 只连续调用都正常返回 |

---

## 三、预估时间

| 方式 | 单只耗时 | 1355 只总耗时 | 风险 |
|---|---|---|---|
| **单进程** (推荐) | 5.77s | **~130 分钟 (2.2 小时)** | 无 |
| 4 进程 (ProcessPoolExecutor) | - | ~45-65 分钟 | 中 (可能限流) |
| 8 进程 | - | ~35-50 分钟 | 高 (易限流) |

**推荐: 单进程后台跑 2.2 小时**, 零风险。

---

## 四、字段映射 (baostock → 本地格式)

本地 by-day csv 是 38 列 (见 `subjects/subject/backtest/data_loader/preprocess.py`), baostock 能直接给 ~12 列, 其余后处理补齐或留空:

| 本地字段 | baostock 来源 | 备注 |
|---|---|---|
| 日期 | `date` | 直接 |
| 代码 | (本地映射) | 6 位 + 交易所后缀 |
| 名称 | `query_stock_basic` | 单独一次 |
| 所属行业 | `query_stock_industry` (申万一级) | 单独一次 |
| 开盘价/最高价/最低价/收盘价 | `open/high/low/close` | 直接 |
| 前收盘价 | 后处理: `close.shift(1)` | |
| 成交量(股) | `volume` | |
| 成交额(元) | `amount` | baostock 有, 不用算 |
| 换手率 | 后处理: `volume / 流通股本` | |
| 涨幅% | 后处理: `(close - preclose) / preclose * 100` | |
| 振幅% | 后处理: `(high - low) / preclose * 100` | |
| 是否ST | `query_stock_basic` | 少部分 |
| 量比 | ❌ 留空 | baostock 没有, 本地引擎不依赖 |
| 3/6/10/25 日涨幅% | 后处理: `close.pct_change(periods)` | rolling |
| 是否涨停 | 后处理: `涨幅% >= 9.5%` | |
| 总股本/流通股本 | `query_stock_basic` | |
| 总市值/流通市值 | 后处理: `close × 股本` | |
| PE/PB/PS | ❌ 留空 | baostock 没有 |
| 5/10/20/30/60/120/250 日线 | 后处理: `close.rolling(N).mean()` | |
| 上市时间/退市时间 | `query_stock_basic` | |
| 是否融资融券 | `query_stock_basic` | |

---

## 五、生成流程

### 步骤 1: 拉基础信息 (5 分钟)

```python
import baostock as bs
import pandas as pd
bs.login()

# 1355 只股票: sh.600000 / sz.000001
stock_list = pd.read_csv('data/stock_universe.csv')  # 自行生成: HS300+CSI1000+CYB_STAR_50
basic_info = {}
for code in stock_list['bs_code']:
    rs = bs.query_stock_basic(code=code)
    if rs.error_code == '0':
        while rs.next():
            row = rs.get_row_data()
            basic_info[code] = {
                'name': row[1],
                'ipoDate': row[2],
                'outDate': row[3],
                'type': row[4],
            }

pd.DataFrame(basic_info).T.to_csv('data/stock_basic_info.csv')
```

### 步骤 2: 拉行业分类 (2 分钟)

```python
industry = {}
for date_str in ['2023-01-09', '2024-01-09', '2025-01-09']:
    for code in stock_list['bs_code']:
        rs = bs.query_stock_industry(code=code)
        if rs.error_code == '0':
            while rs.next():
                row = rs.get_row_data()
                # row 内容: code, code_name, industry, industry_classification
                industry[(code, date_str)] = row[2]

pd.DataFrame(industry).T.to_csv('data/industry_snapshot.csv')
```

### 步骤 3: 拉 K 线 (核心, 单进程 ~130 分钟)

```python
import time
from pathlib import Path

OUT_DIR = Path('data/data-by-stock-bs')
OUT_DIR.mkdir(parents=True, exist_ok=True)

bs.login()
results = []
t_total = time.time()
for i, code in enumerate(stock_list['bs_code']):
    t0 = time.time()
    rs = bs.query_history_k_data_plus(
        code,
        'date,open,high,low,close,volume,amount',
        start_date='2018-01-01', end_date='2026-05-31',
        frequency='d', adjustflag='3'  # 前复权
    )
    rows = []
    while rs.error_code == '0' and rs.next():
        rows.append(rs.get_row_data())
    df = pd.DataFrame(rows, columns=['date','open','high','low','close','volume','amount'])
    # 输出 by-stock
    code6 = code.split('.')[1]
    df.to_csv(OUT_DIR / f'{code6}.csv', index=False)
    elapsed = time.time() - t0
    if (i+1) % 50 == 0:
        print(f'{i+1}/{len(stock_list)}, {elapsed:.1f}s, ETA {(len(stock_list)-i-1)*elapsed/60:.0f}min')
bs.logout()
```

### 步骤 4: 后处理生成 by-day (~5 分钟)

```python
import pandas as pd
from pathlib import Path

DAY_DIR = Path('data/data-by-day-bs')
DAY_DIR.mkdir(parents=True, exist_ok=True)

# 读所有 by-stock, 按日期 group 写到 by-day
all_dfs = []
for csv_file in Path('data/data-by-stock-bs').glob('*.csv'):
    df = pd.read_csv(csv_file)
    df['code'] = csv_file.stem
    all_dfs.append(df)

big = pd.concat(all_dfs, ignore_index=True)
big['date'] = pd.to_datetime(big['date'])

# 按日期 group 拆分
for date, group in big.groupby('date'):
    date_str = date.strftime('%Y-%m-%d')
    year_dir = DAY_DIR / str(date.year)
    year_dir.mkdir(parents=True, exist_ok=True)
    group.to_csv(year_dir / f'{date_str}.csv', index=False)
```

### 步骤 5: 后处理补字段 (~5 分钟)

读 by-stock, 加上前收盘价、涨幅%、均线等字段; 跟 `stock_basic_info.csv` join 加名称/上市时间。

### 步骤 6: 切换数据源

修改 `subjects/subject/backtest/data_loader/_paths.py`, 加一个开关:

```python
DATA_SOURCE = 'bs'  # 'gold' (金玥) 或 'bs' (baostock)

if DATA_SOURCE == 'bs':
    STOCK_DIR = DATA_ROOT / 'data-by-stock-bs'
    DAY_DIR = DATA_ROOT / 'data-by-day-bs'
else:
    STOCK_DIR = DATA_ROOT / 'data-by-stock'
    DAY_DIR = DATA_ROOT / 'data-by-day'
```

### 步骤 7: 验证 (~5 分钟)

- 跑 `python run_weight_test.py`
- 预期: 年化 35-38% (跟 JQ 38.59% 接近), 持仓天数 ~28-32 天

---

## 六、限流与失败处理

- baostock 单只失败: 重试 3 次, 仍失败跳过并记录
- 整批限流: 加 `time.sleep(1)` 在每只之间 (单进程够用)
- 超时: baostock 默认无超时, 长任务可能挂死, 建议加 `signal.alarm(30)` 保护

---

## 七、关键校验点

1. **数据完整性**: 每只股票应有 ~2000 行 (2018-2026 约 2000 交易日)
2. **价格连续性**: `close.shift(1) == preclose`, 不应有跳空 (除权日除外)
3. **跟 JQ 对齐**: 抽样 10 只股票, 对比 baostock 前复权 vs JQ 成交价, MAE 应 < 1 元
4. **行业映射**: 抽样几只股票, baostock 申万行业 vs JQ `get_industry()` 应一致

---

## 八、相关文件

| 文件 | 路径 |
|---|---|
| 数据集配置 | `data/config.py` (HS300, CSI1000, CYB_STAR_50) |
| 本地数据加载 | `subjects/subject/backtest/data_loader/` |
| 本地字段规范 | `subjects/subject/backtest/data_loader/preprocess.py` |
| 现有 by-stock | `data/data-by-stock/{code}_金玥数据.csv` |
| 现有 by-day | `data/data-by-day/{YYYY}/{date}_金玥数据.csv` |
| 全量对比报告 | `result/trend_momentum_strategy_1/diff_analysis.md` |
| 代码差异分析 | `result/trend_momentum_strategy_1/code_diff_analysis.md` |
| baostock 对比结果 | `result/trend_momentum_strategy_1/baostock_compare/` |

---

**生成时间**: 2026-06-16
**状态**: 方案设计完成, 实测过前 10 只 (单进程 5.77s/只, 无限流)
**下一步**: 用户批准后启动全量 1355 只单进程拉取 (~2.2 小时)