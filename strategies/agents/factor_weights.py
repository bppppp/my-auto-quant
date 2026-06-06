"""
src.agents.factor_weights — 模式 3: 因子权重调优（Mode 3: Factor Weights）

来源 prompt: src/agents/prompts/factor_weights.md
入口: `python strategies.py factor_weights <name>` / `factor_weights once|watch <name>`
引导源（I1）: signals track 优先 → main track → original

约束（§7.3 / §7.4）:
  - 唯一可改: entry_signals[].weight / exit_signals[].weight
  - 5 字段（name / factors / direction / trigger / logic）必须原样复制 latest
  - factors 列表**不进入 LLM 输出**,由代码从 latest 整体继承
  - 不改 params / targets / test_universe / position_weights / body

硬校验（mode='factor_weights'）: #4 / #5 / #6 / #7 / #8 / #16 / #20 / #23 / #24 + G3
监听: report_signals_v*.md
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from strategies.agents.base_agent import (  # noqa: E402
    build_llm,
    check_g3_factors_immutable,
    check_g3_signals_immutable,
    find_latest_md,
    get_reports_for_tuning,
    load_prompt,
    next_version,
    original_md_path,
    parse_strategy_json,
    read_md,
    strategy_dir_for,
    validate_md_structure,
    write_md,
)
from strategies.agents.log_utils import banner, log_print, section  # noqa: E402
from strategies.config import RuntimeSettings, get_llm_settings  # noqa: E402


# ====================================================================
# 数据流(§7.2)—— 模式 3 只在 strategiesWeight/ 找,找不到直接报错
# ====================================================================
def _resolve_latest(name: str, from_original: bool) -> Path:
    """模式 3 引导源: 严格从 strategiesWeight/ 找 <name>_weight_v<N>.md。

    Args:
        name: 策略名
        from_original: True → 强制用顶层 <name>_original.md

    Raises:
        FileNotFoundError: strategiesWeight/ 中无文件(且未用 --from-original)
    """
    if from_original:
        # 顶层 subjects/<name>/<name>_original.md
        p = original_md_path(name)
        if not p.exists():
            raise FileNotFoundError(f"--from-original 指定的原始快照不存在: {p}")
        return p

    # 只在 strategiesWeight/ 找 → 找不到直接报错(用户要求:不 fallback)
    sdir = strategy_dir_for(name, track="signals")
    if not sdir.exists() or not any(sdir.glob(f"{name}_weight_v*.md")):
        raise FileNotFoundError(
            f"模式 3:策略 {name!r} 在 strategiesWeight/ 下找不到 <name>_weight_v*.md。"
            f"请先在 strategiesParam/ 下至少跑一次 generate 或 optimize,再 factor_weights。"
        )

    latest = find_latest_md(name, track="signals", fallback_to_original=False)
    if not latest:
        raise FileNotFoundError(
            f"模式 3:策略 {name!r} 在 strategiesWeight/ 下找不到 <name>_weight_v*.md。"
        )
    return latest


def _build_user_prompt(
    latest_path: Path,
    latest_fm: dict,
    latest_body: str,
    reports_text: str,
) -> str:
    import json

    parts = [
        "## 待调优策略（latest signals v<N>，signals track 优先）\n",
        f"文件: {latest_path.name}\n",
        "```yaml",
        json.dumps(latest_fm, ensure_ascii=False, indent=2),
        "```",
    ]
    if latest_body:
        parts.append("\n## Strategy Narrative（仅参考，不重写）\n")
        parts.append("```")
        parts.append(latest_body[:5000])
        parts.append("```")

    if reports_text:
        parts.append("\n## 回测报告（最多 5 份,F2 分配）\n")
        parts.append(reports_text)

    parts.append(
        """
