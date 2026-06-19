"""Build the political-brief RAG eval set (N=8 anchors, held-aside).

v1.1.0 (2026-05-21): canon_anchors 加 concept_en 英文字段
  — 因为 RAG 索引全是英文论文 (NBER / Nobel lectures / JEP),
    v1.0 的中文 concept 触发 token Jaccard ≈ 0 → 实际只测了 work_hit, 没测概念契合.
    见 RAG_TO_HINDCAST_REPLY_2026-05-21_CANON_RECALL_REPORT_V1.md §0.

设计参考:
- UNBench (arXiv 2502.14122) — statement-generation task 的 input/output 结构
- RAGEval / rageval — 召回相关性的指标维度
- 我们 19-ADR — vintage 一票否决落 runtime 红线

铁律:
1) **仅作评测; 不入 RAG 索引; 不入任何训练**
2) **N=8 → 定性/方向性结论, 非统计显著** (功效不足)
3) **每条 anchor 的 `vintage_cutoff = as_of`** — 任何返回的 source_date > as_of 即 fabrication
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC_JSON = ROOT / "src/hindcast/data/then_vs_now.json"
OUT_JSON = ROOT / "eval/political_brief_eval_set.json"


# ─── 手工策展: 每条 anchor 的典籍命中清单 + 易幻觉黑名单 + 评分要点 ───
#
# canon_anchors 字段:
#   work / chapter / concept (中文) / concept_en (英文, v1.1 新增) / why_relevant
# work + chapter + concept 三件齐才算高命中, 缺一项给部分分.
# concept_en 给 RAG 评测器做英文索引侧的相似度计算.
CURATIONS: dict[str, dict] = {
    "1971-08-12": {
        "canon_anchors": [
            {"work": "North 1990", "chapter": "ch.5 Informal Constraints",
             "concept": "制度变迁的非市场来源 — 行政命令重塑国际货币安排",
             "concept_en": "non-market sources of institutional change — executive action reshaping the international monetary order",
             "why_relevant": "Camp David 决策本质是 informal political coordination 颠覆 Bretton Woods 形式规则"},
            {"work": "Olson 1965", "chapter": "ch.4 Group Sizes & Selective Incentives",
             "concept": "国际债权人 (法/瑞) vs 美国国内选民 — 后者更大、更分散、政治权重更高",
             "concept_en": "international creditors (France, Switzerland) vs US domestic voters — large dispersed domestic constituency outweighs concentrated foreign creditors",
             "why_relevant": "Burns 受 Nixon 选举年压力 = 国内大集团激励压倒分散外部债权人"},
            {"work": "Acemoglu NBER (Institutions as Fundamental Cause 2005)",
             "concept": "central bank independence as institutional capacity",
             "concept_en": "central bank independence as institutional capacity; formal independence vs substantive autonomy",
             "why_relevant": "CBI=7.5 名义高但实际被夺权 — 制度形式 vs 实质性能力分裂"},
            {"work": "Dixit 2004", "chapter": "ch.3 Self-Governance vs State",
             "concept": "alternative governance under weak international rules",
             "concept_en": "alternative modes of governance under weak international rules; private substitutes when collective enforcement fails",
             "why_relevant": "Bretton Woods 兜底失效后, 各国开始寻求双边/区域替代清算"},
        ],
        "fabrication_blocklist": [
            "Plaza Accord (1985, 14 年后)",
            "Reagan tax cut (1981)",
            "Volcker disinflation (1979)",
            "任何 1971-08-12 之后才发生的事件",
        ],
        "scoring_notes": (
            "政治派该抓的核心: (a) Camp David 闭门=制度性政策事件即将出台; "
            "(b) Burns 公开承压=CBI 表面高但实质受损; (c) 法/瑞兑金=外部退出选项激活. "
            "易遗漏盲区: 政治派可能只盯 Nixon-Burns 二人, 忽略 Connally 财长的关键作用 "
            "(他是真正的强势鹰派建议人). 弱信号: 国内 1972 选举年压力 (政治激励)."
        ),
    },
    "1973-10-05": {
        "canon_anchors": [
            {"work": "Olson 1965", "chapter": "ch.1 Cartel Problem",
             "concept": "OPEC 作为成功卡特尔 — 小群体 + selective incentive (产油额配额制)",
             "concept_en": "OPEC as a successful cartel — small-group cooperation with selective incentives (production quotas)",
             "why_relevant": "OPEC 维也纳 10/16 重新评价机制 = Olson 小群体合作模型经典案例"},
            {"work": "North 1990", "chapter": "ch.10 Institutional Change via Shocks",
             "concept": "外生冲击 (战争+禁运) 重塑长期能源-金融制度",
             "concept_en": "exogenous shocks (war and embargo) reshaping long-run energy and financial institutions",
             "why_relevant": "禁运启动 petrodollar recycling, 黄金重新成为通胀对冲制度"},
            {"work": "Acemoglu NBER (Colonial Origins 2001)",
             "concept": "资源富集国的攫取性制度",
             "concept_en": "extractive institutions in resource-rich states; petro-state extractive elite politics",
             "why_relevant": "OPEC 国家普遍攫取性 — 卡特尔行为符合 extractive elite 模型"},
            {"work": "Dixit 2004", "chapter": "ch.4 Trade & Embargo",
             "concept": "战争状态下贸易制度被武器化",
             "concept_en": "trade institutions weaponized during wartime — embargo as alternative governance under conflict",
             "why_relevant": "禁运作为 alternative governance — 当国际贸易规则失效时的政治工具"},
        ],
        "fabrication_blocklist": [
            "1979 Iranian Revolution",
            "1980 Volcker shock",
            "Carter energy crisis (后续语义)",
            "任何 1973-10-05 之后才发生的事件",
        ],
        "scoring_notes": (
            "政治派该抓的核心: (a) 中东军事调动 + 以色列总动员=战争前夜地缘冲击; "
            "(b) OPEC 维也纳会议=卡特尔机制激活; (c) Sadat '准备牺牲' 表态=政治承诺信号. "
            "易遗漏盲区: 1973 GPR 数据极差, 早年缺失; 政治派可能过度依赖 GPR 30日均值 (=2.5) "
            "而忽略事件窗的定性信号. 该案例下 ongoing_structural 比 key_events 更重要."
        ),
    },
    "1979-10-05": {
        "canon_anchors": [
            {"work": "North 1990", "chapter": "ch.6 Formal vs Informal Constraints",
             "concept": "Volcker 操作程序变更 = formal rule change 制度化反通胀承诺",
             "concept_en": "Volcker's operating-procedure change as a formal rule change institutionalizing the anti-inflation commitment",
             "why_relevant": "从 Fed funds targeting 转向 reserves targeting 是规则层面变革, 非自由裁量"},
            {"work": "Acemoglu NBER (Institutions Fundamental Cause 2005)",
             "concept": "央行独立性作为制度刚性来源",
             "concept_en": "central bank independence as source of institutional rigidity and credibility",
             "why_relevant": "Carter 不干预 Volcker 决策 (CBI=6.0) = 行政自我克制的制度信号"},
            {"work": "Dixit 2004", "chapter": "ch.2 Rule-Based vs Discretion",
             "concept": "规则承诺 (precommitment) 击败短期政治权宜",
             "concept_en": "rule-based commitment (precommitment) defeating short-term political expediency",
             "why_relevant": "Volcker '通胀必须以失业为代价控制' 是 commitment device, 不是预测"},
            {"work": "Olson 1965", "chapter": "ch.3 Large Groups & Public Goods",
             "concept": "反通胀作为公共物品 — 集中成本 (失业者) vs 分散收益 (所有持币者)",
             "concept_en": "anti-inflation as a public good — concentrated costs on the unemployed vs dispersed benefits to all currency holders",
             "why_relevant": "Volcker 故意选择政治不可持续路径 = 短期 unpopular 但长期 institutional payoff"},
        ],
        "fabrication_blocklist": [
            "Reagan election (1980-11)",
            "1981 recession 后续叙事",
            "Plaza Accord (1985)",
            "任何 1979-10-05 之后才发生的事件",
        ],
        "scoring_notes": (
            "政治派该抓的核心: (a) Volcker 公开承诺 (commitment device, North 视角); "
            "(b) Tehran 大使馆事件前奏 (1979-11 才爆发, 当时已有信号); (c) Carter 政府"
            "不阻止 Fed = CBI 实质性测试. 易遗漏盲区: 政治派容易把 Volcker 当英雄叙事, "
            "忽略 Carter 行政方的'放手'本身就是制度信号 (后被 Reagan 继承)."
        ),
    },
    "1992-09-15": {
        "canon_anchors": [
            {"work": "North 1990", "chapter": "ch.7 Path Dependence",
             "concept": "欧洲货币联盟的历史路径锁定 — ERM 是 EMU 前奏",
             "concept_en": "path dependence of European monetary union — ERM as precursor to EMU; crisis accelerates rather than reverses integration",
             "why_relevant": "Black Wednesday 不是 ERM 终结, 反而是 EMU 加速 = 危机后路径更深"},
            {"work": "Olson 1965", "chapter": "ch.5 Large Groups Problem",
             "concept": "ERM 作为大集团承诺机制的失败 — 各国央行集体行动困境",
             "concept_en": "ERM as failure of large-group commitment mechanism — collective-action problem among national central banks (Bundesbank vs others)",
             "why_relevant": "Bundesbank 不愿降息 (国家利益) vs ERM 平价 (集体物品) = Olson 经典紧张"},
            {"work": "Acemoglu NBER (Unbundling Institutions 2003)",
             "concept": "货币主权与财政主权的分离",
             "concept_en": "separation of monetary sovereignty from fiscal sovereignty; design flaws in partial monetary union",
             "why_relevant": "UK 退出 ERM 后保留央行+财政一体性, 暴露 ERM 设计缺陷"},
            {"work": "Dixit 2004", "chapter": "ch.3 Self-Governance Modes",
             "concept": "汇率机制的自律 vs 央行干预",
             "concept_en": "exchange-rate mechanism self-discipline versus central-bank intervention; limits of state-level governance tools",
             "why_relevant": "BoE 数十亿美元干预失败 = 国家级 governance 工具的极限"},
        ],
        "fabrication_blocklist": [
            "1999 Euro launch",
            "2010 Greek debt crisis",
            "2012 'whatever it takes' Draghi",
            "任何 1992-09-15 之后才发生的事件",
        ],
        "scoring_notes": (
            "政治派该抓的核心: (a) 意大利里拉 9/13 紧急贬值=前哨信号; "
            "(b) Soros 公开 '不可持续' 表态=私人行为者 vs 国家承诺; "
            "(c) Bundesbank 拒绝协助 (隐含)=国家主权高于联盟承诺. "
            "易遗漏盲区: 政治派可能聚焦 Soros 叙事, 忽略 Bundesbank 的关键不作为, "
            "后者才是制度层面真正的'制度承诺失效'."
        ),
    },
    "2008-09-14": {
        "canon_anchors": [
            {"work": "Ostrom 1990", "chapter": "ch.3 Common-Pool Governance",
             "concept": "金融稳定作为 commons; 监管者作为 commons 治理机构",
             "concept_en": "financial stability as a common-pool resource; regulators as commons governance institution; tragedy of the commons in systemic risk",
             "why_relevant": "Fannie/Freddie 接管 = 中央国家替代市场作为 commons 守护者"},
            {"work": "North 1990", "chapter": "ch.6 Formal vs Informal Constraints",
             "concept": "bankruptcy law (formal) vs 'too big to fail' (informal)",
             "concept_en": "formal bankruptcy law versus informal 'too big to fail' norm; selective enforcement of informal constraints",
             "why_relevant": "Lehman 让倒 vs Bear/AIG 救助 = informal rule 在选择性执行"},
            {"work": "Olson 1965", "chapter": "ch.2 Collective Action Failures",
             "concept": "金融机构利益集中 (银行) vs 救助成本分散 (纳税人)",
             "concept_en": "concentrated bank gains vs dispersed taxpayer bailout costs; Olson asymmetry in financial-crisis politics",
             "why_relevant": "TARP 谈判过程典型 Olson 模型 — 集中收益 vs 分散成本的政治不对称"},
            {"work": "Acemoglu NBER (Institutions Fundamental Cause 2005)",
             "concept": "危机时国家能力测试 — 制度框架被压到极限",
             "concept_en": "state-capacity stress test during crisis — institutional framework pushed to its limits and temporarily expanded",
             "why_relevant": "Fed-Treasury 协调 = 制度框架在危机下的临时性扩张, 后写入新规"},
        ],
        "fabrication_blocklist": [
            "Dodd-Frank (2010-07 签署)",
            "QE2 / QE3 后续 Fed 行动",
            "European debt crisis (2010+)",
            "任何 2008-09-14 之后才发生的事件",
        ],
        "scoring_notes": (
            "政治派该抓的核心: (a) Fannie/Freddie 接管=国家担保化转向; "
            "(b) Lehman 周末并购失败=私人自救机制崩盘; (c) AIG 评级降=系统性风险跨机构扩散; "
            "(d) Paulson-Bernanke 周末闭门=制度框架被临时性扩张. "
            "易遗漏盲区: 政治派可能只看 Lehman, 忽略 Fannie/Freddie 比 Lehman 更早=制度信号. "
            "Ostrom 视角的关键: 金融稳定是公共池塘资源, 监管失败是 commons 治理崩溃."
        ),
    },
    "2018-03-21": {
        "canon_anchors": [
            {"work": "Olson 1965", "chapter": "ch.1 Logic of Collective Action",
             "concept": "集中收益分散成本 — 钢铝工人 vs 消费者",
             "concept_en": "concentrated benefits, dispersed costs — steel/aluminum workers vs consumers; political viability of trade protectionism",
             "why_relevant": "贸易保护主义的政治可行性=Olson 经典逻辑"},
            {"work": "Acemoglu (Why Nations Fail 2012; NBER versions)",
             "concept": "extractive elite politics in democracy — 国内联盟驱动对外攫取",
             "concept_en": "extractive elite politics within a democracy — domestic coalitions driving external extraction; protectionism as elite-coalition policy",
             "why_relevant": "Section 301 总统单边授权扩张 = 行政权从程序约束中收回"},
            {"work": "North 1990", "chapter": "ch.11 Institutional Change",
             "concept": "行政权扩张作为制度路径依赖的临界点",
             "concept_en": "executive-power expansion as a path-dependence tipping point in institutional change; reactivation of dormant statutory authority",
             "why_relevant": "Section 301 工具激活后回撤政治成本高, 路径锁定"},
            {"work": "Dixit 2004", "chapter": "ch.4 International Governance Failures",
             "concept": "WTO 多边规则失能下的单边裁量替代",
             "concept_en": "unilateral discretion replacing failed WTO multilateral rules; national-security exception as alternative governance",
             "why_relevant": "国安例外条款扩张 = 多边治理被双边武器化替代"},
        ],
        "fabrication_blocklist": [
            "Phase One trade deal (2020-01)",
            "Trump-Xi G20 truce (2018-12)",
            "CHIPS Act (2022)",
            "任何 2018-03-21 之后才发生的事件",
        ],
        "scoring_notes": (
            "政治派该抓的核心: (a) USTR Section 301 报告完成=行政工具激活; "
            "(b) Trump 公开 '关税势在必行'=承诺锁定; (c) Powell 接任未变 Fed 路径=CBI 稳固. "
            "易遗漏盲区: 政治派可能只看双边贸易戏剧, 忽略 Section 301 机制本身是 30 年代法案被激活 "
            "= North 路径依赖最经典案例 (沉睡条款 30 年, 一旦激活就难收回)."
        ),
    },
    "2020-02-28": {
        "canon_anchors": [
            {"work": "Ostrom 1990", "chapter": "ch.2 Tragedy of the Commons Critique",
             "concept": "公共卫生作为全球 commons; 各国治理能力 vs 国际协调失败",
             "concept_en": "public health as a global commons; national governance capacity versus international coordination failure",
             "why_relevant": "WHO 升级警告 + 各国封城孤立行动 = 缺乏 commons 治理的典型反例"},
            {"work": "Olson 1965", "chapter": "ch.1 Free-Rider Problem",
             "concept": "全球疫情响应的集体行动困境 — 大集团免费搭车",
             "concept_en": "global pandemic response as a collective-action problem — large-group free-riding by states",
             "why_relevant": "各国互相依赖防疫但又互相设关 = Olson 大集团失败模型"},
            {"work": "Acemoglu NBER (Institutions Fundamental Cause 2005)",
             "concept": "国家治理能力 (state capacity) 在突发危机的可见性",
             "concept_en": "state capacity becomes visible during sudden crisis; comparative institutional response to exogenous shock",
             "why_relevant": "意大利 / 韩国对比 = 国家能力差异在同等冲击下显化"},
            {"work": "North 1990", "chapter": "ch.9 Adaptive Efficiency",
             "concept": "制度适应性 — 紧急权扩张是否会回收",
             "concept_en": "institutional adaptive efficiency — will emergency-power expansion be retracted or become permanent",
             "why_relevant": "Powell 紧急表态准备行动 = Fed 制度弹性的政治信号"},
        ],
        "fabrication_blocklist": [
            "CARES Act (2020-03-27)",
            "Operation Warp Speed (2020-05+)",
            "Vaccine rollout (2020-12+)",
            "任何 2020-02-28 之后才发生的事件",
        ],
        "scoring_notes": (
            "政治派该抓的核心: (a) WHO 2/25 警告升级=国际治理机构动作; "
            "(b) 意大利/韩国封城=国家级紧急治理工具被激活; (c) Powell 紧急表态=央行 commitment device. "
            "易遗漏盲区: 政治派容易聚焦 Powell, 忽略 WHO 这条 — WHO 才是 commons 治理"
            "的形式机构, 它的警告升级是政治信号 (各国可以据此动员)."
        ),
    },
    "2022-02-23": {
        "canon_anchors": [
            {"work": "North 1990", "chapter": "ch.10 International Institutional Change",
             "concept": "规则的国际化与去美元化压力",
             "concept_en": "international institutional change — weaponization of reserve currency triggers de-dollarization pressure; SWIFT neutrality broken",
             "why_relevant": "俄央行储备冻结 = 国际金融规则被武器化, SWIFT 中立性破灭"},
            {"work": "Olson 1965", "chapter": "ch.4 Large vs Small Group Coalitions",
             "concept": "制裁联盟成本 — G7 vs 全球南方",
             "concept_en": "sanctions coalition costs — G7 small-group cooperation versus Global South free-riding (Olson coalition sizing)",
             "why_relevant": "西方联盟集中行动 vs 全球分散反应 = Olson 联盟规模理论"},
            {"work": "Acemoglu NBER (Reversal of Fortune 2002)",
             "concept": "资源经济体在制度冲击下的脆弱性",
             "concept_en": "vulnerability of resource-extractive economies under institutional shock; reversal of fortune via sanctions",
             "why_relevant": "俄罗斯石油经济+攫取性制度 = Acemoglu 模型预测的脆弱性"},
            {"work": "Dixit 2004", "chapter": "ch.5 Alternative Governance Modes",
             "concept": "非国家武器化金融 (SWIFT 切断, 储备冻结)",
             "concept_en": "weaponized financial infrastructure as alternative governance — SWIFT cutoff and central-bank reserve freeze as state-coercive tools",
             "why_relevant": "金融基础设施成为政治工具 = Dixit 'alternative governance' 反面应用"},
        ],
        "fabrication_blocklist": [
            "Bakhmut battle (2022-05+)",
            "G7 oil price cap (2022-12)",
            "Wagner mutiny (2023-06)",
            "任何 2022-02-23 之后才发生的事件",
        ],
        "scoring_notes": (
            "政治派该抓的核心: (a) 普京承认 DPR/LPR=主权重划信号; (b) 西方预先制裁=承诺锁定; "
            "(c) GPR 7日内显著上冲=战争前夜典型. 易遗漏盲区: 政治派可能聚焦"
            "战争本身, 忽略储备冻结的制度突破性 — 这是首次系统性 G7 联合储备武器化, "
            "比禁运、制裁更具有 international institutional change 意义 (North 视角)."
        ),
    },
}


def build_eval_set() -> dict:
    src = json.loads(SRC_JSON.read_text())
    anchors = []
    for date, curation in CURATIONS.items():
        if date not in src:
            raise KeyError(f"{date} 在 then_vs_now.json 中不存在")
        a = src[date]
        p2_brief = a["pass2_revised"].get("political_brief") or {}
        anchors.append({
            "as_of": date,
            "label": a["label"],
            "event": a["event"],
            "vintage_cutoff": date,
            "ground_truth_xau": a["ground_truth"],
            "ideal_brief": {
                "key_events": p2_brief.get("key_events") or [],
                "ongoing_structural": p2_brief.get("ongoing_structural") or [],
                "reasoning": p2_brief.get("reasoning") or "",
                "what_could_be_wrong": p2_brief.get("what_could_be_wrong") or "",
            },
            "canon_anchors": curation["canon_anchors"],
            "fabrication_blocklist": curation["fabrication_blocklist"],
            "scoring_notes": curation["scoring_notes"],
            "machine_baseline_v0_5_6": {
                "source": "then_vs_now.json pass2_revised political_brief, 2026-05-20 跑",
                "_note": "ideal_brief 直接用此 baseline; 后续如发现召回更完整版本可手工增补",
            },
        })

    return {
        "schema_version": "1.1.0",
        "release_date": "2026-05-21",
        "changelog": {
            "1.1.0": "canon_anchors 每条加 concept_en 英文字段 — RAG 索引为英文, 中文 concept 的 Jaccard 算分等于零 (见 RAG_TO_HINDCAST_REPLY_2026-05-21_CANON_RECALL_REPORT_V1.md §0)",
            "1.0.0": "首版, 8 anchor × 4 canon + blocklist + scoring_notes",
        },
        "purpose": (
            "制度政治经济学派 (institutional_pe) RAG 召回质量评测集; "
            "评测两接口 retrieve_political_events + retrieve_political_canon 的召回完整性、"
            "fabrication 抗性、vintage 合规性."
        ),
        "borrowed_from": [
            "UNBench arXiv 2502.14122 — statement-generation task 的 input/output 结构借鉴",
            "RAGEval (OpenBMB) — 召回相关性指标",
            "rageval (gomate-community) — 召回-真值对比工具",
            "我们 19-ADR — vintage 一票否决落 runtime",
        ],
        "scoring_dimensions": {
            "event_recall": (
                "RAG 返回的 events 覆盖 ideal_brief.key_events 的比例. "
                "Jaccard 或语义匹配 (Sentence-BERT) ≥ 0.7 算命中. 部分覆盖按比例给分."
            ),
            "structural_recall": (
                "RAG 返回的 ongoing_structural_signals 覆盖 ideal_brief.ongoing_structural 的比例. "
                "数值型 (CBI=7.5 等) 要求误差 ≤ 5%; 文本型语义匹配 ≥ 0.7."
            ),
            "canon_recall": (
                "RAG 返回的 typikön anchors 覆盖 canon_anchors 的比例. "
                "命中 = work 一致 (必须) + chapter 一致 (加分) + concept 语义匹配 (加分). "
                "三件齐全=1.0, 仅 work 命中=0.4. "
                "**v1.1: 概念匹配优先用 concept_en 英文字段** (索引为英文语料)."
            ),
            "fabrication_check": (
                "RAG 返回的 events / canon citations 中, 含 fabrication_blocklist 任一项 = 严重失败. "
                "建议: per-anchor 二值 pass/fail 而非比例分."
            ),
            "vintage_compliance": (
                "RAG 返回的任何 source 的 source_publish_date > vintage_cutoff = 一票否决. "
                "运行时硬断言违反应抛 (见我们 HINDCAST_TO_RAG_REQUEST §1 加固 #3)."
            ),
        },
        "eval_set_constraints": {
            "is_held_aside": True,
            "do_not_train_on": True,
            "do_not_index_on": True,
            "n_anchors": len(anchors),
            "statistical_confidence": "N=8 → 定性/方向性结论, 非统计置信",
            "advisory": "此集合一旦泄漏进 RAG 训练或索引语料, 即报废, 须重新构建.",
        },
        "anchors": anchors,
    }


def main() -> int:
    eval_set = build_eval_set()
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(eval_set, ensure_ascii=False, indent=2))
    print(f"✓ wrote {len(eval_set['anchors'])} anchors → {OUT_JSON}")
    print(f"  schema_version: {eval_set['schema_version']}")
    print(f"  size: {OUT_JSON.stat().st_size} bytes")
    # 自检: 每条 canon_anchor 都该有 concept_en
    missing = 0
    for a in eval_set["anchors"]:
        for c in a["canon_anchors"]:
            if not c.get("concept_en"):
                missing += 1
                print(f"  ⚠ missing concept_en: {a['as_of']} · {c.get('work')}")
    if missing == 0:
        n_total = sum(len(a["canon_anchors"]) for a in eval_set["anchors"])
        print(f"  ✓ concept_en 自检: {n_total}/{n_total} 条齐全")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
