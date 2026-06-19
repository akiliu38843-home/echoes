# 产品设计：历史回响 (Hindcast Echoes)

> 给「干活模型」的一次性实现规格。读完即可从头建到尾，无需再问产品决策。
> 本文件描述的是在**已有引擎之上**加三层（翻译层 / API / 前端），不改引擎内核。

---

## 0. 一句话产品

把一件正在发生（或可能发生）的事丢进来，系统**不预测涨跌**，而是：
找到**结构上最像的历史时刻** → 翻译成**6 个维度上对人类生活的影响** → 露出**5 个学派为什么这么判断（含它们的分歧）**。

定位基调：**知识好奇**——「原来如此，世界是这样运转的」，不是降焦虑、不是投资建议。

---

## 1. 锁定的产品决策（不要再改）

| 维度 | 决策 |
|---|---|
| 主交互形态 | **双栏镜像 + 卡片流**：顶部「当下 ↔ 历史回响」对照，下方 6 张生活影响卡片，卡片可翻面看学派推理 |
| 情绪定位 | **知识好奇**：文案讲「为什么会这样（因果机制）」，不给「你该做 X」的行动建议；学派推理是主菜不是脚注 |
| 事件来源 | **热点推荐 + 自带事件**：首页是 GDELT 驱动的热点 feed，也允许用户粘贴自己的事件 |
| 招牌功能 | **学派吵架**：把 5 学派对同一问题的不同判断并列，分歧本身是卖点 |

---

## 2. 系统架构

```
                    ┌─────────────────────────────────────────┐
现有引擎 (不改)      │  run_narrative_chain(event) → NarrativeSession │
                    │  9 个 lens 输出 + 中枢大脑 + 知识注入        │
                    └───────────────────┬─────────────────────┘
                                        │ NarrativeSession
        ┌───────────────────────────────▼──────────────────────────┐
新增 ①  │  翻译层 translator.py                                       │
        │  build_life_report(session) → LifeReport (dict)            │
        │   · 从 9 个 lens 抽证据摘要 (确定性)                          │
        │   · 1 次 LLM 调用：证据 → 6 张生活卡 + 镜像 + 吵架 (大白话)     │
        └───────────────────────────────┬──────────────────────────┘
                                        │ LifeReport JSON
新增 ②  ┌───────────────────────────────▼──────────────────────────┐
        │  API: POST /api/life-report   GET /api/trending             │
        └───────────────────────────────┬──────────────────────────┘
                                        │ HTTP JSON
新增 ③  ┌───────────────────────────────▼──────────────────────────┐
        │  前端 web/echoes.html (单页)：热点 feed → 镜像+卡片 → 翻面吵架  │
        └────────────────────────────────────────────────────────────┘
```

**现有可复用资产（已验证可用）：**
- `hindcast.chain.run_narrative_chain(event) -> NarrativeSession`
- `POST /api/narrative`（web.py:872，已存在，返回原始 session payload）
- 知识注入已接：Wikidata / GDELT / Manifesto / World Bank(嵌入) / WVS Wave7(嵌入) / D-PLACE
- FastAPI app 在 `src/hindcast/web.py`；前端在 `web/`

---

## 3. 引擎输出 JSON 形状（翻译层的输入，照抄）

`NarrativeSession.outputs` 是 `list[LensOutput]`，每个 `LensOutput.raw` 是该 lens 的 JSON。各 lens 的 `raw` 键如下：

### 历史派（spacetime 层，必调）
```jsonc
// lens_id="long_durée_structural"
{ "depth_structures": ["..."], "structural_path": "...",
  "historical_analogues": ["1870s 全球化退潮 — 结构相似性说明", "..."],
  "what_event_is_not": "...", "downstream_hint": "..." }

// lens_id="contingency_narrative"
{ "key_decision_nodes": [{"actor","time","decision","why_pivotal"}],
  "counterfactuals": [{"if_alternative","predicted_path"}],
  "actual_path_explanation": "...", "historical_analogues": ["..."], "downstream_hint": "..." }
```

