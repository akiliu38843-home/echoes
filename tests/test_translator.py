"""tests/test_translator.py — 翻译层单元测试 (mock NarrativeSession, 不打真 LLM).

P2: 三路并行调用 (echo / cards / debate)，用 side_effect 按 system prompt 分发。
运行：PYTHONPATH=src .venv/bin/python -m pytest tests/test_translator.py -v
"""
from __future__ import annotations

from unittest.mock import patch

from hindcast.narrative_types import LensOutput, NarrativeEvent, NarrativeSession


# ──────────────────────────────────────────────────────────────
# Fixtures: mock session with all 9 lenses
# ──────────────────────────────────────────────────────────────

def _make_session() -> NarrativeSession:
    event = NarrativeEvent(text="美国对华关税全面升级", as_of="2026-06-18", mode="current")

    outputs = [
        LensOutput(
            lens_id="long_durée_structural", discipline="history",
            label_zh="长时段结构派", label_en="Long-durée Structural",
            raw={
                "depth_structures": ["全球化退潮结构", "大国博弈周期"],
                "structural_path": "守成大国 vs 新兴大国 + 保护主义抬头",
                "historical_analogues": [
                    "1870s–1890s 第一次全球化退潮 — 结构相似：守成工业强国面对新兴工业化国家崛起",
                    "1971 尼克松冲击 — 汇率与贸易体系重组",
                ],
                "what_event_is_not": "不是 1930 大萧条：结构不同，那是内生金融危机而非贸易战",
                "downstream_hint": "关注制度层对冲手段与意识形态变迁",
            },
        ),
        LensOutput(
            lens_id="contingency_narrative", discipline="history",
            label_zh="偶然性叙事派", label_en="Contingency Narrative",
            raw={
                "key_decision_nodes": [
                    {"actor": "USTR", "time": "2026-05", "decision": "关税重组审查", "why_pivotal": "触发报复链"}
                ],
                "actual_path_explanation": "贸易战由关税升级路径锁定",
                "historical_analogues": ["1930 斯穆特-霍利关税法", "2018 第一轮贸易战"],
                "downstream_hint": "政治决策节点是关键变量",
            },
        ),
        LensOutput(
            lens_id="institutional_pe", discipline="politics",
            label_zh="制度政治经济派", label_en="Institutional PE",
            raw={
                "transmission_channels": ["WTO 争端机制受压", "双边协定空间收窄", "国内政治极化"],
                "reasoning": "North/Acemoglu 视角：关税冲击触发制度变迁压力",
            },
        ),
        LensOutput(
            lens_id="austrian", discipline="economics",
            label_zh="奥地利学派", label_en="Austrian",
            raw={
                "school": "Austrian",
                "verdict": {"T+5": {"dir": "up", "range_pct": [2, 5]}, "T+20": {"dir": "up", "range_pct": [4, 9]}},
                "top_signals": ["货币扭曲", "资源误置"],
                "reasoning": "关税是价格扭曲机制",
                "confidence": 0.55,
            },
        ),
        LensOutput(
            lens_id="monetarist", discipline="economics",
            label_zh="货币学派", label_en="Monetarist",
            raw={
                "school": "Monetarist",
                "verdict": {"T+5": {"dir": "up", "range_pct": [1, 4]}, "T+20": {"dir": "flat", "range_pct": [-1, 3]}},
                "reasoning": "关税短期推高价格",
                "confidence": 0.50,
            },
        ),
        LensOutput(
            lens_id="keynesian", discipline="economics",
            label_zh="凯恩斯派", label_en="Keynesian",
            raw={
                "school": "Keynesian",
                "verdict": {"T+5": {"dir": "up", "range_pct": [3, 7]}, "T+20": {"dir": "up", "range_pct": [3, 8]}},
                "reasoning": "关税冲击需求，需财政刺激对冲",
                "confidence": 0.48,
            },
        ),
        LensOutput(
            lens_id="rational_expectations", discipline="economics",
            label_zh="理性预期派", label_en="Rational Expectations",
            raw={
                "school": "Rational Expectations",
                "verdict": {"T+5": {"dir": "flat", "range_pct": [-2, 2]}, "T+20": {"dir": "flat", "range_pct": [-1, 3]}},
                "reasoning": "市场已充分定价关税风险",
                "confidence": 0.40,
            },
        ),
        LensOutput(
            lens_id="structural_functional", discipline="sociology",
            label_zh="结构功能派", label_en="Structural Functional",
            raw={
                "agil_analysis": {
                    "A_adaptation": "失业率升至 4.2%，低收入群体首先受冲击",
                    "G_goal": "国家目标转向经济安全优先于效率",
                    "I_integration": "信任度 37%，社会凝聚力承压",
                    "L_latency": "民族主义情绪为政策合法性背书",
                },
                "dysfunction_diagnosis": "关税破坏 A 子系统的适应弹性",
                "solidarity_type": "有机团结向机械团结退化",
                "downstream_hint": "关注 I 子系统信任崩解",
            },
        ),
        LensOutput(
            lens_id="conflict_theory", discipline="sociology",
            label_zh="冲突理论派", label_en="Conflict Theory",
            raw={
                "class_power_map": {
                    "winners": ["国内制造业资本", "政治精英"],
                    "losers": ["消费者", "进口依赖中小企业"],
                    "neutral_or_ambiguous": ["金融资本"],
                },
                "inequality_anchor": "美国 Gini 系数 39.8（2023），关税将扩大购买力差距",
                "ideology_critique": "「保护就业」话语掩盖资本积累逻辑",
                "contradiction_exposed": "全球化受益者反身攻击自身赖以获利的秩序",
                "downstream_hint": "贫富分化加剧是结构性后果",
            },
        ),
        LensOutput(
            lens_id="cultural_values", discipline="anthropology",
            label_zh="文化价值观派", label_en="Cultural Values",
            raw={
                "cultural_position": {
                    "tr_sr_reading": "美国 TR/SR=-0.5，中国 TR/SR=+0.3",
                    "s_se_reading": "美国 S/SE=+1.8，中国 S/SE=-0.4",
                    "trust_reading": "美国政府信任 37%，中国 93%",
                },
                "event_value_resonance": "触发经济民族主义 vs 自由主义身份撕裂",
                "internal_tensions": ["全球化受益者 vs 铁锈带工人"],
                "modernization_trajectory": "可能触发反现代化民粹转向",
                "downstream_hint": "身份政治将超越经济理性",
            },
        ),
        LensOutput(
            lens_id="interpretive_structural", discipline="anthropology",
            label_zh="阐释/结构派", label_en="Interpretive/Structural",
            raw={
                "thick_description": {
                    "surface_layer": "关税数字与贸易额",
                    "middle_layer": "「美国优先」vs「核心利益」象征战争",
                    "deep_layer": "现代性与主权的根本张力",
                },
                "binary_opposition": {"primary": "开放 vs 封闭", "mediation_attempt": "「有管理的贸易」"},
                "pollution_boundary": "中国技术被定义为「污染」美国安全边界",
                "liminality_check": "双方处于旧秩序已破、新规则未立的阈限状态",
                "downstream_hint": "象征秩序重建先于经济秩序",
            },
        ),
        LensOutput(
            lens_id="realist_power_transition", discipline="intl_relations",
            label_zh="现实主义·权力转移派", label_en="Realism",
            raw={
                "power_balance_reading": "美国 2022 CINC=.124 vs 中国 .234，中国体量已居首（带 caveat：CINC 高估人口大国）",
                "structural_position": "处于权力转移收敛区，体系紧张上升",
                "security_dilemma": "美国技术管制被中方视为遏制，触发反制螺旋",
                "hegemonic_transition_risk": "修昔底德式对撞风险中等偏高，但经济捆绑提供刹车",
                "daily_life_transmission": "供应链重组 + 科技管制 → 进口品价格与就业受冲击",
                "time_horizon": "国力转移是几十年尺度，结构调整非一两年可完成",
                "downstream_hint": "权力结构视角揭示了经济语言遮蔽的体系对抗",
            },
        ),
        LensOutput(
            lens_id="liberal_institutionalism", discipline="intl_relations",
            label_zh="自由制度主义派", label_en="Liberal Institutionalism",
            raw={
                "institutional_constraints": "关税绕开 WTO 争端机制，制度被掏空而非缓冲",
                "interdependence_analysis": "中美供应链深度捆绑，全面脱钩代价极高",
                "absolute_gains_view": "存在被相对收益逻辑遮蔽的有限合作空间",
                "regime_resilience": "现有秩序受压但短期不至断裂，渐进调整为主",
                "daily_life_transmission": "跨境流动与合作红利受损 → 物价与选择变少",
                "downstream_hint": "制度视角揭示纯实力语言遮蔽的合作约束",
            },
        ),
        LensOutput(
            lens_id="central_brain", discipline="central_brain",
            label_zh="中枢大脑", label_en="Central Brain",
            raw={
                "lens_breakdown": "历史+经济+政治+社会+人类",
                "meta_judgment": "各派分歧根本在时间尺度：经济派看季度，历史派看十年",
                "disclaimer": "本分析为学派叙事，非预测，非建议",
                "synthesis_zh": "关税升级是结构性转折点，而非孤立贸易摩擦。",
                "synthesis_en": "A structural inflection point.",
            },
        ),
    ]
    return NarrativeSession(event=event, outputs=outputs)


