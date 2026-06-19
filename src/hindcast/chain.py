"""动态学科 chain orchestrator (22-ADR §2.2 / §2.3 / §2.5).

执行顺序 (固定):
  事件 → [知识预取: EventKG+GDELT 并行] →
  [spacetime: 历史必调, 并行] → [Router LLM] →
  [institution层, 并行] → [material层, 并行] →
  [psyche_culture层, 并行] → [central_brain: 必调, 串行]

fan-in: 每层消费所有上游输出 (事件 + 所有已完成 lens 的 JSON 产出).
knowledge_ctx: 外部知识库预取结果, 按 discipline 注入 user prompt.

新增学科: 只需建 disciplines/<name>.py + register(Lens(...)), 不改此文件.
"""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed

from openai import OpenAI

from hindcast.disciplines import (
    LAYER_ORDER,
    Lens,
    all_disciplines,
    discipline_lenses,
)
from hindcast.llm import chat_json, get_client
from hindcast.narrative_types import (
    LensOutput,
    NarrativeEvent,
    NarrativeSession,
    RouterOutput,
)

# 22-ADR §2.3: 历史必调 + 不经 router
_SPACETIME_DISC = "history"
_CASE_MATCH_SYSTEM = "你是历史结构类比专家。只输出 JSON，不要任何额外文字。"
# 22-ADR §2.6: 中枢大脑最后 + 必调
_CENTRAL_BRAIN_DISC = "central_brain"
# 22-ADR §2.7: 经济派默认开, router 可豁免 (极少)
_DEFAULT_ON_DISCS = {"economics"}
# 叙事类 lens 输出比经济预测更长
_NARRATIVE_MAX_TOKENS = 1000


def _build_user_prompt(
    event: NarrativeEvent,
    upstream: list[LensOutput],
    lens: Lens,
    knowledge_ctx: dict[str, str] | None = None,
) -> str:
    """构建单个 lens 的 user prompt (含 fan-in 上游输出 + 外部知识注入).

    knowledge_ctx: discipline → pre-fetched context string (EventKG / GDELT).
    经济派在历史 tab 额外补充结构状态变量; 在现实事件 tab 加 '叙事模式' 提示.
    """
    parts = [f"## 当前事件\n\n{event.text}\n\n日期: {event.as_of}\n"]

    if lens.discipline == "economics":
        if event.mode == "current":
            parts.append(
                "\n⚠️ 叙事模式: 这是现实事件分析."
                " 不出方向/幅度/置信度."
                " 只讲你的学派 frame 怎么看这个事件的因果传导路径.\n"
            )
        elif event.structural_context:
            parts.append(f"\n## 结构状态变量\n\n{event.structural_context}\n")

    # 外部知识库注入 (EventKG → history; GDELT → politics)
    if knowledge_ctx and lens.discipline in knowledge_ctx:
        ctx = knowledge_ctx[lens.discipline]
        if ctx:
            parts.append(ctx)

    if upstream:
        parts.append("\n---\n## 上游学科分析 (可采纳 / 忽略 / 反驳)\n")
        for out in upstream:
            if not out.failed:
                parts.append(f"\n### {out.label_zh} ({out.lens_id})\n")
                parts.append(json.dumps(out.raw, ensure_ascii=False, indent=2))

    return "\n".join(parts)


def _match_narrative_case(
    event: NarrativeEvent,
    client: OpenAI,
) -> tuple[str, str] | None:
    """LLM 把事件文本映射到最近似历史时期。返回 (case_id, label) 或 None。

    只在 HINDCAST_USE_RAG=1 时运行；失败时 graceful fallback → None。
    """
    from hindcast import rag
    if not rag.is_enabled():
        return None
    cases = rag.load_history_cases()
    if not cases:
        return None
    case_lines = "\n".join(
        f"- {c['id']}: {c['label']} ({c['date'][:4]})" for c in cases
    )
    user_prompt = (
        f"事件: {event.text}\n日期: {event.as_of}\n\n"
        f"可选历史时期:\n{case_lines}\n\n"
        '输出 JSON: {"case_id": "<最匹配的 id>", "reason": "<一句话>"}'
    )
    try:
        result = chat_json(
            client,
            system=_CASE_MATCH_SYSTEM,
            user=user_prompt,
            max_tokens=100,
        )
        case_id = result.get("case_id", "")
        matched = next((c for c in cases if c["id"] == case_id), None)
        if matched:
            return case_id, matched["label"]
    except Exception:
        pass
    return None


