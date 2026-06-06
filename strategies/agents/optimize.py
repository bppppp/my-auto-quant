"""
src.agents.optimize — 模式 2: Part A 参数调优（Mode 2: Optimize）

来源 prompt: src/agents/prompts/optimize.md
入口: `python strategies.py optimize <name>` / `optimize once <name>` / `optimize watch <name>`
约束（§6.5 / §6.6）:
  - 仅改 params[].default / range / reason（reason 不进 .md）
  - 其它字段（name / type / description）必须与 latest 完全一致（G2）
  - param 数量 1:1（G1 缺报错，多丢弃）
  - 不改 factors / signals / targets / test_universe / body
  - position_weights：LLM 不直接改；写盘前会**自动同步**——任何 `param.name`
    出现在 `position_weights` 顶层 key 时，其值会被改成新 default（详见 §6.5）

硬校验（mode='optimize'）: #10 / #11 / #18 / #19 + G1 / G2
监听: watcher.Watcher（debounce 5s 触发回调）
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
    check_g1_param_count,
    check_g2_param_immutable,
    extract_sections,
    find_all_reports,
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
from strategies.agents.watcher import run_watch  # noqa: E402
from strategies.config import RuntimeSettings, get_llm_settings  # noqa: E402


# ====================================================================
# 单次触发数据流（§6.2）
# ====================================================================
def _build_user_prompt(
    latest_path: Path,
    latest_fm: dict,
    latest_body: str,
    reports_text: str,
    from_original: bool,
) -> str:
    """构造 optimize 的 user_prompt（注入完整 .md + 5 份报告）。"""
    import json

    parts = ["## 待调优策略（latest）\n"]
    parts.append(f"文件: {latest_path.name}{'（--from-original）' if from_original else ''}\n")
    parts.append("```yaml")
    parts.append(json.dumps(latest_fm, ensure_ascii=False, indent=2))
    parts.append("```")
    if latest_body:
        parts.append("\n## Strategy Narrative（仅参考，不重写）\n")
        parts.append("```")
        parts.append(latest_body[:5000])  # 截断以省 token
        parts.append("```")

    if reports_text:
        parts.append("\n## 回测报告（最多 5 份，F2 分配）\n")
        parts.append(reports_text)

    parts.append(
        """
