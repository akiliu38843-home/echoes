"""GDELT DOC API v2 客户端 (政治派 RAG).

GDELT: 全球每日 10-15 万条新闻事件, 1979 年至今.
DOC API: https://api.gdeltproject.org/api/v2/doc/doc
无需认证, 免费; **限制: 近 90 天内的文章** (历史事件跳过, 不报错).

用途: 给政治 lens (institutional_pe) 注入"当前地缘政治新闻背景",
      补充制度分析所需的实时信号 (限 mode="current" 且 as_of 在近 90 天内).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

GDELT_ENDPOINT = "https://api.gdeltproject.org/api/v2/doc/doc"
_TIMEOUT = 10
_MAX_DAYS_BACK = 85  # 留 5 天缓冲, 避免 API 边界报错


def is_available() -> bool:
    try:
        import requests  # noqa: F401
        return True
    except ImportError:
        return False


def _is_recent_enough(as_of: str) -> bool:
    """Check if as_of date is within GDELT DOC API's coverage window."""
    try:
        event_dt = datetime.strptime(as_of[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        now = datetime.now(tz=timezone.utc)
        return (now - event_dt).days <= _MAX_DAYS_BACK
    except Exception:
        return False


def search_recent(
    query: str,
    as_of: str,
    timespan_days: int = 30,
    max_records: int = 8,
) -> list[dict[str, Any]]:
    """Search GDELT for recent news about a query.

    Args:
        query:        English search phrase (e.g. case label like "Lehman collapse")
        as_of:        Event date "YYYY-MM-DD"; skips if >85 days ago
        timespan_days: Look-back window in days
        max_records:  Max articles to return

    Returns [] for historical events, on failure, or if requests not installed.
    """
    if not is_available():
        return []
    if not _is_recent_enough(as_of):
        return []  # 超出 DOC API 覆盖范围, 静默跳过

    try:
        import requests
        from hindcast.knowledge import _PROXY

        params = {
            "query":      query,
            "mode":       "artlist",
            "maxrecords": max_records,
            "format":     "json",
            "timespan":   f"{timespan_days}d",
            "sort":       "hybridrel",
        }
        resp = requests.get(
            GDELT_ENDPOINT,
            params=params,
            timeout=_TIMEOUT,
            proxies=_PROXY,
        )
        if resp.status_code != 200:
            return []
        data = resp.json()
        articles = data.get("articles", [])
        return [
            {
                "title":         a.get("title", ""),
                "url":           a.get("url", ""),
                "domain":        a.get("domain", ""),
                "seendate":      a.get("seendate", "")[:8],
                "sourcecountry": a.get("sourcecountry", ""),
                "language":      a.get("language", ""),
            }
            for a in articles[:max_records]
            if a.get("title")
        ]
    except Exception:
        return []


def format_for_prompt(articles: list[dict[str, Any]], query: str) -> str:
    """Format GDELT results for politics lens injection."""
    if not articles:
        return ""
    lines = [
        "",
        "---",
        f"## 🌐 GDELT 地缘政治新闻: 近期「{query[:50]}」相关报道",
        "",
        "以下是全球媒体对相关事件的近期报道 (GDELT 检索), 供制度分析参考:",
        "",
    ]
    for i, a in enumerate(articles, 1):
        date_str = f" [{a['seendate']}]" if a.get("seendate") else ""
        country = f" ({a['sourcecountry']})" if a.get("sourcecountry") else ""
        lines.append(f"  {i}. {a['title']}{date_str} — {a.get('domain', '')}{country}")
    lines += [
        "",
        "**提示**: 结合上述新闻背景分析制度压力与利益集团博弈. 不要引用文章 URL.",
        "",
    ]
    return "\n".join(lines)
