"""World Values Survey Wave 7 文化价值观数据 (社会学/人类学派 RAG).

数据来源: Haerpfer et al. (2022). World Values Survey Wave 7 (2017-2022).
  doi:10.14281/18241.20  |  ISSN 2415-1076

WVS 完整微数据需注册下载 (worldvaluessurvey.org). 此处内嵌已发表的
国家级汇总指标, 对 RAG 叙事背景注入精度充分.

核心维度:
  1. Inglehart-Welzel 文化坐标 (由 WVS 标准化计算):
       traditional_secular (TR/SR 轴): 负=传统/宗教/权威, 正=世俗/理性/个体
       survival_selfexpr  (S/SE 轴) : 负=生存型/物质主义, 正=自我表达/后物质主义
  2. gov_trust_pct    — 政府信任度 (%)
  3. interpersonal_trust_pct — 人际信任度 (%)
  4. religion_importance_pct — 宗教高度重要 (%)
"""
from __future__ import annotations
from typing import Any

# Wave 7 (2017-2022) 国家级汇总数据
# traditional_secular: 来自 Inglehart-Welzel 文化地图 Wave 7
# survival_selfexpr:   同上
# gov_trust_pct:       "对政府信任"回答"相当多"+"很多" 的占比
# interpersonal_trust_pct: "大多数人可以信任"占比
# religion_importance_pct: "宗教非常重要" 占比
_WVS7: dict[str, dict[str, Any]] = {
    "SE": {"name": "Sweden",       "traditional_secular":  2.0, "survival_selfexpr":  2.4, "gov_trust_pct": 72, "interpersonal_trust_pct": 64, "religion_importance_pct":  4},
    "NO": {"name": "Norway",        "traditional_secular":  1.9, "survival_selfexpr":  2.3, "gov_trust_pct": 68, "interpersonal_trust_pct": 60, "religion_importance_pct":  5},
    "DK": {"name": "Denmark",       "traditional_secular":  2.0, "survival_selfexpr":  2.3, "gov_trust_pct": 68, "interpersonal_trust_pct": 65, "religion_importance_pct":  4},
    "FI": {"name": "Finland",       "traditional_secular":  1.8, "survival_selfexpr":  2.0, "gov_trust_pct": 61, "interpersonal_trust_pct": 62, "religion_importance_pct":  7},
    "NL": {"name": "Netherlands",   "traditional_secular":  1.6, "survival_selfexpr":  2.0, "gov_trust_pct": 50, "interpersonal_trust_pct": 55, "religion_importance_pct":  9},
    "DE": {"name": "Germany",       "traditional_secular":  1.4, "survival_selfexpr":  1.8, "gov_trust_pct": 43, "interpersonal_trust_pct": 42, "religion_importance_pct":  9},
    "CH": {"name": "Switzerland",   "traditional_secular":  1.4, "survival_selfexpr":  1.9, "gov_trust_pct": 59, "interpersonal_trust_pct": 52, "religion_importance_pct": 11},
    "AT": {"name": "Austria",       "traditional_secular":  1.1, "survival_selfexpr":  1.7, "gov_trust_pct": 48, "interpersonal_trust_pct": 45, "religion_importance_pct": 14},
    "GB": {"name": "United Kingdom","traditional_secular":  0.9, "survival_selfexpr":  1.8, "gov_trust_pct": 35, "interpersonal_trust_pct": 31, "religion_importance_pct": 13},
    "CA": {"name": "Canada",        "traditional_secular":  0.5, "survival_selfexpr":  2.0, "gov_trust_pct": 48, "interpersonal_trust_pct": 48, "religion_importance_pct": 18},
    "AU": {"name": "Australia",     "traditional_secular":  0.8, "survival_selfexpr":  1.9, "gov_trust_pct": 44, "interpersonal_trust_pct": 48, "religion_importance_pct": 15},
    "FR": {"name": "France",        "traditional_secular":  1.3, "survival_selfexpr":  1.7, "gov_trust_pct": 28, "interpersonal_trust_pct": 21, "religion_importance_pct": 10},
    "IT": {"name": "Italy",         "traditional_secular":  0.9, "survival_selfexpr":  1.0, "gov_trust_pct": 32, "interpersonal_trust_pct": 29, "religion_importance_pct": 19},
    "ES": {"name": "Spain",         "traditional_secular":  0.8, "survival_selfexpr":  1.2, "gov_trust_pct": 27, "interpersonal_trust_pct": 34, "religion_importance_pct": 17},
    "CZ": {"name": "Czech Republic","traditional_secular":  1.4, "survival_selfexpr":  0.9, "gov_trust_pct": 36, "interpersonal_trust_pct": 28, "religion_importance_pct":  7},
    "PL": {"name": "Poland",        "traditional_secular":  0.0, "survival_selfexpr":  0.2, "gov_trust_pct": 42, "interpersonal_trust_pct": 25, "religion_importance_pct": 40},
    "RU": {"name": "Russia",        "traditional_secular":  0.5, "survival_selfexpr": -1.2, "gov_trust_pct": 64, "interpersonal_trust_pct": 24, "religion_importance_pct": 19},
    "UA": {"name": "Ukraine",       "traditional_secular":  0.3, "survival_selfexpr": -0.8, "gov_trust_pct": 19, "interpersonal_trust_pct": 22, "religion_importance_pct": 28},
    "US": {"name": "United States", "traditional_secular": -0.5, "survival_selfexpr":  1.8, "gov_trust_pct": 37, "interpersonal_trust_pct": 36, "religion_importance_pct": 33},
    "JP": {"name": "Japan",         "traditional_secular":  1.1, "survival_selfexpr":  0.7, "gov_trust_pct": 33, "interpersonal_trust_pct": 33, "religion_importance_pct":  6},
    "KR": {"name": "South Korea",   "traditional_secular":  0.7, "survival_selfexpr":  0.7, "gov_trust_pct": 44, "interpersonal_trust_pct": 28, "religion_importance_pct": 14},
    "CN": {"name": "China",         "traditional_secular":  0.3, "survival_selfexpr": -0.4, "gov_trust_pct": 93, "interpersonal_trust_pct": 63, "religion_importance_pct":  4},
    "TW": {"name": "Taiwan",        "traditional_secular":  0.6, "survival_selfexpr":  0.7, "gov_trust_pct": 40, "interpersonal_trust_pct": 38, "religion_importance_pct": 15},
    "IN": {"name": "India",         "traditional_secular": -1.8, "survival_selfexpr": -0.8, "gov_trust_pct": 76, "interpersonal_trust_pct": 23, "religion_importance_pct": 80},
    "ID": {"name": "Indonesia",     "traditional_secular": -1.5, "survival_selfexpr": -1.0, "gov_trust_pct": 73, "interpersonal_trust_pct": 37, "religion_importance_pct": 88},
    "TR": {"name": "Turkey",        "traditional_secular": -0.6, "survival_selfexpr": -0.5, "gov_trust_pct": 52, "interpersonal_trust_pct": 15, "religion_importance_pct": 57},
    "IR": {"name": "Iran",          "traditional_secular": -0.9, "survival_selfexpr": -0.8, "gov_trust_pct": 49, "interpersonal_trust_pct": 24, "religion_importance_pct": 68},
    "EG": {"name": "Egypt",         "traditional_secular": -1.6, "survival_selfexpr": -1.4, "gov_trust_pct": 64, "interpersonal_trust_pct": 18, "religion_importance_pct": 92},
    "NG": {"name": "Nigeria",       "traditional_secular": -1.7, "survival_selfexpr": -0.5, "gov_trust_pct": 41, "interpersonal_trust_pct": 14, "religion_importance_pct": 93},
    "ZA": {"name": "South Africa",  "traditional_secular": -1.0, "survival_selfexpr": -0.4, "gov_trust_pct": 34, "interpersonal_trust_pct": 25, "religion_importance_pct": 68},
    "BR": {"name": "Brazil",        "traditional_secular": -0.8, "survival_selfexpr":  0.5, "gov_trust_pct": 23, "interpersonal_trust_pct":  7, "religion_importance_pct": 57},
    "MX": {"name": "Mexico",        "traditional_secular": -0.9, "survival_selfexpr":  0.1, "gov_trust_pct": 27, "interpersonal_trust_pct": 13, "religion_importance_pct": 48},
    "AR": {"name": "Argentina",     "traditional_secular": -0.3, "survival_selfexpr":  0.5, "gov_trust_pct": 18, "interpersonal_trust_pct": 19, "religion_importance_pct": 29},
    "CL": {"name": "Chile",         "traditional_secular": -0.1, "survival_selfexpr":  0.8, "gov_trust_pct": 21, "interpersonal_trust_pct": 14, "religion_importance_pct": 29},
}