## 任务
请基于以上 .md + 5 份报告，按 system prompt 的规范输出**完整 params 列表**（覆盖式）：
- 必含**所有现有 param**（一个不漏，按 name 1:1 对应）
- name / type / description **原样复制 latest**（G2 不可改字段前后对比）
- default / range 可改（核心调优对象）
- 新增 reason 字段（≤ 80 字符，进审计，不进 .md）
"""
    )
    return "\n".join(parts)


def _format_validation_errors(errors: list, g_errs: list) -> str:
    """把硬校验失败 + G1/G2 失败转成 user_prompt 末尾反馈。"""
    lines = ["## ⚠️ 硬校验失败（请修正后重生成）\n"]
    if errors:
        lines.append("### 模式 2 硬校验（#10/#11/#18/#19）")
        for e in errors:
            lines.append(f"- `{e.code}`: {e.message}")
    if g_errs:
        lines.append("\n### G1 / G2 不可改字段前后对比")
        for e in g_errs:
            lines.append(f"- `{e.code}`: {e.message}")
    lines.append("\n请重新输出完整 params 列表（覆盖式），保持 name / type / description 与 latest 完全一致。")
    return "\n".join(lines)


def run_optimize_once(
    name: str,
    *,
    from_original: bool = False,
    max_retries: int = 5,
    round_no: int = 1,
) -> Path | None:
    """跑一次 optimize 模式（§6.2 单次触发数据流）。

    Args:
        name: 策略名
        from_original: True → 从 <name>_original.md 引导（§15.2）
        max_retries: LLM 重试上限
        round_no: 当前轮次（用于 3+1 think 策略：每 4 轮一周期，最后一轮开 think）

    Returns:
        新写入的 <name>_v<N+1>.md 路径；LLM 失败 / 校验失败时返回 None
    """
    # 1) 读 latest .md
    banner(f"模式 2: optimize 启动 | name={name}, from_original={from_original}, max_retries={max_retries}")
    if from_original:
        # 顶层 subjects/<name>/<name>_original.md
        latest_path = original_md_path(name)
        if not latest_path.exists():
            raise FileNotFoundError(f"--from-original 指定的原始快照不存在: {latest_path}")
    else:
        # strategiesParam/<name>_v<N>.md 中版本号最大的
        latest_path = find_latest_md(name, track="main")
        if not latest_path:
            raise FileNotFoundError(
                f"策略 {name!r} 不存在 latest .md。"
                f"请先跑 generate 模式,或用 --from-original 显式指定原始快照。"
            )
    log_print(f"[optimize] 引导源: {latest_path}")

    latest_fm, latest_body = read_md(latest_path)
    is_original = latest_path.name.endswith("_original.md")
    latest_params = latest_fm.get("params", [])
    log_print(f"[optimize] latest frontmatter 字段: {sorted(latest_fm.keys())}")
    log_print(f"[optimize] latest params 数量: {len(latest_params)}")
    log_print(f"[optimize] latest body 长度: {len(latest_body)} 字符")

    # 2) 读 5 份回测报告(F2 分配,模式 2 监听 reportParams/)
    section("[optimize] 加载回测报告 (reportParams/, F2 分配)")
    reports_text = get_reports_for_tuning(name, mode="params", max_reports=5)
    if not reports_text:
        log_print(f"[optimize] 策略 {name!r} 无回测报告——将基于 .md 自身调优(无报告反馈)")
    else:
        n_reports = reports_text.count("## report_")
        log_print(f"[optimize] 加载报告: {n_reports} 份(最新 1 完整 + 其余精简)")

    # 3) LLM 调优(模式 2 强制 think)
    log_print(f"[optimize] 初始化 LLM(temperature=0.3, think=True) + 加载 optimize.md system prompt")
    settings = get_llm_settings(temperature=0.3, enable_thinking=True)
    llm = build_llm(settings)
    system_prompt = load_prompt("optimize")
    user_prompt = _build_user_prompt(
        latest_path, latest_fm, latest_body, reports_text, from_original
    )
    log_print(f"[optimize] system prompt: {len(system_prompt)} 字符, user prompt: {len(user_prompt)} 字符")

    feedback_md = ""
    last_error: Exception | None = None
    new_params: list[dict] | None = None
    for attempt in range(1, max_retries + 1):
        section(f"[optimize] attempt {attempt}/{max_retries}")
        full_user = user_prompt + ("\n\n" + feedback_md if feedback_md else "")
        log_print(f"[optimize] → 调 LLM 调优 params(default/range 可改, name/type/description 不可改)...")
        try:
            response = llm.invoke(system_prompt, full_user)
        except Exception as e:
            last_error = e
            log_print(f"[optimize] ✗ LLM 调用失败: {type(e).__name__}: {e}")
            feedback_md = f"## ⚠️ LLM 调用失败（attempt {attempt}/{max_retries}）\n\n{type(e).__name__}: {e}"
            continue

        log_print(f"[optimize] → 解析返回 JSON...")
        try:
            data = parse_strategy_json(response)
        except Exception as e:
            last_error = e
            log_print(f"[optimize] ✗ JSON 解析失败: {e}")
            feedback_md = f"## ⚠️ JSON 解析失败（attempt {attempt}/{max_retries}）\n\n{e}"
            continue
        if isinstance(data, dict):
            log_print(f"[optimize] ✓ JSON 解析成功(顶层字段: {sorted(data.keys())})")

        if not isinstance(data, dict) or "params" not in data:
            last_error = ValueError("输出缺 params 顶层 key")
            log_print(f"[optimize] ✗ 输出缺 params 顶层 key")
            feedback_md = "## ⚠️ 输出缺 params 顶层 key（仅输出 params 列表，不增不删）"
            continue

        new_params_raw = data["params"]
        if not isinstance(new_params_raw, list):
            last_error = ValueError("params 不是 list")
            log_print(f"[optimize] ✗ params 不是 list(实际 {type(new_params_raw).__name__})")
            feedback_md = "## ⚠️ params 必须是 list"
            continue
        log_print(f"[optimize] → LLM 返回 {len(new_params_raw)} 个 params(latest={len(latest_params)})")

        # 4) 本地 merge + 校验
        # G1: 数量 1:1
        log_print(f"[optimize] → G1 校验(数量 1:1 + 过滤多余)...")
        g1_errs = check_g1_param_count(new_params_raw, latest_params)
        # 过滤掉 new 里 latest 没有的（多给 → 丢弃）
        latest_names = {p.get("name") for p in latest_params}
        new_params_filtered = [p for p in new_params_raw if p.get("name") in latest_names]
        # 按 latest 顺序重排
        order = {n: i for i, n in enumerate(latest_names)}
        new_params_filtered.sort(key=lambda p: order.get(p.get("name"), 999))
        log_print(f"[optimize]   过滤后保留 {len(new_params_filtered)}/{len(new_params_raw)} (按 latest 顺序重排)")

        # G2: 不可改字段前后对比
        log_print(f"[optimize] → G2 校验(name/type/description 不可改)...")
        g2_errs = check_g2_param_immutable(new_params_filtered, latest_params)

        # 模式 2 硬校验（#10/#11/#18/#19）
        log_print(f"[optimize] → 模式 2 硬校验(#10/#11/#18/#19)...")
        merged_fm = dict(latest_fm)
        merged_fm["params"] = new_params_filtered
        struct_errs = validate_md_structure(merged_fm, latest_body, mode="optimize")

        if g1_errs or g2_errs or struct_errs:
            log_print(f"[optimize] ✗ 校验失败: G1={len(g1_errs)} G2={len(g2_errs)} struct={len(struct_errs)}")
            for e in (g1_errs + g2_errs + struct_errs)[:5]:
                log_print(f"[optimize]   错误: [{e.code}] {e.message}")
            if len(g1_errs) + len(g2_errs) + len(struct_errs) > 5:
                log_print(f"[optimize]   ... 另 {len(g1_errs) + len(g2_errs) + len(struct_errs) - 5} 项未列出")
            feedback_md = _format_validation_errors(struct_errs, g1_errs + g2_errs)
            last_error = ValueError(
                f"硬校验失败 G1={len(g1_errs)} G2={len(g2_errs)} struct={len(struct_errs)}"
            )
            continue
        log_print(f"[optimize] ✓ 全部校验通过(G1=0 G2=0 struct=0)")

        new_params = new_params_filtered
        break

    if new_params is None:
        log_print(f"[optimize] ✗ 重试 {max_retries} 次后仍失败: {last_error}")
        return None

    # 5) 写盘 → subjects/<name>/strategiesParam/<name>_v<N+1>.md
    if is_original:
        next_v = 2  # --from-original 时写 v2
    else:
        next_v = next_version(name, track="main")

    new_fm = dict(latest_fm)
    new_fm["params"] = new_params
    # position_weights 显示值自动跟随(§6.5 注释:对应 param 的 default 改了 → 显示值自动跟随)
    pw = new_fm.get("position_weights", {})
    if isinstance(pw, dict):
        new_pw = dict(pw)
        for p in new_params:
            pn = p.get("name")
            if pn in new_pw and "default" in p:
                new_pw[pn] = p["default"]
        new_fm["position_weights"] = new_pw

    new_path = strategy_dir_for(name, track="main") / f"{name}_v{next_v}.md"
    section(f"[optimize] 写盘")
    log_print(f"[optimize] → 目标: {new_path}")
    write_md(new_path, new_fm, latest_body)
    log_print(f"[optimize] ✓ 已写: {new_path}")
    log_print(f"[optimize]   params 改动摘要: {len(new_params)} 项 default/range 已更新")
    return new_path


# ====================================================================
# 持续监听(§6.3)—— 监听 subjects/<name>/reportParams/report_v*.md
# ====================================================================
def run_optimize_watch(
    name: str,
    *,
    from_original: bool = False,
    round_no: int = 1,
) -> None:
    """监听 reportParams/report_v*.md 新增,debounce 后跑 optimize.once。

    持续循环,直到 Ctrl+C 或达到 max_listen_iterations。
    """
    from strategies.agents.watcher import Watcher

    rt = RuntimeSettings.from_env()
    # 新结构:subjects/<name>/reportParams/
    reports_dir = _PROJECT_ROOT / "subjects" / name / "reportParams"
    log_print(f"[optimize.watch] 监听目录: {reports_dir}")
    log_print(f"[optimize.watch] debounce: {rt.debounce_seconds}s, max_iterations: {rt.max_listen_iterations}, create_only: {rt.watch_create_only}")

    def _on_new_file(path: Path) -> None:
        log_print(f"[optimize.watch] 检测到新报告: {path.name}")
        result = run_optimize_once(name, from_original=from_original, round_no=round_no)
        if result:
            log_print(f"[optimize.watch] 已生成: {result}")
        else:
            log_print(f"[optimize.watch] 本轮失败,跳过")

    watcher = Watcher(
        watch_dir=reports_dir,
        glob_pattern="report_v*.md",
        on_change=_on_new_file,
        debounce_seconds=rt.debounce_seconds,
        create_only=rt.watch_create_only,
        max_iterations=rt.max_listen_iterations,
    )
    run_watch(watcher, first_run=lambda: run_optimize_once(name, from_original=from_original, round_no=round_no))


__all__ = ["run_optimize_once", "run_optimize_watch"]
