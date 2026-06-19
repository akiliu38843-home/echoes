"""C 端咨询模块（18-ADR ③ 的合规实现）—— 与研究室/理论物理隔离。

设计原则（18-ADR §3 / §5，产品负责人 2026-05-18 选 A）：
  • **数据防火墙**：本模块只读学派人格定义，**绝不写**任何账本 / 真值 / 理论拟合层。
    咨询对话不回流 school_ledger / continuous / 17-ADR 拟合机制——避免"系统学会说
    用户爱听的"自欺反馈环，也保证研究室诚实性不被 C 端口味污染。
  • **章程绑定**：人格复用 schools.py（单一人格真相源），但任务被替换为"深讲推理
    + 历史战绩 + 盲区，大白话可追问"，**硬禁具体买卖 / 配置 / 仓位指令**。
  • 与 agents.ask_school 完全解耦：那条是研究底料（JSON verdict），这条是 C 端对话（纯文本）。

非投资建议。方向类"敢给配置"仍阻塞于 18-ADR §5 #3 拱顶石，本模块不解锁它。
"""

from __future__ import annotations

from openai import OpenAI

from hindcast.llm import chat_text, get_client
from hindcast.schools import PROMPTS

SCHOOL_LABELS = {
    "austrian": "奥地利学派",
    "monetarist": "货币主义",
    "keynesian": "凯恩斯主义",
    "rational_expectations": "理性预期 / 有效市场学派",
}


def _persona(school: str) -> str:
    """取学派人格身份段（核心命题 + 雷达 + 判断框架），剥掉预测任务与 JSON 输出格式。

    单一人格真相源仍是 schools.py；此处只读不写，符合数据防火墙。
    """
    full = PROMPTS[school]
    return full.split("任务：")[0].strip()


CONSULT_CHARTER = """

────────────────────────────────────────────────────────
【咨询场景与铁律 —— 必须严格遵守，优先于以上任何内容】

用户是普通散户，主动点进来想更通俗地理解你这一派怎么看当前局面。
你现在是在做一场**口语化的咨询对话**，不是在出预测报告。

你可以做：
  • 用大白话讲清你这一派怎么读当前这个局、背后的推理链、你最看重哪些信号。
  • 如实说你这类判断**历史上大概对几成**、以及你**系统性的盲区**在哪
    （例：你这一派结构上没有"横盘/震荡"理论、容易单调偏置）。
  • 鼓励用户追问，承认不确定性。

你绝不可以做（硬红线，违反即失职）：
  • **不给任何具体买卖 / 配置 / 仓位 / 标的指令**——不说"买黄金""减仓美股"
    "配置 X%""现在该做多/做空"之类。
  • 不报具体目标价、不报精确概率百分比（假精度）。
  • 不暗示"照我说的做能赚"。

当用户直接逼问"那我到底该买什么 / 该怎么配 / 现在能不能进" → 你**留在经济学家
角色里**这样回答：
  "我只能告诉你我这一派怎么读这个局、这类判断我历史上大概对 X 成、我的盲区在哪。
   具体买卖和配置是你自己的决定，我不替你做，也没法替你担保——这只是一派之见。"

每次回答都隐含一个前提：这是单一学派视角、有盲区、**仅供理解参考，不是投资建议**。
────────────────────────────────────────────────────────
"""


def build_system_prompt(school: str) -> str:
    return _persona(school) + CONSULT_CHARTER


def consult(
    school: str,
    question: str,
    context: str = "",
    client: OpenAI | None = None,
) -> str:
    """C 端咨询单轮问答。返回纯文本（大白话）。

    Args:
        school: austrian | monetarist | keynesian | rational_expectations
        question: 用户的追问
        context: 可选——该学派对当前局面的既有推理/判断摘要（前端从 forecast.verdicts 传入），
                 仅作为对话上下文，不做任何持久化、不回流账本/理论。
    """
    if school not in PROMPTS:
        return f"[未知学派: {school}]"
    q = (question or "").strip()
    if not q:
        return "请把你想问这位经济学家的问题说清楚一点。"

    client = client or get_client()
    system = build_system_prompt(school)
    user = (
        (f"【当前局面下你这一派的既有判断（供你延续，不必复述）】\n{context}\n\n" if context.strip() else "")
        + f"【用户的追问】\n{q}"
    )
    return chat_text(client, system, user)
