# Hindcast Eval · 制度政治派 RAG 评测集

`political_brief_eval_set.json` — 给 RAG 那边评测 institutional_pe 学派召回质量用的 held-aside 评测集。

## 它评什么

5 个维度 (见 JSON `scoring_dimensions`):

1. **event_recall** — RAG 返回的事件覆盖 `ideal_brief.key_events` 的比例
2. **structural_recall** — RAG 返回的持续制度状态覆盖 `ideal_brief.ongoing_structural` 的比例
3. **canon_recall** — RAG 返回的典籍命中 `canon_anchors` (work + chapter + concept) 的比例
4. **fabrication_check** — RAG 返回中是否含 `fabrication_blocklist` 任一项 (含=严重失败)
5. **vintage_compliance** — RAG 返回任何 source 的发布日期 > `vintage_cutoff` 即一票否决

## 它**不**评什么

- 不评政治派 prompt 写得好不好 — 那是我们这边 prompt 工程
- 不评 4 经济派被简报影响后准不准 — 那是 `then_vs_now.json` Pass2 vs Pass1 的差分
- 不评 RAG 返回文字的"漂亮度" / ROUGE / BERTScore — 我们关心的是召回完整性, 不是 statement generation 质量

## 几条铁律

- ✅ **仅作评测** — 不入 RAG 索引, 不入任何训练; 一旦泄漏即报废
- ✅ **N=8 → 定性结论** — 不是统计置信; 用来防大坑, 不用来发论文
- ✅ **每条 anchor 的 vintage_cutoff = as_of** — runtime 硬断言违反

## 使用建议 (给 RAG)

1. 收到本文件后, 复制到你们 eval 目录, **不要复制进 raw/ 或 indices/**
2. 跑 RAG 召回的脚本, 输出每条 anchor 的 RAG 返回 → 跟本评测集对比 → 算 5 维分
3. 用 [rageval (gomate-community)](https://github.com/gomate-community/rageval) 现成工具算召回相关性
4. 出一份 markdown 简报回来: 每维度的 8 anchor 分 + 总均分 + 哪条 anchor 最弱

## 构造方法 (透明)

- 跑 `build_political_brief_eval_set.py` 重新生成
- `ideal_brief` = 直接用 v0.5.6 跑 `then_vs_now.json` 的 Pass2 political_brief
- `canon_anchors` / `fabrication_blocklist` / `scoring_notes` = 手工策展, 见脚本顶部 `CURATIONS` dict
- 如发现 ideal_brief 需要增补 (例如 RAG 实测发现该 anchor 漏了重要事件), 改`CURATIONS` 然后重跑脚本; **不要直接改 JSON**

## 版本

- v1.0.0 (2026-05-20) · N=8 · 8 anchors: 1971 Nixon / 1973 OPEC / 1979 Volcker / 1992 ERM / 2008 Lehman / 2018 Trade War / 2020 COVID / 2022 Russia