# ── mock LLM 返回（按 prompt 分发） ─────────────────────────────
_MOCK_ECHO = {
    "present_label": "美国对华关税全面升级",
    "historical_label": "1870s–1890s 全球化退潮",
    "similarity": 78,
    "similarity_is_qualitative": True,
    "similarity_breakdown": [
        {"dimension": "结构格局", "score": 85, "note": "守成 vs 挑战"},
        {"dimension": "触发机制", "score": 78, "note": "关税壁垒"},
        {"dimension": "时代背景", "score": 70, "note": "全球化见顶"},
    ],
    "why_structural": "都是守成大国对新兴大国，且都靠保护主义。",
    "why_not_obvious": "不是 1930 大萧条：那是内生金融危机。",
    "structural_mapping": [
        {"element": "守成霸权国", "then": "英国", "now": "美国", "note": "—", "evidence_tag": "history"},
        {"element": "挑战者", "then": "美/德", "now": "中国", "note": "—", "evidence_tag": "history"},
        {"element": "触发机制", "then": "关税", "now": "关税+技术管制", "note": "—", "evidence_tag": "school"},
    ],
    "other_echoes": [{"label": "1971 尼克松冲击", "similarity": 61}],
}

_MOCK_CARDS = {
    "audience": "中国",
    "cards": [
        {
            "key": k, "icon": "X", "title": "T",
            "tldr": f"{k} 一句人话，就像……",
            "headline": f"{k} headline",
            "why": f"{k} 完整因果链很长很长。",
            "causal_chain": [
                {"step": 1, "cause": "关税↑", "effect": "进口价↑", "mechanism": "传导", "grounding": "T+20 +3~8%"},
                {"step": 2, "cause": "进口价↑", "effect": "CPI↑", "mechanism": "传导", "grounding": "机制推断，无数据锚"},
            ],
            "then": "上次宏观上价格上行",
            "horizon": "约 T+12 月",
            "confidence": 0.5,
            "confidence_note": "分歧中等",
            "data_anchors": [{"country": "美国", "indicator": "Gini", "value": "39.8"}],
            "by_country": [
                {"country": "中国", "impact": "出口承压"},
                {"country": "美国", "impact": "进口品涨价"},
            ],
            "evidence_tag": "data",
            "source_lenses": ["keynesian"],
        }
        for k in ["wallet", "job", "social", "identity", "power", "tempo"]
    ]
}

