"""
src.agents.generate — 模式 1: 策略生成（Mode 1: Generate）

入口: `python strategies.py generate`
来源 prompt: src/agents/prompts/generate.md
硬校验: validate_md_structure (mode='generate') 跑 22 硬 + 1 软
评估:   quality_eval.py (1 次过，K2 失败 → 重生成整篇)

工作流（strategies.md §5.1）:
  1) 调 LLM（think 模式, T=0.3）生成完整 JSON
     输入: system=generate.md + user=业务目标 + 数据契约
     输出: {name, test_universe, frontmatter, strategy_narrative}
  2) validate_md_structure 硬校验（22 硬 + 1 软）
     硬失败 → 反馈 + 重生成（最多 5 次）
  3) quality_eval 业务评估（1 次过）
     失败 → 反馈 + 重生成整篇
  4) 写盘: <name>_v1.md + <name>_original.md

失败处理: 5 次重试全失败 → 抛异常退出，不写任何文件。
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
    load_prompt,
    original_md_path,
    parse_strategy_json,
    strategy_dir_for,
    strategy_root,
    subject_dir,
    validate_auto_name,
    validate_md_structure,
    write_md,
)
from strategies.agents.log_utils import banner, log_print, section  # noqa: E402
from strategies.agents.quality_eval import run_quality_eval  # noqa: E402
from strategies.config import RuntimeSettings, get_llm_settings  # noqa: E402

# ====================================================================
# fail-fast 异常分类
# ====================================================================
# 连接/认证/参数错误——重试 N 次也不会通过,直接 fail-fast 报配置问题
# 速率限制/服务端错误——可能 transient,正常重试
class _LLMConfigError(RuntimeError):
    """LLM 配置/网络类错误(连接、超时、鉴权、参数)。

    与普通 RuntimeError 区分:_run_generate_once 抛此错时,
    run_generate 外层循环不再重试(否则会无限循环同一个配置错误)。
    """


try:
    from openai import APIConnectionError, APITimeoutError, AuthenticationError, BadRequestError
    _FAIL_FAST_EXC = (APIConnectionError, APITimeoutError, AuthenticationError, BadRequestError)
except ImportError:  # 没装 openai 时退化到名字匹配
    _FAIL_FAST_EXC = ()
_FAIL_FAST_NAMES = {"APIConnectionError", "APITimeoutError", "AuthenticationError", "BadRequestError"}


def _is_fail_fast_error(exc: BaseException) -> bool:
    """判断是否属于"重试也救不回来"的错误(连接/超时/鉴权/参数)。"""
    if _FAIL_FAST_EXC and isinstance(exc, _FAIL_FAST_EXC):
        return True
    # openai 未导入时按类名匹配(覆盖 langchain_openai 等其他 SDK)
    return type(exc).__name__ in _FAIL_FAST_NAMES


def _build_user_prompt() -> str:
    """模式 1 的 user_prompt：业务目标 + 数据契约 + 约束。"""
    return """请按 system prompt 中的规范生成一份 A 股中周期波段策略。

## 业务目标
- 期望年化 > 20%（硬规则）
- 收益/回撤比 ≥ 1.0（硬规则）
- 胜率 × 盈亏比 ≥ 1.5（数学自洽下界）
- 5 项 targets 数值内部一致（高收益 + 高回撤 = 矛盾）

## 数据契约
- 数据范围: data-by-day/{YYYY}/{YYYY-MM-DD}_金玥数据.csv (2018-2026)
- 字段: 38 列（行情 + 成交 + 涨跌 + 股本 + 估值 + 标识）—— 详见 data/README.md §2
- 测试集: 从 HS300 / CSI1000 / CYB_STAR_50 中选 1~3 个（默认 ["HS300"]）

## A 股硬约束
- T+1 交割；最小买入 100 股
- 涨跌停: 主板 ±10% / 创业·科创 ±20% / ST ±5%
- 停牌日不成交；新股 / 退市 / 一字板默认跳过
- 费用: 买入佣金万 2.5（最低 5 元）+ 沪市过户费万 0.1；卖出加印花税万 10

