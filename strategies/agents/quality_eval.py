"""
src.agents.quality_eval — 业务质量评估（仅模式 1 使用）

来源 prompt: src/agents/prompts/quality_eval.md
评估 6 维: business_goal_alignment / target_consistency / bull_bear_adaptability /
        parameter_tunability / logical_self_consistency / data_implementability(hard gate)

工作流（strategies.md §9.1 / K2）:
  1) 调 LLM（独立调用，system=quality_eval.md）
  2) 解析评估 JSON
  3) 判定 hard gate:
     - data_implementability.score < 6 → passed=false
     - 任一软指标 score == 0 → passed=false
  4) 返回结果（不重试——失败直接反馈给 generate 重生成整篇）

入参: frontmatter dict + body str + 可选 LLMSettings
出参: dict 形如 {passed, hard_evaluation, soft_evaluation, summary, hard_pass_recommendation}
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
    parse_strategy_json,
)
from strategies.agents.log_utils import log_print  # noqa: E402
from strategies.config import LLMSettings, get_llm_settings  # noqa: E402


def _build_user_prompt(frontmatter: dict, body: str) -> str:
    """构造 quality_eval 的 user_prompt（含被评估的策略）。"""
    import json

    return f"""## 待评估策略

### Frontmatter
```json
{json.dumps(frontmatter, ensure_ascii=False, indent=2)}
```

### Strategy Narrative
```
{body}
```

请按 system prompt 中的 6 维评估体系打分,严格用 JSON 输出（用 ```json 代码块）。
"""


# 6 个评估维度(LLM 评分 0-10)
_EVAL_DIMS = (
    "business_goal_alignment",
    "target_consistency",
    "bull_bear_adaptability",
    "parameter_tunability",
    "logical_self_consistency",
    "data_implementability",
)
_MAX_SCORE_PER_DIM = 10
_TOTAL_MAX = len(_EVAL_DIMS) * _MAX_SCORE_PER_DIM  # 60
_PASS_THRESHOLD = 0.85  # 85% (用户决策 2026-06-08 调整,从 90% 改为 85%)


def _judge_hard_gates(eval_result: dict) -> dict:
    """根据 soft_evaluation 6 维总分判定通过。

    规则(用户决策 2026-06-08):
      通过条件 = 6 维总分 >= 51/60(85%)
      不通过 → passed=false(并标注实际得分/满分)
    """
    soft = eval_result.get("soft_evaluation", {})

    # 汇总总分(夹在 [0, 10] 区间,缺失维度按 0 计)
    total = 0
    dim_scores: dict[str, float] = {}
    for dim in _EVAL_DIMS:
        content = soft.get(dim, {})
        if not isinstance(content, dict):
            dim_scores[dim] = 0.0
            continue
        s = content.get("score", 0)
        try:
            s = float(s)
        except (TypeError, ValueError):
            s = 0
        # 夹到 [0, 10]
        s = max(0.0, min(_MAX_SCORE_PER_DIM, s))
        dim_scores[dim] = s
        total += s

    ratio = total / _TOTAL_MAX
    passed = ratio >= _PASS_THRESHOLD

    eval_result["passed"] = passed
    eval_result["hard_pass_recommendation"] = "pass" if passed else "fail"
    eval_result["_quality_total"] = total
    eval_result["_quality_total_max"] = _TOTAL_MAX
    eval_result["_quality_ratio"] = ratio

    # 打印 6 维分数明细
    log_print("[quality_eval] 6 维评分明细:")
    for dim, s in dim_scores.items():
        bar = "█" * int(s) + "░" * (10 - int(s))
        status = "✓" if s >= 6 else "✗"
        log_print(f"[quality_eval]   {status} {dim:30s} {s:5.1f}/10  {bar}")
    log_print(
        f"[quality_eval] 总分: {total:5.1f}/{_TOTAL_MAX}  "
        f"({ratio*100:5.1f}%) {'≥' if passed else '<'} 85% 阈值  →  "
        f"{'PASS ✓' if passed else 'FAIL ✗'}"
    )

    # 在 summary 末尾追加分数信息,便于上层反馈给 LLM
    suffix = (
        f"\n\n[quality_eval 阈值] 总分 {total:.1f}/{_TOTAL_MAX} "
        f"= {ratio * 100:.1f}%{' ≥' if passed else ' <'} 85% 阈值"
        f" → {'pass' if passed else 'fail'}"
    )
    eval_result["summary"] = (eval_result.get("summary", "") + suffix).strip()

    return eval_result


def run_quality_eval(
    frontmatter: dict,
    body: str,
    *,
    settings: LLMSettings | None = None,
) -> dict:
    """调 LLM 评估已生成的策略（仅模式 1 调用）。

    Args:
        frontmatter: 解析后的 frontmatter dict
        body: strategy_narrative 字符串
        settings: 复用 LLM 设置（generate 模式传入同一 LLM 实例）

    Returns:
        dict 形如:
        {
          "passed": bool,
          "hard_evaluation": {...},
          "soft_evaluation": {
            "business_goal_alignment": {"score": N, "issues": [...]},
            ...
          },
          "summary": str,
          "hard_pass_recommendation": "pass" | "pass_with_warnings" | "fail",
        }
    """
    log_print("[quality_eval] → 准备评估(6 维: business_goal_alignment, target_consistency, "
              "bull_bear_adaptability, parameter_tunability, logical_self_consistency, data_implementability)")
    if settings is None:
        settings = get_llm_settings(temperature=0.2, enable_thinking=False)
    llm = build_llm(settings)
    system_prompt = load_prompt("quality_eval")
    user_prompt = _build_user_prompt(frontmatter, body)
    log_print(f"[quality_eval] system prompt: {len(system_prompt)} 字符, user prompt: {len(user_prompt)} 字符")
    log_print("[quality_eval] → 调 LLM 评估(独立调用, think=False)...")

    # 1 次过——不重试
    try:
        response = llm.invoke(system_prompt, user_prompt)
        log_print("[quality_eval] → 解析评估 JSON...")
        result = parse_strategy_json(response)
    except Exception as e:
        # 解析/调用失败 → 视为硬失败
        log_print(f"[quality_eval] ✗ LLM 调用/解析失败: {type(e).__name__}: {e}")
        return {
            "passed": False,
            "hard_evaluation": {"error": f"{type(e).__name__}: {e}"},
            "soft_evaluation": {},
            "summary": f"quality_eval LLM 调用/解析失败: {e}",
            "hard_pass_recommendation": "fail",
        }
    log_print("[quality_eval] ✓ 评估 JSON 解析成功")

    # 兜底字段
    result.setdefault("passed", False)
    result.setdefault("hard_evaluation", {})
    result.setdefault("soft_evaluation", {})
    result.setdefault("summary", "")
    result.setdefault("hard_pass_recommendation", "fail")

    # 6 维 soft_evaluation 兜底
    for dim in _EVAL_DIMS:
        result["soft_evaluation"].setdefault(dim, {"score": 0, "issues": []})

    # hard gate 判定
    return _judge_hard_gates(result)


__all__ = ["run_quality_eval"]