### 政治派（institution 层）
```jsonc
{ "transmission_channels": ["..."], "reasoning": "...（North/Acemoglu 视角）" }
```

### 经济派（material 层，**唯一给方向/幅度的**，4 立场各一份）
```jsonc
// lens_id ∈ {austrian, monetarist, keynesian, rational_expectations}
{ "school": "...", "verdict": { "T+5": {"dir":"up|down|flat","range_pct":[lo,hi]},
                                "T+20":{"dir":"up|down|flat","range_pct":[lo,hi]} },
  "top_signals": ["..."], "historical_precedents": ["..."],
  "volatility_class": "...", "reasoning": "...", "confidence": 0.0 }
```

### 社会学派（psyche_culture 层）
```jsonc
// lens_id="structural_functional"
{ "agil_analysis": {"A_adaptation","G_goal","I_integration","L_latency"},
  "dysfunction_diagnosis": "...", "repair_mechanisms": ["..."],
  "solidarity_type": "...", "downstream_hint": "..." }

// lens_id="conflict_theory"
{ "class_power_map": {"winners","losers","neutral_or_ambiguous"},
  "inequality_anchor": "...（含 Gini 数字）", "ideology_critique": "...",
  "bourdieu_field_analysis": "...", "contradiction_exposed": "...", "downstream_hint": "..." }
```

### 人类学派（psyche_culture 层）
```jsonc
// lens_id="cultural_values"
{ "cultural_position": {"tr_sr_reading","s_se_reading","trust_reading"},
  "event_value_resonance": "...", "internal_tensions": ["..."],
  "cross_cultural_contrast": "...", "modernization_trajectory": "...", "downstream_hint": "..." }

// lens_id="interpretive_structural"
{ "thick_description": {"surface_layer","middle_layer","deep_layer"},
  "binary_opposition": {"primary","mediation_attempt"},
  "pollution_boundary": "...", "liminality_check": "...",
  "cross_cultural_analogy": "...", "downstream_hint": "..." }
```

### 中枢大脑（meta 层，最后）
```jsonc
{ "lens_breakdown": "...", "meta_judgment": "...（各派分歧的本质）",
  "reader_tool": "...", "disclaimer": "...",
  "synthesis_zh": "...约200字", "synthesis_en": "...~150 words" }
```

---

## 4. 新增模块 ①：翻译层 `src/hindcast/translator.py`

### 4.1 对外函数
```python
def build_life_report(
    session: NarrativeSession,
    client: OpenAI | None = None,
) -> dict:
    """把 9-lens 叙事结果翻译成「历史回响」生活报告 (LifeReport JSON)。
    1 次 LLM 调用。失败时 graceful fallback：返回 degraded 报告 (只填能确定性提取的字段)。
    """
```

### 4.2 处理流程
1. **确定性抽证据摘要** `_extract_evidence(session) -> dict`：
   按 lens_id 把上面每个 `raw` 里的关键字段拎出来，拼成一个紧凑 digest（控制 token）。
   重点保留：历史派 `historical_analogues` / `structural_path` / `what_event_is_not`；
   经济派每派的 `verdict`(T+5/T+20 dir+range) / `reasoning` / `confidence`；
   政治派 `reasoning`；社会学 `inequality_anchor` / `agil_analysis` / `class_power_map`；
   人类学 `cultural_position` / `event_value_resonance` / `thick_description`；
   中枢 `meta_judgment` / `synthesis_zh` / `disclaimer`。
   **同时透传知识注入里的硬数字**（Gini、信任%、文化坐标、经济 range_pct）——翻译时必须引用，禁止编造。
2. **1 次 LLM 调用** `chat_json(client, system=TRANSLATOR_PROMPT, user=digest)` → LifeReport。
3. **校验补全**：缺字段补空、cards 必须正好 6 张且 key 固定、similarity 落在 0–100。

> 复用 `hindcast.llm.chat_json`（与 chain.py 同款）；client=None 时 `get_client()`。