## 输出要求
1. 输出 JSON（用 ```json 代码块），结构与 system prompt 严格一致
2. `name`: snake_case，≤ 64 字符，无 _v<N> 后缀
3. `test_universe`: list，从 3 个 universe 中选 1~3 个（HS300 / CSI1000 / CYB_STAR_50）
4. `frontmatter`: 6 区块（targets / factors / entry_signals / exit_signals / position_weights / params）+ 元信息
5. `strategy_narrative`: 单字段，≥ 1200 字符，含 5 节
6. `params[].description`: ≥ 30 字符，含含义/单位/典型取值/默认值理由 4 要素
7. 所有数字阈值 param 化（trigger 中除 0/1/100/1000 外不能有硬编码数字）
8. factors 不带 weight / direction，仅作"计算词汇表"
9. signals weight 是比例关系（不要求总和 = 1.0）
10. factors 列表里的每个因子必须被至少一个 signal 的 trigger 引用
11. factors[].calculation 必填（伪代码）
12. strategy_narrative 第 5 节必含 4 类 NaN 处理（上市未满 N 日 / 停牌 / 涨跌停 / 一字板）
"""


def _format_validation_errors(errors: list) -> str:
    """把 ValidationError 列表转成给 LLM 看的反馈 markdown。"""
    if not errors:
        return ""
    lines = ["## ⚠️ 上次硬校验失败（请修正后重生成）\n"]
    hard = [e for e in errors if not str(e.code).endswith("-soft")]
    soft = [e for e in errors if str(e.code).endswith("-soft")]

    if hard:
        lines.append("### 硬失败（必须修复）")
        for e in hard:
            lines.append(f"- `{e.code}`: {e.message}")
    if soft:
        lines.append("\n### 软检查（建议修复）")
        for e in soft:
            lines.append(f"- `{e.code}`: {e.message}")
    lines.append("\n请重新输出完整 JSON，保持 `name` 一致。")
    return "\n".join(lines)


# 6 维修复模板 — 当 LLM 在某维低分时,告诉它下次具体怎么改
_DIMENSION_FIX_TEMPLATES = {
    "business_goal_alignment": (
        "重新审视 targets.annual_return 与策略类型的关系: "
        "趋势跟随策略年化 > 25% 较激进,均值回归策略 < 15% 较合理"
    ),
    "target_consistency": (
        "重算 win_rate × profit_loss_ratio: 若 < 1.5,提高盈亏比或胜率; "
        "高夏普必须配高收益;高胜率可降盈亏比"
    ),
    "bull_bear_adaptability": (
        "narrative 第 2 节须**明文**写 3 环境差异化处理(牛/熊/震荡),"
        "每环境 2-3 行,所有阈值用 `{param_name}`,**不**做实时市场识别"
    ),
    "parameter_tunability": (
        "B2 8 项检查: 入场/出场/调仓/加仓/减仓/风控/仓位调整/position_weights 字段; "
        "description 4 要素: 含义+单位+典型取值+默认值理由"
    ),
    "logical_self_consistency": (
        "narrative 第 3 节须明确**出场优先级**(固定止损>移动止损>时间止损), "
        "每个 signal weight 给业务理由"
    ),
    "data_implementability": (
        "factors[].calculation 必须用标准公式(`mean(x, N)`/`atr(h,l,c, N)`/"
        "`100 - 100/(1+...)`),禁止 `market_sentiment` / `news_score` 等不可计算变量"
    ),
}


def _pick_weakest_dimension(soft_eval: dict) -> str:
    """从 soft_eval 里挑 gap 最大的维度(分数最低的)。"""
    worst_dim = None
    worst_gap = -1.0
    for dim, content in soft_eval.items():
        if not isinstance(content, dict):
            continue
        try:
            score = float(content.get("score", 0))
        except (TypeError, ValueError):
            score = 0.0
        gap = 10.0 - score
        if gap > worst_gap:
            worst_gap = gap
            worst_dim = dim
    return worst_dim or "data_implementability"


def _format_quality_eval_feedback(eval_result: dict, *, attempt: int = 1) -> str:
    """把 quality_eval 失败转成 user_prompt 末尾的反馈。

    通过条件: 6 维总分 >= 51/60(85%, 见 quality_eval._PASS_THRESHOLD)。
    不通过则展示按 gap 降序的每维分数 + 弱维度 issues + 修复模板,引导 LLM 改进。

    Args:
        eval_result: quality_eval 返回的 dict
        attempt: 当前是第几次尝试(>= 3 时插入"换思路"警告)
    """
    lines: list[str] = ["## 上次 quality_eval 未通过(请修正后重生成)\n"]

    # 0) 失败 ≥ 3 次时,在头部加"换思路"警告
    if attempt >= 3:
        lines.append(f"### ⚠️ 已失败 {attempt} 次\n")
        lines.append("请**大幅修改策略类型/因子选择/出入场逻辑**,不要在原 spec 上做小调整。\n")

    # 1) 6 维分数表(按 gap 降序排,LLM 一眼看到最弱维度)
    soft = eval_result.get("soft_evaluation", {})
    sorted_dims = sorted(
        soft.items(),
        key=lambda kv: -(10 - float(kv[1].get("score", 0))) if isinstance(kv[1], dict) else 0,
    )
    lines.append("### 6 维评分(按 gap 降序)\n")
    lines.append("| 维度 | 分数 | 满分 | 差距 |")
    lines.append("|---|---|---|---|")
    for dim, content in sorted_dims:
        if not isinstance(content, dict):
            continue
        try:
            s = float(content.get("score", 0))
        except (TypeError, ValueError):
            s = 0
        gap = max(0.0, 10 - s)
        # issues 嵌入到对应维度行
        issues = content.get("issues", [])
        if issues:
            issue_strs = [
                f"[{issue.get('severity', 'info')}] {issue.get('description', '')}"
                for issue in issues
            ]
            cell = f"{dim} (有 {len(issues)} 个 issue)"
        else:
            cell = dim
        lines.append(f"| {cell} | {s} | 10 | {gap:.1f} |")

    total = eval_result.get("_quality_total", 0)
    total_max = eval_result.get("_quality_total_max", 60)
    ratio = eval_result.get("_quality_ratio", 0)
    lines.append(
        f"| **总分** | **{total:.1f}** | **{total_max}** | "
        f"**{ratio*100:.1f}% < 85% 阈值** |"
    )
    lines.append("")

    # 2) issues(按维度归类,而不是按 severity)
    for dim, content in sorted_dims:
        if not isinstance(content, dict):
            continue
        issues = content.get("issues", [])
        if not issues:
            continue
        lines.append(f"### {dim} 的 issues")
        for issue in issues:
            sev = issue.get("severity", "info")
            desc = issue.get("description", "")
            lines.append(f"- [{sev}] {desc}")
        lines.append("")

    # 3) 修复模板(按当前最弱维度)
    weakest = _pick_weakest_dimension(soft)
    template = _DIMENSION_FIX_TEMPLATES.get(weakest, "")
    if template:
        lines.append(f"### 修复模板(按当前最弱维度:`{weakest}`)\n")
        lines.append(template)
        lines.append("")

    # 4) 引导 LLM 改进 + summary
    lines.append("### 提升方向")
    lines.append("- 重点关注分数最低的维度(差距最大)")
    lines.append("- error 级 issue 必须修复,否则该维度分数无法提升")
    lines.append(f"- 修复后总分需达到 {int(total_max * 0.85)}/{total_max}(85%,见 quality_eval._PASS_THRESHOLD)才算通过")
    lines.append("")
    lines.append(f"### summary\n{eval_result.get('summary', '')}")
    lines.append("\n请按上述反馈重新输出完整 JSON。")
    return "\n".join(lines)


def run_generate(*, max_retries: int = 5) -> Path:
    """跑 generate 模式,**直到生成一个通过 quality_eval 的策略为止**(用户决策)。

    内部结构:
      - 外层无限循环:每次跑一次"完整 generate 流程",失败则从头开始新一轮
      - 内层 N 次重试(_run_generate_once 内):一次完整流程内的 LLM/parse/校验/eval 重试
        (含硬校验失败 + quality_eval 失败,都加反馈让 LLM 改进)

    通过条件(quality_eval):6 维总分 >= 51/60(85%,见 quality_eval._PASS_THRESHOLD)。

    Returns:
        写入的 <name>_v1.md 路径
    """
    rt = RuntimeSettings.from_env()
    banner("模式 1: generate 启动")
    log_print(f"[generate] 目标: 生成新策略,直到通过 quality_eval 85% 阈值(51/60)")
    log_print(f"[generate] 每轮内 LLM 重试上限: {max_retries} (env: SELF_EVAL_MAX_RETRIES)")
    log_print(f"[generate] LLM: model=见配置, temperature=0.3, think=True")
    log_print(f"[generate] 日志文件: strategies/log/run.log(同时落盘)")
    log_print("")

    round_no = 0
    while True:
        round_no += 1
        log_print("")
        banner(f"[generate] 第 {round_no} 轮尝试")
        log_print(f"[generate] 策略名将由 LLM 自动生成(snake_case, ≤64 字符)")
        try:
            path = _run_generate_once(max_retries=max_retries, round_no=round_no)
            log_print("")
            log_print(f"[generate] ✓ 成功: {path}")
            return path
        except _LLMConfigError:
            # 配置/网络类错误——重试同一个配置也没用,直接退出
            raise
        except RuntimeError as e:
            log_print(f"[generate] ✗ 本轮失败: {e}")
            log_print(f"[generate] 重新开始下一轮(无上限)...")


def _run_generate_once(*, max_retries: int, round_no: int) -> Path:
    """单轮 generate 流程(max_retries 次重试)。

    Raises:
        RuntimeError: 重试耗尽仍未通过 quality_eval
    """
    log_print(f"[generate] 初始化: 加载 generate.md system prompt + 构造 LLM 客户端...")
    settings = get_llm_settings(temperature=0.3, enable_thinking=True)
    llm = build_llm(settings)
    system_prompt = load_prompt("generate")
    log_print(f"[generate] system prompt 长度: {len(system_prompt)} 字符")

    user_prompt = _build_user_prompt()
    feedback_md = ""

    # 连接类错误重试上限(配错 endpoint / SSL / 鉴权时,重试也救不回来——快速失败)
    conn_max = RuntimeSettings.from_env().connection_max_retries
    conn_fail_count = 0

    last_error: Exception | None = None
    for attempt in range(1, max_retries + 1):
        section(f"[generate] attempt {attempt}/{max_retries}")
        full_user = user_prompt + ("\n\n" + feedback_md if feedback_md else "")
        log_print(f"[generate] user_prompt 长度(含反馈): {len(full_user)} 字符")
        log_print(f"[generate] → 调 LLM 生成完整 JSON 策略...")
        try:
            response = llm.invoke(system_prompt, full_user)
        except Exception as e:
            last_error = e
            log_print(f"[generate] ✗ LLM 调用失败: {type(e).__name__}: {e}")
            # fail-fast:连接/超时/鉴权/参数类错误,重试不会改变结果
            if _is_fail_fast_error(e):
                conn_fail_count += 1
                log_print(
                    f"[generate] ✗ fail-fast 错误(已累计 {conn_fail_count}/{conn_max}): "
                    f"{type(e).__name__}"
                )
                log_print(
                    f"[generate]   提示:请检查 .env 里的 LLM_BASE_URL / LLM_API_KEY / LLM_MODEL / "
                    f"网络/代理/SSL 配置。"
                )
                if conn_fail_count >= conn_max:
                    raise _LLMConfigError(
                        f"LLM 连续 {conn_fail_count} 次 fail-fast 错误({type(e).__name__}: {e})。"
                        f"大概率是 .env 配置或网络问题,不是 LLM 输出问题。"
                        f"请检查 LLM_BASE_URL / LLM_API_KEY / LLM_MODEL / 网络/代理/SSL。"
                    ) from e
                # 未达上限则继续重试(本类错误)
                continue
            feedback_md = f"## ⚠️ LLM 调用失败（attempt {attempt}/{max_retries}）\n\n{type(e).__name__}: {e}"
            continue

        # 解析 JSON
        log_print(f"[generate] → 解析 LLM 返回 JSON(剥 think 块 + 找 ```json```)...")
        try:
            data = parse_strategy_json(response)
        except Exception as e:
            last_error = e
            log_print(f"[generate] ✗ JSON 解析失败: {e}")
            feedback_md = f"## ⚠️ JSON 解析失败（attempt {attempt}/{max_retries}）\n\n{e}"
            continue
        if isinstance(data, dict):
            log_print(f"[generate] ✓ JSON 解析成功(顶层字段: {sorted(data.keys())})")
        else:
            log_print(f"[generate] ✓ JSON 解析成功(顶层类型: {type(data).__name__})")

        # 校验 + 修复 frontmatter
        log_print(f"[generate] → 校验输出结构(顶层 4 字段 + 类型)...")
        try:
            data = _postprocess_generate_output(data)
        except ValueError as e:
            last_error = e
            log_print(f"[generate] ✗ 输出结构不合法: {e}")
            feedback_md = f"## ⚠️ 输出结构不合法（attempt {attempt}/{max_retries}）\n\n{e}"
            continue
        log_print(f"[generate] ✓ 输出结构合法")

        # 硬校验
        log_print(f"[generate] → 跑硬校验(模式 generate: 22 硬 + 1 软)...")
        fm = data["frontmatter"]
        body = data["strategy_narrative"]
        # 若 LLM 按新 prompt 只在顶层写 test_universe,frontmatter 这边缺失
        # 注入（仅在 frontmatter 缺时填充,已有则保留 LLM 写的值）
        fm.setdefault("test_universe", data["test_universe"])
        errors = validate_md_structure(fm, body, mode="generate")
        hard_errs = [e for e in errors if not str(e.code).endswith("-soft")]
        soft_errs = [e for e in errors if str(e.code).endswith("-soft")]
        if hard_errs:
            log_print(f"[generate] ✗ 硬校验失败: {len(hard_errs)} 项硬 + {len(soft_errs)} 项软")
            for e in hard_errs[:5]:
                log_print(f"[generate]   硬错误: [{e.code}] {e.message}")
            if len(hard_errs) > 5:
                log_print(f"[generate]   ... 另 {len(hard_errs) - 5} 项未列出")
            feedback_md = _format_validation_errors(errors)
            last_error = ValueError(f"硬校验失败 {len(hard_errs)} 项")
            continue
        log_print(f"[generate] ✓ 硬校验通过(软: {len(soft_errs)} 项)")

        # quality_eval（1 次过）
        log_print(f"[generate] → 调 quality_eval 业务质量评估(独立 LLM 调用)...")
        eval_result = run_quality_eval(fm, body, settings=settings)
        if not eval_result.get("passed", False):
            log_print(
                f"[generate] ✗ quality_eval 未通过: "
                f"{eval_result.get('_quality_total', 0):.1f}/"
                f"{eval_result.get('_quality_total_max', 60)} = "
                f"{eval_result.get('_quality_ratio', 0)*100:.1f}% < 85% 阈值"
            )
            feedback_md = _format_quality_eval_feedback(eval_result, attempt=attempt)
            last_error = ValueError(
                f"quality_eval 未通过: {eval_result.get('summary', 'unknown')}"
            )
            continue
        log_print(
            f"[generate] ✓ quality_eval 通过: "
            f"{eval_result.get('_quality_total', 0):.1f}/"
            f"{eval_result.get('_quality_total_max', 60)} = "
            f"{eval_result.get('_quality_ratio', 0)*100:.1f}% ≥ 85% 阈值"
        )

        # 写盘
        log_print(f"[generate] → 校验策略名 + 准备写盘...")
        # 1) <name>_v1.md → subjects/<name>/strategiesParam/<name>_v1.md
        # 2) <name>_original.md → subjects/<name>/<name>_original.md(顶层,immutable)
        name = validate_auto_name(data["name"])
        sroot = strategy_root(name)  # 自动创建 subjects/<name>/
        sdir = strategy_dir_for(name, track="main")  # strategiesParam/
        v1_path = sdir / f"{name}_v1.md"
        original_path = original_md_path(name)  # 顶层
        log_print(f"[generate] ✓ 策略名: {name}")
        log_print(f"[generate]   → v1:     {v1_path}")
        log_print(f"[generate]   → original: {original_path}(immutable)")

        # 标记 + 写盘
        frontmatter = _build_final_frontmatter(fm, name, data["test_universe"])
        write_md(v1_path, frontmatter, body)
        log_print(f"[generate] ✓ 已写: {v1_path}")
        # original.md 副本(H1 / H2 / §15.8)—— 不可变,顶层
        write_md(original_path, frontmatter, body, immutable=True)
        log_print(f"[generate] ✓ 已写: {original_path}(immutable)")

        return v1_path

    raise RuntimeError(
        f"generate 重试 {max_retries} 次后仍失败: {last_error}"
    )


def _postprocess_generate_output(data: Any) -> dict:
    """清理 + 标准化 LLM 输出。

    Raises:
        ValueError: 结构不合法
    """
    if not isinstance(data, dict):
        raise ValueError(f"输出顶层不是 dict（实际 {type(data).__name__}）")
    for k in ("name", "test_universe", "frontmatter", "strategy_narrative"):
        if k not in data:
            raise ValueError(f"输出缺字段 {k!r}")
    if not isinstance(data["frontmatter"], dict):
        raise ValueError("frontmatter 不是 dict")
    if not isinstance(data["strategy_narrative"], str):
        raise ValueError("strategy_narrative 不是 string")
    return data


def _build_final_frontmatter(fm: dict, name: str, test_universe: list) -> dict:
    """构造最终 .md frontmatter（含元信息 + test_universe 顶层）。"""
    out = dict(fm)
    out["test_universe"] = test_universe
    # 元信息（如未提供则补默认）
    out.setdefault("description", f"LLM 生成策略: {name}")
    out.setdefault("universe", _universe_to_text(test_universe))
    out.setdefault("holding_period", "中周期波段（2 周 – 2 个月）")
    out.setdefault("rebalance_freq", "每 5 个交易日")
    return out


def _universe_to_text(test_universe: list[str]) -> str:
    """test_universe list → 中文本。"""
    mapping = {
        "HS300": "沪深 300",
        "CSI1000": "中证 1000",
        "CYB_STAR_50": "科创 50 + 创业板 50",
    }
    return " + ".join(mapping.get(u, u) for u in test_universe)


__all__ = ["run_generate"]
