"""翻译层：把 9-lens NarrativeSession → LifeReport（历史回响生活报告）.

build_life_report(session) → dict

P2 架构：三路并行 LLM 调用（消除单次大调用截断风险）：
  · ECHO   调用 → 双栏镜像 + 相似度拆维 + 结构对照表
  · CARDS  调用 → 6 张生活卡（人话 TL;DR + 因果链 + 证据标注）
  · DEBATE 调用 → 学派吵架
meta（综合/免责）由中枢大脑确定性透传，不走 LLM。

任一路失败 → 该块降级，其余照常（不再全盘崩）。
"""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor

from openai import OpenAI

from hindcast.llm import chat_json, get_client
from hindcast.narrative_types import NarrativeSession

# ──────────────────────────────────────────────────────────────
# 共享规则片段
# ──────────────────────────────────────────────────────────────
_TONE_RULES = """\
═══ 语气：高中生能懂 ═══
- 写给一个聪明的高中生看：句子短，少用长从句。
- 一出现专业名词（如 基尼系数 / 理性预期 / 厚描述 / 阈限），
  立刻用一句「就像……」的生活化类比解释，再往下说。
- 不堆术语；能用大白话就不用行话。但该精确的地方要精确，别牺牲严谨。
"""

_HONESTY_RULES = """\
═══ 诚实红线 ═══
- 只能用 digest 里给的硬数字（基尼系数 / 经济区间 range_pct / 信任% / 文化坐标）；
  没有就留空，【严禁】凭空编造数字。
- 引用硬数字时【必须标明是哪个国家】的数据（如「美国 Gini 39.8」「中国政府信任 93%」），
  不可把一国的数字张冠李戴到另一国头上。
- 这是面向【今天的人】的产品：只讲事件对【现在我们的生活】的冲击。
  过去只作【宏观】结构参照（价格/就业/汇率/政策/时间尺度），
  【绝不】描写“那时普通人的日常生活/家庭故事”。
- 【严禁】任何行动建议（买 / 卖 / 换工作 / 囤货 / “你应该……”）。
  只讲「为什么会这样」，绝不教「做什么」。
- 严格输出 JSON，无多余文字，无代码围栏，无注释。
"""

_EVIDENCE_TAG_RULES = """\
═══ 证据标签 evidence_tag（三选一，标注这条结论的依据来源）═══
  "data"    = 用了 digest 里的硬数字（基尼系数 / 经济区间 / 信任% / 文化坐标）
  "school"  = 主要是某个学派的推理判断
  "history" = 主要来自历史类比 / 历史案例
"""

_VALID_TAGS = {"data", "school", "history"}

# ──────────────────────────────────────────────────────────────
# ① ECHO 调用：双栏镜像 + 相似度拆维 + 结构对照表
# ──────────────────────────────────────────────────────────────
ECHO_PROMPT = f"""\
你是「历史回响」的【类比分析】生成器。基于叙事证据摘要（digest），
产出「当下 ↔ 历史」的严谨对照。

{_TONE_RULES}
{_HONESTY_RULES}
{_EVIDENCE_TAG_RULES}

═══ 核心要求 ═══
① 相似度拆维：不要只给一个笼统的相似度数字（那是虚假精确）。
   拆成 3~4 个结构维度，每个维度单独打分 + 一句话说明。
   维度示例：结构格局 / 触发机制 / 时代背景 / 力量对比。
② 结构对照表 structural_mapping：把今天和历史时刻拆成结构要素，逐行对齐。
   每行给 element（要素）/ then（那时是谁）/ now（现在是谁）/ note（一句说明）/ evidence_tag。
   若 digest 的 intl_relations 给了 CINC 国力数字，"守成霸权国 / 新兴挑战者" 等行
   必须引用具体 CINC 份额（如 美.124 vs 中.234），evidence_tag 标 "data"；
   并尊重 CINC caveat（体量≠综合国力，不可过度解读）。
③ why_structural：拆开讲“相似在哪几个结构要素上、为什么是结构相似而非表面相似”（4~6 句）。
④ why_not_obvious：基于历史派 what_event_is_not，讲“为什么不是那个最顺嘴的对比”（2~3 句）。

═══ 严格输出此 JSON ═══
{{
  "present_label": "一句话描述当下事件（≤30字）",
  "historical_label": "最佳历史类比时期（≤20字）",
  "similarity": <整数 0–100，总体定性相似度>,
  "similarity_is_qualitative": true,
  "similarity_breakdown": [
    {{"dimension": "结构格局", "score": <整数0–100>, "note": "一句说明"}},
    {{"dimension": "触发机制", "score": <整数>, "note": "…"}},
    {{"dimension": "时代背景", "score": <整数>, "note": "…"}}
  ],
  "why_structural": "4~6句",
  "why_not_obvious": "2~3句",
  "structural_mapping": [
    {{"element": "守成霸权国", "then": "19世纪的英国", "now": "今天的美国", "note": "一句", "evidence_tag": "history"}},
    {{"element": "新兴挑战者", "then": "…", "now": "…", "note": "…", "evidence_tag": "history"}},
    {{"element": "触发机制", "then": "…", "now": "…", "note": "…", "evidence_tag": "school"}}
  ],
  "other_echoes": [{{"label": "另一个历史类比", "similarity": <整数>}}]
}}
"""

