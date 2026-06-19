"""人类学跨文化数据客户端 (社会学/人类学派 RAG).

D-PLACE (Database of Places, Language, Culture and Environment):
  - Ethnographic Atlas (EA): 1291 个人类社会, 267 个文化变量
  - 来源: Max Planck Institute for Evolutionary Anthropology
  - 通过 GitHub raw URL 直接 CSV 访问, 无需 API key / auth
  - societies.csv 含: 社会名称, HRAF 地区, 经纬度, 语系

HRAF 6 大地区:
  Africa / Circum-Mediterranean / East Eurasia /
  North America / Oceania / South America

用于社会学 lens 注入: 从跨文化比较视角提供结构类比背景.
"""
from __future__ import annotations
import csv
import io
from typing import Any

_SOCIETIES_URL = (
    "https://raw.githubusercontent.com/D-PLACE/dplace-data"
    "/master/datasets/EA/societies.csv"
)
_TIMEOUT = 10
_CACHE: dict[str, Any] = {}

# 关键词 → HRAF 地区 (模糊匹配)
_REGION_HINTS: list[tuple[str, str]] = [
    ("US",        "North America"),
    ("USA",       "North America"),
    ("America",   "North America"),
    ("Canada",    "North America"),
    ("Mexico",    "North America"),
    ("tariff",    "North America"),
    ("dollar",    "North America"),
    ("Brazil",    "South America"),
    ("Latin",     "South America"),
    ("Argentina", "South America"),
    ("UK",        "Circum-Mediterranean"),
    ("Britain",   "Circum-Mediterranean"),
    ("Europe",    "Circum-Mediterranean"),
    ("Germany",   "Circum-Mediterranean"),
    ("France",    "Circum-Mediterranean"),
    ("Rome",      "Circum-Mediterranean"),
    ("China",     "East Eurasia"),
    ("Japan",     "East Eurasia"),
    ("India",     "East Eurasia"),
    ("Asia",      "East Eurasia"),
    ("Africa",    "Africa"),
    ("Pacific",   "Oceania"),
    ("Australia", "Oceania"),
]


def is_available() -> bool:
    try:
        import requests  # noqa: F401
        return True
    except ImportError:
        return False


def _load_societies() -> list[dict[str, str]]:
    """Load and cache EA societies from GitHub raw CSV (direct, no proxy)."""
    if "societies" in _CACHE:
        return _CACHE["societies"]
    try:
        import requests
        # GitHub raw works with direct connection; proxy not needed
        resp = requests.get(_SOCIETIES_URL, timeout=_TIMEOUT)
        if resp.status_code != 200:
            _CACHE["societies"] = []
            return []
        reader = csv.DictReader(io.StringIO(resp.text))
        societies = list(reader)
        _CACHE["societies"] = societies
        return societies
    except Exception:
        _CACHE["societies"] = []
        return []


# Bounding boxes for HRAF regions: (lat_min, lat_max, lon_min, lon_max)
_REGION_BBOX: list[tuple[str, float, float, float, float]] = [
    ("North America",          15.0,  83.0, -170.0,  -52.0),
    ("South America",         -60.0,  15.0,  -82.0,  -34.0),
    ("Circum-Mediterranean",   25.0,  72.0,  -15.0,   60.0),
    ("Africa",                -35.0,  38.0,  -18.0,   52.0),
    ("East Eurasia",            5.0,  80.0,   40.0,  145.0),
    ("Oceania",               -50.0,  25.0,  110.0,  180.0),
]


def _guess_region(keyword: str) -> str | None:
    kw_lower = keyword.lower()
    for hint, region in _REGION_HINTS:
        if hint.lower() in kw_lower:
            return region
    return None


def _society_region(s: dict[str, str]) -> str | None:
    """Determine HRAF region from society's Lat/Long coordinates."""
    try:
        lat = float(s.get("Lat", ""))
        lon = float(s.get("Long", ""))
    except (TypeError, ValueError):
        return None
    for region, lat_min, lat_max, lon_min, lon_max in _REGION_BBOX:
        if lat_min <= lat <= lat_max and lon_min <= lon <= lon_max:
            return region
    return None


def get_regional_societies(keyword: str, limit: int = 5) -> tuple[str, list[dict[str, str]]]:
    """Return (region_name, sample_societies) for the region implied by keyword.

    Uses coordinate bounding boxes for region detection.
    Falls back to a global sample if region can't be inferred.
    """
    if not is_available():
        return "", []
    societies = _load_societies()
    if not societies:
        return "", []

    region = _guess_region(keyword)
    if region:
        pool = [s for s in societies if _society_region(s) == region]
        if not pool:
            pool = societies
    else:
        pool = societies
        region = "Global"

    step = max(1, len(pool) // limit)
    samples = pool[::step][:limit]
    return region, samples


def format_for_prompt(region: str, societies: list[dict[str, str]]) -> str:
    """Format D-PLACE/EA data for sociology/anthropology lens injection."""
    if not societies:
        return ""
    # pref_name_for_society is the canonical society name in EA
    names = [
        s.get("pref_name_for_society") or s.get("id", "")
        for s in societies
    ]
    names = [n for n in names if n]
    if not names:
        return ""
    lines = [
        "",
        "---",
        f"## 🌍 D-PLACE / Ethnographic Atlas: 跨文化结构比较 ({region})",
        "",
        "以下数据来自 Murdock Ethnographic Atlas (1291 社会, Max Planck 人类学研究所):",
        "",
        f"  **{region} 代表性社会**: {', '.join(names)}",
        "",
        "  **EA 核心比较维度** (可用于跨文化类比):",
        "  - 政治整合层级: 游群 / 部落 / 酋邦 / 早期国家",
        "  - 生计经济: 采集狩猎 / 游牧畜牧 / 农耕 / 混合",
        "  - 家庭与亲属制度: 核心家庭 / 扩展家庭 / 母系/父系氏族",
        "  - 社会分层 & 财产继承规则",
        "",
        "**提示**: 以上述跨文化框架为参照,"
        " 分析本事件所在社会与历史上结构类似社会的共性 (结构功能主义)"
        " 或制度冲突根源 (冲突理论).",
        "",
    ]
    return "\n".join(lines)