_MOCK_DEBATE = {
    "question": "这件事会怎样影响普通人？",
    "voices": [
        {"lens": "keynesian", "label_zh": "经济·凯恩斯派", "stance": "需求萎缩是主要风险", "data_anchor": "T+20 +3~8%"},
        {"lens": "conflict_theory", "label_zh": "社会·冲突派", "stance": "掩盖阶级撕裂", "data_anchor": "Gini 39.8"},
        {"lens": "long_durée_structural", "label_zh": "历史·长时段派", "stance": "十年级秩序重组", "data_anchor": "相似度 78%"},
        {"lens": "cultural_values", "label_zh": "人类学·文化派", "stance": "认同政治主导", "data_anchor": "信任 37% vs 93%"},
    ],
    "crux": "他们吵的根本是时间尺度不同。",
}


def _dispatch(client, system=None, user=None, max_tokens=None, **kw):
    """按 system prompt 的特征词分发到对应 mock。"""
    if "类比分析" in system:
        return dict(_MOCK_ECHO)
    if "生活影响卡" in system:
        return {"cards": [dict(c) for c in _MOCK_CARDS["cards"]]}
    if "学派吵架" in system:
        return dict(_MOCK_DEBATE)
    return {"_failed": True, "_error": "unknown prompt"}


# ──────────────────────────────────────────────────────────────
# Tests
# ──────────────────────────────────────────────────────────────