def _prefetch_knowledge(
    event: NarrativeEvent,
    narrative_case: tuple[str, str] | None,
) -> dict[str, str]:
    """并行预取外部知识: Wikidata (历史派) + GDELT/Manifesto (政治派) + WorldBank/WVS (社会学派) + WVS/EA (人类学派).

    使用 narrative_case label (英文) 作查询词, 避免中文 → 英文 KG 不匹配.
    任一来源失败均 graceful fallback → "" (不影响 chain 主流程).

    注入分工:
      sociology    → World Bank 结构指标 (Gini/失业) + WVS 信任/宗教数据
      anthropology → WVS Inglehart-Welzel 文化坐标 + D-PLACE/EA 跨文化参照
    """
    from hindcast.knowledge import event_kg, gdelt, manifesto, sociology, anthropology, wvs, intl_relations

    keyword = ""
    if narrative_case:
        keyword = (
            narrative_case[1].split("—")[0].split(",")[0].strip()[:60]
        )

    results: dict[str, str] = {
        "history":       "",
        "politics":      "",
        "sociology":     "",
        "anthropology":  "",
        "intl_relations": "",
    }

    def _fetch_history():
        if not keyword:
            return ""
        events = event_kg.search_by_keyword(keyword, limit=6)
        return event_kg.format_for_prompt(events, keyword)

    def _fetch_politics():
        parts: list[str] = []
        if keyword:
            articles = gdelt.search_recent(keyword, event.as_of, timespan_days=30)
            parts.append(gdelt.format_for_prompt(articles, keyword))
        if manifesto.is_available():
            parties = manifesto.get_parties_for_country("US")
            positions = [manifesto.get_positions(p["party_id"]) for p in parties[:3]]
            positions = [p for p in positions if p]
            parts.append(manifesto.format_for_prompt(parties, positions, keyword))
        return "\n".join(p for p in parts if p)

    def _fetch_sociology():
        """World Bank 结构指标 + WVS 信任/宗教 → 供结构功能派/冲突派使用."""
        kw = keyword or event.text[:60]
        parts: list[str] = []
        indicators = sociology.get_social_indicators(kw)
        parts.append(sociology.format_for_prompt(indicators, kw))
        cultural = wvs.get_cultural_values(kw)
        parts.append(wvs.format_for_prompt(cultural, kw))
        return "\n".join(p for p in parts if p)

    def _fetch_anthropology():
        """WVS Inglehart-Welzel 文化坐标 + D-PLACE/EA 跨文化参照 → 供文化价值观派/阐释结构派使用."""
        kw = keyword or event.text[:60]
        parts: list[str] = []
        cultural = wvs.get_cultural_values(kw)
        parts.append(wvs.format_for_prompt(cultural, kw))
        region, societies_list = anthropology.get_regional_societies(kw, limit=5)
        parts.append(anthropology.format_for_prompt(region, societies_list))
        return "\n".join(p for p in parts if p)

    def _fetch_intl_relations():
        """COW NMC CINC 国力格局 → 供现实主义/自由制度主义派使用."""
        kw = keyword or event.text[:60]
        balance = intl_relations.get_power_balance(kw)
        return intl_relations.format_for_prompt(balance, kw)

    with ThreadPoolExecutor(max_workers=5) as ex:
        f_hist  = ex.submit(_fetch_history)
        f_pol   = ex.submit(_fetch_politics)
        f_soc   = ex.submit(_fetch_sociology)
        f_anth  = ex.submit(_fetch_anthropology)
        f_ir    = ex.submit(_fetch_intl_relations)
        for key, future in [
            ("history",       f_hist),
            ("politics",      f_pol),
            ("sociology",     f_soc),
            ("anthropology",  f_anth),
            ("intl_relations", f_ir),
        ]:
            try:
                results[key] = future.result(timeout=18)
            except Exception:
                results[key] = ""

    return results


def _call_lens(
    lens: Lens,
    event: NarrativeEvent,
    upstream: list[LensOutput],
    client: OpenAI,
    narrative_case: tuple[str, str] | None = None,
    knowledge_ctx: dict[str, str] | None = None,
) -> LensOutput:
    """调用单个 lens, 返回 LensOutput."""
    user_prompt = _build_user_prompt(event, upstream, lens, knowledge_ctx)
    # 经济派 + CausalRAG 已匹配到历史时期 → 注入因果路径
    if narrative_case is not None and lens.discipline == "economics":
        from hindcast import rag
        evidence = rag.retrieve_for_narrative(lens.id, narrative_case[0])
        if evidence:
            user_prompt += rag.format_evidence_for_narrative(evidence, narrative_case[1])
    raw = chat_json(
        client,
        system=lens.prompt,
        user=user_prompt,
        max_tokens=_NARRATIVE_MAX_TOKENS,
    )
    failed = bool(raw.get("_failed"))
    return LensOutput(
        lens_id=lens.id,
        discipline=lens.discipline,
        label_zh=lens.label_zh,
        label_en=lens.label_en,
        raw=raw,
        failed=failed,
        error=raw.get("_error", "") if failed else "",
    )


