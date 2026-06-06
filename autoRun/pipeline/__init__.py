"""
my-quant3 autoRun 自动化流水线

包含:
- generate: 调 strategies.py generate 生成新策略
- translate: LLM 翻译 spec → strategy.py (含 Claude 直修)
- params_loop: 跑回测 + optimize once 循环
- pick_best: argmax(annual_return) 选最优
- export: 复制最优到 result/

完整文档见 autoRun/SETUP.md
"""
__version__ = "1.0.0"
