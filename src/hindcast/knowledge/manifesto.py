"""Manifesto Project API 客户端 (政治派 RAG, 政党纲领立场).

Manifesto Project: 50+ 国、1000+ 政党, 1945 年至今, 每年更新.
API: https://manifesto-project.wzb.eu/api/v1/
免费 API key: 注册账号 → 个人页面生成 key → export MANIFESTO_API_KEY=xxx

核心端点 (均为 GET):
  /api/v1/list_core_versions  — 列出所有可用 core 数据集版本
  /api/v1/get_parties?key=MPDS2023a — 政党名单 (CSV list-of-lists)
  /api/v1/get_core?key=MPDS2023a   — 核心数据集 (含 rile/welfare/markeco 等)

country code: Manifesto 用自己的数字编码 (美国=61, 德国=41, 英国=51, 法国=31, 日本=32)
"""
from __future__ import annotations

import os
from typing import Any

MANIFESTO_API_BASE = "https://manifesto-project.wzb.eu/api/v1"
_DEFAULT_DATASET = "MPDS2023a"

# Manifesto country codes (与 ISO 不同)
_COUNTRY_CODES = {
    "US": "61", "DE": "41", "GB": "51", "FR": "31",
    "JP": "71", "IT": "32", "ES": "33", "CA": "62",
    "AU": "63", "NZ": "64", "SE": "11", "NO": "12",
}
# rile 分数: 负=左翼/扩张, 正=右翼/紧缩; 范围约 -100 ~ +100

# 缓存：key → (parties, core_rows)
_CACHE: dict[str, Any] = {}


def is_available() -> bool:
    return bool(os.getenv("MANIFESTO_API_KEY")) and _requests_ok()


def _requests_ok() -> bool:
    try:
        import requests  # noqa: F401
        return True
    except ImportError:
        return False


def _api_key() -> str:
    return os.getenv("MANIFESTO_API_KEY", "")


def _get(endpoint: str, params: dict | None = None) -> Any:
    """Make a GET request to Manifesto API, return parsed JSON."""
    import requests
    from hindcast.knowledge import _PROXY

    p = {"api_key": _api_key()}
    if params:
        p.update(params)
    resp = requests.get(
        f"{MANIFESTO_API_BASE}/{endpoint}",
        params=p,
        timeout=15,
        proxies=_PROXY,
    )
    if resp.status_code != 200:
        return None
    return resp.json()


def _load_core(dataset: str = _DEFAULT_DATASET) -> list[dict[str, Any]]:
    """Load and cache the core dataset as list of dicts."""
    cache_key = f"core_{dataset}"
    if cache_key in _CACHE:
        return _CACHE[cache_key]
    rows = _get("get_core", {"key": dataset})
    if not rows or not isinstance(rows, list) or len(rows) < 2:
        _CACHE[cache_key] = []
        return []
    header = rows[0]
    data = [dict(zip(header, r)) for r in rows[1:]]
    _CACHE[cache_key] = data
    return data


def _load_parties(dataset: str = _DEFAULT_DATASET) -> list[dict[str, Any]]:
    """Load and cache the party list as list of dicts."""
    cache_key = f"parties_{dataset}"
    if cache_key in _CACHE:
        return _CACHE[cache_key]
    rows = _get("get_parties", {"key": dataset})
    if not rows or not isinstance(rows, list) or len(rows) < 2:
        _CACHE[cache_key] = []
        return []
    header = rows[0]
    data = [dict(zip(header, r)) for r in rows[1:]]
    _CACHE[cache_key] = data
    return data


def get_parties_for_country(country_iso2: str, dataset: str = _DEFAULT_DATASET) -> list[dict[str, Any]]:
    """Get major parties for a country (ISO-2 code, e.g. 'US', 'DE').

    Returns list of {party_id, party_name, country_name}.
    """
    if not is_available():
        return []
    try:
        manifesto_country = _COUNTRY_CODES.get(country_iso2.upper())
        if not manifesto_country:
            return []
        parties = _load_parties(dataset)
        result = [
            {
                "party_id":     int(p["party"]),
                "party_name":   p.get("name_english") or p.get("abbrev", ""),
                "country_name": p.get("countryname", ""),
            }
            for p in parties
            if str(p.get("country", "")) == manifesto_country
            and float(p.get("max_pervote", 0) or 0) > 5  # 只取有实质选票的政党
        ]
        # 按最高得票率排序
        result.sort(key=lambda x: float(
            next((p.get("max_pervote", 0) for p in parties if int(p.get("party", 0)) == x["party_id"]), 0) or 0
        ), reverse=True)
        return result[:4]
    except Exception:
        return []


def get_positions(party_id: int, dataset: str = _DEFAULT_DATASET) -> dict[str, Any]:
    """Get latest policy position scores for a party from MPDS core dataset.

    Key scores:
      rile:     left(-100) to right(+100) overall scale
      welfare:  welfare state emphasis (%)
      markeco:  market economy emphasis (%)
      planeco:  planned economy emphasis (%)
    """
    if not is_available():
        return {}
    try:
        data = _load_core(dataset)
        matching = [r for r in data if str(r.get("party", "")) == str(party_id)]
        if not matching:
            return {}
        latest = max(matching, key=lambda r: r.get("edate", ""))
        return {
            "party_id":   party_id,
            "party_name": latest.get("partyname", ""),
            "year":       str(latest.get("edate", ""))[-4:],
            "rile":       _float(latest.get("rile")),
            "welfare":    _float(latest.get("welfare")),
            "markeco":    _float(latest.get("markeco")),
            "planeco":    _float(latest.get("planeco")),
        }
    except Exception:
        return {}


def _float(v: Any) -> float | None:
    try:
        return round(float(v), 2) if v not in (None, "", "NA") else None
    except (TypeError, ValueError):
        return None


def format_for_prompt(
    parties: list[dict[str, Any]],
    positions: list[dict[str, Any]],
    context: str,
) -> str:
    """Format Manifesto data for politics lens injection."""
    positions = [p for p in positions if p]
    if not positions and not parties:
        return ""
    lines = [
        "",
        "---",
        "## 📜 Manifesto Project: 主要政党政策立场 (MPDS 编码)",
        "",
        "以下数据来自 Manifesto Project 学术数据库 (政党纲领自动编码):",
        "",
    ]
    for pos in positions:
        rile = pos.get("rile")
        rile_str = f"左右轴={rile:+.1f}" if rile is not None else "左右轴=N/A"
        welfare = pos.get("welfare")
        w_str = f" 福利国家={welfare:.1f}%" if welfare is not None else ""
        markeco = pos.get("markeco")
        m_str = f" 市场经济={markeco:.1f}%" if markeco is not None else ""
        year = pos.get("year", "")
        lines.append(
            f"  - **{pos['party_name']}** ({year}): {rile_str}{w_str}{m_str}"
        )
    lines += [
        "",
        "**提示**: rile 负值=左翼/财政扩张倾向, 正值=右翼/紧缩倾向."
        " 结合政党立场分析制度约束与财政政策空间.",
        "",
    ]
    return "\n".join(lines)
