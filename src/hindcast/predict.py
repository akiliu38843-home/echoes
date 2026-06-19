"""主公开 API：predict() — 4 学派常态预测 + 纯多数投票。

v0.5 MVP 不含 RA-CR 辩论协议（见 09-ADR-PURE-VOTING-MVP.md）。
本模块是 MCP server / Web UI 后续包装的主入口。
"""

from __future__ import annotations

from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Literal

from openai import OpenAI
from pydantic import BaseModel, Field

from hindcast.agents import Verdict, ask_school
from hindcast.llm import get_client
from hindcast.political_brief import format_brief_for_economists, get_political_brief
from hindcast.state import SCHOOLS, School, StructuralState


Direction = Literal["up", "down", "flat", "NO_SIGNAL"]


class HorizonForecast(BaseModel):
    """单个时间维度的整合预测。"""

    dir: Direction
    vote_counts: dict[str, int]
    school_directions: dict[str, str]


class Forecast(BaseModel):
    """完整预测结果——主公开 API 返回值。"""

    as_of: str
    label: str
    asset: str = "XAU/USD"
    horizons: dict[str, HorizonForecast]
    verdicts: list[Verdict]
    n_valid_schools: int
    political_brief: dict | None = None  # 第 5 派 (v0.5.6) 政治简报; None = 未启用/失败

    @property
    def is_unanimous(self) -> bool:
        """4 学派对所有 horizon 都同向。"""
        return all(
            len(set(h.school_directions.values())) == 1 for h in self.horizons.values()
        )

    @property
    def is_split(self) -> bool:
        """至少一个 horizon 出现 2:2 平局或更分裂。"""
        for h in self.horizons.values():
            counts = h.vote_counts.values()
            if max(counts) == 2 and sum(counts) == 4:
                return True
        return False


def majority_vote(directions: list[str]) -> tuple[str, dict[str, int]]:
    """纯多数投票。平局按 up > down > flat 排序。"""
    valid_dirs = [d for d in directions if d != "NO_SIGNAL"]
    if not valid_dirs:
        return "NO_SIGNAL", {}
    counter = Counter(valid_dirs)
    counts = dict(counter)
    # 平局排序优先级：up 第一（更符合"基础叙事是结构性贬值"的偏置）
    sorted_dirs = sorted(
        counter.most_common(), key=lambda x: (-x[1], {"up": 0, "down": 1, "flat": 2}[x[0]])
    )
    return sorted_dirs[0][0], counts


def predict(
    state: StructuralState,
    asset: str = "XAU/USD",
    horizons: list[str] | None = None,
    client: OpenAI | None = None,
    bridge_priors: dict | None = None,
    include_political_brief: bool = True,
) -> Forecast:
    """主入口：给定结构状态 → 政治简报 (可选) → 4 学派并行 → 多数投票 → Forecast。

    v0.5.6: 增加 include_political_brief。开启后, 制度政治派先跑一次,
    它的 reasoning 作为可选参考注入 4 经济派 prompt; 政治派本身不投票。
    失败时静默降级——4 经济派仍独立跑, 与 v0.5.5 行为等同。
    """
    horizons = horizons or ["T+5", "T+20"]
    client = client or get_client()

    # ─── 第 5 派: 政治简报 (跑在 4 经济派之前) ───
    political_brief: dict | None = None
    if include_political_brief:
        brief = get_political_brief(state, client)
        if not brief.get("_failed"):
            political_brief = brief
            state = state.model_copy(update={
                "political_brief_section": format_brief_for_economists(brief),
            })
        # 失败则静默——4 经济派照常裸跑

    # ─── 注入 bridge priors（XAU 集成预测核心 v0.5.4）───
    state_with_priors = state
    if bridge_priors and asset == "XAU/USD":
        prior_lines = ["## 🌉 桥梁变量预测信号（前面已预测, 作为 XAU 集成 prior）", ""]
        for k, v in bridge_priors.items():
            prior_lines.append(f"- **{v.get('label', k)}**: T+5 {v['t5']} · T+20 {v['t20']}")
        prior_lines.append("")
        prior_lines.append("**集成公式**: XAU = -TIPS × β1 + BEI × β2 + (-DXY) × β3 + GPR × β4 + 央行购金 × β5")
        prior_lines.append("- TIPS down + BEI up + DXY down ⇒ XAU strong bull")
        prior_lines.append("- TIPS up + BEI flat + DXY up ⇒ XAU bearish")
        prior_lines.append("- 你的 verdict 必须**显式参考**这些 prior（不能忽略它们直接重新推理）")
        state_with_priors = state.model_copy(update={"prior_section": "\n".join(prior_lines)})

    verdicts: list[Verdict] = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {
            pool.submit(ask_school, client, school, state_with_priors): school
            for school in SCHOOLS
        }
        for fut in as_completed(futures):
            verdicts.append(fut.result())

    # ─── 每个 horizon 多数投票 ───
    horizon_forecasts: dict[str, HorizonForecast] = {}
    for h in horizons:
        school_dirs = {
            v.school: (v.direction(h) if not v._failed else "NO_SIGNAL")
            for v in verdicts
        }
        dirs = [d for d in school_dirs.values() if d != "NO_SIGNAL"]
        winner, counts = majority_vote(dirs)
        horizon_forecasts[h] = HorizonForecast(
            dir=winner,
            vote_counts=counts,
            school_directions=school_dirs,
        )

    n_valid = sum(1 for v in verdicts if not v._failed)

    return Forecast(
        as_of=state.as_of,
        label=state.label,
        asset=asset,
        horizons=horizon_forecasts,
        verdicts=verdicts,
        n_valid_schools=n_valid,
        political_brief=political_brief,
    )
