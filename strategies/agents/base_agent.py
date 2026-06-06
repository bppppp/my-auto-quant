"""
strategies.agents.base_agent — 共享工具（Shared Tools for All Modes）

所有模式（generate / optimize / factor_weights / quality_eval）的共用函数：
  - 路径工具（project_root / subject_dir / strategy_dir / reports_dir / original_md_path）
  - .md 读写（read_md / write_md）—— frontmatter 与 body 分离
  - 报告查找（find_all_reports）—— F2 分配（最新完整 + 其它精简）
  - LLM 构建（build_llm）—— 注入 system_prompt，调用 chat
  - JSON 解析（parse_strategy_json）—— 兼容 think 块、```json code block
  - 硬校验（validate_md_structure）—— 22 硬 + 1 软（按模式分类）
  - 提示加载（load_prompt）—— 从 strategies/agents/prompts/*.md 读取 system message
  - 自动起名校验（validate_auto_name）—— snake_case ≤ 64 字符

新文件结构（subjects/<name>/ 下）:
  ├── <name>_original.md                # 顶层，immutable
  ├── strategiesParam/<name>_v<N>.md    # 模式 1 / 模式 2
  ├── strategiesWeight/<name>_weight_v<N>.md   # 模式 3
  ├── reportParams/report_v*.md         # 模式 2 监听
  └── reportWeight/report_signals_v*.md # 模式 3 监听

所有"硬规则"集中在本文件:
  - G1（param 数量 1:1）/ G2（param 不可改字段前后对比）/ G3（signal/factors 锁死）
  - 22 硬校验 + 1 软（按 mode 取子集）
  - param.description ≥ 30 字符（B4）/ targets.annual_return > 0.20（O1）

参考 strategies.md §11 文件结构 + §8.4 硬校验表 + §13 实现要点。
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

# 让根目录 + strategies 包 import 生效
# strategies/agents/base_agent.py → 3 层:my-quant3/
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from strategies.agents.log_utils import log_overwrite, log_print  # noqa: E402
from strategies.config import LLMSettings, get_llm_settings  # noqa: E402


# ====================================================================
# 路径工具
# ====================================================================
def project_root() -> Path:
    """项目根目录 `D:/project/quant/my-quant3/`。"""
    return _PROJECT_ROOT


def subject_dir() -> Path:
    """策略实例目录 `subjects/`(复数)。"""
    return _PROJECT_ROOT / "subjects"


def _track_subdir(track: str) -> str:
    """track → 子目录名。

    Args:
        track: "main" → "strategiesParam"(模式 1/2 写/读)
              "signals" → "strategiesWeight"(模式 3 写/读)
    """
    if track == "main":
        return "strategiesParam"
    if track == "signals":
        return "strategiesWeight"
    raise ValueError(f"未知 track {track!r}（应为 'main' 或 'signals'）")


def _mode_subdir(mode: str) -> str:
    """mode → 报告子目录名。

    Args:
        mode: "params" → "reportParams"(模式 2 报告)
              "weights" → "reportWeight"(模式 3 报告)
    """
    if mode == "params":
        return "reportParams"
    if mode == "weights":
        return "reportWeight"
    raise ValueError(f"未知 mode {mode!r}（应为 'params' 或 'weights'）")


def strategy_dir_for(name: str, *, track: str = "main") -> Path:
    """单个策略的目录 `subjects/<name>/strategiesParam|strategiesWeight/`(自动创建)。

    Args:
        name: 策略名
        track: "main"(模式 1/2) → strategiesParam | "signals"(模式 3) → strategiesWeight
    """
    p = subject_dir() / name / _track_subdir(track)
    p.mkdir(parents=True, exist_ok=True)
    return p


def reports_dir_for(name: str, *, mode: str = "params") -> Path:
    """单个策略的报告目录 `subjects/<name>/reportParams|reportWeight/`(自动创建)。

    Args:
        name: 策略名
        mode: "params" → reportParams(模式 2 报告) | "weights" → reportWeight(模式 3 报告)
    """
    p = subject_dir() / name / _mode_subdir(mode)
    p.mkdir(parents=True, exist_ok=True)
    return p


def backtest_dir_for(name: str) -> Path:
    """单个策略的回测目录 `subjects/<name>/backtest/`(自动创建)。"""
    p = subject_dir() / name / "backtest"
    p.mkdir(parents=True, exist_ok=True)
    return p


def original_md_path(name: str) -> Path:
    """原始快照路径 `subjects/<name>/<name>_original.md`(顶层,不自动创建)。"""
    return subject_dir() / name / f"{name}_original.md"


def strategy_root(name: str) -> Path:
    """单个策略的根目录 `subjects/<name>/`(自动创建)。"""
    p = subject_dir() / name
    p.mkdir(parents=True, exist_ok=True)
    return p


# ====================================================================
# .md 读写（frontmatter + body 分离）
# ====================================================================
_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", re.DOTALL)


def read_md(path: Path) -> tuple[dict, str]:
    """读 .md 文件，拆成 (frontmatter_dict, body_str)。

    失败: 文件不存在 → FileNotFoundError;YAML 解析失败 → ValueError。
    """
    if not path.exists():
        raise FileNotFoundError(f".md 文件不存在: {path}")

    text = path.read_text(encoding="utf-8")
    m = _FRONTMATTER_RE.match(text)
    if not m:
        raise ValueError(f".md 缺少 frontmatter (---...---): {path}")

    fm_text, body = m.group(1), m.group(2)
    try:
        # 使用 PyYAML；fallback 到 json（兼容将 list/dict 写在同一行的写法）
        import yaml  # type: ignore

        frontmatter = yaml.safe_load(fm_text)
        if not isinstance(frontmatter, dict):
            raise ValueError(f"frontmatter 不是 dict: {path}")
    except ImportError:
        # 退化：手动解析
        frontmatter = _simple_yaml_parse(fm_text)
    return frontmatter, body


def write_md(
    path: Path,
    frontmatter: dict,
    body: str,
    *,
    immutable: bool = False,
) -> None:
    """写 .md 文件（frontmatter + body）。

    Args:
        path: 目标路径
        frontmatter: dict 形式的 frontmatter
        body: 策略 narrative 字符串
        immutable: True 时保护 *_original.md 不被覆盖（H3 + §15.8 三层防护）
    """
    if immutable and path.exists() and path.name.endswith("_original.md"):
        raise RuntimeError(
            f"原始快照不可覆盖: {path}。"
            f"如需重启请用 --from-original flag 显式引用。"
        )

    # 优先用 PyYAML 序列化
    try:
        import yaml  # type: ignore

        fm_str = yaml.safe_dump(
            frontmatter,
            allow_unicode=True,
            sort_keys=False,
            default_flow_style=False,
        )
    except ImportError:
        fm_str = _simple_yaml_dump(frontmatter)

    # 头部 + 元信息注释（如有）
    header = f"---\n{fm_str}---\n\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(header + body, encoding="utf-8")


# 简化 YAML（无 PyYAML 时 fallback；只支持本项目实际用到的结构）
def _simple_yaml_parse(text: str) -> dict:
    """超简 YAML 解析——支持 key: value / key: [a, b] / - { ... } 列表项。"""
    out: dict = {}
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip() or line.strip().startswith("#"):
            i += 1
            continue
        # 顶层 key
        if line.startswith("  ") or line.startswith("\t") or line.startswith("-"):
            i += 1
            continue
        m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*:\s*(.*)$", line)
        if not m:
            i += 1
            continue
        key, value = m.group(1), m.group(2).strip()
        if value == "":
            # 嵌套 list/dict
            nested: list | dict = []
            is_list = True
            j = i + 1
            while j < len(lines):
                sub = lines[j]
                if not sub.strip():
                    j += 1
                    continue
                if sub.startswith("  ") or sub.startswith("\t"):
                    if is_list:
                        if sub.lstrip().startswith("- "):
                            item_text = sub.lstrip()[2:].strip()
                            if item_text.startswith("{") and item_text.endswith("}"):
                                nested.append(_inline_dict(item_text))
                            else:
                                nested.append(item_text)
                    j += 1
                else:
                    break
            out[key] = nested
            i = j
        else:
            if value.startswith("[") and value.endswith("]"):
                inner = value[1:-1].strip()
                out[key] = [x.strip().strip('"').strip("'") for x in inner.split(",") if x.strip()]
            elif value.startswith('"') and value.endswith('"'):
                out[key] = value[1:-1]
            elif value.startswith("'") and value.endswith("'"):
                out[key] = value[1:-1]
            elif value.lower() in ("true", "false"):
                out[key] = value.lower() == "true"
            else:
                try:
                    out[key] = float(value) if "." in value else int(value)
                except ValueError:
                    out[key] = value
            i += 1
    return out


def _inline_dict(text: str) -> dict:
    """解析 inline 形式 `{"name": ..., "x": y}`  → dict。"""
    text = text.strip().rstrip(",")
    if not (text.startswith("{") and text.endswith("}")):
        return {"_raw": text}
    body = text[1:-1].strip()
    out: dict = {}
    # 用栈式 split（简化版，仅支持一层）
    parts: list[str] = []
    buf = ""
    in_str = False
    quote_char = ""
    depth = 0
    for ch in body:
        if in_str:
            buf += ch
            if ch == quote_char:
                in_str = False
        elif ch in ('"', "'"):
            in_str = True
            quote_char = ch
            buf += ch
        elif ch in "[{(":
            depth += 1
            buf += ch
        elif ch in "]})":
            depth -= 1
            buf += ch
        elif ch == "," and depth == 0:
            parts.append(buf.strip())
            buf = ""
        else:
            buf += ch
    if buf.strip():
        parts.append(buf.strip())
    for p in parts:
        if ":" not in p:
            continue
        k, _, v = p.partition(":")
        out[k.strip().strip('"').strip("'")] = _parse_scalar(v.strip())
    return out


def _parse_scalar(v: str) -> Any:
    """解析 inline 字典中的标量值。"""
    v = v.strip()
    if v.startswith("[") and v.endswith("]"):
        inner = v[1:-1].strip()
        if not inner:
            return []
        return [_parse_scalar(x.strip()) for x in inner.split(",")]
    if v.startswith('"') and v.endswith('"'):
        return v[1:-1]
    if v.startswith("'") and v.endswith("'"):
        return v[1:-1]
    if v.lower() in ("true", "false"):
        return v.lower() == "true"
    if v == "" or v == "null" or v == "~":
        return None
    try:
        return float(v) if "." in v else int(v)
    except ValueError:
        return v


def _simple_yaml_dump(obj: dict, indent: int = 0) -> str:
    """超简 YAML 序列化（fallback）。"""
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
                        inline = ", ".join(
                            f'"{_yaml_escape(str(k2))}": {_yaml_value(v2)}'
                            for k2, v2 in item.items()
                        )
                        out.append(f"{pad}  - {{{inline}}}")
                    else:
                        out.append(f"{pad}  - {_yaml_value(item)}")
        else:
            out.append(f"{pad}{k}: {_yaml_value(v)}")
    return "\n".join(out) + "\n"


def _yaml_escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


def _yaml_value(v: Any) -> str:
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, list):
        return "[" + ", ".join(_yaml_value(x) for x in v) + "]"
    s = str(v)
    if "\n" in s:
        return "|\n" + "\n".join("    " + line for line in s.splitlines())
    return f'"{_yaml_escape(s)}"'


# ====================================================================
# 报告查找（F2 分配）
# ====================================================================
def find_all_reports(
    name: str,
    *,
    mode: str = "params",
    glob_pattern: str | None = None,
    limit: int = 5,
) -> list[Path]:
    """找最近 N 份报告,按 _v(\\d+) 数字倒序(最新 → 最旧)。

    Args:
        name: 策略名
        mode: "params" → reportParams/(模式 2 报告)
              "weights" → reportWeight/(模式 3 报告)
        glob_pattern: 自定义 glob(默认根据 mode 选)
        limit: 最多 N 份(默认 5)
    """
    if glob_pattern is None:
        glob_pattern = "report_signals_v*.md" if mode == "weights" else "report_v*.md"
    reports_dir = reports_dir_for(name, mode=mode)
    if not reports_dir.exists():
        return []

    files = list(reports_dir.glob(glob_pattern))
    files.sort(key=lambda p: _version_of(p.name), reverse=True)
    return files[:limit]


def _version_of(filename: str) -> int:
    """从文件名提取 _v(\\d+) 数字,找不到返回 -1。"""
    m = re.search(r"_v(\d+)", filename)
    return int(m.group(1)) if m else -1


def get_reports_for_tuning(
    name: str,
    *,
    mode: str = "params",
    glob_pattern: str | None = None,
    max_reports: int = 5,
) -> str:
    """生成给 LLM 看的报告拼装文本(F2 分配:最新完整 + 其它精简)。

    Args:
        name: 策略名
        mode: "params" → reportParams/(模式 2)
              "weights" → reportWeight/(模式 3)
        glob_pattern: 自定义 glob(默认根据 mode 选)
        max_reports: 最多参考 N 份

    Returns:
        拼装好的 markdown 文本,无报告时返回 ""。
    """
    reports = find_all_reports(name, mode=mode, glob_pattern=glob_pattern, limit=max_reports)
    if not reports:
        return ""

    text_parts: list[str] = []
    for i, r in enumerate(reports):
        content = r.read_text(encoding="utf-8")
        if i == 0:
            text_parts.append(f"## {r.name}\n{content}")
        else:
            trimmed = extract_sections(content, sections=["§0", "§1", "§2"])
            text_parts.append(f"## {r.name}(精简)\n{trimmed}")
    return "\n\n".join(text_parts)


def extract_sections(text: str, *, sections: list[str]) -> str:
    """按 §0/§1/§2 章节名截取报告内容（其它段丢弃）。"""
    keep: list[str] = []
    for sec in sections:
        m = re.search(rf"^{re.escape(sec)}\b.*?(?=^§\d+\s|\Z)", text, re.MULTILINE | re.DOTALL)
        if m:
            keep.append(m.group(0).rstrip())
    return "\n\n".join(keep) if keep else text


# ====================================================================
# 提示加载
# ====================================================================
def load_prompt(name: str) -> str:
    """从 src/agents/prompts/{name}.md 加载 system prompt。

    Args:
        name: generate / optimize / factor_weights / quality_eval
    """
    path = Path(__file__).resolve().parent / "prompts" / f"{name}.md"
    if not path.exists():
        raise FileNotFoundError(f"prompt 文件不存在: {path}")
    return path.read_text(encoding="utf-8")


# ====================================================================
# LLM 构建 + 调用
# ====================================================================
def build_llm(settings: LLMSettings | None = None) -> Any:
    """构造 LLM 客户端。

    优先用 OpenAI 兼容 SDK；fallback 到 langchain。
    不实际发起网络请求，仅返回配置好的 client。
    """
    if settings is None:
        settings = get_llm_settings()

    try:
        from openai import OpenAI  # type: ignore

        client = OpenAI(
            base_url=settings.base_url,
            api_key=settings.api_key,
            timeout=settings.timeout,
            # 关键:openai SDK v1+ 默认 max_retries=2,会做指数退避重试。
            # LLM_TIMEOUT=1200 时,3 次 × 1200s = 3600s(=1 小时)才超时,
            # 与日志里的 1h+ 卡死完全吻合。关掉重试,单次失败即返回。
            max_retries=int(os.getenv("LLM_MAX_RETRIES", "0")),
        )
        return _OpenAIChat(client=client, model=settings.model, settings=settings)
    except ImportError:
        pass

    try:
        from langchain_openai import ChatOpenAI  # type: ignore

        return ChatOpenAI(
            base_url=settings.base_url,
            api_key=settings.api_key,
            model=settings.model,
            temperature=settings.temperature,
            max_tokens=settings.max_tokens,
            timeout=settings.timeout,
        )
    except ImportError:
        pass

    raise RuntimeError(
        "未安装 openai 或 langchain-openai。pip install openai（或 langchain-openai）"
    )


@dataclass
class _OpenAIChat:
    """轻量 OpenAI 兼容 chat 封装。"""

    client: Any
    model: str
    settings: LLMSettings

    def invoke(self, system_prompt: str, user_prompt: str) -> str:
        """调 LLM，返回文本结果。"""
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": self.settings.temperature,
            "max_tokens": self.settings.max_tokens,
            "timeout": self.settings.timeout,
        }
        # thinking 字段放在 extra_body(OpenAI SDK 顶层不识别)
        #   - DeepSeek V4:  {"thinking": {"type": "enabled" | "disabled"}}
        #                   + {"reasoning_effort": "low"|"medium"|"high"|"max"}
        #   - MiniMax:      {"thinking": {"type": "adaptive" | "disabled"}}
        #                   (用 "enabled" 会被 API 拒 400,且不支持 reasoning_effort)
        # 切换 provider 只改 .env,不改代码:
        #   DeepSeek  →  LLM_THINKING_TYPE=enabled  LLM_REASONING_EFFORT=high
        #   MiniMax    →  LLM_THINKING_TYPE=adaptive LLM_REASONING_EFFORT=  (留空)
        extra_body = kwargs.setdefault("extra_body", {})
        think_on_type = self.settings.thinking_type or "enabled"
        think_off_type = "disabled"
        extra_body["thinking"] = (
            {"type": think_on_type} if self.settings.enable_thinking else {"type": think_off_type}
        )
        # reasoning_effort 仅在非空时传(MiniMax 不支持)
        if self.settings.reasoning_effort:
            extra_body["reasoning_effort"] = self.settings.reasoning_effort

        sys_p_len = len(system_prompt)
        usr_p_len = len(user_prompt)
        log_print(
            f"[LLM] → 调用开始 | model={self.model} | "
            f"temperature={self.settings.temperature} | max_tokens={self.settings.max_tokens} | "
            f"think={self.settings.enable_thinking} (type={think_on_type if self.settings.enable_thinking else think_off_type}) | "
            f"reasoning_effort={self.settings.reasoning_effort or '(none)'} | "
            f"system_prompt={sys_p_len} 字符, user_prompt={usr_p_len} 字符"
        )
        log_print("[LLM] ⏳ 等待 LLM 返回(可能需要数十秒到几分钟)...", end="")
        t0 = time.perf_counter()
        try:
            resp = self.client.chat.completions.create(**kwargs)
        except Exception:
            log_print("")  # 换行收尾
            raise
        elapsed = time.perf_counter() - t0
        content = resp.choices[0].message.content or ""
        # stdout 覆盖上一行"⏳ 等待...";log 文件独立成行
        log_overwrite(
            f"[LLM] ✓ 返回完成 | 耗时 {elapsed:.1f}s | "
            f"输出 {len(content)} 字符 | "
            f"首 80 字: {content[:80]!r}{'...' if len(content) > 80 else ''}"
        )
        return content



# ====================================================================
# JSON 解析（兼容 think 块 + ```json```）
# ====================================================================
_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)
_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```", re.DOTALL)


def parse_strategy_json(text: str) -> dict | list:
    """从 LLM 输出中提取 JSON 对象。

    策略:
      1. 先剥掉 <think>...</think> 块
      2. 找 ```json``` 代码块
      3. 退化: 找第一个 { ... } 平衡块
      4. 退化: 整段 json.loads
    """
    # 1. 剥 think
    cleaned = _THINK_RE.sub("", text)
    # 2. 找 ```json``` 块
    m = _JSON_BLOCK_RE.search(cleaned)
    if m:
        candidate = m.group(1)
    else:
        # 3. 找平衡的 { ... } / [ ... ]
        candidate = _extract_balanced(cleaned)
    if not candidate:
        candidate = cleaned.strip()

    # 4. parse
    try:
        return json.loads(candidate)
    except json.JSONDecodeError as e:
        raise ValueError(f"LLM 输出无法解析为 JSON: {e}\n\n原始文本:\n{text[:2000]}")


def _extract_balanced(text: str) -> str:
    """提取第一个括号平衡的 JSON 块。"""
    for opener, closer in [("{", "}"), ("[", "]")]:
        start = text.find(opener)
        if start < 0:
            continue
        depth = 0
        in_str = False
        quote = ""
        for i in range(start, len(text)):
            ch = text[i]
            if in_str:
                if ch == "\\":
                    continue
                if ch == quote:
                    in_str = False
                continue
            if ch in ('"', "'"):
                in_str = True
                quote = ch
                continue
            if ch == opener:
                depth += 1
            elif ch == closer:
                depth -= 1
                if depth == 0:
                    return text[start : i + 1]
    return ""


# ====================================================================
# 自动起名校验（B4 / §10.1）
# ====================================================================
_AUTO_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


def validate_auto_name(name: str) -> str:
    """校验自动生成名：snake_case，字母开头，≤ 64 字符，无版本后缀。

    Raises:
        ValueError: 不合法时
    """
    if not name:
        raise ValueError("策略名不能为空")
    if not _AUTO_NAME_RE.match(name):
        raise ValueError(
            f"策略名 {name!r} 不合法：必须 snake_case（字母开头，仅含 [a-z0-9_]），≤ 64 字符"
        )
    if re.search(r"_v\d+$", name):
        raise ValueError(f"策略名 {name!r} 含版本号后缀（_v1）——系统自动加，请去除")
    return name


def next_version(
    name: str,
    *,
    track: Literal["main", "signals"] = "main",
) -> int:
    """计算下一个版本号。

    track="main":   数 subjects/<name>/strategiesParam/<name>_v<N>.md 的最大 N
    track="signals": 数 subjects/<name>/strategiesWeight/<name>_weight_v<N>.md 的最大 N

    Returns:
        下一个可用版本号(从 1 开始)
    """
    sdir = strategy_dir_for(name, track=track)
    if track == "main":
        pattern = re.compile(rf"^{re.escape(name)}_v(\d+)\.md$")
    else:
        pattern = re.compile(rf"^{re.escape(name)}_weight_v(\d+)\.md$")

    existing = [int(m.group(1)) for f in sdir.iterdir() if (m := pattern.match(f.name))]
    return max(existing, default=0) + 1


def find_latest_md(
    name: str,
    *,
    track: Literal["main", "signals"] = "main",
    fallback_to_original: bool = True,
) -> Path | None:
    """找最大版本号的 .md(默认 fallback 到顶层 <name>_original.md)。

    track="main":   在 subjects/<name>/strategiesParam/ 下找 <name>_v<N>.md
    track="signals": 在 subjects/<name>/strategiesWeight/ 下找 <name>_weight_v<N>.md
                     (找不到时不 fallback,直接返回 None——模式 3 硬规则)

    Returns:
        Path 或 None(不存在时)
    """
    sdir = strategy_dir_for(name, track=track) if sdir_check(name, track) else None
    if sdir is None or not sdir.exists():
        if track == "signals" or not fallback_to_original:
            return None
        return original_md_path(name) if original_md_path(name).exists() else None

    if track == "main":
        pattern = re.compile(rf"^{re.escape(name)}_v(\d+)\.md$")
    else:
        pattern = re.compile(rf"^{re.escape(name)}_weight_v(\d+)\.md$")

    candidates: list[tuple[int, Path]] = []
    for f in sdir.iterdir():
        m = pattern.match(f.name)
        if m:
            candidates.append((int(m.group(1)), f))
    if not candidates:
        if track == "signals" or not fallback_to_original:
            return None
        # main track 退化到顶层 original.md
        op = original_md_path(name)
        return op if op.exists() else None
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]


def sdir_check(name: str, track: str) -> bool:
    """检查 <name> 目录下是否有 _track_subdir(track) 子目录(用于避免 mkdir 副作用)。"""
    p = subject_dir() / name / _track_subdir(track)
    return p.exists()


# ====================================================================
# 硬校验（validate_md_structure）
# ====================================================================
# 校验项定义（按 §8.4 分组 A-F + 模式 2/3 专属子集）
@dataclass
class ValidationError:
    """硬校验失败的描述。"""

    code: str  # "#21" / "G1" / "G2-name" / 等
    message: str
    field: str | None = None

    def __str__(self) -> str:
        if self.field:
            return f"[{self.code}] {self.message} (field={self.field})"
        return f"[{self.code}] {self.message}"


def validate_md_structure(
    frontmatter: dict,
    body: str,
    *,
    mode: Literal["generate", "optimize", "factor_weights"],
) -> list[ValidationError]:
    """按模式分类硬校验（§8.4）。

    Args:
        frontmatter: 解析后的 dict
        body: strategy_narrative 字符串（mode 2/3 可忽略）
        mode: generate / optimize / factor_weights

    Returns:
        ValidationError 列表（空 = 通过）
    """
    errors: list[ValidationError] = []

    if mode == "generate":
        errors.extend(_check_generate(frontmatter, body))
    elif mode == "optimize":
        errors.extend(_check_optimize(frontmatter, body))
    elif mode == "factor_weights":
        errors.extend(_check_factor_weights(frontmatter, body))

    return errors


# ---------- 模式 1 (generate) 全跑 22 硬 + 1 软 ----------
def _check_generate(fm: dict, body: str) -> list[ValidationError]:
    errs: list[ValidationError] = []
    # A. 基础结构（#1-#3, #9）
    if not isinstance(fm, dict):
        errs.append(ValidationError("#1", "frontmatter 不是 dict"))

    # #2 targets 5 项
    targets = fm.get("targets", {})
    if not isinstance(targets, dict):
        errs.append(ValidationError("#2", "targets 缺失或不是 dict", "targets"))
    else:
        for key in ("annual_return", "win_rate", "profit_loss_ratio", "sharpe", "max_drawdown"):
            if key not in targets:
                errs.append(ValidationError("#2", f"targets.{key} 缺失", f"targets.{key}"))
            elif not isinstance(targets[key], (int, float)):
                errs.append(ValidationError("#2", f"targets.{key} 不是数值", f"targets.{key}"))

    # #3 test_universe（3 选 1+，与 data/config.py 对齐）
    tu = fm.get("test_universe", [])
    valid_uni = {"HS300", "CSI1000", "CYB_STAR_50"}
    if not isinstance(tu, list) or not (1 <= len(tu) <= 3):
        errs.append(ValidationError("#3", "test_universe 必须是 1~3 元素 list", "test_universe"))
    else:
        for u in tu:
            if u not in valid_uni:
                errs.append(
                    ValidationError(
                        "#3",
                        f"test_universe 含非法值 {u!r}（仅允许 HS300 / CSI1000 / CYB_STAR_50）",
                        "test_universe",
                    )
                )

    # #9 position_weights
    pw = fm.get("position_weights", {})
    if not isinstance(pw, dict) or len(pw) < 1:
        errs.append(ValidationError("#9", "position_weights 至少 1 字段", "position_weights"))

    # B. signals 结构 + 权重
    # #4 factors 非空
    factors = fm.get("factors", [])
    factor_names = {f.get("name") for f in factors if isinstance(f, dict) and f.get("name")}
    if not factors:
        errs.append(ValidationError("#4", "factors 列表为空", "factors"))

    # #5/#6 entry_signals / exit_signals
    for sig_key, code in (("entry_signals", "#5"), ("exit_signals", "#6")):
        sigs = fm.get(sig_key, [])
        if not sigs:
            errs.append(ValidationError(code, f"{sig_key} 列表为空", sig_key))
        for i, sig in enumerate(sigs):
            if not isinstance(sig, dict):
                errs.append(ValidationError(code, f"{sig_key}[{i}] 不是 dict", sig_key))
                continue
            for f in ("name", "weight", "factors", "direction", "trigger", "logic"):
                if f not in sig:
                    errs.append(
                        ValidationError(code, f"{sig_key}[{i}] 缺字段 {f!r}", f"{sig_key}[{i}].{f}")
                    )

    # #7 signals[].factors 引用合法（不引用 param 名；引用的因子在 factors 列表中）
    param_names = {p.get("name") for p in fm.get("params", []) if isinstance(p, dict)}
    for sig_key in ("entry_signals", "exit_signals"):
        for i, sig in enumerate(fm.get(sig_key, [])):
            if not isinstance(sig, dict):
                continue
            for fname in sig.get("factors") or []:
                if fname in param_names:
                    errs.append(
                        ValidationError(
                            "#7",
                            f"{sig_key}[{i}].factors 引用了 param 名 {fname!r}",
                            f"{sig_key}[{i}].factors",
                        )
                    )
                elif fname not in factor_names:
                    errs.append(
                        ValidationError(
                            "#7",
                            f"{sig_key}[{i}].factors 引用了未声明因子 {fname!r}",
                            f"{sig_key}[{i}].factors",
                        )
                    )

    # #8 weight 是非负数值
    for sig_key in ("entry_signals", "exit_signals"):
        for i, sig in enumerate(fm.get(sig_key, [])):
            if not isinstance(sig, dict):
                continue
            w = sig.get("weight")
            if not isinstance(w, (int, float)) or w < 0:
                errs.append(
                    ValidationError(
                        "#8",
                        f"{sig_key}[{i}].weight 必须是 ≥ 0 数值（实际 {w!r}）",
                        f"{sig_key}[{i}].weight",
                    )
                )

    # C. params
    # #10 params 非空
    params = fm.get("params", [])
    if not params:
        errs.append(ValidationError("#10", "params 列表为空", "params"))

    # #11 range 是 2 元素 [min, max]
    for i, p in enumerate(params):
        if not isinstance(p, dict):
            continue
        rng = p.get("range")
        if not (isinstance(rng, list) and len(rng) == 2):
            errs.append(
                ValidationError(
                    "#11",
                    f"params[{i}].range 必须是 2 元素 [min, max]（实际 {rng!r}）",
                    f"params[{i}].range",
                )
            )

    # #12 default in range (软检查)
    for i, p in enumerate(params):
        if not isinstance(p, dict):
            continue
        rng = p.get("range")
        dft = p.get("default")
        if isinstance(rng, list) and len(rng) == 2 and isinstance(dft, (int, float)):
            mn, mx = min(rng), max(rng)
            if not (mn <= dft <= mx):
                errs.append(
                    ValidationError(
                        "#12-soft",
                        f"params[{i}].default={dft} 超出 range={rng}（软检查）",
                        f"params[{i}].default",
                    )
                )

    # #13 description ≥ 30 字符
    for i, p in enumerate(params):
        if not isinstance(p, dict):
            continue
        desc = (p.get("description") or "").strip()
        if len(desc) < 30:
            errs.append(
                ValidationError(
                    "#13",
                    f"params[{i}].description 长度 < 30 字符（实际 {len(desc)}）",
                    f"params[{i}].description",
                )
            )

    # D. strategy_narrative
    # #14 body 存在 + 字符数 ≥ 1500
    if not body or len(body.strip()) < 1500:
        errs.append(
            ValidationError(
                "#14",
                f"strategy_narrative 字符数 < 1500（实际 {len(body.strip() if body else '')}）",
                "strategy_narrative",
            )
        )

    # #15 含 6 节
    if body:
        for sec in ("### 1.", "### 2.", "### 3.", "### 4.", "### 5.", "### 6."):
            if sec not in body:
                errs.append(
                    ValidationError(
                        "#15",
                        f"strategy_narrative 缺节 {sec!r}",
                        "strategy_narrative",
                    )
                )

    # E. 信号引用一致性 + 因子完整性
    # #16 signals[].factors 引用必须作为独立 token 出现在 trigger
    for sig_key in ("entry_signals", "exit_signals"):
        for i, sig in enumerate(fm.get(sig_key, [])):
            if not isinstance(sig, dict):
                continue
            factors_list = sig.get("factors") or []
            trigger = sig.get("trigger") or ""
            for fname in factors_list:
                if not _is_token_in(fname, trigger):
                    errs.append(
                        ValidationError(
                            "#16",
                            f"{sig_key}[{i}].factors 引用 {fname!r} 未在 trigger 中独立出现",
                            f"{sig_key}[{i}].trigger",
                        )
                    )

    # #18 position_weights 字段必须在 params 列表里能找到
    pw_keys = set((fm.get("position_weights") or {}).keys())
    for k in pw_keys:
        if k not in param_names:
            errs.append(
                ValidationError(
                    "#18",
                    f"position_weights.{k} 在 params 列表里找不到同名 param",
                    f"position_weights.{k}",
                )
            )

    # #19 param 语义单义（narrative 引用 param 应符合 description 语义——本检查仅做粗略长度/格式）
    # 完整版需 LLM 软判断；这里只检查 {param_name} 引用语法合法性
    if body:
        for m in re.finditer(r"\{([A-Za-z_][A-Za-z0-9_]*)\}", body):
            ref = m.group(1)
            if ref not in param_names:
                errs.append(
                    ValidationError(
                        "#19",
                        f"strategy_narrative 引用了未声明的 param {{{ref}}}",
                        "strategy_narrative",
                    )
                )

    # #20 factors 列表里的每个因子必须被至少一个 signal 的 trigger 引用
    used_factors: set[str] = set()
    for sig_key in ("entry_signals", "exit_signals"):
        for sig in fm.get(sig_key, []):
            if not isinstance(sig, dict):
                continue
            trigger = sig.get("trigger") or ""
            for fname in factor_names:
                if fname and _is_token_in(fname, trigger):
                    used_factors.add(fname)
    for fname in factor_names:
        if fname and fname not in used_factors:
            errs.append(
                ValidationError(
                    "#20",
                    f"factor {fname!r} 未被任何 signal 的 trigger 引用（孤立因子）",
                    f"factors.{fname}",
                )
            )

    # #23 trigger 公式中除数学常量（0,1,100,1000）外无其他硬编码数字
    for sig_key in ("entry_signals", "exit_signals"):
        for i, sig in enumerate(fm.get(sig_key, [])):
            if not isinstance(sig, dict):
                continue
            trigger = sig.get("trigger") or ""
            hardcoded = _find_hardcoded_numbers(trigger)
            if hardcoded:
                errs.append(
                    ValidationError(
                        "#23",
                        f"{sig_key}[{i}].trigger 含硬编码数字 {hardcoded}（除 0,1,100,1000 外必须 param 化）",
                        f"{sig_key}[{i}].trigger",
                    )
                )

    # #24 每个因子必含 3 字段
    for i, f in enumerate(fm.get("factors", [])):
        if not isinstance(f, dict):
            continue
        for k in ("name", "description", "calculation"):
            v = f.get(k)
            if not v or (isinstance(v, str) and not v.strip()):
                errs.append(
                    ValidationError(
                        "#24",
                        f"factors[{i}].{k} 为空",
                        f"factors[{i}].{k}",
                    )
                )

    # F. 收益门槛
    # #21 annual_return > 0.20
    ar = targets.get("annual_return") if isinstance(targets, dict) else None
    if isinstance(ar, (int, float)) and not (ar > 0.20):
        errs.append(
            ValidationError(
                "#21",
                f"targets.annual_return={ar} 不满足 > 0.20 硬规则（O1）",
                "targets.annual_return",
            )
        )

    # #22 annual_return / abs(max_drawdown) ≥ 1.0
    md_val = targets.get("max_drawdown") if isinstance(targets, dict) else None
    if isinstance(ar, (int, float)) and isinstance(md_val, (int, float)) and md_val != 0:
        ratio = ar / abs(md_val)
        if ratio < 1.0:
            errs.append(
                ValidationError(
                    "#22",
                    f"annual_return/abs(max_drawdown)={ratio:.3f} < 1.0（O3 风险预算）",
                    "targets",
                )
            )

    return errs


# ---------- 模式 2 (optimize) 仅 4 项 params 相关 ----------
def _check_optimize(fm: dict, body: str) -> list[ValidationError]:
    errs: list[ValidationError] = []
    params = fm.get("params", [])

    # #10 params 非空
    if not params:
        errs.append(ValidationError("#10", "params 列表为空", "params"))

    # #11 range 是 2 元素
    for i, p in enumerate(params):
        if not isinstance(p, dict):
            continue
        rng = p.get("range")
        if not (isinstance(rng, list) and len(rng) == 2):
            errs.append(
                ValidationError(
                    "#11",
                    f"params[{i}].range 必须是 2 元素 [min, max]（实际 {rng!r}）",
                    f"params[{i}].range",
                )
            )

    # #18 position_weights 字段必须能在 params 列表找到
    param_names = {p.get("name") for p in params if isinstance(p, dict)}
    pw_keys = set((fm.get("position_weights") or {}).keys())
    for k in pw_keys:
        if k not in param_names:
            errs.append(
                ValidationError(
                    "#18",
                    f"position_weights.{k} 在 params 列表里找不到同名 param",
                    f"position_weights.{k}",
                )
            )

    # #19 param 语义单义
    if body:
        for m in re.finditer(r"\{([A-Za-z_][A-Za-z0-9_]*)\}", body):
            ref = m.group(1)
            if ref not in param_names:
                errs.append(
                    ValidationError(
                        "#19",
                        f"strategy_narrative 引用了未声明的 param {{{ref}}}",
                        "strategy_narrative",
                    )
                )

    return errs


# ---------- 模式 3 (factor_weights) 9 项 signals/factors ----------
def _check_factor_weights(fm: dict, body: str) -> list[ValidationError]:
    errs: list[ValidationError] = []
    # #4 factors 非空
    factors = fm.get("factors", [])
    if not factors:
        errs.append(ValidationError("#4", "factors 列表为空", "factors"))
    factor_names = {f.get("name") for f in factors if isinstance(f, dict) and f.get("name")}

    # #5/#6 entry_signals / exit_signals 非空 + 6 字段
    for sig_key, code in (("entry_signals", "#5"), ("exit_signals", "#6")):
        sigs = fm.get(sig_key, [])
        if not sigs:
            errs.append(ValidationError(code, f"{sig_key} 列表为空", sig_key))
        for i, sig in enumerate(sigs):
            if not isinstance(sig, dict):
                errs.append(ValidationError(code, f"{sig_key}[{i}] 不是 dict", sig_key))
                continue
            for f in ("name", "weight", "factors", "direction", "trigger", "logic"):
                if f not in sig:
                    errs.append(
                        ValidationError(code, f"{sig_key}[{i}] 缺字段 {f!r}", f"{sig_key}[{i}].{f}")
                    )

    # #7 signals[].factors 引用合法
    for sig_key in ("entry_signals", "exit_signals"):
        for i, sig in enumerate(fm.get(sig_key, [])):
            if not isinstance(sig, dict):
                continue
            for fname in sig.get("factors") or []:
                if fname not in factor_names:
                    errs.append(
                        ValidationError(
                            "#7",
                            f"{sig_key}[{i}].factors 引用了未声明因子 {fname!r}",
                            f"{sig_key}[{i}].factors",
                        )
                    )

    # #8 weight ≥ 0
    for sig_key in ("entry_signals", "exit_signals"):
        for i, sig in enumerate(fm.get(sig_key, [])):
            if not isinstance(sig, dict):
                continue
            w = sig.get("weight")
            if not isinstance(w, (int, float)) or w < 0:
                errs.append(
                    ValidationError(
                        "#8",
                        f"{sig_key}[{i}].weight 必须是 ≥ 0 数值（实际 {w!r}）",
                        f"{sig_key}[{i}].weight",
                    )
                )

    # #16 signals[].factors 引用必须作为独立 token 出现在 trigger
    for sig_key in ("entry_signals", "exit_signals"):
        for i, sig in enumerate(fm.get(sig_key, [])):
            if not isinstance(sig, dict):
                continue
            factors_list = sig.get("factors") or []
            trigger = sig.get("trigger") or ""
            for fname in factors_list:
                if not _is_token_in(fname, trigger):
                    errs.append(
                        ValidationError(
                            "#16",
                            f"{sig_key}[{i}].factors 引用 {fname!r} 未在 trigger 中独立出现",
                            f"{sig_key}[{i}].trigger",
                        )
                    )

    # #20 factors 列表里的每个因子必须被至少一个 signal 的 trigger 引用
    used_factors: set[str] = set()
    for sig_key in ("entry_signals", "exit_signals"):
        for sig in fm.get(sig_key, []):
            if not isinstance(sig, dict):
                continue
            trigger = sig.get("trigger") or ""
            for fname in factor_names:
                if fname and _is_token_in(fname, trigger):
                    used_factors.add(fname)
    for fname in factor_names:
        if fname and fname not in used_factors:
            errs.append(
                ValidationError(
                    "#20",
                    f"factor {fname!r} 未被任何 signal 的 trigger 引用（孤立因子）",
                    f"factors.{fname}",
                )
            )

    # #23 trigger 公式中除数学常量外无其他硬编码数字
    for sig_key in ("entry_signals", "exit_signals"):
        for i, sig in enumerate(fm.get(sig_key, [])):
            if not isinstance(sig, dict):
                continue
            trigger = sig.get("trigger") or ""
            hardcoded = _find_hardcoded_numbers(trigger)
            if hardcoded:
                errs.append(
                    ValidationError(
                        "#23",
                        f"{sig_key}[{i}].trigger 含硬编码数字 {hardcoded}",
                        f"{sig_key}[{i}].trigger",
                    )
                )

    # #24 每个因子必含 3 字段
    for i, f in enumerate(fm.get("factors", [])):
        if not isinstance(f, dict):
            continue
        for k in ("name", "description", "calculation"):
            v = f.get(k)
            if not v or (isinstance(v, str) and not v.strip()):
                errs.append(
                    ValidationError(
                        "#24",
                        f"factors[{i}].{k} 为空",
                        f"factors[{i}].{k}",
                    )
                )

    return errs


# ====================================================================
# G1 / G2 / G3 锁死检查（合并到本地 merge 后执行）
# ====================================================================
def check_g1_param_count(new_params: list[dict], latest_params: list[dict]) -> list[ValidationError]:
    """G1: param 数量 1:1 覆盖。"""
    errs: list[ValidationError] = []
    latest_names = {p.get("name") for p in latest_params}
    new_names = {p.get("name") for p in new_params}
    missing = latest_names - new_names
    if missing:
        errs.append(
            ValidationError(
                "G1",
                f"params 缺失: {sorted(missing)}（G1 硬规则：必须 1:1 覆盖）",
            )
        )
    # 多给的 param 由调用方在 merge 时丢弃（防 LLM 自由发挥）
    return errs


def check_g2_param_immutable(
    new_params: list[dict], latest_params: list[dict]
) -> list[ValidationError]:
    """G2: param 不可改字段（name / type / description）必须与 latest 完全一致。"""
    errs: list[ValidationError] = []
    latest_by_name = {p.get("name"): p for p in latest_params}
    for new_p in new_params:
        name = new_p.get("name")
        latest = latest_by_name.get(name)
        if not latest:
            continue  # G1 已经报过
        for f in ("name", "type", "description"):
            if new_p.get(f) != latest.get(f):
                errs.append(
                    ValidationError(
                        f"G2-{f}",
                        f"param {name!r} 的 {f} 字段被修改（latest={latest.get(f)!r}, new={new_p.get(f)!r}）",
                        f"params.{name}.{f}",
                    )
                )
    return errs


def check_g3_signals_immutable(
    new_signals: dict[str, list[dict]], latest_signals: dict[str, list[dict]]
) -> list[ValidationError]:
    """G3 信号字段锁死（LLM 侧）：5 字段（name / factors / direction / trigger / logic）+ 数量 1:1。"""
    errs: list[ValidationError] = []
    for sig_key in ("entry_signals", "exit_signals"):
        new_list = new_signals.get(sig_key, [])
        latest_list = latest_signals.get(sig_key, [])
        if len(new_list) != len(latest_list):
            errs.append(
                ValidationError(
                    f"G3-{sig_key}-count",
                    f"{sig_key} 数量变化（latest={len(latest_list)}, new={len(new_list)}）——G3 锁死，不增不删",
                )
            )
            continue
        latest_by_name = {s.get("name"): s for s in latest_list}
        for new_s in new_list:
            name = new_s.get("name")
            latest = latest_by_name.get(name)
            if not latest:
                errs.append(
                    ValidationError(
                        f"G3-{sig_key}-missing",
                        f"{sig_key} 含 latest 没有的 signal {name!r}（G3 数量锁死）",
                    )
                )
                continue
            for f in ("name", "factors", "direction", "trigger", "logic"):
                if new_s.get(f) != latest.get(f):
                    errs.append(
                        ValidationError(
                            f"G3-{f}",
                            f"{sig_key}.{name} 的 {f} 字段被修改（latest={latest.get(f)!r}, new={new_s.get(f)!r}）",
                            f"{sig_key}.{name}.{f}",
                        )
                    )
    return errs


def check_g3_factors_immutable(
    new_factors: list[dict], latest_factors: list[dict]
) -> list[ValidationError]:
    """G3 factors 锁死（代码侧 / 防御性）：factors 列表 3 字段 + 数量 1:1。

    理论上不会失败——factors 由代码从 latest 整体继承。失败 = 代码 bug。
    """
    errs: list[ValidationError] = []
    if len(new_factors) != len(latest_factors):
        errs.append(
            ValidationError(
                "G3-factors-count",
                f"factors 数量变化（latest={len(latest_factors)}, new={len(new_factors)}）——代码 bug",
            )
        )
        return errs
    latest_by_name = {f.get("name"): f for f in latest_factors}
    for new_f in new_factors:
        name = new_f.get("name")
        latest = latest_by_name.get(name)
        if not latest:
            errs.append(
                ValidationError(
                    "G3-factors-missing",
                    f"factors 含 latest 没有的因子 {name!r}（代码 bug）",
                )
            )
            continue
        for f in ("name", "description", "calculation"):
            if new_f.get(f) != latest.get(f):
                errs.append(
                    ValidationError(
                        f"G3-factors-{f}",
                        f"factor {name!r} 的 {f} 字段被修改（latest={latest.get(f)!r}, new={new_f.get(f)!r}）——代码 bug",
                        f"factors.{name}.{f}",
                    )
                )
    return errs


# ====================================================================
# 辅助：token 独立匹配 + 硬编码数字扫描
# ====================================================================
def _is_token_in(token: str, text: str) -> bool:
    """token 是否在 text 中作为独立标识符出现（严格解析，非子串匹配）。

    用单词边界 \\b；对含下划线的 snake_case 也适用。
    """
    if not token or not text:
        return False
    return bool(re.search(rf"\b{re.escape(token)}\b", text))


# 数学常量（白名单）
_MATH_CONSTANTS = {"0", "1", "100", "1000"}


def _find_hardcoded_numbers(trigger: str) -> list[str]:
    """找 trigger 中所有"非数学常量"的硬编码数字（#23）。

    处理:
      - {param_name} → 跳过（合法）
      - 0, 1, 100, 1000 → 跳过（数学常量）
      - 因子名 / 系统变量（snake_case）→ 跳过（不是数字）
      - 单独的纯数字 token → 报告
    """
    if not trigger:
        return []
    bad: list[str] = []
    # 先剥掉所有 {param_name}
    cleaned = re.sub(r"\{[A-Za-z_][A-Za-z0-9_]*\}", "", trigger)
    # 找连续数字 token
    for m in re.finditer(r"\b(\d+(?:\.\d+)?)\b", cleaned):
        n = m.group(1)
        if n not in _MATH_CONSTANTS and n not in ("2",):  # 2 也允许（倍数常用）
            bad.append(n)
    return bad


# ====================================================================
# 列出所有策略
# ====================================================================
def list_all_strategies() -> list[str]:
    """列出 subject/ 下所有策略名（含子目录的 .md 名）。"""
    sd = subject_dir()
    if not sd.exists():
        return []
    return sorted([p.name for p in sd.iterdir() if p.is_dir()])


__all__ = [
    "project_root",
    "subject_dir",
    "strategy_dir_for",
    "reports_dir_for",
    "backtest_dir_for",
    "strategy_root",
    "original_md_path",
    "read_md",
    "write_md",
    "find_all_reports",
    "get_reports_for_tuning",
    "extract_sections",
    "load_prompt",
    "build_llm",
    "parse_strategy_json",
    "validate_auto_name",
    "next_version",
    "find_latest_md",
    "ValidationError",
    "validate_md_structure",
    "check_g1_param_count",
    "check_g2_param_immutable",
    "check_g3_signals_immutable",
    "check_g3_factors_immutable",
    "list_all_strategies",
]
