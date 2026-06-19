"""叙事模拟器共享数据类型 (chain.py / router.py 共用).

22-ADR §2 定义的 pipeline 数据结构:
  NarrativeEvent  → 事件输入
  LensOutput      → 单个 lens 产出
  RouterOutput    → Router 决策
  NarrativeSession → 完整叙事会话结果
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


@dataclass
class NarrativeEvent:
    """叙事 chain 的输入单元."""

    text: str
    as_of: str
    mode: Literal["historical", "current"] = "current"
    structural_context: str = ""


@dataclass
class LensOutput:
    """单个 lens 调用的产出."""

    lens_id: str
    discipline: str
    label_zh: str
    label_en: str
    raw: dict
    failed: bool = False
    error: str = ""


@dataclass
class RouterOutput:
    """Router LLM 的决策产出 (22-ADR §2.4)."""

    selected_disciplines: list[str]
    exempted_default: list[str]
    reasoning: str
    raw: dict


@dataclass
class NarrativeSession:
    """完整叙事会话结果."""

    event: NarrativeEvent
    outputs: list[LensOutput] = field(default_factory=list)
    router: RouterOutput | None = None
    rag_case_id: str | None = None    # 历史时期映射结果 (RAG enabled 时填充)
    rag_case_label: str | None = None

    def success_outputs(self) -> list[LensOutput]:
        return [o for o in self.outputs if not o.failed]

    def outputs_by_discipline(self) -> dict[str, list[LensOutput]]:
        result: dict[str, list[LensOutput]] = {}
        for o in self.outputs:
            result.setdefault(o.discipline, []).append(o)
        return result