# ──────────────────────────────────────────────────────────────
# ② CARDS 调用：6 张生活卡（人话 TL;DR + 因果链 + 证据标注）
# ──────────────────────────────────────────────────────────────
CARDS_PROMPT = f"""\
你是「历史回响」的【生活影响卡】生成器。把叙事证据翻译成 6 张讲“对今天的人有什么冲击”的卡片。

{_TONE_RULES}
{_HONESTY_RULES}
{_EVIDENCE_TAG_RULES}

═══ 读者视角（重要）═══
- 默认读者 = 【中国普通人】。所有卡片默认讲"这件事对中国人的生活有什么影响"。
- 若事件明显涉及【多个国家】（如中美贸易战、对某国制裁、他国大选），
  则【区分不同国家】的影响差异：以中国为主，用 by_country 字段点出其他相关国家
  在该维度上的影响有何不同（哪国更疼、方向是否相反）。
- 若事件只涉及单一国家或影响对各国大体一致，by_country 留空数组。
- 顶层 audience 字段填本报告主视角（默认 "中国"；若主体明显是别国，填那个国家）。

═══ 六张卡片：key 固定且按此顺序，每张主要取自 ═══
| key       | icon | 主要取自                                          |
|-----------|------|--------------------------------------------------|
| wallet    | 💰   | 经济派 verdict(T+5/T+20 dir+range) + 凯恩斯/货币派 reasoning |
| job       | 💼   | 经济派传导 + 社会学 AGIL 的 A_adaptation（含失业数据）|
| social    | 🤝   | 社会学 inequality_anchor(基尼系数) + I_integration(信任%)|
| identity  | 🪪   | 人类学 event_value_resonance + 内部张力 + 文化坐标 |
| power     | 🏛   | 政治派 reasoning + transmission_channels + 国际关系派(权力格局/制度约束/相互依赖)|
| tempo     | ⏳   | 历史派 depth_structures + structural_path + 国际关系派 time_horizon（国力转移=几十年尺度）|

═══ 每张卡的字段要求 ═══
- tldr：一句【最大白话】的人话，最好带生活化类比（“就像……”）。让任何人一眼看懂这卡讲啥。
- headline：对今天的人会怎样（一句，≤30字）。
- why：完整因果机制（4~7句），把传导链条讲透，讲“为什么会冲击今天的我们”。
  用上 digest 里对应学派的厚材料（阶级图谱 / 三层意义 / 反事实 / AGIL）。禁行动建议。
- causal_chain：把 why 拆成 2~4 个可读的传导步骤（结构化）。每步：
  cause（起因）→ effect（结果）+ mechanism（机制一句）+ grounding（有硬数字就引用，没有写“机制推断，无数据锚”）。
- then：上一次结构类似时【宏观上】怎么走（价格/就业/汇率/时间尺度）；写不出填“（缺宏观历史细节）”。
- evidence_tag：这张卡结论的主要依据（data / school / history）。
- data_anchors：引用到的具体硬数字，【对象数组】，每项 {{"country":"中国","indicator":"政府信任度(WVS)","value":"93%"}}；
  country 可留空字符串；没有就空数组 []；禁止编造。【不要用纯字符串，必须是对象】。
- by_country：仅当事件涉及多国且该维度影响有差异时填；每项 {{"country":"中国/美国/…", "impact":"一句该国在此维度的影响"}}；否则空数组。
- confidence：0.0–1.0。经济四派方向分歧大（有 up/down 相反）→ ≤0.40；无数据锚且分歧大 → ≤0.30。

═══ 严格输出此 JSON ═══
{{
  "audience": "中国",
  "cards": [
    {{
      "key": "wallet", "icon": "💰", "title": "钱包",
      "tldr": "一句带类比的大白话（默认讲对中国人的影响）",
      "headline": "…",
      "why": "4~7句完整因果链",
      "causal_chain": [
        {{"step": 1, "cause": "关税↑", "effect": "进口到岸价↑", "mechanism": "一句", "grounding": "经济派T+20 +3~8%"}},
        {{"step": 2, "cause": "进口价↑", "effect": "CPI传导", "mechanism": "一句", "grounding": "机制推断，无数据锚"}}
      ],
      "then": "上一次结构类似时宏观上怎么走",
      "horizon": "约 T+X 月",
      "confidence": 0.0,
      "confidence_note": "分歧/数据锚说明",
      "data_anchors": [{{"country": "中国", "indicator": "政府信任度(WVS)", "value": "93%"}}],
      "by_country": [
        {{"country": "中国", "impact": "中国消费者/出口商在钱包维度如何"}},
        {{"country": "美国", "impact": "美国一方有何不同（更疼/方向相反等）"}}
      ],
      "evidence_tag": "data",
      "source_lenses": ["keynesian", "monetarist"]
    }}
    // 其余 job/social/identity/power/tempo 五张，结构相同，icon 依次 💼🤝🪪🏛⏳
    // 单一国家事件时 by_country 留空数组 []
  ]
}}
"""

