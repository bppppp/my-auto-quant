"""
my-quant3 策略生成系统 — CLI 入口
============================================================
=== 模式 1: 生成新策略 ===
============================================================
python strategies/strategies.py generate
# 行为:LLM 按业务目标(前 90% 锚点)生成新策略
# 产出:subjects/<name>/strategiesParam/<name>_v1.md + subjects/<name>/<name>_original.md

============================================================
=== 模式 2: Part A 参数调优 ===
============================================================
python strategies/strategies.py optimize <name>                     # 默认 = once(单次触发)
python strategies/strategies.py optimize <name> once                # 显式单次触发
python strategies/strategies.py optimize <name> watch               # 持续监听(Ctrl+C 退出)

# 重启时从原始版本引导(可选)
python strategies/strategies.py optimize <name> once --from-original

============================================================
=== 模式 3: Part B 因子权重调优 ===
============================================================
python strategies/strategies.py factor_weights <name>               # 默认 = once
python strategies/strategies.py factor_weights <name> once          # 显式单次
python strategies/strategies.py factor_weights <name> watch         # 持续监听

============================================================
=== 工具命令 ===
============================================================
python strategies/strategies.py list                           # 列出 subjects/ 下所有策略

============================================================
=== 实现模块结构 ===
============================================================
strategies/                ← 本目录
  strategies.py            ← CLI 入口(本文件 + argparser)
  config.py                ← LLMSettings + RuntimeSettings
  __init__.py
  agents/
    base_agent.py          ← 共享工具(路径/.md读写/报告/硬校验/JSON解析)
    generate.py            ← 模式 1(generate)
    optimize.py            ← 模式 2(optimize once/watch)
    factor_weights.py      ← 模式 3(factor_weights once/watch)
    quality_eval.py        ← 业务质量评估(仅模式 1)
    watcher.py             ← watchdog + debounce(watch 模式用)
    prompts/
      generate.md          ← 模式 1 system prompt
      optimize.md          ← 模式 2 system prompt
      factor_weights.md    ← 模式 3 system prompt
      quality_eval.md      ← 质量评估 system prompt

config.py                  ← 根 LLM 端点配置(base_url / model / api_key)

subjects/<name>/           ← 模式 1 生成的策略实例
  <name>_original.md       # 顶层(immutable 原始快照)
  strategiesParam/         # 模式 1 / 模式 2
    <name>_v1.md / <name>_v<N>.md
  strategiesWeight/        # 模式 3
    <name>_weight_v1.md / <name>_weight_v<N>.md
  reportParams/            # 模式 2 监听
    report_v*.md
  reportWeight/            # 模式 3 监听
    report_signals_v*.md
  backtest/                # 外部回测器(按 .md 契约生成代码)

完整 spec 见 strategies.md(项目根)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


# 让根目录与 strategies 同级包都可见
# strategies/strategies.py → 2 层:my-quant3/
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


# ====================================================================
# 子命令 handler
# ====================================================================
def cmd_generate(_args: argparse.Namespace) -> int:
    """模式 1:生成新策略"""
    from strategies.agents.generate import run_generate
    from strategies.config import RuntimeSettings

    rt = RuntimeSettings.from_env()
    try:
        path = run_generate(max_retries=rt.self_eval_max_retries)
    except Exception as e:
        print(f"[generate] 失败: {type(e).__name__}: {e}", file=sys.stderr)
        return 1
    print(f"[generate] 成功: {path}")
    return 0


def cmd_list(_args: argparse.Namespace) -> int:
    """工具:列出 subjects/ 下所有策略(显示 original + strategiesParam + strategiesWeight 三个区域)"""
    from strategies.agents.base_agent import (
        list_all_strategies,
        strategy_dir_for,
        original_md_path,
    )

    names = list_all_strategies()
    if not names:
        print("(无策略)")
        return 0
    for n in names:
        # 新结构:subjects/<name>/{strategiesParam,strategiesWeight}/
        sp = strategy_dir_for(n, track="main")
        sw = strategy_dir_for(n, track="signals")
        sp_files = sorted([f.name for f in sp.glob("*.md")]) if sp.exists() else []
        sw_files = sorted([f.name for f in sw.glob("*.md")]) if sw.exists() else []
        orig = original_md_path(n)
        orig_exists = orig.exists()
        print(
            f"- {n}  "
            f"(original={'Y' if orig_exists else 'N'}, "
            f"strategiesParam={len(sp_files)}:{', '.join(sp_files) or '-'}, "
            f"strategiesWeight={len(sw_files)}:{', '.join(sw_files) or '-'})"
        )
    return 0


def _add_optimize_subcommand(sub) -> None:
    """optimize 子命令组(once / watch)"""
    p = sub.add_parser("optimize", help="模式 2:Part A 参数调优")
    p.add_argument(
        "name",
        nargs="?",
        help="策略名(在 subject/<name>/strategy/ 下的 .md 前缀)",
    )
    p.add_argument(
        "subcmd",
        nargs="?",
        choices=["once", "watch"],
        help="子命令:once(单次触发,默认)/ watch(持续监听)",
    )
    p.add_argument(
        "--from-original",
        action="store_true",
        help="从 <name>_original.md 引导(默认从 main track 最新版引导)",
    )
    p.set_defaults(_handler=_handle_optimize)


def _handle_optimize(args: argparse.Namespace) -> int:
    """optimize once/watch 分派"""
    if not args.name:
        print("错误:optimize 需要策略名。运行 `python strategies.py optimize -h` 查看帮助", file=sys.stderr)
        return 2
    subcmd = args.subcmd or "once"  # 默认 once(E2)
    from strategies.agents.optimize import run_optimize_once, run_optimize_watch
    from strategies.config import RuntimeSettings

    rt = RuntimeSettings.from_env()

    if subcmd == "once":
        try:
            path = run_optimize_once(
                args.name,
                from_original=args.from_original,
                max_retries=rt.optimize_max_retries,
            )
        except FileNotFoundError as e:
            print(f"[optimize] {e}", file=sys.stderr)
            return 1
        except Exception as e:
            print(f"[optimize] 失败: {type(e).__name__}: {e}", file=sys.stderr)
            return 1
        if path is None:
            print("[optimize] 本轮失败(LLM/校验/解析全部重试耗尽),未写入", file=sys.stderr)
            return 1
        print(f"[optimize] 成功: {path}")
        return 0
    elif subcmd == "watch":
        try:
            run_optimize_watch(args.name, from_original=args.from_original)
        except KeyboardInterrupt:
            print("\n[optimize.watch] 退出")
        return 0
    return 2


def _add_factor_weights_subcommand(sub) -> None:
    """factor_weights 子命令组(once / watch)"""
    p = sub.add_parser(
        "factor_weights",
        help="模式 3:Part B 因子权重调优(仅改 signals[].weight)",
    )
    p.add_argument(
        "name",
        nargs="?",
        help="策略名",
    )
    p.add_argument(
        "subcmd",
        nargs="?",
        choices=["once", "watch"],
        help="子命令:once(单次触发,默认)/ watch(持续监听)",
    )
    p.add_argument(
        "--from-original",
        action="store_true",
        help="从 <name>_original.md 引导",
    )
    p.set_defaults(_handler=_handle_factor_weights)


def _handle_factor_weights(args: argparse.Namespace) -> int:
    if not args.name:
        print("错误:factor_weights 需要策略名。运行 `python strategies.py factor_weights -h`", file=sys.stderr)
        return 2
    subcmd = args.subcmd or "once"
    from strategies.agents.factor_weights import run_factor_weights_once, run_factor_weights_watch
    from strategies.config import RuntimeSettings

    rt = RuntimeSettings.from_env()

    if subcmd == "once":
        try:
            path = run_factor_weights_once(
                args.name,
                from_original=args.from_original,
                max_retries=rt.factor_weights_max_retries,
            )
        except FileNotFoundError as e:
            print(f"[factor_weights] {e}", file=sys.stderr)
            return 1
        except Exception as e:
            print(f"[factor_weights] 失败: {type(e).__name__}: {e}", file=sys.stderr)
            return 1
        if path is None:
            print("[factor_weights] 本轮失败,未写入", file=sys.stderr)
            return 1
        print(f"[factor_weights] 成功: {path}")
        return 0
    elif subcmd == "watch":
        try:
            run_factor_weights_watch(args.name, from_original=args.from_original)
        except KeyboardInterrupt:
            print("\n[factor_weights.watch] 退出")
        return 0
    return 2


# ====================================================================
# argparse 构建
# ====================================================================
def build_parser() -> argparse.ArgumentParser:
    """构建 CLI argparser(E1 互斥子命令组 + E2 默认单次)。"""
    parser = argparse.ArgumentParser(
        prog="strategies.py",
        description="my-quant3 策略生成系统 CLI(详见 strategies.md)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
模式 1 (generate):  python strategies.py generate
模式 2 (optimize):   python strategies.py optimize <name> [once|watch] [--from-original]
模式 3 (weights):    python strategies.py factor_weights <name> [once|watch] [--from-original]
工具 (list):         python strategies.py list
""",
    )

    sub = parser.add_subparsers(dest="command", help="子命令", metavar="<command>")

    # generate(无子命令组,单次触发)
    p_gen = sub.add_parser("generate", help="模式 1:生成新策略(LLM 按业务目标生成)")
    p_gen.set_defaults(_handler=cmd_generate)

    # optimize / factor_weights(once | watch 互斥)
    _add_optimize_subcommand(sub)
    _add_factor_weights_subcommand(sub)

    # list
    p_list = sub.add_parser("list", help="列出 subject/ 下所有策略")
    p_list.set_defaults(_handler=cmd_list)

    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI 入口函数。"""
    parser = build_parser()
    args = parser.parse_args(argv)

    if not hasattr(args, "_handler"):
        parser.print_help()
        return 2

    return args._handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
