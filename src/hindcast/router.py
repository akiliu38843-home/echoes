"""Router LLM: 历史之后, 决定后续学科组合 (22-ADR §2.4).

位置: 历史层完成后 → 看事件 + 历史 2 立场输出 → 挑后续学科子集.
不排顺序 (顺序由 chain.py 按 LAYER_ORDER 固定).
成本: ~$0.01/次 (小模型快速路由).

降级策略: router 调用失败时, 选所有已注册可选学科 (保守兜底).
"""
from __future__ import annotations

import json

from openai import OpenAI

from hindcast.disciplines import all_disciplines
from hindcast.llm import chat_json
from hindcast.narrative_types import LensOutput, NarrativeEvent, RouterOutput

# 这些学科不需要 router 决定 (由 chain 系统管理)
_SYSTEM_MANAGED = {"history", "central_brain"}

_ROUTER_SYSTEM = """\
你是叙事模拟器的路由器 (Router).

你的工作: 根据事件类型 + 历史学派的初步 framing, 从"可选学科池"挑出后续最相关的学科.

规则:
- economics (经济学) 是默认开的. 只在事件跟经济/金融完全无关时才豁免 (极少发生).
- 其它学科: 按事件类型挑 2-4 个最相关的.
- 不用选 history 或 central_brain (系统自动处理).

选择参考:
- 地缘冲突/战争/外交/大国博弈/关税/制裁/技术管制 → politics + intl_relations (国际关系) 选
- 跨国权力格局/霸权竞争/同盟/相互依赖 → intl_relations 选
- 法律/监管/司法 → law 如注册了必选; politics 大概率
- 民意/社会运动/代际 → sociology 选
- 技术/AI/平台监管 → sociology + politics + law
- 金融/货币政策 → politics 选; sociology 可能
- 自然灾害/气候 → sociology 可能
- 文化/身份/宗教 → sociology + 可能 anthropology

输出严格 JSON:
{
  "selected": ["politics"],
  "exempted_from_default": [],
  "reasoning": "<2 句: 为什么选这组>"
}

只输出 JSON, 不要任何额外文字.
"""


def route(
    event: NarrativeEvent,
    history_outputs: list[LensOutput],
    client: OpenAI,
) -> RouterOutput:
    """Router LLM: 历史完成后决定后续学科组合.

    Args:
        event: 事件输入
        history_outputs: 历史层已完成的 lens 输出
        client: OpenAI client

    Returns:
        RouterOutput (含 selected_disciplines + exempted_default + reasoning)
    """
    optional_pool = [d for d in all_disciplines() if d not in _SYSTEM_MANAGED]

    history_text_parts = []
    for out in history_outputs:
        if not out.failed:
            history_text_parts.append(
                f"### {out.label_zh} ({out.lens_id})\n"
                + json.dumps(out.raw, ensure_ascii=False, indent=2)
            )
    history_text = "\n\n".join(history_text_parts) or "(历史层无输出)"

    user_prompt = (
        f"## 事件\n\n{event.text}\n\n(as_of: {event.as_of})\n\n"
        f"## 历史学派分析\n\n{history_text}\n\n"
        f"## 可选学科池\n\n{json.dumps(optional_pool, ensure_ascii=False)}\n\n"
        "请选择后续学科子集（JSON）。"
    )

    raw = chat_json(client, _ROUTER_SYSTEM, user_prompt, max_tokens=300)

    if raw.get("_failed"):
        return RouterOutput(
            selected_disciplines=optional_pool,
            exempted_default=[],
            reasoning="router_failed_fallback_all",
            raw=raw,
        )

    registered = set(all_disciplines())
    selected_raw = raw.get("selected", optional_pool)
    selected = [d for d in selected_raw if d in registered and d not in _SYSTEM_MANAGED]

    return RouterOutput(
        selected_disciplines=selected,
        exempted_default=raw.get("exempted_from_default", []),
        reasoning=raw.get("reasoning", ""),
        raw=raw,
    )