def test_extract_evidence_covers_all_lenses():
    from hindcast.translator import _extract_evidence

    ev = _extract_evidence(_make_session())
    assert "structural" in ev["history"] and "contingency" in ev["history"]
    assert ev["history"]["structural"]["what_event_is_not"]
    for lid in ["austrian", "monetarist", "keynesian", "rational_expectations"]:
        assert "verdict" in ev["economics"][lid]
    assert ev["politics"]["reasoning"]
    assert ev["sociology"]["conflict_theory"]["inequality_anchor"]
    assert ev["anthropology"]["cultural_values"]["event_value_resonance"]
    assert ev["intl_relations"]["realist"]["power_balance_reading"]
    assert ev["intl_relations"]["liberal"]["interdependence_analysis"]
    assert ev["central_brain"]["synthesis_zh"] and ev["central_brain"]["meta_judgment"]


def test_life_report_shape():
    from hindcast.translator import _CARD_KEYS, build_life_report

    session = _make_session()
    with patch("hindcast.translator.chat_json", side_effect=_dispatch):
        with patch("hindcast.translator.get_client", return_value=None):
            r = build_life_report(session)

    # event 由引擎真实值覆盖
    assert r["event"]["text"] == session.event.text

    # echo: 相似度拆维 + 对照表 + 恒定性标记
    echo = r["echo"]
    assert echo["similarity_is_qualitative"] is True
    assert 0 <= echo["similarity"] <= 100
    assert len(echo["similarity_breakdown"]) == 3
    for d in echo["similarity_breakdown"]:
        assert 0 <= d["score"] <= 100
    assert len(echo["structural_mapping"]) == 3
    for m in echo["structural_mapping"]:
        assert m["evidence_tag"] in {"data", "school", "history"}
        assert "then" in m and "now" in m

    # 默认中国视角 + 契约状态
    assert r["audience"] == "中国"
    assert r["status"] == "ok"
    assert r["meta"]["status"] == "ok" and r["meta"]["degraded_parts"] == []

    # data_anchors 规范形态 = 对象数组 {country,indicator,value}
    for c in r["cards"]:
        for a in c["data_anchors"]:
            assert set(a.keys()) == {"country", "indicator", "value"}

    # cards: 6 张、key 顺序固定、含 tldr/causal_chain/evidence_tag/by_country
    assert [c["key"] for c in r["cards"]] == _CARD_KEYS
    for c in r["cards"]:
        assert c["tldr"]
        assert isinstance(c["causal_chain"], list) and len(c["causal_chain"]) >= 1
        for s in c["causal_chain"]:
            assert "cause" in s and "effect" in s
        assert c["evidence_tag"] in {"data", "school", "history"}
        assert 0.0 <= c["confidence"] <= 1.0
        assert isinstance(c["by_country"], list)
        for bc in c["by_country"]:
            assert bc["country"] and bc["impact"]

    # debate
    assert len(r["debate"]["voices"]) >= 4

    # meta 透传中枢
    assert r["meta"]["synthesis_zh"]
    assert "uncertainty_note" in r["meta"]