# ──────────────────────────────────────────────────────────────
# ③ DEBATE 调用：学派吵架
# ──────────────────────────────────────────────────────────────
DEBATE_PROMPT = f"""\
你是「历史回响」的【学派吵架】生成器。把各学派对同一事件的不同判断并列，分歧本身就是看点。

{_TONE_RULES}
{_HONESTY_RULES}

═══ 要求 ═══
- voices：4~6 条，覆盖经济 / 社会 / 历史 / 人类学 / 国际关系，至少 4 个学科各一条
  （若 digest 有 intl_relations，务必纳入现实主义或自由制度主义的声音）。
  每条：lens（lens_id）/ label_zh（如“经济·凯恩斯派”）/ stance（这派怎么看，一句≤40字）/
  data_anchor（引用的具体数字，没有留空）。
- crux：他们为什么吵——范畴 / 时间尺度 / 因果语言的根本分歧（取自中枢 meta_judgment，1~2句）。

═══ 严格输出此 JSON ═══
{{
  "question": "这件事会怎样影响普通人？",
  "voices": [
    {{"lens": "keynesian", "label_zh": "经济·凯恩斯派", "stance": "…", "data_anchor": "T+20 +3~8%"}},
    {{"lens": "conflict_theory", "label_zh": "社会·冲突派", "stance": "…", "data_anchor": "基尼 39.8"}}
  ],
  "crux": "他们为什么吵（1~2句）"
}}
"""

# ──────────────────────────────────────────────────────────────
# 6 张卡片的 key + 元数据（顺序固定）
# ──────────────────────────────────────────────────────────────
_CARD_KEYS = ["wallet", "job", "social", "identity", "power", "tempo"]
_CARD_META = {
    "wallet":   ("💰", "钱包"),
    "job":      ("💼", "饭碗"),
    "social":   ("🤝", "人际"),
    "identity": ("🪪", "认同"),
    "power":    ("🏛", "规则"),
    "tempo":    ("⏳", "节奏"),
}

_UNCERTAINTY_NOTE = "本报告是结构类比与多学派叙事，非投资建议，非未来预测（21-ADR）"


