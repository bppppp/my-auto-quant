"""
my-quant3 autoRun 流水线主入口

完整流程: A 生成 → B 翻译 → C params 20 轮 → D 选最优 →
          E weight 20 轮 → F 选最优 → H 导出到 result/ → G 下一策略

Usage:
  python pipeline.py check-env                          # 检查环境
  python pipeline.py --batch 5 --params-rounds 20 --weight-rounds 20
  python pipeline.py --strategy ma_cross_atr_volume     # 单策略
  python pipeline.py --from-stage B                    # 从某阶段开始
  python pipeline.py --reset                            # 清空 state.json
  python pipeline.py --dry-run                          # 只显示计划
"""
from __future__ import annotations

import argparse
import io
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# Windows: 强制 UTF-8 输出 (避免 emoji/中文乱码)
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# autoRun/pipeline.py → autoRun/ → my-quant3/
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# subjects/subject/ 是 Python package 'subject', 需要把 subjects/ 加到 sys.path
_SUBJECTS_PARENT = _PROJECT_ROOT / "subjects"
if str(_SUBJECTS_PARENT) not in sys.path:
    sys.path.insert(0, str(_SUBJECTS_PARENT))

from autoRun.pipeline.config import (  # noqa: E402
    PipelineConfig,
    auto_run_dir,
    project_root,
    result_dir,
    subjects_dir,
)
from autoRun.pipeline.exporter import export as export_result  # noqa: E402
from autoRun.pipeline.log_utils import banner, get_logger, section  # noqa: E402
from autoRun.pipeline.parser import list_all_reports, parse_report  # noqa: E402
from autoRun.pipeline.scorer import score  # noqa: E402
from autoRun.pipeline.state import (  # noqa: E402
    STATE_PATH,
    STAGE_EXPORTED,
    STAGE_FAILED,
    STAGE_GENERATED,
    STAGE_PARAMS_DONE,
    STAGE_PARAMS_LOOP,
    STAGE_PICKED_PARAMS,
    STAGE_PICKED_WEIGHT,
    STAGE_TRANSLATED,
    STAGE_WEIGHT_DONE,
    STAGE_WEIGHT_LOOP,
    State,
)
from autoRun.pipeline.translator import (  # noqa: E402
    TranslationFailed,
    translate,
)

log = get_logger()


# ========== 路径冲突解决 ==========

def resolve_name_conflict(name: str) -> str:
    """冲突时自动加 _1 / _2 / _3 数字后缀."""
    from autoRun.pipeline.config import subjects_dir as _sd
    existing = [p.name for p in _sd().iterdir() if p.is_dir()] if _sd().exists() else []
    if name not in existing:
        return name
    for n in range(1, 1000):
        candidate = f"{name}_{n}"
        if candidate not in existing:
            return candidate
    raise RuntimeError(f"无法为 {name!r} 找到唯一名")


def rename_strategy_dir(old_name: str, new_name: str) -> Path:
    """重命名 subjects/<old>/ → subjects/<new>/, 同步改 spec / v1 文件名 + name 字段."""
    old_dir = subjects_dir() / old_name
    new_dir = subjects_dir() / new_name
    if not old_dir.exists():
        raise FileNotFoundError(f"{old_dir} 不存在")
    old_dir.rename(new_dir)

    # 改 _original.md 内 name 字段
    for md in new_dir.glob("*_original.md"):
        content = md.read_text(encoding="utf-8")
        content = re.sub(
            rf"^name:\s*{re.escape(old_name)}\s*$",
            f"name: {new_name}",
            content,
            count=1,
            flags=re.MULTILINE,
        )
        new_md = new_dir / md.name.replace(old_name, new_name)
        md.rename(new_md)
        new_md.write_text(content, encoding="utf-8")

    # 改 v1.md 文件名
    for v1 in new_dir.glob(f"{old_name}_v1.md"):
        v1.rename(new_dir / v1.name.replace(old_name, new_name))

    return new_dir


# ========== Stage A: 生成新策略 ==========