## 任务
请基于以上 .md + 5 份 signals 报告,按 system prompt 的规范输出:
- 完整 entry_signals + exit_signals 列表（**仅 2 个顶层 key**,不含 factors）
- 5 字段（name / factors / direction / trigger / logic）**原样复制 latest**
- 仅 weight 字段填新值
- 数量 1:1（不增不删）
- factors 列表不输出,由代码整体继承
"""
    )
    return "\n".join(parts)


def _format_validation_errors(errors: list, g_errs: list) -> str:
    lines = ["## ⚠️ 硬校验失败（请修正后重生成）\n"]
    if errors:
        lines.append("### 模式 3 硬校验（#4-#8/#16/#20/#23/#24）")
        for e in errors:
            lines.append(f"- `{e.code}`: {e.message}")
    if g_errs:
        lines.append("\n### G3 不可改字段前后对比")
        for e in g_errs:
            lines.append(f"- `{e.code}`: {e.message}")
    lines.append(
        "\n请重新输出完整 entry_signals + exit_signals 列表（**仅 2 个顶层 key**,不含 factors）,"
        "5 字段原样复制,仅 weight 填新值。"
    )
    return "\n".join(lines)


def run_factor_weights_once(
    name: str,
    *,
    from_original: bool = False,
    max_retries: int = 5,
    round_no: int = 1,
) -> Path | None:
    """跑一次 factor_weights 模式。

    Args:
        name: 策略名
        from_original: True → 从 <name>_original.md 引导
        max_retries: LLM 重试上限
        round_no: 当前轮次

    Returns:
        新写入的 <name>_signals_v<N+1>.md 路径;LLM 失败/校验失败时 None
    """
    # 1) 读 latest .md（I1 引导源）
    banner(f"模式 3: factor_weights 启动 | name={name}, from_original={from_original}, max_retries={max_retries}")
    latest_path = _resolve_latest(name, from_original)
    log_print(f"[factor_weights] 引导源: {latest_path}")
    latest_fm, latest_body = read_md(latest_path)
    is_original = latest_path.name.endswith("_original.md")
    log_print(f"[factor_weights] latest frontmatter 字段: {sorted(latest_fm.keys())}")
    log_print(f"[factor_weights] latest entry_signals={len(latest_fm.get('entry_signals', []))}, "
              f"exit_signals={len(latest_fm.get('exit_signals', []))}, "
              f"factors={len(latest_fm.get('factors', []))}")
    log_print(f"[factor_weights] latest body 长度: {len(latest_body)} 字符")

    # 2) 读 5 份 report_signals 报告(模式 3 监听 reportWeight/)
    section("[factor_weights] 加载回测报告 (reportWeight/, F2 分配)")
    reports_text = get_reports_for_tuning(name, mode="weights", max_reports=5)
    if not reports_text:
        log_print(f"[factor_weights] 策略 {name!r} 无 weights 报告——将基于 .md 自身调优")
    else:
        n_reports = reports_text.count("## report_")
        log_print(f"[factor_weights] 加载报告: {n_reports} 份(最新 1 完整 + 其余精简)")

    # 3) LLM 调权重(模式 3 强制 think)
    log_print(f"[factor_weights] 初始化 LLM(temperature=0.3, think=True) + 加载 factor_weights.md system prompt")
    settings = get_llm_settings(temperature=0.3, enable_thinking=True)
    llm = build_llm(settings)
    system_prompt = load_prompt("factor_weights")
    user_prompt = _build_user_prompt(latest_path, latest_fm, latest_body, reports_text)
    log_print(f"[factor_weights] system prompt: {len(system_prompt)} 字符, user prompt: {len(user_prompt)} 字符")

    feedback_md = ""
    last_error: Exception | None = None
    new_signals: dict | None = None
    for attempt in range(1, max_retries + 1):
        section(f"[factor_weights] attempt {attempt}/{max_retries}")
        full_user = user_prompt + ("\n\n" + feedback_md if feedback_md else "")
        log_print(f"[factor_weights] → 调 LLM 调优 signal weights(仅 weight 可改, 其余 5 字段不可改)...")
        try:
            response = llm.invoke(system_prompt, full_user)
        except Exception as e:
            last_error = e
            log_print(f"[factor_weights] ✗ LLM 调用失败: {type(e).__name__}: {e}")
            feedback_md = f"## ⚠️ LLM 调用失败（attempt {attempt}/{max_retries}）\n\n{type(e).__name__}: {e}"
            continue

        log_print(f"[factor_weights] → 解析返回 JSON...")
        try:
            data = parse_strategy_json(response)
        except Exception as e:
            last_error = e
            log_print(f"[factor_weights] ✗ JSON 解析失败: {e}")
            feedback_md = f"## ⚠️ JSON 解析失败（attempt {attempt}/{max_retries}）\n\n{e}"
            continue
        if isinstance(data, dict):
            log_print(f"[factor_weights] ✓ JSON 解析成功(顶层字段: {sorted(data.keys())})")

        if not isinstance(data, dict) or "entry_signals" not in data or "exit_signals" not in data:
            last_error = ValueError("输出必须含 entry_signals + exit_signals 顶层 key（不含 factors）")
            log_print(f"[factor_weights] ✗ 输出缺 entry_signals/exit_signals 顶层 key")
            feedback_md = "## ⚠️ 输出必须含 entry_signals + exit_signals 顶层 key（不含 factors）"
            continue
        if "factors" in data:
            last_error = ValueError("输出不应含 factors 顶层 key（由代码从 latest 整体继承）")
            log_print(f"[factor_weights] ✗ 输出含 factors 顶层 key(应不输出)")
            feedback_md = "## ⚠️ 输出不应含 factors 顶层 key（由代码整体继承,你只输出 signals）"
            continue

        # 4) 本地 merge + 校验
        latest_signals = {
            "entry_signals": latest_fm.get("entry_signals", []),
            "exit_signals": latest_fm.get("exit_signals", []),
        }
        new_signals_raw = {
            "entry_signals": data["entry_signals"],
            "exit_signals": data["exit_signals"],
        }
        log_print(f"[factor_weights] → LLM 返回 entry={len(new_signals_raw['entry_signals'])}, exit={len(new_signals_raw['exit_signals'])}")

        # G3 信号字段锁死
        log_print(f"[factor_weights] → G3 校验(signal 5 字段不可改 + 数量 1:1)...")
        g3_sig_errs = check_g3_signals_immutable(new_signals_raw, latest_signals)
        # G3 factors 锁死（代码侧，防御性）
        latest_factors = latest_fm.get("factors", [])
        g3_fac_errs = check_g3_factors_immutable(latest_factors, latest_factors)  # 防御性自检

        # 模式 3 硬校验
        log_print(f"[factor_weights] → 模式 3 硬校验(#4/#5/#6/#7/#8/#16/#20/#23/#24)...")
        merged_fm = dict(latest_fm)
        merged_fm["entry_signals"] = new_signals_raw["entry_signals"]
        merged_fm["exit_signals"] = new_signals_raw["exit_signals"]
        struct_errs = validate_md_structure(merged_fm, latest_body, mode="factor_weights")

        if g3_sig_errs or struct_errs:
            log_print(f"[factor_weights] ✗ 校验失败: G3-sig={len(g3_sig_errs)} struct={len(struct_errs)}")
            for e in (g3_sig_errs + struct_errs)[:5]:
                log_print(f"[factor_weights]   错误: [{e.code}] {e.message}")
            if len(g3_sig_errs) + len(struct_errs) > 5:
                log_print(f"[factor_weights]   ... 另 {len(g3_sig_errs) + len(struct_errs) - 5} 项未列出")
            feedback_md = _format_validation_errors(struct_errs, g3_sig_errs + g3_fac_errs)
            last_error = ValueError(
                f"硬校验失败 G3-sig={len(g3_sig_errs)} struct={len(struct_errs)}"
            )
            continue
        log_print(f"[factor_weights] ✓ 全部校验通过(G3-sig=0 struct=0)")

        new_signals = new_signals_raw
        break

    if new_signals is None:
        log_print(f"[factor_weights] ✗ 重试 {max_retries} 次后仍失败: {last_error}")
        return None

    # 5) 写盘 → subjects/<name>/strategiesWeight/<name>_weight_v<N+1>.md
    if is_original:
        next_v = 2
    else:
        next_v = next_version(name, track="signals")

    new_fm = dict(latest_fm)
    new_fm["entry_signals"] = new_signals["entry_signals"]
    new_fm["exit_signals"] = new_signals["exit_signals"]
    # factors 列表原样继承(理论上未变化,防御性自检已通过)
    new_fm["factors"] = latest_fm.get("factors", [])

    new_path = strategy_dir_for(name, track="signals") / f"{name}_weight_v{next_v}.md"
    section(f"[factor_weights] 写盘")
    log_print(f"[factor_weights] → 目标: {new_path}")
    write_md(new_path, new_fm, latest_body)
    log_print(f"[factor_weights] ✓ 已写: {new_path}")
    log_print(f"[factor_weights]   signal weights 改动: entry {len(new_signals['entry_signals'])} 项 + exit {len(new_signals['exit_signals'])} 项")
    return new_path


# ====================================================================
# 持续监听(§7.2)—— 监听 subjects/<name>/reportWeight/report_signals_v*.md
# ====================================================================
def run_factor_weights_watch(
    name: str,
    *,
    from_original: bool = False,
    round_no: int = 1,
) -> None:
    from strategies.agents.watcher import Watcher, run_watch

    rt = RuntimeSettings.from_env()
    # 新结构:subjects/<name>/reportWeight/
    reports_dir = _PROJECT_ROOT / "subjects" / name / "reportWeight"
    log_print(f"[factor_weights.watch] 监听目录: {reports_dir}")
    log_print(f"[factor_weights.watch] debounce: {rt.debounce_seconds}s, max_iterations: {rt.max_listen_iterations}, create_only: {rt.watch_create_only}")

    def _on_new_file(path: Path) -> None:
        log_print(f"[factor_weights.watch] 检测到新报告: {path.name}")
        result = run_factor_weights_once(name, from_original=from_original, round_no=round_no)
        if result:
            log_print(f"[factor_weights.watch] 已生成: {result}")
        else:
            log_print(f"[factor_weights.watch] 本轮失败,跳过")

    watcher = Watcher(
        watch_dir=reports_dir,
        glob_pattern="report_signals_v*.md",
        on_change=_on_new_file,
        debounce_seconds=rt.debounce_seconds,
        create_only=rt.watch_create_only,
        max_iterations=rt.max_listen_iterations,
    )
    run_watch(
        watcher,
        first_run=lambda: run_factor_weights_once(name, from_original=from_original, round_no=round_no),
    )


__all__ = ["run_factor_weights_once", "run_factor_weights_watch"]
