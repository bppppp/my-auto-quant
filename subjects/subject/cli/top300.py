"""
subjects.subject.cli.top300 - Top300 Test Set Selector

Usage:
      python -m subject.cli.main run-top300 --strategy <name> --rounds 3
"""
from __future__ import annotations
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

# ===== 预过滤: 仅保留主板/创业板/科创板, 排除退市股和现在 ST 股 =====
# 60 = 上证主板, 00 = 深证主板/中小板, 30 = 深证创业板, 688 = 上证科创板
# 不含 8/4 开头 (北交所), 不含 4/9 开头 (老三板退市整理)
_ALLOWED_CODE_PREFIXES: tuple[str, ...] = ("60", "00", "30", "688")

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
      sys.path.insert(0, str(_PROJECT_ROOT))

from strategies.agents.base_agent import (
      build_llm, check_g1_param_count, check_g2_param_immutable,
      next_version, original_md_path, parse_strategy_json, read_md,
      strategy_dir_for, validate_md_structure, write_md,
)
from strategies.agents.log_utils import banner, log_print, section
from strategies.config import get_llm_settings
from subject.backtest.runner import BacktestRunner


@dataclass
class RoundResult:
      round_no: int
      params_version: str
      top300: list[dict]
      avg_annual_return: float
      total_stocks_tested: int
      backtest_summary: dict


@dataclass
class Top300FinalResult:
      best_round: int
      best_avg_return: float
      top300_codes: list[str]
      rounds_results: list[RoundResult] = field(default_factory=list)