### 4.3 LifeReport 输出契约（前端依赖此形状）
```jsonc
{
  "event": { "text": "...", "as_of": "2026-..." },

  "echo": {                          // 双栏镜像
    "present_label": "2025 中美关税全面升级",
    "historical_label": "1870s–1890s 第一次全球化退潮",
    "similarity": 78,                // 0-100，定性结构相似度
    "similarity_is_qualitative": true,   // 永远 true，前端须标注「定性估计，非统计指标」
    "why_structural": "都是『守成大国 vs 新兴大国 + 保护主义抬头』，而非表面的贸易战相似",
    "why_not_obvious": "为什么不是 1930 大萧条：那是事件相似，结构不同",
    "other_echoes": [ {"label":"1971 尼克松冲击","similarity":61} ]  // 来自 historical_analogues 其余项
  },

  "cards": [                         // 必须正好 6 张，key 固定且按此顺序
    {
      "key": "wallet",  "icon": "💰", "title": "钱包",
      "headline": "购买力会被进口成本侵蚀",        // 现在会怎样（一句）
      "why": "为什么：关税抬高进口品价格，传导到日用消费……",  // 因果机制（知识好奇重点）
      "then": "上一次（1870s）：进口工业品价格上行，普通家庭实际购买力缩水约……",  // 历史那时
      "horizon": "约 T+12〜18 月",
      "confidence": 0.55,            // 0-1
      "confidence_note": "经济四派分歧中等；有硬数据锚",
      "data_anchors": ["美国 CPI 注入值", "经济派 T+20 range_pct"],
      "source_lenses": ["keynesian", "monetarist"]
    }
    // key 依次：wallet 💰 / job 💼 / social 🤝 / identity 🪪 / power 🏛 / tempo ⏳
  ],

  "debate": {                        // 学派吵架（招牌）
    "question": "这件事会怎样？",
    "voices": [
      { "lens": "keynesian", "label_zh": "经济·凯恩斯派",
        "stance": "短期物价↑但可刺激本土就业", "data_anchor": "T+20 range +3〜8%" },
      { "lens": "conflict_theory", "label_zh": "社会·冲突派",
        "stance": "这只是掩盖了贫富撕裂", "data_anchor": "美国 Gini 39.8 且在升" }
      // 4-6 条，覆盖经济/社会/人类/历史
    ],
    "crux": "他们为什么吵：范畴/时间尺度/因果语言不同（取自中枢 meta_judgment）"
  },

  "meta": {
    "synthesis_zh": "……（中枢 synthesis_zh 原文）",
    "disclaimer": "……（中枢 disclaimer 原文）",
    "uncertainty_note": "本报告是结构类比与多学派叙事，非投资建议，非未来预测（21-ADR）"
  }
}
```

### 4.4 六张卡片的「学派 → 生活维度」映射表（写进 TRANSLATOR_PROMPT）

| key | icon | 维度 | 主要取自 | 这张卡讲什么 |
|---|---|---|---|---|
| `wallet` | 💰 | 钱包 | 经济派 verdict(T+5/T+20 dir+range) + 凯恩斯/货币派 reasoning | 物价/存款/汇率 → 购买力会怎样、为什么 |
| `job` | 💼 | 饭碗 | 经济派 transmission + 社会学 `agil_analysis.A_adaptation`（失业数据） | 哪些行业/谁先受冲击、要多久 |
| `social` | 🤝 | 人际 | 社会学 `inequality_anchor`(Gini) + `I_integration`(信任%) | 社会信任/撕裂会怎样、机制 |
| `identity` | 🪪 | 认同 | 人类学 `event_value_resonance` + `internal_tensions` + 文化坐标 | 归属/认同/文化战争如何被触动 |
| `power` | 🏛 | 规则 | 政治派 `reasoning` + `transmission_channels` | 谁掌权/政策走向、制度约束 |
| `tempo` | ⏳ | 节奏 | 历史派 `depth_structures` + `structural_path`（时间尺度） | 影响多久才显现、上次花了多久 |

