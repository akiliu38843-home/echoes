"""外部知识库客户端 (22-ADR 叙事路径 RAG 扩展).

子模块:
  event_kg    — Wikidata SPARQL mwapi (历史派, 1亿+条目含历史事件)
  gdelt       — GDELT DOC API v2 (政治派, 近期全球政治新闻)
  manifesto   — Manifesto Project API (政治派, 政党纲领语料, 需 MANIFESTO_API_KEY)
  sociology    — World Bank 嵌入式数据 (社会学派, Gini/政府支出/失业率, 14国)
  wvs          — WVS Wave 7 嵌入式数据 (社会学/人类学派, Inglehart-Welzel 文化坐标, 35国)
  anthropology — D-PLACE/Ethnographic Atlas GitHub raw CSV (社会学派, 跨文化比较)

启用方式: 无需额外 env flag, 仅依赖网络可达性 + requests 已安装.
失败时全部 graceful fallback → 空字符串, 不影响 chain 主流程.
"""

# 本机代理 (见 CLAUDE.md 全局规则)
_PROXY = {
    "http": "http://127.0.0.1:7897",
    "https": "http://127.0.0.1:7897",
}