# ──────────────────────────────────────────────────────────────
# 确定性证据抽取
# ──────────────────────────────────────────────────────────────
def _extract_evidence(session: NarrativeSession) -> dict:
    """从 9 个 lens 的 raw 字段中确定性抽取关键证据 → 紧凑 digest dict."""
    evidence: dict = {
        "event": {"text": session.event.text, "as_of": session.event.as_of},
        "history": {},
        "economics": {},
        "politics": {},
        "sociology": {},
        "anthropology": {},
        "intl_relations": {},
        "central_brain": {},
    }

    for out in session.outputs:
        if out.failed:
            continue
        r = out.raw
        lid = out.lens_id

        if out.discipline == "history":
            if lid == "long_durée_structural":
                evidence["history"]["structural"] = {
                    "depth_structures": r.get("depth_structures", []),
                    "structural_path": r.get("structural_path", ""),
                    "historical_analogues": r.get("historical_analogues", []),
                    "what_event_is_not": r.get("what_event_is_not", ""),
                    "downstream_hint": r.get("downstream_hint", ""),
                }
            elif lid == "contingency_narrative":
                evidence["history"]["contingency"] = {
                    "key_decision_nodes": r.get("key_decision_nodes", [])[:3],
                    "actual_path_explanation": r.get("actual_path_explanation", ""),
                    "historical_analogues": r.get("historical_analogues", []),
                    "downstream_hint": r.get("downstream_hint", ""),
                }

        elif out.discipline == "economics":
            evidence["economics"][lid] = {
                "school": r.get("school", lid),
                "verdict": r.get("verdict", {}),
                "reasoning": r.get("reasoning", ""),
                "confidence": r.get("confidence", 0.0),
                "top_signals": r.get("top_signals", [])[:3],
                "historical_precedents": r.get("historical_precedents", [])[:2],
            }

        elif out.discipline == "politics":
            evidence["politics"] = {
                "transmission_channels": r.get("transmission_channels", []),
                "reasoning": r.get("reasoning", ""),
            }

        elif out.discipline == "sociology":
            if lid == "structural_functional":
                evidence["sociology"]["structural_functional"] = {
                    "agil_analysis": r.get("agil_analysis", {}),
                    "dysfunction_diagnosis": r.get("dysfunction_diagnosis", ""),
                    "solidarity_type": r.get("solidarity_type", ""),
                    "downstream_hint": r.get("downstream_hint", ""),
                }
            elif lid == "conflict_theory":
                evidence["sociology"]["conflict_theory"] = {
                    "class_power_map": r.get("class_power_map", {}),
                    "inequality_anchor": r.get("inequality_anchor", ""),
                    "ideology_critique": r.get("ideology_critique", ""),
                    "contradiction_exposed": r.get("contradiction_exposed", ""),
                    "downstream_hint": r.get("downstream_hint", ""),
                }

        elif out.discipline == "anthropology":
            if lid == "cultural_values":
                evidence["anthropology"]["cultural_values"] = {
                    "cultural_position": r.get("cultural_position", {}),
                    "event_value_resonance": r.get("event_value_resonance", ""),
                    "internal_tensions": r.get("internal_tensions", []),
                    "cross_cultural_contrast": r.get("cross_cultural_contrast", ""),
                    "modernization_trajectory": r.get("modernization_trajectory", ""),
                    "downstream_hint": r.get("downstream_hint", ""),
                }
            elif lid == "interpretive_structural":
                evidence["anthropology"]["interpretive_structural"] = {
                    "thick_description": r.get("thick_description", {}),
                    "binary_opposition": r.get("binary_opposition", {}),
                    "pollution_boundary": r.get("pollution_boundary", ""),
                    "liminality_check": r.get("liminality_check", ""),
                    "cross_cultural_analogy": r.get("cross_cultural_analogy", ""),
                    "downstream_hint": r.get("downstream_hint", ""),
                }

        elif out.discipline == "intl_relations":
            if lid == "realist_power_transition":
                evidence["intl_relations"]["realist"] = {
                    "power_balance_reading": r.get("power_balance_reading", ""),
                    "structural_position": r.get("structural_position", ""),
                    "security_dilemma": r.get("security_dilemma", ""),
                    "hegemonic_transition_risk": r.get("hegemonic_transition_risk", ""),
                    "daily_life_transmission": r.get("daily_life_transmission", ""),
                    "time_horizon": r.get("time_horizon", ""),
                    "downstream_hint": r.get("downstream_hint", ""),
                }
            elif lid == "liberal_institutionalism":
                evidence["intl_relations"]["liberal"] = {
                    "institutional_constraints": r.get("institutional_constraints", ""),
                    "interdependence_analysis": r.get("interdependence_analysis", ""),
                    "absolute_gains_view": r.get("absolute_gains_view", ""),
                    "regime_resilience": r.get("regime_resilience", ""),
                    "daily_life_transmission": r.get("daily_life_transmission", ""),
                    "downstream_hint": r.get("downstream_hint", ""),
                }

        elif out.discipline == "central_brain":
            evidence["central_brain"] = {
                "meta_judgment": r.get("meta_judgment", ""),
                "synthesis_zh": r.get("synthesis_zh", ""),
                "disclaimer": r.get("disclaimer", ""),
                "lens_breakdown": r.get("lens_breakdown", ""),
            }

    return evidence


