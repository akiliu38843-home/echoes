"""Chain orchestrator 冒烟测试 (不调真实 LLM).

覆盖:
  - 全 chain 执行顺序 (spacetime → institution → material → meta)
  - force_disciplines 跳过 router
  - include_central_brain=False 豁免中枢大脑
  - NarrativeSession 工具方法
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from hindcast.chain import run_narrative_chain
from hindcast.disciplines import all_disciplines, discipline_lenses
from hindcast.narrative_types import NarrativeEvent


def _mock_json(client, system, user, **kwargs):  # noqa: ANN001
    """通用 mock: 按 system prompt 关键词返回最小合法 JSON."""
    if "Braudel" in system:
        return {
            "lens": "long_durée_structural",
            "depth_structures": ["test"],
            "structural_path": "test",
            "historical_analogues": [],
            "what_event_is_not": "",
            "downstream_hint": "test",
        }
    if "Lawrence Stone" in system:
        return {
            "lens": "contingency_narrative",
            "key_decision_nodes": [],
            "counterfactuals": [],
            "actual_path_explanation": "test",
            "historical_analogues": [],
            "downstream_hint": "",
        }
    if "路由器" in system:
        return {"selected": ["politics", "sociology"], "exempted_from_default": [], "reasoning": "test"}
    if "Parsons" in system:
        return {"lens": "structural_functional", "agil_analysis": {}, "dysfunction_diagnosis": "test",
                "repair_mechanisms": [], "solidarity_type": "", "downstream_hint": ""}
    if "Bourdieu" in system:
        return {"lens": "conflict_theory", "class_power_map": {}, "ideology_critique": "test",
                "bourdieu_field_analysis": "", "contradiction_exposed": "", "downstream_hint": ""}
    if "中枢大脑" in system:
        return {
            "lens_breakdown": "test",
            "meta_judgment": "test",
            "reader_tool": "test",
            "disclaimer": "test",
            "synthesis_zh": "test",
            "synthesis_en": "test",
        }
    return {"narrative": "test", "school": "test"}


@pytest.fixture
def event() -> NarrativeEvent:
    return NarrativeEvent(text="美联储宣布加息 50 BP", as_of="2026-06-16", mode="current")


def test_disciplines_registered():
    """注册表 sanity: 各学科全在, sociology / intl_relations 各 2 lens."""
    discs = set(all_disciplines())
    assert "economics" in discs
    assert "politics" in discs
    assert "history" in discs
    assert "sociology" in discs
    assert "anthropology" in discs
    assert "intl_relations" in discs
    assert "central_brain" in discs
    soc_lenses = discipline_lenses("sociology")
    assert len(soc_lenses) == 2
    ids = {l.id for l in soc_lenses}
    assert "structural_functional" in ids
    ir_ids = {l.id for l in discipline_lenses("intl_relations")}
    assert ir_ids == {"realist_power_transition", "liberal_institutionalism"}
    assert "conflict_theory" in ids


def test_full_chain_execution_order(event: NarrativeEvent):
    """历史先跑 → 经济/政治中间 → 中枢大脑最后."""
    with (
        patch("hindcast.chain.chat_json", side_effect=_mock_json),
        patch("hindcast.router.chat_json", side_effect=_mock_json),
        patch("hindcast.chain.get_client", return_value=None),
    ):
        session = run_narrative_chain(event)

    discs_in_order = [o.discipline for o in session.outputs]
    # 历史是前两个
    assert discs_in_order[0] == "history"
    assert discs_in_order[1] == "history"
    # 中枢大脑最后一个
    assert discs_in_order[-1] == "central_brain"
    # 经济在中枢大脑之前
    econ_idx = [i for i, d in enumerate(discs_in_order) if d == "economics"]
    cb_idx = discs_in_order.index("central_brain")
    assert all(i < cb_idx for i in econ_idx)


def test_all_outputs_success(event: NarrativeEvent):
    """mock 场景下所有 lens 不失败."""
    with (
        patch("hindcast.chain.chat_json", side_effect=_mock_json),
        patch("hindcast.router.chat_json", side_effect=_mock_json),
        patch("hindcast.chain.get_client", return_value=None),
    ):
        session = run_narrative_chain(event)

    failed = [o for o in session.outputs if o.failed]
    assert not failed, f"Unexpected failures: {[o.lens_id for o in failed]}"


def test_force_disciplines_skips_router(event: NarrativeEvent):
    """force_disciplines=[] 跳过 router, 只跑历史 + 中枢大脑."""
    with (
        patch("hindcast.chain.chat_json", side_effect=_mock_json),
        patch("hindcast.chain.get_client", return_value=None),
    ):
        session = run_narrative_chain(event, force_disciplines=[])

    discs = {o.discipline for o in session.outputs}
    assert "history" in discs
    assert "central_brain" in discs
    assert "economics" not in discs  # 没在 force_disciplines 里
    assert session.router is None  # router 未调用


def test_no_central_brain(event: NarrativeEvent):
    """include_central_brain=False 豁免中枢大脑."""
    with (
        patch("hindcast.chain.chat_json", side_effect=_mock_json),
        patch("hindcast.router.chat_json", side_effect=_mock_json),
        patch("hindcast.chain.get_client", return_value=None),
    ):
        session = run_narrative_chain(event, include_central_brain=False)

    discs = {o.discipline for o in session.outputs}
    assert "central_brain" not in discs


def test_session_helpers(event: NarrativeEvent):
    """NarrativeSession 工具方法."""
    with (
        patch("hindcast.chain.chat_json", side_effect=_mock_json),
        patch("hindcast.router.chat_json", side_effect=_mock_json),
        patch("hindcast.chain.get_client", return_value=None),
    ):
        session = run_narrative_chain(event)

    assert len(session.success_outputs()) == len(session.outputs)
    by_disc = session.outputs_by_discipline()
    assert "history" in by_disc
    assert len(by_disc["history"]) == 2  # 长时段 + 偶然性
