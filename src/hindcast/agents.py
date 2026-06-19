"""4 学派 Agent 类——单个学派对结构状态的判断。

v0.5 MVP：纯 LLM 调用，无 GraphRAG/CausalRAG 依赖。当用户的 CausalRAG 完成后，
在 ask() 里加 retrieve_evidence(state, school) → 注入 prompt。
"""

from __future__ import annotations

from typing import Literal

from openai import OpenAI
from pydantic import BaseModel, Field

from hindcast.llm import chat_json
from hindcast import rag
from hindcast.schools import PROMPTS
from hindcast.state import School, StructuralState


Direction = Literal["up", "down", "flat"]
VolatilityClass = Literal[
    "exogenous_shock",
    "endogenous_technical",
    "stochastic_noise",
    "structural_break",
]


class Horizon(BaseModel):
    dir: Direction
    range_pct: list[float] = Field(default_factory=lambda: [0.0, 0.0])


class Verdict(BaseModel):
    """单个学派对单个结构状态的判断（一对 horizon 全部覆盖）。

    v0.5 加入波动归因字段 (ADR-002)：
      volatility_class — 4 类波动判定
      attribution_note — 归因依据
    """

    school: School
    verdict: dict[str, Horizon]                # "T+5" / "T+20" → Horizon
    top_signals: list[str] = Field(default_factory=list)
    historical_precedents: list[str] = Field(default_factory=list)
    volatility_class: VolatilityClass = "exogenous_shock"  # default 兼容已有 prompt
    attribution_note: str = ""
    reasoning: str = ""
    confidence: float = 0.0
    _failed: bool = False
    _error: str | None = None

    def direction(self, horizon: str) -> Direction:
        return self.verdict.get(horizon, Horizon(dir="flat")).dir


def ask_school(
    client: OpenAI,
    school: School,
    state: StructuralState,
) -> Verdict:
    """让某个学派对结构状态出 verdict。

    若 env `HINDCAST_USE_RAG=1`，先调 CausalRAG 拿 evidence 注入 prompt——
    LLM 必须在 evidence 框架内回答（supports + contradicts + 锚定的 ID）。
    RAG 失败时自动降级，不破 75% baseline。
    """
    system_prompt = PROMPTS[school]
    user_prompt = state.format_for_prompt()

    # Optional: inject CausalRAG evidence
    if rag.is_enabled():
        for horizon in ("T+5", "T+20"):
            # 我们对每个 horizon 各查一次（DAG 路径 target node 不同）
            # 取 T+5 作为主 evidence；T+20 信息相似就不重复了
            if horizon == "T+5":
                evidence = rag.retrieve_evidence(
                    school=school,
                    structural_state=state.values,
                    horizon=horizon,
                    target_asset="XAU/USD",
                )
                if evidence and not evidence.get("_failed"):
                    user_prompt += rag.format_evidence_for_prompt(evidence)
                break

    raw = chat_json(client, system_prompt, user_prompt)

    if raw.get("_failed"):
        return Verdict(
            school=school,
            verdict={
                "T+5": Horizon(dir="flat"),
                "T+20": Horizon(dir="flat"),
            },
            _failed=True,
            _error=raw.get("_error"),
        )

    # 容错：把原始 dict 输出 normalize 成 Verdict
    try:
        horizons = {
            h: Horizon(**raw["verdict"][h]) for h in raw["verdict"].keys()
        }
    except (KeyError, TypeError) as e:
        return Verdict(
            school=school,
            verdict={"T+5": Horizon(dir="flat"), "T+20": Horizon(dir="flat")},
            _failed=True,
            _error=f"schema: {e}",
        )

    # Confidence 上限约束（ADR-002 §5）
    vc = raw.get("volatility_class", "exogenous_shock")
    confidence = raw.get("confidence", 0.0)
    confidence_caps = {
        "exogenous_shock": 1.0,
        "endogenous_technical": 0.3,
        "stochastic_noise": 0.1,
        "structural_break": 0.2,
    }
    confidence = min(confidence, confidence_caps.get(vc, 1.0))

    return Verdict(
        school=school,
        verdict=horizons,
        top_signals=raw.get("top_signals", []),
        historical_precedents=raw.get("historical_precedents", []),
        volatility_class=vc,
        attribution_note=raw.get("attribution_note", ""),
        reasoning=raw.get("reasoning", ""),
        confidence=confidence,
    )