# ──────────────────────────────────────────────────────────────
# 校验工具
# ──────────────────────────────────────────────────────────────
def _clamp_int(v, lo: int, hi: int, default: int = 0) -> int:
    try:
        return max(lo, min(hi, int(v)))
    except (TypeError, ValueError):
        return default


def _clamp_float(v, lo: float, hi: float, default: float = 0.0) -> float:
    try:
        return max(lo, min(hi, float(v)))
    except (TypeError, ValueError):
        return default


def _tag(v) -> str:
    return v if v in _VALID_TAGS else "school"


def _norm_anchors(raw) -> list:
    """data_anchors 规范化为统一对象数组 [{country, indicator, value}].

    契约规范形态 = 对象数组。模型偶尔吐纯字符串 → 兜进 value 字段，保证前端只见一种形态。
    """
    out = []
    for a in _as_list(raw):
        if isinstance(a, dict):
            out.append({
                "country": str(a.get("country", "")),
                "indicator": str(a.get("indicator", "")),
                "value": str(a.get("value", a.get("number", ""))),
            })
        elif isinstance(a, str) and a.strip():
            out.append({"country": "", "indicator": "", "value": a.strip()})
    return out


def _as_list(v) -> list:
    return v if isinstance(v, list) else []


# ──────────────────────────────────────────────────────────────
# 各块校验
# ──────────────────────────────────────────────────────────────
def _validate_echo(raw: dict | None, session: NarrativeSession) -> dict:
    if not isinstance(raw, dict) or raw.get("_failed"):
        return {
            "present_label": session.event.text[:60],
            "historical_label": "",
            "similarity": 0,
            "similarity_is_qualitative": True,
            "similarity_breakdown": [],
            "why_structural": "",
            "why_not_obvious": "",
            "structural_mapping": [],
            "other_echoes": [],
            "_degraded": True,
        }

    breakdown = []
    for d in _as_list(raw.get("similarity_breakdown")):
        if isinstance(d, dict):
            breakdown.append({
                "dimension": str(d.get("dimension", "")),
                "score": _clamp_int(d.get("score"), 0, 100),
                "note": str(d.get("note", "")),
            })

    mapping = []
    for m in _as_list(raw.get("structural_mapping")):
        if isinstance(m, dict):
            mapping.append({
                "element": str(m.get("element", "")),
                "then": str(m.get("then", "")),
                "now": str(m.get("now", "")),
                "note": str(m.get("note", "")),
                "evidence_tag": _tag(m.get("evidence_tag")),
            })

    others = []
    for e in _as_list(raw.get("other_echoes")):
        if isinstance(e, dict):
            others.append({
                "label": str(e.get("label", "")),
                "similarity": _clamp_int(e.get("similarity"), 0, 100),
            })

    return {
        "present_label": str(raw.get("present_label", session.event.text[:60])),
        "historical_label": str(raw.get("historical_label", "")),
        "similarity": _clamp_int(raw.get("similarity"), 0, 100),
        "similarity_is_qualitative": True,  # 恒为 True
        "similarity_breakdown": breakdown,
        "why_structural": str(raw.get("why_structural", "")),
        "why_not_obvious": str(raw.get("why_not_obvious", "")),
        "structural_mapping": mapping,
        "other_echoes": others,
    }


def _validate_cards(raw: dict | None, error: str = "") -> list:
    cards_in = {}
    if isinstance(raw, dict) and not raw.get("_failed"):
        for c in _as_list(raw.get("cards")):
            if isinstance(c, dict) and c.get("key") in _CARD_KEYS:
                cards_in[c["key"]] = c

    degraded = not cards_in
    out = []
    for key in _CARD_KEYS:
        icon, title = _CARD_META[key]
        c = cards_in.get(key, {})

        chain = []
        for s in _as_list(c.get("causal_chain")):
            if isinstance(s, dict):
                chain.append({
                    "step": _clamp_int(s.get("step"), 1, 99, len(chain) + 1),
                    "cause": str(s.get("cause", "")),
                    "effect": str(s.get("effect", "")),
                    "mechanism": str(s.get("mechanism", "")),
                    "grounding": str(s.get("grounding", "")),
                })

        by_country = []
        for bc in _as_list(c.get("by_country")):
            if isinstance(bc, dict) and bc.get("country") and bc.get("impact"):
                by_country.append({
                    "country": str(bc.get("country", "")),
                    "impact": str(bc.get("impact", "")),
                })

        out.append({
            "key": key, "icon": icon, "title": title,
            "tldr": str(c.get("tldr", "")),
            "headline": str(c.get("headline", "（分析暂时不可用）" if degraded else "")),
            "why": str(c.get("why", "")),
            "causal_chain": chain,
            "then": str(c.get("then", "")),
            "horizon": str(c.get("horizon", "")),
            "confidence": _clamp_float(c.get("confidence"), 0.0, 1.0),
            "confidence_note": str(c.get("confidence_note", f"卡片生成失败: {error[:60]}" if degraded else "")),
            "data_anchors": _norm_anchors(c.get("data_anchors")),
            "by_country": by_country,
            "evidence_tag": _tag(c.get("evidence_tag")),
            "source_lenses": _as_list(c.get("source_lenses")),
        })
    return out


