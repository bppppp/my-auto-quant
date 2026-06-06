# my-quant3 autoRun 流水线 — 新电脑部署

## 1. 准备环境

- Python 3.10+
- Windows 10/11 / Linux / macOS
- 8GB+ 内存, 20GB+ 磁盘 (含数据)

## 2. 拉代码 + 装依赖

```bash
git clone <repo-url> /path/to/my-quant3
cd /path/to/my-quant3
pip install -r autoRun/requirements.txt
```

## 3. 配 .env

```bash
cp .env.example .env
# 编辑 .env, 至少填 LLM_API_KEY / LLM_BASE_URL / LLM_MODEL
```

## 4. 准备金玥数据

`data/` 目录需含 `data-by-stock/` 和 `data-by-day/` 两个子目录。

详见 `data/README.md`。

如果数据是压缩包：

```bash
tar -xzf data.tar.gz
```

如果是单独下载：见 `data/README.md §1` 的目录结构，把数据放到对应位置。

## 5. 验证

```bash
python autoRun/pipeline.py check-env
```

期望输出：

```
✅ .env 存在, LLM_API_KEY 已配置
✅ openai 已安装
✅ watchdog 已安装
✅ yaml 已安装
✅ pandas 已安装
✅ numpy 已安装
✅ data/ 存在: 5841 只股票, 2267 个横截面文件
✅ strategies.agents.base_agent 可导入
✅ subject.backtest.runner 可导入
📝 state.json: ... (不存在 (首次运行))

━━━ ✅ 环境就绪, 可以跑流水线 ━━━
```

## 6. 试跑（1 个策略 + 2 轮 params + 2 轮 weight）

```bash
python autoRun/pipeline.py --batch 1 --params-rounds 2 --weight-rounds 2
```

跑完后到 `result/<strategy_name>/` 看产物。

## 7. 完整跑（5 个策略 + 20 轮 + 20 轮）

```bash
python autoRun/pipeline.py --batch 5 --params-rounds 20 --weight-rounds 20
```

约 4-8 小时（取决于 LLM 响应速度）。

## 8. 断点续跑

随时 `Ctrl+C` 退出，再次运行：

```bash
python autoRun/pipeline.py
```

会自动从 `autoRun/pipeline_state.json` 恢复，跳过已完成的策略和阶段。

## 9. 干跑（只看计划）

```bash
python autoRun/pipeline.py --dry-run
```

## 10. 单策略重跑

```bash
# 从头跑
python autoRun/pipeline.py --strategy ma_cross_atr_volume

# 从某阶段开始 (例如翻译)
python autoRun/pipeline.py --strategy ma_cross_atr_volume --from-stage B
```

## 11. 调整参数

通过环境变量覆盖默认值（也支持 CLI 参数）：

```bash
# 跑 3 个策略, params 10 轮, weight 5 轮
python autoRun/pipeline.py --batch 3 --params-rounds 10 --weight-rounds 5
```

或临时改环境变量：

```bash
PIPELINE_BATCH_SIZE=3 PIPELINE_PARAMS_ROUNDS=10 python autoRun/pipeline.py
```

## 12. 关键目录与文件

```
D:\project\quant\my-quant3\
├── autoRun/                     # 流水线代码 (本目录)
│   ├── pipeline.py              # 主入口
│   ├── pipeline/                # 子包
│   │   ├── config.py            # 配置
│   │   ├── translator.py        # spec → code 翻译
│   │   ├── test_runner.py       # 5 步测试
│   │   ├── parser.py            # 报告解析
│   │   ├── scorer.py            # 评分
│   │   ├── state.py             # 进度持久化
│   │   ├── exporter.py          # Stage H 输出
│   │   └── prompts/translate.md
│   ├── requirements.txt
│   ├── SETUP.md                 # 本文档
│   ├── pipeline_state.json      # 进度 (gitignore)
│   └── logs/                    # 日志
├── subjects/                    # 策略实例 (autoRun 生成)
├── strategies/                  # generate / optimize / factor_weights CLI
├── data/                        # 金玥数据
├── config.py                    # LLM 配置加载
├── .env                         # 真实 key (gitignore)
├── .env.example                 # 配置模板
└── result/                      # ★ 最终结果输出
    ├── <strategy_name>/
    │   ├── <strategy_name>_final.md
    │   ├── report_final.md
    │   └── report_weight_final.md
    └── ...
```

## 13. 故障排查

| 症状 | 排查 |
|---|---|
| `LLM_API_KEY 未配置` | `.env` 是否存在 + 是否填了 key |
| `ModuleNotFoundError: openai` | `pip install -r autoRun/requirements.txt` |
| `data not found` (回测) | `data/data-by-stock/` 是否有 csv 文件 |
| `翻译连续失败` | 检查 `.env` 的 BASE_URL / MODEL，跑 `python autoRun/pipeline.py check-env` |
| `result 不存在` | 第一次跑流水线后会自动创建 |

## 14. 进阶：开发模式

如要修改 pipeline 行为：

1. 编辑 `autoRun/pipeline/*.py`
2. 改完直接跑，无需重新安装
3. 状态自动保留（`autoRun/pipeline_state.json`）
4. 如要从头来：加 `--reset` 标志

## 15. 完整流程（每个策略）

```
A: generate
   ↓ subjects/<name>/<name>_original.md + <name>_v1.md
B: translate
   ↓ 1 次 LLM + 最多 9 次 Claude 直修
   ↓ subjects/<name>/generated/strategy.py (5 步测试全过)
C: params 调优 20 轮
   ↓ strategiesParam/v1..v20 + reportParams/report_v1..v20
D: 选最优 params (argmax annual_return) + 复制到 strategiesWeight/v1
E: weight 调优 20 轮
   ↓ strategiesWeight/v1..v20 (v1=best params 副本) + reportWeight/
F: 选最优 weight (argmax annual_return)
H: 导出到 result/<name>/
   ├─ <name>_final.md        ← strategiesWeight/<name>_weight_<best_v>.md
   ├─ report_final.md         ← reportParams/report_<best_params_v>.md
   └─ report_weight_final.md  ← reportWeight/report_signals_<best_weight_v>.md
G: 回到 A (下一策略)
```
