"""第 5 派 · 制度政治经济学派分析 (政治简报)。

与 agents.ask_school 平行但 **不返回 Verdict**——它的产出是给 4 经济派当
可选参考资料用的, 不参与多数投票。

设计原则 (见 schools.INSTITUTIONAL_PE_PROMPT):
- 不出方向 / 幅度 / 置信度
- 跑在 4 经济派之前
- 输出文本被 predict.py 注入到 state.political_brief_section, 再喂给 4 经济派
"""

from __future__ import annotations

from openai import OpenAI

from hindcast.disciplines import get_lens
from hindcast.llm import chat_json
from hindcast.state import StructuralState

# v0.5.7 refactor: prompt 文本 + metadata 走 registry 单一真相源.
# 旧 SCHOOL_ID / SCHOOL_LABEL_ZH / SCHOOL_LABEL_EN 常量保留 (向后兼容
# build_then_vs_now.py 等老消费者), 但内部转 lens metadata.
_LENS = get_lens("institutional_pe", discipline="politics")
assert _LENS is not None, "institutional_pe lens 未注册; 检查 disciplines/politics.py 是否正确"

SCHOOL_ID = _LENS.id
SCHOOL_LABEL_ZH = _LENS.label_zh
SCHOOL_LABEL_EN = _LENS.label_en
_PROMPT = _LENS.prompt


def _is_degenerate_empty(raw: dict) -> bool:
    """LLM 偶发抖动会返回 not-failed 但所有字段都空的"非诚实空响应"。

    判定: 既无 key_events 又无 ongoing_structural 又无 reasoning —— 这种情况
    几乎一定是 LLM bug 而不是政治学派真的"没看见任何东西"(因为它至少能写
    reasoning 说"信息不足")。诊断: 实测 1971-08-12 第一跑触发此模式, 重跑即正常。
    """
    return (
        not (raw.get("key_events") or [])
        and not (raw.get("ongoing_structural") or [])
        and not (raw.get("reasoning") or "").strip()
    )


def get_political_brief(
    state: StructuralState,
    client: OpenAI,
    max_retries: int = 2,
) -> dict:
    """跑制度政治派, 返回 dict (含 key_events / ongoing_structural / reasoning / what_could_be_wrong)。

    重试逻辑: chat_json _failed 重试 + degenerate empty 重试, 最多 max_retries 次。
    最终失败时返回 {"_failed": True, "_error": ...}——上游 (predict.py) 应当
    把"无政治简报"视为正常状态, 4 经济派像现在一样独立跑, 不要因此失败。
    """
    user_prompt = state.format_for_prompt()
    last_error = "no_attempt"

    for attempt in range(max_retries + 1):
        raw = chat_json(client, _PROMPT, user_prompt)
        if raw.get("_failed"):
            last_error = raw.get("_error", "unknown")
            continue
        if _is_degenerate_empty(raw):
            last_error = "degenerate_empty_response"
            continue
        # 正常: 字段缺失全部用空 default
        return {
            "school": raw.get("school", SCHOOL_ID),
            "as_of": raw.get("as_of", state.as_of),
            "key_events": raw.get("key_events", []),
            "ongoing_structural": raw.get("ongoing_structural", []),
            "reasoning": raw.get("reasoning", ""),
            "what_could_be_wrong": raw.get("what_could_be_wrong", ""),
        }

    return {
        "_failed": True,
        "_error": last_error,
        "school": SCHOOL_ID,
        "as_of": state.as_of,
    }


def format_brief_for_economists(brief: dict) -> str:
    """把政治简报渲染成喂给 4 经济派 prompt 的 markdown 片段。

    前缀明示 "可参考可忽略", 防止经济派变复读机。
    """
    if brief.get("_failed"):
        return ""

    lines = [
        "",
        "---",
        "## 🌍 政治分析师简报 (制度政治经济学派 · 独立分析)",
        "",
        "> 以下为政治学派独立分析, **仅供参考**——你 (经济学派) 可以采纳, ",
        "> 可以忽略, 可以反驳。政治派不出经济方向, 只看政治事实+制度含义。",
        "",
    ]

    events = brief.get("key_events") or []
    if events:
        lines.append("### 关键事件")
        for e in events:
            ev = e.get("event", "")
            shift = e.get("institutional_shift", "")
            rev = e.get("reversibility", "")
            ch = e.get("transmission_channels") or []
            lines.append(f"- **{ev}**")
            if shift:
                lines.append(f"  · 制度变化: {shift}")
            if rev:
                lines.append(f"  · 可逆性: {rev}")
            if ch:
                lines.append(f"  · 经济传导通道 (仅列举): {' / '.join(ch)}")
        lines.append("")

    ongoing = brief.get("ongoing_structural") or []
    if ongoing:
        lines.append("### 持续制度状态")
        for o in ongoing:
            lines.append(f"- {o}")
        lines.append("")

    reasoning = brief.get("reasoning", "")
    if reasoning:
        lines.append("### 政治派整体判读")
        lines.append(reasoning)
        lines.append("")

    wcbw = brief.get("what_could_be_wrong", "")
    if wcbw:
        lines.append(f"### 政治派自查")
        lines.append(f"> {wcbw}")
        lines.append("")

    lines.append("---")
    lines.append("")
    return "\n".join(lines)
