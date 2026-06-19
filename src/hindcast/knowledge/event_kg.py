"""历史事件知识库客户端 (历史派 RAG).

使用 Wikidata SPARQL + mwapi 搜索服务检索历史事件.
Wikidata: 1 亿+ 条目, 含大量历史事件与时间戳, 免费公开.
SPARQL 端点: https://query.wikidata.org/sparql

原计划接 EventKG (eventkginterface.l3s.uni-hannover.de) 但端点不稳定 (500/HTML).
Wikidata 覆盖度更高且 SLA 更强, 作为替代方案.

用途: 给历史 lens (long_durée_structural / contingency_narrative) 注入
      "知识图谱中检索到的结构相似历史事件", 补充 LLM 训练数据记忆以外的细节.
"""
from __future__ import annotations

from typing import Any

SPARQL_ENDPOINT = "https://query.wikidata.org/sparql"
_TIMEOUT = 12  # Wikidata mwapi 稍慢于简单查询
_USER_AGENT = "HindcastRAG/0.5 (narrative knowledge retrieval; non-commercial educational use)"


def is_available() -> bool:
    """Check if requests is importable."""
    try:
        import requests  # noqa: F401
        return True
    except ImportError:
        return False


def search_by_keyword(keyword: str, limit: int = 6) -> list[dict[str, Any]]:
    """Search Wikidata for historical events matching a keyword.

    Uses Wikidata mwapi search (full-text, fast) + optional time metadata.
    Returns list of dicts: {label, description, point_in_time, item_id}.
    Empty list on failure or network error.
    """
    if not is_available() or not keyword.strip():
        return []

    safe_kw = (
        keyword.split("—")[0].split(",")[0].strip()[:60]
        .replace('"', "").replace("\\", "").replace("\n", " ")
    )
    if not safe_kw:
        return []

    query = f"""
SELECT DISTINCT ?item ?itemLabel ?pointInTime ?description WHERE {{
  SERVICE wikibase:mwapi {{
    bd:serviceParam wikibase:endpoint "www.wikidata.org" ;
                    wikibase:api "Search" ;
                    mwapi:srsearch "{safe_kw}" ;
                    mwapi:srlimit "{limit}" .
    ?item wikibase:apiOutputItem mwapi:title .
  }}
  ?item rdfs:label ?itemLabel .
  FILTER(LANG(?itemLabel) = "en") .
  OPTIONAL {{ ?item wdt:P585 ?pointInTime . }}
  OPTIONAL {{ ?item schema:description ?description . FILTER(LANG(?description) = "en") . }}
}} LIMIT {limit}
"""

    try:
        import requests
        from hindcast.knowledge import _PROXY

        resp = requests.get(
            SPARQL_ENDPOINT,
            params={"query": query, "format": "json"},
            headers={
                "Accept": "application/sparql-results+json",
                "User-Agent": _USER_AGENT,
            },
            timeout=_TIMEOUT,
            proxies=_PROXY,
        )
        if resp.status_code != 200:
            return []

        bindings = resp.json().get("results", {}).get("bindings", [])
        events = []
        for r in bindings:
            events.append({
                "label":         r.get("itemLabel",    {}).get("value", ""),
                "description":   r.get("description",  {}).get("value", ""),
                "point_in_time": r.get("pointInTime",  {}).get("value", "")[:10],
                "item_id":       r.get("item",         {}).get("value", "").split("/")[-1],
            })
        return events
    except Exception:
        return []


def format_for_prompt(events: list[dict[str, Any]], keyword: str) -> str:
    """Format Wikidata search results for history lens injection."""
    if not events:
        return ""
    lines = [
        "",
        "---",
        f"## 🕰️ Wikidata 知识图谱: 关键词「{keyword}」检索到的历史事件",
        "",
        "以下事件来自 Wikidata, 供结构类比参考:",
        "",
    ]
    for i, e in enumerate(events, 1):
        date_str = f" ({e['point_in_time']})" if e.get("point_in_time") else ""
        desc_str = f" — {e['description'][:80]}" if e.get("description") else ""
        lines.append(f"  {i}. **{e['label']}**{date_str}{desc_str}")
    lines += [
        "",
        "**提示**: 使用上述事件中与本事件结构最相似的案例作为 historical_analogues 的具体锚点.",
        "",
    ]
    return "\n".join(lines)