def run_top300_optimize(
      name: str,
      *,
      rounds: int = 3,
      max_retries: int = 3,
      start_date: str | None = None,
      end_date: str | None = None,
      limit: int | None = None,
) -> Top300FinalResult | None:
      banner(f"Top300 selector | name={name}, rounds={rounds}")

      # 打印配置信息
      log_print("=" * 60)
      log_print(f"[top300] 配置参数:")
      log_print(f"       rounds: {rounds}")
      log_print(f"       max_retries: {max_retries}")
      log_print(f"       start_date: {start_date or '默认5年'}")
      log_print(f"       end_date: {end_date or '数据末日'}")
      log_print(f"       limit: {limit or '不限'}")
      log_print("=" * 60)

      original_path = original_md_path(name)
      if not original_path.exists():
          log_print(f"[top300] Error: original not found: {original_path}")
          return None

      log_print(f"[top300] Step 1/5: 读取原始快照")
      log_print(f"       文件: {original_path}")
      original_fm, original_body = read_md(original_path)
      log_print(f"       params数量: {len(original_fm.get('params', []))}")

      v1_path = strategy_dir_for(name, track="main") / f"{name}_v1.md"
      if not v1_path.exists():
          log_print(f"[top300] Step 2/5: 初始化 v1")
          log_print(f"       创建: {v1_path}")
          write_md(v1_path, dict(original_fm), original_body)
      else:
          log_print(f"[top300] Step 2/5: v1 已存在")

      rounds_results = []
      latest_path = v1_path
      latest_fm = original_fm

      for round_no in range(1, rounds + 1):
          log_print("")
          log_print("=" * 60)
          log_print(f"[top300] ========== 第 {round_no}/{rounds} 轮 ==========")
          log_print("=" * 60)

          # 打印该轮参数
          log_print(f"[top300] Step 3/5: 当前参数版本")
          log_print(f"       文件: {latest_path.name}")
          params = {p["name"]: p["default"] for p in latest_fm.get("params", [])}
          log_print(f"       参数: {params}")

          # 获取全部股票
          log_print(f"[top300] Step 4/5: 准备回测")
          all_codes = BacktestRunner.get_all_stock_codes()
          total_all = len(all_codes)

          # 预过滤: 排除退市股 / 现在 ST 股 / 非主板创业板科创板代码
          log_print(f"       预过滤: 退市/ST/非主板/创业板/科创板...")
          all_codes, filter_stats = _filter_eligible_codes(all_codes)
          log_print(
              f"       预过滤完成: 总 {filter_stats['total']} → 保留 {filter_stats['kept']} 只"
              f"  (前缀剔除 {filter_stats['filtered_prefix']},"
              f"  退市剔除 {filter_stats['filtered_delisted']},"
              f"  ST 剔除 {filter_stats['filtered_st']},"
              f"  缺失 {filter_stats['filtered_missing']})"
          )

          # 如果指定了 limit，只取前 limit 只股票进行回测
          if limit:
              all_codes = all_codes[:limit]

          log_print(f"       总股票数: {total_all} -> 实际测试: {len(all_codes)}")
          log_print(f"       时间范围: {start_date or '默认'} ~ {end_date or '默认'}")

          # subjects_dir 必须是项目根目录下的 subjects/ (不是策略目录)
          subjects_dir = _PROJECT_ROOT / "subjects"

          runner = BacktestRunner(
              strategy_name=name,
              mode="params",
              start_date=start_date,
              end_date=end_date,
              subjects_dir=subjects_dir,
          )
          runner.params = params
          runner.spec = latest_fm

          log_print(f"[top300] 开始回测...")
          log_print(f"       回测中请耐心等待...")

          all_summaries = runner.backtest_all_stocks_summary(all_codes=all_codes)
          total_tested = len(all_summaries)

          log_print(f"[top300] 回测完成!")
          log_print(f"       实际测试: {total_tested} 只")

          # Top300 结果
          log_print("")
          log_print(f"[top300] ========== Top300 结果 ==========")
          top300_list = all_summaries[:300]
          top300_codes = [s.code for s in top300_list]
          top_n = len(top300_list)
          avg_return = sum(s.annual_return for s in top300_list) / top_n if top_n else 0.0
          log_print(f"       平均年化收益率 (top {top_n}): {avg_return:+.2%}")
          log_print(f"       Top10股票:")
          for i, s in enumerate(top300_list[:10], 1):
              log_print(f"         {i}. {s.code} ({s.name}): {s.annual_return:+.2%}")

          round_result = RoundResult(
              round_no=round_no, params_version=f"v{round_no}",
              top300=[{"code": s.code, "name": s.name, "annual_return": s.annual_return} for s in top300_list],
              avg_annual_return=avg_return, total_stocks_tested=total_tested,
              backtest_summary={"avg_return": avg_return, "total_tested": total_tested, "top300": top300_codes},
          )
          rounds_results.append(round_result)

          if round_no < rounds:
              log_print("")
              log_print(f"[top300] Step 5/5: LLM 调优参数")
              new_path = _optimize_once(name=name, latest_path=latest_path, latest_fm=latest_fm,
latest_body=original_body, max_retries=max_retries)
              if new_path is None:
                  log_print(f"[top300] 警告: Round {round_no} LLM 调优失败，跳过")
                  continue
              latest_path = new_path
              latest_fm, _ = read_md(new_path)
              log_print(f"[top300] 调优完成: {new_path.name}")

      log_print("")
      log_print("=" * 60)
      log_print("[top300] ========== 最终决策 ==========")
      best = max(rounds_results, key=lambda r: r.avg_annual_return)
      log_print(f"       最优轮次: Round {best.round_no}")
      log_print(f"       平均年化收益率: {best.avg_annual_return:+.2%}")
      log_print("=" * 60)

      final_result = Top300FinalResult(
          best_round=best.round_no, best_avg_return=best.avg_annual_return,
          top300_codes=[item["code"] for item in best.top300], rounds_results=rounds_results,
      )

      out_dir = _PROJECT_ROOT / "subjects" / name / "test_universe"
      out_dir.mkdir(parents=True, exist_ok=True)
      out_path = out_dir / "top300.md"
      _write_top300_md(out_path, name, final_result)
      log_print(f"[top300] 已写入: {out_path}")

      return final_result


