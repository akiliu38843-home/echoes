"""事件修正辅助链（v0.4 §3.3 / W4 任务）。

输入：
  - 当前结构状态（14/15 变量）
  - 新事件描述（自然语言，如 "USTR 宣布对中国新能源车征收 100% 关税"）

输出：4 学派对常态预测的 delta 修正：
  {
    "T+5":  {"adjust_pct": +0.7, "reason": "..."},
    "T+20": {"adjust_pct": +1.8, "reason": "..."}
  }
  + is_structural_change 标记

集成方式：先跑 predict() 拿常态，再跑 modulate_with_event() 拿修正，
UI 把两路径并列展示。
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Literal, Optional

from openai import OpenAI
from pydantic import BaseModel, Field

from hindcast.llm import chat_json, get_client
from hindcast.schools import PROMPTS
from hindcast.state import SCHOOLS, School, StructuralState


# ─── 在常规学派 prompt 之上叠加事件冲击模式指令 ───
SHOCK_MODE_INSTRUCTION = """

---
**🟧 冲击修正模式（不是从头预测，是修正你已有的常态判断）**

你已经在常态模式下基于结构状态给出过判断。现在出现了新事件：

**事件描述**: <EVENT_TEXT>

## 第一步：先按 ADR-002 给事件分类（不可跳过）

事件 `volatility_class` 分类：
- **exogenous_shock**：事件本身就是逻辑驱动（央行决议 / 政策 / 数据 / 制裁 / 地缘）→ 可用学派叙事算 delta
- **endogenous_technical**：事件本身是市场内生（如"程序化止损被触发"/"VIX 飙升导致 deleveraging"）→ delta 仅用技术面解释，不挂学派
- **stochastic_noise**：事件无实质内容（如"新闻噪声 / 谣言未证实"）→ delta = 0
- **structural_break**：事件描述本身就是"无可归因的大幅异动"→ delta 标记不可用

## 第二步：基于分类给 delta

**Confidence 上限约束**（ADR-002 §5，不可违反）：
- exogenous_shock → ≤ 1.0
- endogenous_technical → ≤ 0.3
- stochastic_noise → ≤ 0.1
- structural_break → ≤ 0.2

**反幻觉硬规则**：
- 若事件分类 != exogenous_shock → adjust_pct 应该接近 0
- 禁止编造 "市场或许正在提前消化" 之类辞令

JSON 必须用以下 schema:
{
  "school": "<your_school>",
  "event_volatility_class": "exogenous_shock | endogenous_technical | stochastic_noise | structural_break",
  "event_attribution_note": "<1 句：你为什么这么分类>",
  "delta_to_steady_state": {
    "T+5":  {"adjust_pct": <float>, "reason": "<1 句；若分类 != exogenous_shock 必须是技术面/反幻觉表述>"},
    "T+20": {"adjust_pct": <float>, "reason": "<1 句>"}
  },
  "is_structural_change": <true|false>,
  "structural_impact_note": "<如果是结构性变化, 说明哪个变量应该更新>",
  "amplifies": ["<被这个事件放大的变量 ID>", ...],
  "confidence": <0.0-1.0，受 event_volatility_class 上限约束>
}

不要输出 JSON 以外的任何文字。
"""


class HorizonDelta(BaseModel):
    adjust_pct: float
    reason: str = ""


EventVolatilityClass = Literal[
    "exogenous_shock", "endogenous_technical", "stochastic_noise", "structural_break"
]


class EventDelta(BaseModel):
    school: School
    delta_to_steady_state: dict[str, HorizonDelta]
    event_volatility_class: EventVolatilityClass = "exogenous_shock"
    event_attribution_note: str = ""
    is_structural_change: bool = False
    structural_impact_note: str = ""
    amplifies: list[str] = Field(default_factory=list)
    confidence: float = 0.0
    _failed: bool = False
    _error: Optional[str] = None


class EventModulation(BaseModel):
    """事件修正全结果——4 学派 delta 合计 + 整合修正方向。"""

    event_text: str
    deltas: list[EventDelta]
    aggregate: dict[str, float]  # horizon → mean adjust_pct（剔除 _failed）
    structural_change_votes: int  # 多少学派认为是结构性变化


def ask_school_event(
    client: OpenAI,
    school: School,
    state: StructuralState,
    event_text: str,
) -> EventDelta:
    """让某个学派对事件出 delta（修正其常态判断）。"""
    system_prompt = PROMPTS[school] + SHOCK_MODE_INSTRUCTION.replace("<EVENT_TEXT>", event_text)
    user_prompt = state.format_for_prompt() + f"\n\n# 新事件\n{event_text}"

    raw = chat_json(client, system_prompt, user_prompt)
    if raw.get("_failed"):
        return EventDelta(
            school=school,
            delta_to_steady_state={
                "T+5": HorizonDelta(adjust_pct=0.0),
                "T+20": HorizonDelta(adjust_pct=0.0),
            },
            _failed=True,
            _error=raw.get("_error"),
        )

    try:
        deltas = {
            h: HorizonDelta(**raw["delta_to_steady_state"][h])
            for h in raw.get("delta_to_steady_state", {})
        }
    except (KeyError, TypeError) as e:
        return EventDelta(
            school=school,
            delta_to_steady_state={"T+5": HorizonDelta(adjust_pct=0.0), "T+20": HorizonDelta(adjust_pct=0.0)},
            _failed=True,
            _error=f"schema: {e}",
        )

    # Confidence 上限约束（ADR-002 §5）
    vc = raw.get("event_volatility_class", "exogenous_shock")
    confidence = raw.get("confidence", 0.0)
    caps = {
        "exogenous_shock": 1.0,
        "endogenous_technical": 0.3,
        "stochastic_noise": 0.1,
        "structural_break": 0.2,
    }
    confidence = min(confidence, caps.get(vc, 1.0))

    return EventDelta(
        school=school,
        delta_to_steady_state=deltas,
        event_volatility_class=vc,
        event_attribution_note=raw.get("event_attribution_note", ""),
        is_structural_change=raw.get("is_structural_change", False),
        structural_impact_note=raw.get("structural_impact_note", ""),
        amplifies=raw.get("amplifies", []),
        confidence=confidence,
    )


def modulate_with_event(
    state: StructuralState,
    event_text: str,
    horizons: list[str] | None = None,
    client: OpenAI | None = None,
) -> EventModulation:
    """主入口：让 4 学派对事件出 delta + 合计修正幅度。"""
    horizons = horizons or ["T+5", "T+20"]
    client = client or get_client()

    deltas: list[EventDelta] = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {
            pool.submit(ask_school_event, client, school, state, event_text): school
            for school in SCHOOLS
        }
        for fut in as_completed(futures):
            deltas.append(fut.result())

    # 合计：剔除 _failed，取平均 adjust_pct
    aggregate: dict[str, float] = {}
    for h in horizons:
        vals = [
            d.delta_to_steady_state[h].adjust_pct
            for d in deltas
            if not d._failed and h in d.delta_to_steady_state
        ]
        aggregate[h] = sum(vals) / len(vals) if vals else 0.0

    structural_votes = sum(1 for d in deltas if not d._failed and d.is_structural_change)

    return EventModulation(
        event_text=event_text,
        deltas=deltas,
        aggregate=aggregate,
        structural_change_votes=structural_votes,
    )