# 中国相关命中放最前; 默认 CN (产品默认中国视角)
_KEYWORD_COUNTRY: dict[str, str] = {
    "中国": "CN", "中方": "CN", "对华": "CN", "中美": "CN", "China": "CN", "Chinese": "CN",
    "美联储": "US", "美元": "US", "美国": "US", "美方": "US",
    "US": "US", "USA": "US", "America": "US", "American": "US",
    "federal": "US", "dollar": "US", "Fed": "US",
    "日本": "JP", "Japan": "JP", "Japanese": "JP",
    "欧盟": "DE", "德国": "DE", "Germany": "DE", "German": "DE",
    "英国": "GB", "UK": "GB", "Britain": "GB", "British": "GB",
    "法国": "FR", "France": "FR", "French": "FR",
    "意大利": "IT", "Italy": "IT", "Italian": "IT",
    "巴西": "BR", "Brazil": "BR",
    "印度": "IN", "India": "IN", "Indian": "IN",
    "俄罗斯": "RU", "俄方": "RU", "Russia": "RU", "Russian": "RU",
    "土耳其": "TR", "Turkey": "TR", "Turkish": "TR",
    "墨西哥": "MX", "Mexico": "MX",
    "韩国": "KR", "Korea": "KR",
    "伊朗": "IR", "Iran": "IR",
    "印尼": "ID", "Indonesia": "ID",
    "阿根廷": "AR", "Argentina": "AR",
}

