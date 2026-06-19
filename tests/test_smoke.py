"""冒烟测试——不调 LLM，仅验证 schema / import / 数据完整性。"""

from __future__ import annotations

from hindcast import VARIABLES, SCHOOLS, StructuralState
from hindcast.data import ALL_SNAPSHOTS, GROUND_TRUTH, SNAPSHOTS
from hindcast.predict import majority_vote
from hindcast.schools import PROMPTS


def test_4_schools_registered():
    assert len(SCHOOLS) == 4
    assert set(PROMPTS.keys()) == set(SCHOOLS)


def test_15_variables():
    # v0.4 标题写 14 但 §3.2.1 表有 15 行；以表为准（A1-4 + B1-3 + C1-3 + D1-3 + E1-2 = 15）
    assert len(VARIABLES) == 15


def test_school_relevance_complete():
    """每个变量都要给 4 学派完整 ⭐ 评分。"""
    for var in VARIABLES.values():
        for school in SCHOOLS:
            assert school in var.school_relevance, f"{var.id} 缺 {school}"


def test_snapshots_have_all_variables():
    """每个 snapshot 要含 14 (15) 个变量值。"""
    for snap in ALL_SNAPSHOTS:
        for var_id in VARIABLES.keys():
            assert var_id in snap.values, f"{snap.as_of} 缺 {var_id}"


def test_ground_truth_aligned_with_snapshots():
    """每个 snapshot 都有 ground truth。"""
    for snap in ALL_SNAPSHOTS:
        assert snap.as_of in GROUND_TRUTH


def test_majority_vote_unanimous():
    winner, counts = majority_vote(["up", "up", "up", "up"])
    assert winner == "up"
    assert counts == {"up": 4}


def test_majority_vote_split_2_2_up_priority():
    """2:2 平局按 up > down > flat 优先（见 predict.py majority_vote）。"""
    winner, counts = majority_vote(["up", "up", "down", "down"])
    assert winner == "up"


def test_majority_vote_all_failed():
    winner, _ = majority_vote(["NO_SIGNAL", "NO_SIGNAL", "NO_SIGNAL", "NO_SIGNAL"])
    assert winner == "NO_SIGNAL"


def test_state_format_renders_15_rows():
    snap = SNAPSHOTS["2022-02-23"]
    rendered = snap.format_for_prompt()
    # 应该至少有 15 个变量行（| A1 | ... | | B1 | ... | ...）
    assert rendered.count("|") >= 15 * 3   # 每行 3 个 | 分隔