def _run_layer(
    lenses: list[Lens],
    event: NarrativeEvent,
    upstream: list[LensOutput],
    client: OpenAI,
    narrative_case: tuple[str, str] | None = None,
    knowledge_ctx: dict[str, str] | None = None,
) -> list[LensOutput]:
    """层内并行调用所有 lenses, 返回结果列表."""
    if not lenses:
        return []
    if len(lenses) == 1:
        return [_call_lens(lenses[0], event, upstream, client, narrative_case, knowledge_ctx)]

    results: list[LensOutput | None] = [None] * len(lenses)
    with ThreadPoolExecutor(max_workers=len(lenses)) as ex:
        future_to_idx = {
            ex.submit(_call_lens, l, event, upstream, client, narrative_case, knowledge_ctx): i
            for i, l in enumerate(lenses)
        }
        for fut in as_completed(future_to_idx):
            idx = future_to_idx[fut]
            try:
                results[idx] = fut.result()
            except Exception as e:
                lens = lenses[idx]
                results[idx] = LensOutput(
                    lens_id=lens.id,
                    discipline=lens.discipline,
                    label_zh=lens.label_zh,
                    label_en=lens.label_en,
                    raw={"_failed": True, "_error": str(e)[:200]},
                    failed=True,
                    error=str(e)[:200],
                )
    return [r for r in results if r is not None]


def run_narrative_chain(
    event: NarrativeEvent,
    client: OpenAI | None = None,
    force_disciplines: list[str] | None = None,
    include_central_brain: bool = True,
) -> NarrativeSession:
    """完整叙事 chain: 知识预取 → 历史 → router → 层级 fan-in 流 → 中枢大脑.

    Args:
        event: 事件输入 (NarrativeEvent)
        client: OpenAI client; None = 自动构建
        force_disciplines: 强制指定可选学科列表 (跳过 router; 测试 / 调试用)
        include_central_brain: 是否在最后调用中枢大脑

    Returns:
        NarrativeSession (含 outputs 按执行顺序 + router 决策 + RAG/知识库 provenance)
    """
    client = client or get_client()
    all_outputs: list[LensOutput] = []

    # ── 0. 历史时期映射 (HINDCAST_USE_RAG=1 时): 移到最前, 供知识预取使用 ──────
    narrative_case = _match_narrative_case(event, client)

    # ── 0b. 外部知识预取 (EventKG + GDELT 并行, 网络失败 graceful fallback) ────
    knowledge_ctx = _prefetch_knowledge(event, narrative_case)

    # ── 1. spacetime 层: 历史必调, 并行 + EventKG 注入 ───────────────────────
    history_lenses = discipline_lenses(_SPACETIME_DISC)
    history_outputs = _run_layer(
        history_lenses, event, [], client,
        knowledge_ctx=knowledge_ctx,
    )
    all_outputs.extend(history_outputs)

    # ── 2. Router: 历史完成后决定后续学科 ────────────────────────────────────
    router_out: RouterOutput | None = None
    if force_disciplines is not None:
        selected_discs = set(force_disciplines)
    else:
        from hindcast.router import route
        router_out = route(event, history_outputs, client)
        selected_discs = set(router_out.selected_disciplines)
        # router 豁免 economics? (22-ADR §2.4 极少发生)
        exempted = set(router_out.exempted_default)
        effective_default_on = _DEFAULT_ON_DISCS - exempted
        selected_discs |= effective_default_on

    # ── 3. 按维度层顺序跑后续学科 (institution → material → psyche_culture) ──
    for layer in LAYER_ORDER[1:]:  # 跳过 spacetime (已跑)
        layer_lenses: list[Lens] = []
        for disc in all_disciplines():
            if disc in (_SPACETIME_DISC, _CENTRAL_BRAIN_DISC):
                continue
            if disc not in selected_discs:
                continue
            for lens in discipline_lenses(disc):
                if lens.layer == layer:
                    layer_lenses.append(lens)

        if not layer_lenses:
            continue

        layer_outputs = _run_layer(
            layer_lenses, event, list(all_outputs), client,
            narrative_case=narrative_case,
            knowledge_ctx=knowledge_ctx,
        )
        all_outputs.extend(layer_outputs)

    # ── 4. 中枢大脑: 必调, 最后 ──────────────────────────────────────────────
    if include_central_brain:
        cb_lenses = discipline_lenses(_CENTRAL_BRAIN_DISC)
        if cb_lenses:
            cb_outputs = _run_layer(cb_lenses, event, list(all_outputs), client)
            all_outputs.extend(cb_outputs)

    return NarrativeSession(
        event=event,
        outputs=all_outputs,
        router=router_out,
        rag_case_id=narrative_case[0] if narrative_case else None,
        rag_case_label=narrative_case[1] if narrative_case else None,
    )
