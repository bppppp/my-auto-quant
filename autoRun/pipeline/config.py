"""
pipeline.config — 流水线运行时配置

所有路径相对项目根 (my-quant3/), 跨电脑可移植。

覆盖顺序 (从高到低):
  1. CLI 标志 (--generate-timeout / --backtest-timeout / ...)
  2. PipelineConfig 代码内默认值 (本文件)
  注: 不从 .env 读 (避免与根 config.py 的 .env 加载逻辑冲突)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

# autoRun/pipeline/config.py → autoRun/pipeline/ → autoRun/ → my-quant3/
_PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent.parent


def project_root() -> Path:
    """my-quant3/ 项目根."""
    return _PROJECT_ROOT


def auto_run_dir() -> Path:
    """autoRun/ 目录."""
    return _PROJECT_ROOT / "autoRun"


def subjects_dir() -> Path:
    """subjects/ 目录 (含所有策略)."""
    return _PROJECT_ROOT / "subjects"


def result_dir() -> Path:
    """result/ 目录 (最终结果输出, 项目根下)."""
    return _PROJECT_ROOT / "result"


@dataclass(frozen=True)
class PipelineConfig:
    """流水线配置 (代码默认值, 可被 CLI 标志覆盖)."""

    batch_size: int = 5
    params_rounds: int = 20                   # 用户确认: 20 轮
    weight_rounds: int = 20                   # 用户确认: 20 轮
    translate_max_attempts: int = 10          # 用户确认: 10 次 (1 LLM + 9 Claude 直修)
    consecutive_failures_threshold: int = 3   # 连续失败 N 次后停
    scoring_metric: str = "annual_return"     # 唯一评分指标

    # Smoke test 5 只股票
    smoke_universe: tuple[str, ...] = (
        "000001.SZ", "000002.SZ", "600000.SH", "600519.SH", "000333.SZ",
    )
    smoke_start: str = "2024-06-01"
    smoke_end: str = "2024-12-31"

    # ===== 各阶段 subprocess timeout (秒) =====
    # Stage A (generate) 包含 quality_eval,可能需要 1 - 5 小时
    # None 表示不设超时 (依赖外部 Ctrl+C)
    generate_timeout: int | None = 18000      # 5 小时 (用户确认)
    # Stage C/E 调 optimize / factor_weights (单次 LLM 调优)
    cli_timeout: int | None = 1800            # 30 分钟
    # 单次回测 (params / weight)
    backtest_timeout: int | None = 3600       # 1 小时 (用户确认)
    # 翻译阶段 smoke backtest (5 只股票, 1 个月)
    smoke_timeout: int = 600                  # 10 分钟

    # Stage T (top300) 全量回测筛选 (全量股票 × 滚动 N 年 × rounds 轮)
    # 每轮耗时约 1-4 小时, None 表示不设超时 (依赖 Ctrl+C)
    top300_timeout: int | None = 14400        # 4 小时 (默认每轮上限)
    top300_rounds: int = 1                   # 调优轮数 (每轮 LLM 调参 + 全量回测)
    top300_limit: int | None = None          # 每轮最多测 N 只股票 (None=不限/全量, 调试建议设 50-100)
    # top300 滚动回看窗口: 以 data-by-day/ 末日为 end, start = end - lookback_years 年
    # 默认 2 年 (用户确认: 取代 runner 自带的 5y 默认, top300 用更近的数据更贴近当前市场)
    top300_lookback_years: int = 2

    # 路径 (相对项目根, 可被 CLI 覆盖)
    result_dir: Path = field(default=None)  # type: ignore

    def __post_init__(self):
        if self.result_dir is None:
            object.__setattr__(self, "result_dir", _PROJECT_ROOT / "result")
        elif not self.result_dir.is_absolute():
            object.__setattr__(self, "result_dir", _PROJECT_ROOT / self.result_dir)


__all__ = [
    "project_root",
    "auto_run_dir",
    "subjects_dir",
    "result_dir",
    "PipelineConfig",
]