def _optimize_once(name, latest_path, latest_fm, latest_body, max_retries=3) -> Path | None:
      import json
      latest_params = latest_fm.get("params", [])
      parts = [
          "## Strategy to optimize\n",
          f"File: {latest_path.name}\n",
          "```yaml\n",
          json.dumps(latest_fm, ensure_ascii=False, indent=2),
          "```\n\n## Task\nOutput optimized params:\n- name/type/description from latest\n- default/range can change\n",
      ]
      user_prompt = "\n".join(parts)
      settings = get_llm_settings(temperature=0.3, enable_thinking=True)
      llm = build_llm(settings)
      system_prompt = _load_optimize_prompt()
      feedback_md = ""
      new_params = None

      for attempt in range(1, max_retries + 1):
          log_print(f"[top300.optimize] attempt {attempt}/{max_retries}")
          full_user = user_prompt + ("\n\n" + feedback_md if feedback_md else "")
          try:
              response = llm.invoke(system_prompt, full_user)
          except Exception as e:
              log_print(f"[top300.optimize] LLM failed: {e}")
              feedback_md = f"## LLM failed\n{e}"
              continue
          try:
              data = parse_strategy_json(response)
          except Exception as e:
              log_print(f"[top300.optimize] JSON failed: {e}")
              feedback_md = f"## JSON failed\n{e}"
              continue
          if not isinstance(data, dict) or "params" not in data:
              feedback_md = "## Missing params"
              continue
          new_params_raw = data["params"]
          if not isinstance(new_params_raw, list):
              feedback_md = "## params must be list"
              continue
          g1_errs = check_g1_param_count(new_params_raw, latest_params)
          latest_names = {p.get("name") for p in latest_params}
          new_params_filtered = [p for p in new_params_raw if p.get("name") in latest_names]
          order = {n: i for i, n in enumerate(latest_names)}
          new_params_filtered.sort(key=lambda p: order.get(p.get("name"), 999))
          g2_errs = check_g2_param_immutable(new_params_filtered, latest_params)
          merged_fm = dict(latest_fm)
          merged_fm["params"] = new_params_filtered
          struct_errs = validate_md_structure(merged_fm, latest_body, mode="optimize")
          if g1_errs or g2_errs or struct_errs:
              log_print(f"[top300.optimize] Validation failed")
              feedback_md = "## Validation failed"
              continue
          new_params = new_params_filtered
          break

      if new_params is None:
          log_print(f"[top300.optimize] Failed after {max_retries} retries")
          return None

      next_v = next_version(name, track="main")
      new_fm = dict(latest_fm)
      new_fm["params"] = new_params
      new_path = strategy_dir_for(name, track="main") / f"{name}_v{next_v}.md"
      write_md(new_path, new_fm, latest_body)
      log_print(f"[top300.optimize] Written: {new_path.name}")
      return new_path


def _filter_eligible_codes(codes: list[str]) -> tuple[list[str], dict[str, int]]:
    """预过滤股票代码: 仅保留主板/创业板/科创板, 排除退市股和现在 ST 股.

    过滤规则 (按顺序短路):
      1. 6 位代码前缀必须以 60 / 00 / 30 / 688 开头
      2. 最新一行的 退市时间 必须为空或 "-"
      3. 最新一行的 是否ST 必须为 "否"

    Returns:
        (filtered_codes, stats) - stats 含 4 个计数键
    """
    import pandas as pd
    from subject.backtest.data_loader import STOCK_DIR, STOCK_FILE_SUFFIX

    stats = {
        "total": len(codes),
        "kept": 0,
        "filtered_prefix": 0,
        "filtered_delisted": 0,
        "filtered_st": 0,
        "filtered_missing": 0,
    }
    kept: list[str] = []
    stock_dir = STOCK_DIR

    for code in codes:
        code6 = code.split(".")[0]
        # 规则 1: 前缀
        if not any(code6.startswith(p) for p in _ALLOWED_CODE_PREFIXES):
            stats["filtered_prefix"] += 1
            continue
        # 规则 2/3: 读最新一行检查退市 & ST
        f = stock_dir / f"{code6}{STOCK_FILE_SUFFIX}"
        if not f.exists():
            stats["filtered_missing"] += 1
            continue
        try:
            df = pd.read_csv(f, usecols=["是否ST", "退市时间"], encoding="utf-8", low_memory=False)
        except Exception:
            stats["filtered_missing"] += 1
            continue
        if len(df) == 0:
            stats["filtered_missing"] += 1
            continue
        last = df.iloc[-1]
        delist_val = str(last.get("退市时间", "")).strip()
        if delist_val and delist_val not in ("-", "nan", "NaN", "None"):
            stats["filtered_delisted"] += 1
            continue
        if str(last.get("是否ST", "")).strip() == "是":
            stats["filtered_st"] += 1
            continue
        kept.append(code)

    stats["kept"] = len(kept)
    return kept, stats


def _load_optimize_prompt() -> str:
      path = _PROJECT_ROOT / "strategies" / "agents" / "prompts" / "optimize.md"
      if path.exists():
          return path.read_text(encoding="utf-8")
      return (
          "You are a parameter optimization expert. Output params only. "
          "name/type/description cannot change, default/range can change. "
          'Format: ```json {"params": [...]} ```'
      )


