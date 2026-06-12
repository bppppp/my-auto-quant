"""
pipeline.state — 进度持久化 (state.json)

支持断点续跑 + 原子写入 (.tmp + rename).
"""
from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from .config import auto_run_dir
from .log_utils import get_logger

log = get_logger()

STATE_PATH = auto_run_dir() / "pipeline_state.json"


# Stage 枚举 (status 字段)
STAGE_INIT = "init"
STAGE_GENERATED = "generated"             # Stage A 完成
STAGE_TRANSLATED = "translated"           # Stage B 完成
STAGE_TOP300 = "top300"                   # Stage T 完成 (top300 测试集筛选)
STAGE_PARAMS_LOOP = "params_loop"         # Stage C 进行中
STAGE_PARAMS_DONE = "params_done"         # Stage C 完成
STAGE_PICKED_PARAMS = "picked_params"     # Stage D 完成
STAGE_WEIGHT_LOOP = "weight_loop"         # Stage E 进行中
STAGE_WEIGHT_DONE = "weight_done"         # Stage E 完成
STAGE_PICKED_WEIGHT = "picked_weight"     # Stage F 完成
STAGE_EXPORTED = "exported"               # Stage H 完成
STAGE_FAILED = "failed"                   # 失败


@dataclass
class StrategyRecord:
    """单个策略的进度."""
    name: str
    stage: str = STAGE_INIT
    spec_path: str = ""                    # subjects/<name>/<name>_original.md
    code_path: str = ""                    # subjects/<name>/generated/strategy.py
    translation_attempts: int = 0
    params_history: list[dict] = field(default_factory=list)
    best_params_version: str = ""
    best_params_score: float = float("-inf")
    weight_history: list[dict] = field(default_factory=list)
    best_weight_version: str = ""
    best_weight_score: float = float("-inf")
    failure_reason: str = ""
    completed_at: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "StrategyRecord":
        # 兼容旧字段缺失
        return cls(
            name=d.get("name", ""),
            stage=d.get("stage", STAGE_INIT),
            spec_path=d.get("spec_path", ""),
            code_path=d.get("code_path", ""),
            translation_attempts=d.get("translation_attempts", 0),
            params_history=d.get("params_history", []),
            best_params_version=d.get("best_params_version", ""),
            best_params_score=d.get("best_params_score", float("-inf")),
            weight_history=d.get("weight_history", []),
            best_weight_version=d.get("best_weight_version", ""),
            best_weight_score=d.get("best_weight_score", float("-inf")),
            failure_reason=d.get("failure_reason", ""),
            completed_at=d.get("completed_at", ""),
        )


@dataclass
class State:
    """全局进度."""
    version: str = "1.0"
    started_at: str = ""
    last_update: str = ""
    current_strategy: str = ""             # 正在跑的策略名
    strategies: dict[str, StrategyRecord] = field(default_factory=dict)

    def has_pending(self) -> bool:
        """是否有未完成的策略."""
        return any(
            r.stage not in (STAGE_EXPORTED, STAGE_FAILED)
            for r in self.strategies.values()
        )

    def get(self, name: str) -> StrategyRecord:
        """获取或创建策略记录."""
        if name not in self.strategies:
            self.strategies[name] = StrategyRecord(name=name)
        return self.strategies[name]

    def set_stage(self, name: str, stage: str) -> None:
        r = self.get(name)
        r.stage = stage
        self.current_strategy = name
        self.last_update = datetime.now().isoformat(timespec="seconds")

    def mark_failed(self, name: str, reason: str = "") -> None:
        r = self.get(name)
        r.stage = STAGE_FAILED
        r.failure_reason = reason
        r.completed_at = datetime.now().isoformat(timespec="seconds")

    def mark_exported(self, name: str) -> None:
        r = self.get(name)
        r.stage = STAGE_EXPORTED
        r.completed_at = datetime.now().isoformat(timespec="seconds")
        self.current_strategy = ""

    def record_params(self, name: str, version: int, metrics: dict) -> None:
        r = self.get(name)
        score = metrics.get("annual_return", float("-inf"))
        r.params_history.append({
            "version": f"v{version}",
            "annual_return": score,
            "metrics": metrics,
        })

    def record_params_failure(self, name: str, version: int, error: str) -> None:
        r = self.get(name)
        r.params_history.append({
            "version": f"v{version}",
            "error": error,
        })

    def record_weight(self, name: str, version: int, metrics: dict) -> None:
        r = self.get(name)
        score = metrics.get("annual_return", float("-inf"))
        r.weight_history.append({
            "version": f"v{version}",
            "annual_return": score,
            "metrics": metrics,
        })

    def record_weight_failure(self, name: str, version: int, error: str) -> None:
        r = self.get(name)
        r.weight_history.append({
            "version": f"v{version}",
            "error": error,
        })

    def set_best_params(self, name: str, version: str, score: float) -> None:
        r = self.get(name)
        r.best_params_version = version
        r.best_params_score = score

    def set_best_weight(self, name: str, version: str, score: float) -> None:
        r = self.get(name)
        r.best_weight_version = version
        r.best_weight_score = score

    # ---- 序列化 ----

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "started_at": self.started_at,
            "last_update": self.last_update,
            "current_strategy": self.current_strategy,
            "strategies": {n: r.to_dict() for n, r in self.strategies.items()},
        }

    @classmethod
    def from_dict(cls, d: dict) -> "State":
        return cls(
            version=d.get("version", "1.0"),
            started_at=d.get("started_at", ""),
            last_update=d.get("last_update", ""),
            current_strategy=d.get("current_strategy", ""),
            strategies={
                n: StrategyRecord.from_dict(r) for n, r in d.get("strategies", {}).items()
            },
        )

    def save(self, path: Path = STATE_PATH) -> None:
        """原子写入 (写到 .tmp 再 rename)."""
        path.parent.mkdir(parents=True, exist_ok=True)
        # 写到临时文件
        fd, tmp_path = tempfile.mkstemp(
            prefix=".state_", suffix=".json", dir=path.parent
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)
            # 原子 rename
            os.replace(tmp_path, path)
        except Exception:
            # 失败清理
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise

    @classmethod
    def load(cls, path: Path = STATE_PATH) -> "State":
        """加载 state.json. 不存在则返回空 State."""
        if not path.exists():
            s = cls()
            s.started_at = datetime.now().isoformat(timespec="seconds")
            return s
        try:
            d = json.loads(path.read_text(encoding="utf-8"))
            return cls.from_dict(d)
        except (json.JSONDecodeError, KeyError) as e:
            log.warning(f"state.json 损坏 ({e}), 用空 State 重新开始")
            s = cls()
            s.started_at = datetime.now().isoformat(timespec="seconds")
            return s

    def reset(self) -> None:
        """清空状态 (不删文件, 内存中重置)."""
        self.strategies.clear()
        self.current_strategy = ""
        self.started_at = datetime.now().isoformat(timespec="seconds")
        self.last_update = ""


__all__ = [
    "STATE_PATH",
    "STAGE_INIT",
    "STAGE_GENERATED",
    "STAGE_TRANSLATED",
    "STAGE_TOP300",
    "STAGE_PARAMS_LOOP",
    "STAGE_PARAMS_DONE",
    "STAGE_PICKED_PARAMS",
    "STAGE_WEIGHT_LOOP",
    "STAGE_WEIGHT_DONE",
    "STAGE_PICKED_WEIGHT",
    "STAGE_EXPORTED",
    "STAGE_FAILED",
    "StrategyRecord",
    "State",
]