def _validate_debate(raw: dict | None) -> dict:
    if not isinstance(raw, dict) or raw.get("_failed"):
        return {"question": "这件事会怎样影响普通人？", "voices": [], "crux": ""}
    voices = []
    for v in _as_list(raw.get("voices")):
        if isinstance(v, dict):
            voices.append({
                "lens": str(v.get("lens", "")),
                "label_zh": str(v.get("label_zh", "")),
                "stance": str(v.get("stance", "")),
                "data_anchor": str(v.get("data_anchor", "")),
            })
    return {
        "question": str(raw.get("question", "这件事会怎样影响普通人？")),
        "voices": voices,
        "crux": str(raw.get("crux", "")),
    }


def _build_meta(evidence: dict) -> dict:
    """meta 确定性透传中枢大脑，不走 LLM."""
    cb = evidence.get("central_brain", {})
    return {
        "synthesis_zh": cb.get("synthesis_zh", ""),
        "disclaimer": cb.get("disclaimer", ""),
        "uncertainty_note": _UNCERTAINTY_NOTE,
    }


# ──────────────────────────────────────────────────────────────
# 对外入口
# ──────────────────────────────────────────────────────────────
def build_life_report(
    session: NarrativeSession,
    client: OpenAI | None = None,
) -> dict:
    """把 9-lens NarrativeSession 翻译成「历史回响」LifeReport JSON.

    三路并行 LLM 调用（echo / cards / debate）+ meta 确定性透传。
    任一路失败 → 该块降级，其余照常。
    """
    client = client or get_client()
    evidence = _extract_evidence(session)
    digest = json.dumps(evidence, ensure_ascii=False, indent=2)
    user_msg = f"## 叙事证据摘要\n\n{digest}"

    def _call(system: str, max_tokens: int) -> dict:
        return chat_json(client, system=system, user=user_msg, max_tokens=max_tokens)

    with ThreadPoolExecutor(max_workers=3) as ex:
        f_echo = ex.submit(_call, ECHO_PROMPT, 2800)
        f_cards = ex.submit(_call, CARDS_PROMPT, 6000)
        f_debate = ex.submit(_call, DEBATE_PROMPT, 1600)
        echo_raw = _safe_result(f_echo)
        cards_raw = _safe_result(f_cards)
        debate_raw = _safe_result(f_debate)

    cards_err = (cards_raw or {}).get("_error", "") if isinstance(cards_raw, dict) else ""
    audience = "中国"
    if isinstance(cards_raw, dict) and not cards_raw.get("_failed"):
        aud = cards_raw.get("audience")
        if isinstance(aud, str) and aud.strip():
            audience = aud.strip()

    # 契约：降级标记。meta.status = "ok" | "degraded"；degraded_parts 列出哪几块失败。
    def _failed(raw) -> bool:
        return raw is None or (isinstance(raw, dict) and bool(raw.get("_failed")))
    degraded_parts = [
        name for name, raw in (("echo", echo_raw), ("cards", cards_raw), ("debate", debate_raw))
        if _failed(raw)
    ]
    meta = _build_meta(evidence)
    meta["status"] = "degraded" if degraded_parts else "ok"
    meta["degraded_parts"] = degraded_parts

    return {
        "event": {"text": session.event.text, "as_of": session.event.as_of},
        "audience": audience,
        "status": meta["status"],          # 顶层镜像，方便前端一眼判定
        "echo": _validate_echo(echo_raw, session),
        "cards": _validate_cards(cards_raw, cards_err),
        "debate": _validate_debate(debate_raw),
        "meta": meta,
    }


def _safe_result(future) -> dict | None:
    try:
        return future.result(timeout=130)
    except Exception as e:
        return {"_failed": True, "_error": str(e)[:200]}