def _write_top300_md(path, strategy_name, result):
      try:
          import yaml
          has_yaml = True
      except ImportError:
          has_yaml = False

      rounds_summary = [
          {
              "round": r.round_no,
              "params_version": r.params_version,
              "avg_annual_return": f"{r.avg_annual_return:+.2%}",
              "total_stocks_tested": r.total_stocks_tested,
          }
          for r in result.rounds_results
      ]
      frontmatter = {
          "strategy": strategy_name,
          "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
          "best_round": result.best_round,
          "best_avg_return": f"{result.best_avg_return:+.2%}",
          "rounds_summary": rounds_summary,
      }
      body_lines = [
          "# Top 300 Stocks by Annual Return\n",
          f"*Source: Round {result.best_round} ({result.best_avg_return:+.2%})*\n",
      ]
      for code in result.top300_codes:
          body_lines.append(f"- {code}")

      if has_yaml:
          fm_str = yaml.safe_dump(frontmatter, allow_unicode=True, sort_keys=False, default_flow_style=False)
      else:
          fm_str = _simple_yaml_dump(frontmatter)

      header = f"---\n{fm_str}---\n\n"
      path.write_text(header + "\n".join(body_lines), encoding="utf-8")


def _simple_yaml_dump(obj, indent=0):
      out = []
      pad = "  " * indent
      for k, v in obj.items():
          if isinstance(v, dict):
              out.append(f"{pad}{k}:")
              out.append(_simple_yaml_dump(v, indent + 1))
          elif isinstance(v, list):
              if not v:
                  out.append(f"{pad}{k}: []")
              else:
                  out.append(f"{pad}{k}:")
                  for item in v:
                      if isinstance(item, dict):
                          inline = ", ".join(f'"{k2}": {v2}' for k2, v2 in item.items())
                          out.append(f"{pad}  - {{{inline}}}")
                      else:
                          out.append(f"{pad}  - {item}")
          else:
              out.append(f"{pad}{k}: {v}")
      return "\n".join(out) + "\n"


# ====================================================================
# 测试集读取工具 (供 params/weight 模式默认使用)
# ====================================================================
def load_top300_codes(strategy_name: str) -> list[str] | None:
      """从 test_universe/top300.md 读取 Top300 股票代码列表.

      Args:
          strategy_name: 策略目录名 (如 "ma_cross_atr_volume")

      Returns:
          股票代码列表 (如 ["000001.SZ", "600000.SH", ...])，
          文件不存在时返回 None
      """
      top300_path = _PROJECT_ROOT / "subjects" / strategy_name / "test_universe" / "top300.md"
      if not top300_path.exists():
          log_print(f"[top300] {top300_path} 不存在，使用默认测试集")
          return None

      try:
          fm, body = read_md(top300_path)
          # 从 body 中解析股票代码 (格式: "-000001.SZ")
          codes = []
          for line in body.split("\n"):
              line = line.strip()
              if line.startswith("- "):
                  code = line[2:].strip()
                  if code:
                      codes.append(code)
          log_print(f"[top300] 从 {top300_path} 读取到 {len(codes)} 只股票")
          return codes if codes else None
      except Exception as e:
          log_print(f"[top300] 读取 {top300_path} 失败: {e}")
          return None


def get_test_universe(strategy_name: str) -> list[str]:
      """获取策略的测试集股票代码列表.

      优先级:
      1. test_universe/top300.md 存在 → 读取其中的股票列表
      2. 否则 → fallback 到 HS300

      Args:
          strategy_name: 策略目录名

      Returns:
          股票代码列表

      Raises:
          如果策略目录不存在且 top300.md 不存在，fallback 到 HS300
      """
      # 检查策略目录是否存在
      strategy_dir = _PROJECT_ROOT / "subjects" / strategy_name
      if not strategy_dir.exists():
          log_print(f"[top300] 策略目录 {strategy_dir} 不存在，使用默认测试集 HS300")
          from subject.backtest.universe import HS300_CODES
          return HS300_CODES

      # 尝试从 top300.md 读取
      codes = load_top300_codes(strategy_name)
      if codes:
          return codes

      # fallback 到 HS300
      from subject.backtest.universe import HS300_CODES
      log_print(f"[top300] 使用默认测试集 HS300 ({len(HS300_CODES)} 只)")
      return HS300_CODES


__all__ = [
      "run_top300_optimize",
      "Top300FinalResult",
      "RoundResult",
      "load_top300_codes",
      "get_test_universe",
]