def test_partial_fallback_cards_only():
    """cards 调用失败 → cards 降级，echo/debate 仍正常（分块降级）。"""
    from hindcast.translator import _CARD_KEYS, build_life_report

    def _dispatch_cards_fail(client, system=None, user=None, max_tokens=None, **kw):
        if "生活影响卡" in system:
            return {"_failed": True, "_error": "timeout"}
        return _dispatch(client, system=system, user=user, max_tokens=max_tokens)

    session = _make_session()
    with patch("hindcast.translator.chat_json", side_effect=_dispatch_cards_fail):
        with patch("hindcast.translator.get_client", return_value=None):
            r = build_life_report(session)

    # cards 降级但仍是 6 张占位
    assert [c["key"] for c in r["cards"]] == _CARD_KEYS
    assert r["cards"][0]["headline"] == "（分析暂时不可用）"
    # echo 仍正常
    assert len(r["echo"]["structural_mapping"]) == 3
    # debate 仍正常
    assert len(r["debate"]["voices"]) >= 4


def test_graceful_fallback_all_fail():
    """三路全失败 → 不崩，各块降级。"""
    from hindcast.translator import _CARD_KEYS, build_life_report

    def _all_fail(client, system=None, user=None, max_tokens=None, **kw):
        return {"_failed": True, "_error": "boom"}

    session = _make_session()
    with patch("hindcast.translator.chat_json", side_effect=_all_fail):
        with patch("hindcast.translator.get_client", return_value=None):
            r = build_life_report(session)

    assert r is not None
    assert [c["key"] for c in r["cards"]] == _CARD_KEYS
    assert r["echo"]["similarity_is_qualitative"] is True
    assert r["meta"]["synthesis_zh"]  # meta 来自中枢，不受 LLM 失败影响
    # 降级标记：三路全失败 → status degraded，三块都在 degraded_parts
    assert r["status"] == "degraded"
    assert set(r["meta"]["degraded_parts"]) == {"echo", "cards", "debate"}


def test_data_anchors_normalized_to_objects():
    """data_anchors 即使模型吐字符串，也规范化成对象 {country,indicator,value}。"""
    from hindcast.translator import _norm_anchors
    out = _norm_anchors(["美国 Gini 39.8", {"country": "中国", "indicator": "信任", "value": "93%"}])
    assert all(set(a.keys()) == {"country", "indicator", "value"} for a in out)
    assert out[0] == {"country": "", "indicator": "", "value": "美国 Gini 39.8"}
    assert out[1]["value"] == "93%"


def test_no_action_language():
    from hindcast.translator import CARDS_PROMPT, ECHO_PROMPT, _HONESTY_RULES

    assert "严禁" in _HONESTY_RULES
    assert "买" in _HONESTY_RULES and "卖" in _HONESTY_RULES
    assert "行动建议" in _HONESTY_RULES
    # 共享红线注入到各 prompt
    assert "严禁" in CARDS_PROMPT and "严禁" in ECHO_PROMPT


def test_tone_rules_in_prompts():
    """语气下沉规则（④）应注入各 prompt。"""
    from hindcast.translator import CARDS_PROMPT, DEBATE_PROMPT, ECHO_PROMPT

    for p in (CARDS_PROMPT, ECHO_PROMPT, DEBATE_PROMPT):
        assert "高中生" in p
        assert "类比" in p


def test_glossary_static_and_valid():
    """名词词典（③）：静态、非空、结构合法。"""
    from hindcast.glossary import ALIASES, GLOSSARY, all_terms

    assert len(GLOSSARY) >= 25
    for term, entry in GLOSSARY.items():
        assert entry.get("def"), f"{term} 缺 def"
        assert entry.get("analogy"), f"{term} 缺 analogy"
        assert entry.get("disc") in {
            "economics", "sociology", "anthropology", "history", "politics", "product"
        }
    # 别名都指向真实标准词
    for alias, target in ALIASES.items():
        assert target in GLOSSARY, f"别名 {alias} 指向不存在的词 {target}"
    payload = all_terms()
    assert "terms" in payload and "aliases" in payload