### 4.5 TRANSLATOR_PROMPT 必须包含的硬约束
- **知识好奇语气**：每张卡的 `why` 讲因果机制，**禁止**写「建议你买/卖/换工作」式行动指令。
- **必须引用硬数字**：digest 里给了 Gini/信任%/经济 range_pct/文化坐标的，对应卡片 `data_anchors` 必须落地具体数字；没有的留空，**不许编**。
- **`then`（历史那时）只能基于历史派给的 analogue**：描述「那个时期普通人经历了什么」，写不出就填 `"（缺历史细节）"`，禁止虚构具体数字。
- **similarity 是定性估计**：输出 0-100 但 `similarity_is_qualitative` 恒为 true。
- **confidence 受经济派 confidence + 数据锚有无约束**：四派分歧大或无数据锚 → confidence ≤ 0.4。
- 严格输出 JSON，无多余文字。

---

## 5. 新增模块 ②：API（改 `src/hindcast/web.py`）

### 5.1 `POST /api/life-report`
```python
class LifeReportRequest(BaseModel):
    text: str
    as_of: str = "<今天>"
    mode: Literal["current", "historical"] = "current"

@app.post("/api/life-report")
def post_life_report(req: LifeReportRequest):
    from hindcast.chain import run_narrative_chain
    from hindcast.translator import build_life_report
    from hindcast.narrative_types import NarrativeEvent
    event = NarrativeEvent(text=req.text, as_of=req.as_of, mode=req.mode)
    session = run_narrative_chain(event)
    return build_life_report(session)
```
- 耗时 ~30–90s（chain）+ ~5–10s（翻译）。返回 LifeReport JSON（§4.3）。
- 也保留原 `/api/narrative`（给想看原始 9-lens 的高级用户）。

### 5.2 `GET /api/trending`
热点 feed。**第一版做简化**：内置一个 8–12 条种子事件列表（覆盖经济/地缘/政治），可选用 GDELT 富化标题。
```python
@app.get("/api/trending")
def get_trending():
    # v1: 返回内置 seed 列表 [{id, title, blurb, as_of}]
    # v2(可选): 用 hindcast.knowledge.gdelt 拉近 30 天热门主题富化
    return {"events": SEED_TRENDING}
```
> 种子列表写在 web.py 顶部常量 `SEED_TRENDING`，每条 `{id, title, blurb, as_of}`。

---

## 6. 新增模块 ③：前端 `web/echoes.html`（单页，原生 JS，无框架）

风格对齐现有 `web/index-v2.html`（同配色/字体/卡片圆角）。三屏一页内切换：

### 屏 1 · 热点 feed（落地页）
- `GET /api/trending` 渲染卡片列表；每条可点。
- 顶部一个输入框「发生了什么？」+ 提交按钮 → 走自带事件。
- 点击任一条 → `POST /api/life-report` → loading（提示「正在请 5 个学派会诊，约 1 分钟」）→ 屏 2。

### 屏 2 · 双栏镜像 + 卡片流（主屏）
- 顶部双栏：左「当下 `present_label`」↔ 右「历史回响 `historical_label`」+ 相似度徽章 `similarity%`（旁注小字「定性估计」）。
- 镜像下方一行：`why_not_obvious`（「为什么不是那个最顺嘴的对比」）+ `other_echoes` 可点切换。
- 下方 6 张卡片网格（2×3）：正面显示 `icon / title / headline / horizon / confidence 条`。
- 卡片**可翻面**（CSS flip）：背面显示 `why` + `then` + `data_anchors` + `source_lenses`。

### 屏 3 · 学派吵架（从主屏「他们怎么看？」按钮进入，或浮层）
- 渲染 `debate.voices`：每条一行「学派名 + stance + data_anchor」，用不同色块区分学科。
- 底部 `debate.crux`（他们为什么吵）+ `meta.synthesis_zh` + `meta.disclaimer` + `meta.uncertainty_note`。

### 前端硬要求
- 所有「未来/预测」措辞旁必须有 `uncertainty_note` 可见。
- similarity 徽章旁必须有「定性估计，非统计指标」。
- confidence 用进度条 + 文字双显示。
- 移动端优先（卡片单列堆叠）。

---

## 7. 文件清单 & 改动点

