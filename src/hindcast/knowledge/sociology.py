"""社会结构数据客户端 (社会学派 RAG).

数据来源: World Bank (嵌入式静态表, 2019-2023 最新年份).
  - Gini 系数: SI.POV.GINI
  - 政府支出/GDP: GC.XPN.TOTL.GD.ZS
  - 失业率: SL.UEM.TOTL.ZS

api.worldbank.org 在本机无法访问 (SSL/代理阻断), 故以嵌入表代替.
数据更新粒度: 1-3 年; 对 RAG 叙事背景注入精度充分.

用于 structural_functional / conflict_theory lens 注入.
"""
from __future__ import annotations
from typing import Any

# World Bank 官方数据 (嵌入式, 取各国最近可用年份)
# 格式: country_iso2 → {gini, gini_year, gov_expense, gov_year, unemployment, unemp_year}
_STATIC_DATA: dict[str, dict[str, Any]] = {
    "US": {"gini": 39.8, "gini_year": 2022, "gov_expense": 36.5, "gov_year": 2022, "unemployment": 3.6, "unemp_year": 2023},
    "CN": {"gini": 38.2, "gini_year": 2019, "gov_expense": 33.4, "gov_year": 2021, "unemployment": 5.1, "unemp_year": 2023},
    "DE": {"gini": 31.9, "gini_year": 2019, "gov_expense": 47.5, "gov_year": 2021, "unemployment": 3.0, "unemp_year": 2023},
    "JP": {"gini": 32.9, "gini_year": 2013, "gov_expense": 39.7, "gov_year": 2021, "unemployment": 2.6, "unemp_year": 2023},
    "GB": {"gini": 35.1, "gini_year": 2021, "gov_expense": 45.3, "gov_year": 2021, "unemployment": 4.2, "unemp_year": 2023},
    "FR": {"gini": 30.7, "gini_year": 2021, "gov_expense": 57.4, "gov_year": 2021, "unemployment": 7.1, "unemp_year": 2023},
    "IT": {"gini": 34.8, "gini_year": 2021, "gov_expense": 55.8, "gov_year": 2021, "unemployment": 6.8, "unemp_year": 2023},
    "BR": {"gini": 52.0, "gini_year": 2021, "gov_expense": 41.0, "gov_year": 2021, "unemployment": 8.9, "unemp_year": 2023},
    "IN": {"gini": 35.7, "gini_year": 2019, "gov_expense": 27.0, "gov_year": 2021, "unemployment": 7.1, "unemp_year": 2023},
    "MX": {"gini": 45.4, "gini_year": 2020, "gov_expense": 26.8, "gov_year": 2021, "unemployment": 2.8, "unemp_year": 2023},
    "KR": {"gini": 31.4, "gini_year": 2019, "gov_expense": 32.9, "gov_year": 2021, "unemployment": 2.7, "unemp_year": 2023},
    "CA": {"gini": 31.7, "gini_year": 2019, "gov_expense": 41.5, "gov_year": 2021, "unemployment": 5.5, "unemp_year": 2023},
    "AU": {"gini": 34.3, "gini_year": 2018, "gov_expense": 36.7, "gov_year": 2021, "unemployment": 3.7, "unemp_year": 2023},
    "RU": {"gini": 36.0, "gini_year": 2020, "gov_expense": 35.6, "gov_year": 2021, "unemployment": 3.2, "unemp_year": 2023},
}

# 中国相关命中放最前 (对华/中美 类事件判中国); 默认 CN (产品默认中国视角)
_KEYWORD_COUNTRY: dict[str, str] = {
    "中国": "CN", "中方": "CN", "对华": "CN", "中美": "CN", "China": "CN", "Chinese": "CN",
    "美联储": "US", "美元": "US", "美国": "US", "美方": "US",
    "US": "US", "USA": "US", "America": "US", "American": "US",
    "federal": "US", "dollar": "US", "Fed": "US",
    "日本": "JP", "Japan": "JP", "Japanese": "JP",
    "欧盟": "DE", "欧洲": "DE", "德国": "DE", "Germany": "DE", "German": "DE", "Euro": "DE",
    "英国": "GB", "UK": "GB", "Britain": "GB", "British": "GB",
    "法国": "FR", "France": "FR", "French": "FR",
    "意大利": "IT", "Italy": "IT", "Italian": "IT",
    "巴西": "BR", "Brazil": "BR",
    "印度": "IN", "India": "IN", "Indian": "IN",
    "墨西哥": "MX", "Mexico": "MX",
    "韩国": "KR", "Korea": "KR",
    "加拿大": "CA", "Canada": "CA",
    "俄罗斯": "RU", "俄方": "RU", "Russia": "RU", "Russian": "RU",
}


def is_available() -> bool:
    return True


def _guess_country(keyword: str) -> str:
    for hint, iso2 in _KEYWORD_COUNTRY.items():
        if hint.lower() in keyword.lower():
            return iso2
    return "CN"  # 默认中国视角


def get_social_indicators(keyword: str) -> dict[str, Any]:
    """Return social indicator data for the country implied by keyword."""
    country = _guess_country(keyword)
    data = _STATIC_DATA.get(country)
    if not data:
        return {}
    return {"country": country, **data}


def format_for_prompt(indicators: dict[str, Any], keyword: str) -> str:
    """Format World Bank social indicators for sociology lens injection."""
    if not indicators:
        return ""
    gini  = indicators.get("gini")
    gov   = indicators.get("gov_expense")
    unemp = indicators.get("unemployment")
    if not any(v is not None for v in [gini, gov, unemp]):
        return ""
    country    = indicators.get("country", "US")
    gini_y     = indicators.get("gini_year", "")
    gov_y      = indicators.get("gov_year", "")
    unemp_y    = indicators.get("unemp_year", "")
    lines = [
        "",
        "---",
        f"## 📊 世界银行社会结构指标 ({country}, 数据来源: World Bank)",
        "",
    ]
    if gini is not None:
        lines.append(f"  - **基尼系数**: {gini} ({gini_y})  [参考: <30=高平等, 30-45=中等, >45=高不平等]")
    if gov is not None:
        lines.append(f"  - **政府支出/GDP**: {gov}% ({gov_y})")
    if unemp is not None:
        lines.append(f"  - **失业率**: {unemp}% ({unemp_y})")
    lines += [
        "",
        "**提示**: 基于上述指标分析社会整合度 (涂尔干) 或阶级矛盾烈度 (马克思/韦伯).",
        "",
    ]
    return "\n".join(lines)