def run_stage_a_generate(config: PipelineConfig) -> str:
    """Stage A: 调 strategies.py generate, 自动解决命名冲突."""
    cmd = [sys.executable, "strategies/strategies.py", "generate"]
    log.info(f"  $ {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=project_root(), capture_output=True, text=True, timeout=600)
    if result.returncode != 0:
        raise RuntimeError(f"generate exit {result.returncode}\nSTDOUT: {result.stdout[-500:]}\nSTDERR: {result.stderr[-500:]}")

    # 解析 LLM 输出
    m = re.search(r"\[generate\] 成功: subjects/([^/]+)/", result.stdout)
    if not m:
        raise RuntimeError(f"无法从 generate 输出解析策略名: {result.stdout[-500:]}")
    candidate = m.group(1)

    unique = resolve_name_conflict(candidate)
    if unique != candidate:
        log.info(f"  → 候选名 {candidate!r} 已存在, 重命名为 {unique!r}")
        rename_strategy_dir(candidate, unique)
    else:
        log.info(f"  → 策略名: {unique}")
    return unique


# ========== Stage B: 翻译 ==========

def run_stage_b_translate(name: str, config: PipelineConfig) -> Path:
    """Stage B: 翻译 spec → strategy.py."""
    spec_path = subjects_dir() / name / f"{name}_original.md"
    result = translate(
        spec_path=spec_path,
        max_attempts=config.translate_max_attempts,
        smoke_universe=list(config.smoke_universe),
        smoke_start=config.smoke_start,
        smoke_end=config.smoke_end,
    )
    return result.code_path


# ========== Stage C: params 调优 20 轮 ==========

def run_stage_c_params_loop(name: str, config: PipelineConfig, state: State) -> None:
    """Stage C: params 调优 N 轮."""
    log.info(f"  → params 调优 {config.params_rounds} 轮")
    for round_n in range(1, config.params_rounds + 1):
        log.info(f"  [params {round_n}/{config.params_rounds}]")
        try:
            run_backtest(name, mode="params")
            metrics = parse_latest(name, mode="params")
            if metrics:
                state.record_params(name, round_n, metrics)
                log.info(f"    annual_return={metrics.get('annual_return', 'N/A'):.4f}")
            else:
                state.record_params_failure(name, round_n, "no metrics")
        except Exception as e:
            log.warning(f"  [params {round_n}] 失败, 跳过本轮: {type(e).__name__}: {e}")
            state.record_params_failure(name, round_n, str(e))

        if round_n < config.params_rounds:
            try:
                run_cli("optimize", [name, "once"])
            except Exception as e:
                log.warning(f"  [params {round_n}] optimize 失败: {e}")
    state.set_stage(name, STAGE_PARAMS_DONE)
    state.save()


# ========== Stage D: 选最优 params + 复制到 strategiesWeight/v1 ==========

def run_stage_d_pick_best_params(name: str, config: PipelineConfig, state: State) -> None:
    """Stage D: argmax(annual_return) 选最优 params + 复制到 strategiesWeight/v1."""
    all_reports = list_all_reports(name, mode="params")
    if not all_reports:
        raise RuntimeError(f"未找到任何 params 报告 for {name!r}")

    scored: list[tuple[int, float, dict]] = []
    for v, path in all_reports:
        m = parse_report(path)
        ar = m.get("annual_return", float("-inf"))
        scored.append((v, ar, m))
    scored.sort(key=lambda x: x[1], reverse=True)

    best_v, best_annual, best_metrics = scored[0]
    best_v_str = f"v{best_v}"
    log.info(f"  → 最佳 params: {best_v_str} (annual_return={best_annual:.4f})")
    log.info(f"    Top 3:")
    for v, ar, _ in scored[:3]:
        marker = " ←" if v == best_v else ""
        log.info(f"      v{v}: annual_return={ar:.4f}{marker}")

    state.set_best_params(name, best_v_str, best_annual)

    # 关键: 复制 best_params → strategiesWeight/v1 (作为 weight 调优起点)
    src = subjects_dir() / name / "strategiesParam" / f"{name}_{best_v_str}.md"
    dst = subjects_dir() / name / "strategiesWeight" / f"{name}_weight_v1.md"
    if not src.exists():
        raise FileNotFoundError(f"最佳 params spec 不存在: {src}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    log.info(f"  → 已复制 {best_v_str} → strategiesWeight/weight_v1.md (weight 调优起点)")

    state.set_stage(name, STAGE_PICKED_PARAMS)
    state.save()


# ========== Stage E: weight 调优 20 轮 ==========

def run_stage_e_weight_loop(name: str, config: PipelineConfig, state: State) -> None:
    """Stage E: weight 调优 N 轮 (起点是 v1 = best params 副本)."""
    log.info(f"  → weight 调优 {config.weight_rounds} 轮 (v1 是 best params 副本)")
    for round_n in range(1, config.weight_rounds + 1):
        log.info(f"  [weight {round_n}/{config.weight_rounds}]")
        try:
            run_backtest(name, mode="weight")
            metrics = parse_latest(name, mode="weight")
            if metrics:
                state.record_weight(name, round_n, metrics)
                log.info(f"    annual_return={metrics.get('annual_return', 'N/A'):.4f}")
            else:
                state.record_weight_failure(name, round_n, "no metrics")
        except Exception as e:
            log.warning(f"  [weight {round_n}] 失败, 跳过本轮: {type(e).__name__}: {e}")
            state.record_weight_failure(name, round_n, str(e))

        if round_n < config.weight_rounds:
            try:
                run_cli("factor_weights", [name, "once"])
            except Exception as e:
                log.warning(f"  [weight {round_n}] factor_weights 失败: {e}")
    state.set_stage(name, STAGE_WEIGHT_DONE)
    state.save()


# ========== Stage F: 选最优 weight ==========

def run_stage_f_pick_best_weight(name: str, config: PipelineConfig, state: State) -> None:
    """Stage F: argmax(annual_return) 选最优 weight."""
    all_reports = list_all_reports(name, mode="weight")
    if not all_reports:
        raise RuntimeError(f"未找到任何 weight 报告 for {name!r}")

    scored: list[tuple[int, float, dict]] = []
    for v, path in all_reports:
        m = parse_report(path)
        ar = m.get("annual_return", float("-inf"))
        scored.append((v, ar, m))
    scored.sort(key=lambda x: x[1], reverse=True)

    best_v, best_annual, best_metrics = scored[0]
    best_v_str = f"v{best_v}"
    log.info(f"  → 最佳 weight: {best_v_str} (annual_return={best_annual:.4f})")
    log.info(f"    Top 3:")
    for v, ar, _ in scored[:3]:
        marker = " ←" if v == best_v else ""
        log.info(f"      v{v}: annual_return={ar:.4f}{marker}")

    state.set_best_weight(name, best_v_str, best_annual)
    state.set_stage(name, STAGE_PICKED_WEIGHT)
    state.save()


# ========== Stage H: 导出到 result/ ==========

def run_stage_h_export(name: str, config: PipelineConfig, state: State) -> None:
    """Stage H: 3 个文件 copy 到 result/<name>/."""
    best_params = state.get(name).best_params_version
    best_weight = state.get(name).best_weight_version
    if not best_params or not best_weight:
        raise RuntimeError(f"{name}: 缺少 best_params ({best_params}) 或 best_weight ({best_weight})")

    log.info(f"  → 导出 best_params={best_params} + best_weight={best_weight}")
    result = export_result(
        strategy_name=name,
        best_params_version=best_params,
        best_weight_version=best_weight,
        result_dir=config.result_dir,
    )
    log.info(f"  → 已写入 {result.target_dir}/")
    state.mark_exported(name)
    state.save()


# ========== Subprocess 辅助 ==========

def run_cli(subcommand: str, args: list[str], timeout: int = 600) -> None:
    """调 strategies.py 子命令 (generate/optimize/factor_weights/list)."""
    cmd = [sys.executable, "strategies/strategies.py", subcommand] + args
    log.info(f"    $ {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=project_root(), capture_output=True, text=True, timeout=timeout)
    if result.returncode != 0:
        raise RuntimeError(
            f"{subcommand} exit {result.returncode}\n"
            f"STDOUT: {result.stdout[-500:]}\nSTDERR: {result.stderr[-500:]}"
        )


def run_backtest(name: str, mode: str, timeout: int = 900) -> None:
    """调 subject.cli run 跑 backtest."""
    cmd = [
        sys.executable, "-m", "subject.cli", "run",
        "--strategy", name,
        "--mode", mode,
    ]
    if mode == "weight":
        cmd += ["--weight-test", name]
    log.info(f"    $ {' '.join(cmd)} (cwd=subjects/)")
    result = subprocess.run(
        cmd, cwd=subjects_dir(), capture_output=True, text=True, timeout=timeout
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"backtest {mode} exit {result.returncode}\n"
            f"STDOUT: {result.stdout[-500:]}\nSTDERR: {result.stderr[-500:]}"
        )


def parse_latest(name: str, mode: str) -> dict:
    """从最新 report 解析指标."""
    from autoRun.pipeline.parser import parse_latest_report
    return parse_latest_report(name, mode)


# ========== 主循环 ==========

STAGE_ORDER = ["A", "B", "C", "D", "E", "F", "H"]


def main_loop(args, config: PipelineConfig) -> int:
    state = State.load() if not args.reset else State()
    if not state.started_at:
        state.started_at = ""

    consecutive_translate_failures = 0
    batch_count = 0

    while batch_count < config.batch_size:
        # 决定本轮策略
        if args.strategy:
            strategy_name = args.strategy
            start_stage = args.from_stage or "A"
        elif state.has_pending():
            strategy_name = state.current_strategy or next_pending(state)
            start_stage = current_stage_letter(state.get(strategy_name).stage)
        else:
            # Stage A: 生成新策略
            log.info("━━━ Stage A: generate ━━━")
            try:
                strategy_name = run_stage_a_generate(config)
            except Exception as e:
                log.error(f"Stage A 失败: {e}")
                consecutive_translate_failures += 1
                if consecutive_translate_failures >= config.consecutive_failures_threshold:
                    return maybe_exit_on_failures(args, consecutive_translate_failures)
                continue
            state.get(strategy_name)  # 确保记录存在
            state.set_stage(strategy_name, STAGE_GENERATED)
            state.save()
            start_stage = "B"

        # 跑该策略的所有阶段
        try:
            for stage in STAGE_ORDER:
                if stage_letter_to_index(stage) < stage_letter_to_index(start_stage):
                    continue
                log.info(f"━━━ Stage {stage}: {strategy_name} ━━━")
                run_one_stage(stage, strategy_name, config, state)
                if stage == "B":
                    consecutive_translate_failures = 0
                state.save()

            batch_count += 1
            state.current_strategy = ""
            state.save()

        except TranslationFailed as e:
            log.error(f"Stage B (translate) 失败: {e}")
            consecutive_translate_failures += 1
            state.mark_failed(strategy_name, reason=str(e))
            if consecutive_translate_failures >= config.consecutive_failures_threshold:
                return maybe_exit_on_failures(args, consecutive_translate_failures)
        except Exception as e:
            log.exception(f"Stage 失败: {e}")
            state.mark_failed(strategy_name, reason=f"{type(e).__name__}: {e}")
            if not args.auto:
                return 1

    log.info(f"━━━ 批次完成: {batch_count} 个策略 ━━━")
    return 0


def run_one_stage(stage: str, name: str, config: PipelineConfig, state: State) -> None:
    """分发到具体 stage."""
    if stage == "A":
        # 已在 main_loop 处理
        return
    elif stage == "B":
        run_stage_b_translate(name, config)
        state.set_stage(name, STAGE_TRANSLATED)
    elif stage == "C":
        run_stage_c_params_loop(name, config, state)
    elif stage == "D":
        run_stage_d_pick_best_params(name, config, state)
    elif stage == "E":
        run_stage_e_weight_loop(name, config, state)
    elif stage == "F":
        run_stage_f_pick_best_weight(name, config, state)
    elif stage == "H":
        run_stage_h_export(name, config, state)
    else:
        raise ValueError(f"未知 stage: {stage}")


def next_pending(state: State) -> str:
    for n, r in state.strategies.items():
        if r.stage not in (STAGE_EXPORTED, STAGE_FAILED):
            return n
    return ""


def current_stage_letter(stage: str) -> str:
    mapping = {
        "init": "A",
        "generated": "B",
        "translated": "C",
        "params_loop": "C",
        "params_done": "D",
        "picked_params": "E",
        "weight_loop": "E",
        "weight_done": "F",
        "picked_weight": "H",
        "exported": "Z",
        "failed": "Z",
    }
    return mapping.get(stage, "A")


def stage_letter_to_index(letter: str) -> int:
    return STAGE_ORDER.index(letter) if letter in STAGE_ORDER else 0


def maybe_exit_on_failures(args, n: int) -> int:
    log.warning(f"\n⚠️ 连续 {n} 个策略翻译失败")
    log.info("   请检查:")
    log.info("   1. .env 中的 LLM_API_KEY / LLM_BASE_URL / LLM_MODEL")
    log.info("   2. 最近 1-2 个 _original.md 是否合理")
    log.info("   3. 重跑: python pipeline.py --strategy <name> --from-stage B")
    if args.auto:
        return 1
    return 2


# ========== check-env 子命令 ==========

def cmd_check_env(_args) -> int:
    """检查环境是否就绪."""
    banner("my-quant3 环境检查", char="━")
    warnings = []

    # 1. .env
    env_path = project_root() / ".env"
    if not env_path.exists():
        warnings.append(f"❌ .env 不存在 ({env_path})")
        warnings.append("   → 复制 .env.example 为 .env 并填入 LLM_API_KEY")
    else:
        try:
            from config import LLM_API_KEY
            if not LLM_API_KEY:
                warnings.append("❌ .env 存在但 LLM_API_KEY 为空")
            else:
                print(f"✅ .env 存在, LLM_API_KEY 已配置")
        except Exception as e:
            warnings.append(f"❌ 加载 .env 失败: {e}")

    # 2. Python 依赖
    for pkg in ["openai", "watchdog", "yaml", "pandas", "numpy"]:
        try:
            __import__(pkg)
            print(f"✅ {pkg} 已安装")
        except ImportError:
            warnings.append(f"❌ {pkg} 未安装 — 运行: pip install -r autoRun/requirements.txt")

    # 3. 数据目录
    data_dir = project_root() / "data"
    if not data_dir.exists():
        warnings.append(f"❌ data/ 不存在 ({data_dir})")
        warnings.append("   → 回测需要金玥数据, 见 data/README.md §1")
    else:
        n_stock = len(list((data_dir / "data-by-stock").glob("*.csv"))) if (data_dir / "data-by-stock").exists() else 0
        n_day = sum(1 for _ in (data_dir / "data-by-day").glob("*/*_金玥数据.csv")) if (data_dir / "data-by-day").exists() else 0
        print(f"✅ data/ 存在: {n_stock} 只股票, {n_day} 个横截面文件")

    # 4. 关键模块
    for mod in ["strategies.agents.base_agent", "subject.backtest.runner"]:
        try:
            __import__(mod)
            print(f"✅ {mod} 可导入")
        except ImportError as e:
            warnings.append(f"❌ {mod} 导入失败: {e}")

    # 5. state.json
    print(f"📝 state.json: {STATE_PATH} ({'存在' if STATE_PATH.exists() else '不存在 (首次运行)'})")

    print()
    if warnings:
        banner("发现问题", char="━")
        for w in warnings:
            print(w)
        return 1
    else:
        banner("✅ 环境就绪, 可以跑流水线", char="=")
        return 0


# ========== argparse ==========

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="pipeline",
        description="my-quant3 autoRun 自动化流水线",
    )
    sub = parser.add_subparsers(dest="cmd")

    # 默认 (无子命令) 跑流水线
    parser.add_argument("--batch", type=int, default=None, help="一次跑几个策略 (覆盖 config)")
    parser.add_argument("--strategy", default=None, help="只跑指定策略")
    parser.add_argument("--from-stage", default=None, choices=["A", "B", "C", "D", "E", "F", "H"], help="从某阶段开始")
    parser.add_argument("--params-rounds", type=int, default=None, help="params 调优轮数 (覆盖 config)")
    parser.add_argument("--weight-rounds", type=int, default=None, help="weight 调优轮数 (覆盖 config)")
    parser.add_argument("--translate-max", type=int, default=None, help="翻译重试上限 (覆盖 config)")
    parser.add_argument("--reset", action="store_true", help="清空 state.json")
    parser.add_argument("--dry-run", action="store_true", help="只显示计划不执行")
    parser.add_argument("--auto", action="store_true", help="无人值守模式, 连续失败不暂停")
    parser.add_argument("--result-dir", default=None, help="覆盖 result 输出目录")

    # check-env 子命令
    sub.add_parser("check-env", help="检查环境是否就绪")

    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    if args.cmd == "check-env":
        return cmd_check_env(args)

    # 构造 config
    overrides = {}
    if args.batch:
        overrides["batch_size"] = args.batch
    if args.params_rounds:
        overrides["params_rounds"] = args.params_rounds
    if args.weight_rounds:
        overrides["weight_rounds"] = args.weight_rounds
    if args.translate_max:
        overrides["translate_max_attempts"] = args.translate_max
    if args.result_dir:
        overrides["result_dir"] = Path(args.result_dir)
    config = PipelineConfig(**overrides) if overrides else PipelineConfig.from_env()

    if args.dry_run:
        banner("my-quant3 pipeline 计划 (dry-run)", char="━")
        print(f"  batch_size: {config.batch_size}")
        print(f"  params_rounds: {config.params_rounds}")
        print(f"  weight_rounds: {config.weight_rounds}")
        print(f"  translate_max_attempts: {config.translate_max_attempts}")
        print(f"  result_dir: {config.result_dir}")
        print(f"  smoke_universe: {config.smoke_universe}")
        return 0

    banner("my-quant3 pipeline 启动", char="=")
    log.info(f"  配置文件: {config}")
    return main_loop(args, config)


if __name__ == "__main__":
    sys.exit(main())