| 操作 | 文件 | 说明 |
|---|---|---|
| 新建 | `src/hindcast/translator.py` | 翻译层（§4），含 `build_life_report` + `_extract_evidence` + `TRANSLATOR_PROMPT` |
| 改 | `src/hindcast/web.py` | 加 `POST /api/life-report` + `GET /api/trending` + `SEED_TRENDING` 常量 + 两个 Pydantic model |
| 新建 | `web/echoes.html` | 单页前端（§6） |
| 新建 | `tests/test_translator.py` | 翻译层测试（§9） |
| 改(可选) | `src/hindcast/cli.py` | 加 `hindcast echoes "<事件文本>"` 子命令，命令行直接出 LifeReport（调试用） |

---

## 8. 实现步骤（分阶段，带验收）

**阶段 A — 翻译层（先跑通，不依赖前端）**
1. 写 `_extract_evidence(session)`：用一个已有 NarrativeSession（或 mock）验证 digest 完整。
2. 写 `TRANSLATOR_PROMPT` + `build_life_report`。
3. 验收：`hindcast echoes "美国对华关税全面升级"`（或直接脚本调）能产出合法 LifeReport，6 张卡齐全、Gini/range 数字落地、无行动建议措辞。

**阶段 B — API**
4. 加 `/api/life-report` + `/api/trending` + `SEED_TRENDING`。
5. 验收：`curl -X POST .../api/life-report -d '{"text":"...","as_of":"2026-06-18"}'` 返回 §4.3 形状；`/api/trending` 返回种子列表。

**阶段 C — 前端**
6. 写 `web/echoes.html` 三屏。
7. 验收：浏览器打开 → feed 点一条 → 看到镜像+6卡 → 翻面看推理 → 进吵架屏。

**阶段 D — 收尾**
8. 跑全量测试（含新 `test_translator.py`）；更新 README 加「历史回响」入口说明。

---

## 9. 测试要求 `tests/test_translator.py`

用 **mock NarrativeSession**（手搓 9 个 LensOutput.raw，照 §3 形状），**不打真 LLM**：
- `test_extract_evidence_covers_all_lenses`：digest 含全部 9 lens 关键字段。
- `test_life_report_shape`：mock `chat_json` 返回固定 JSON → `build_life_report` 产出恰好 6 张卡、key 顺序固定、similarity∈[0,100]、`similarity_is_qualitative is True`。
- `test_graceful_fallback`：`chat_json` 抛错 → 返回 degraded 报告（不崩，cards 可为占位）。
- `test_no_action_language`（轻量）：断言 prompt 文本里含「禁止行动建议」约束串。

> 运行环境：`PYTHONPATH=src .venv/bin/python -m pytest tests/ -q`
> （注意：本机 venv 是 py3.14；`uv run` 因 mcp 依赖 py>=3.10 解析失败，直接用 `.venv/bin/python`。）

---

## 10. 设计红线（不可破）

1. **不是投资建议、不预测涨跌方向给用户决策**——经济派的 dir/range 只用来生成「购买力会怎样」的**叙事**，前端永远带 `uncertainty_note`（21-ADR）。
2. **诚实暴露不确定**——similarity 标「定性」，confidence 真实反映分歧，数据缺失写「缺」而非编造。符合用户既定偏好（诚实 FAIL 优于硬过线）。
3. **知识好奇语气**——讲「为什么」，不教「做什么」。
4. **硬数字不许编**——只能用 digest 里透传的注入数据（Gini/信任%/文化坐标/经济 range）。
5. **引擎内核不改**——只在其输出之上加翻译/API/前端三层。

---

## 11. 给干活模型的起手提示

- 引擎入口就一个：`from hindcast.chain import run_narrative_chain`。
- 大白话翻译 + 6 卡 + 镜像 + 吵架，**全部由 `translator.py` 的单次 LLM 调用产出**；Python 只做确定性抽取与校验。
- 先用 mock 把 `translator.py` 和 `test_translator.py` 跑绿，再接 API，最后接前端。
- 不确定 lens 的 raw 形状时，回看 §3（已是实测形状）。
