"""
pipeline.config — 流水线运行时配置

所有路径相对项目根 (my-quant3/), 跨电脑可移植。
环境变量覆盖优先级最高。
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

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
    """流水线配置 (用户确认)."""

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
    smoke_end: str = "2024-06-30"

    # 路径 (相对项目根, 可通过 env 覆盖为绝对路径)
    result_dir: Path = field(default=None)  # type: ignore

    def __post_init__(self):
        if self.result_dir is None:
            object.__setattr__(self, "result_dir", _PROJECT_ROOT / "result")
        elif not self.result_dir.is_absolute():
            object.__setattr__(self, "result_dir", _PROJECT_ROOT / self.result_dir)

    @classmethod
    def from_env(cls) -> "PipelineConfig":
        """从环境变量构造 (覆盖默认值)."""
        kwargs: dict[str, Any] = {}
        if v := os.getenv("PIPELINE_BATCH_SIZE"):
            kwargs["batch_size"] = int(v)
        if v := os.getenv("PIPELINE_PARAMS_ROUNDS"):
            kwargs["params_rounds"] = int(v)
        if v := os.getenv("PIPELINE_WEIGHT_ROUNDS"):
            kwargs["weight_rounds"] = int(v)
        if v := os.getenv("PIPELINE_TRANSLATE_MAX_ATTEMPTS"):
            kwargs["translate_max_attempts"] = int(v)
        if v := os.getenv("PIPELINE_RESULT_DIR"):
            kwargs["result_dir"] = Path(v)
        return cls(**kwargs)


__all__ = [
    "project_root",
    "auto_run_dir",
    "subjects_dir",
    "result_dir",
    "PipelineConfig",
]