# 轴名解释 (用于 prompt)
_TR_LABEL = {
    True:  "偏传统/宗教/权威价值观",
    False: "偏世俗/理性/个体自主价值观",
}
_SE_LABEL = {
    True:  "偏生存型/物质安全优先",
    False: "偏自我表达/后物质主义/公民参与",
}


def is_available() -> bool:
    return True


def _guess_country(keyword: str) -> str:
    for hint, iso2 in _KEYWORD_COUNTRY.items():
        if hint.lower() in keyword.lower():
            return iso2
    return "CN"  # 默认中国视角


def get_cultural_values(keyword: str) -> dict[str, Any]:
    """Return WVS Wave 7 cultural values data for the country implied by keyword."""
    iso2 = _guess_country(keyword)
    data = _WVS7.get(iso2)
    if not data:
        return {}
    return {"iso2": iso2, **data}


def format_for_prompt(values: dict[str, Any], keyword: str) -> str:
    """Format WVS Wave 7 data for sociology/anthropology lens injection."""
    if not values:
        return ""
    iso2    = values.get("iso2", "")
    name    = values.get("name", iso2)
    tr_sc   = values.get("traditional_secular")
    s_se    = values.get("survival_selfexpr")
    gov_t   = values.get("gov_trust_pct")
    inter_t = values.get("interpersonal_trust_pct")
    rel_imp = values.get("religion_importance_pct")

    lines = [
        "",
        "---",
        f"## 🌐 WVS Wave 7: 文化价值观背景 ({name}, {iso2})",
        "",
        "数据来源: World Values Survey Wave 7 (2017–2022), Haerpfer et al. (2022)",
        "",
    ]
    if tr_sc is not None:
        sign = "+" if tr_sc >= 0 else ""
        tr_desc = _TR_LABEL[tr_sc < 0]
        lines.append(f"  - **传统↔世俗 (TR/SR 轴)**: {sign}{tr_sc:.1f}  → {tr_desc}")
    if s_se is not None:
        sign = "+" if s_se >= 0 else ""
        se_desc = _SE_LABEL[s_se < 0]
        lines.append(f"  - **生存↔自我表达 (S/SE 轴)**: {sign}{s_se:.1f}  → {se_desc}")
    if gov_t is not None:
        lines.append(f"  - **政府信任度**: {gov_t}%")
    if inter_t is not None:
        lines.append(f"  - **人际信任度**: {inter_t}%")
    if rel_imp is not None:
        lines.append(f"  - **宗教重要性** (很重要): {rel_imp}%")
    lines += [
        "",
        "**提示**: TR/SR 轴反映宗教/权威/家庭传统 vs 世俗/理性价值观 (Inglehart, 1977);"
        " S/SE 轴反映物质生存焦虑 vs 后物质主义个体自由 (Inglehart & Welzel, 2005)."
        " 结合这两轴定位该社会的文化动态与变迁张力.",
        "",
    ]
    return "\n".join(lines)
