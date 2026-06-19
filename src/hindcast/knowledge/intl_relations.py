"""国际关系学 RAG: 国家物质能力 / 国力格局 (Correlates of War NMC v7).

数据来源: Correlates of War Project, National Material Capabilities v7.0
  Singer, J. David (1987). doi 见 correlatesofwar.org/data-sets/national-material-capabilities
  实测可直链下载 (NMCv7.zip, 4.7MB); 此处内嵌主要大国关键年份切片,
  因 CINC 变化极慢 (年度/历史级), 避免每次拉 4.7MB.

CINC (Composite Index of National Capability) = 一国在 6 项能力上的全球份额均值 (0–1):
  军费 / 兵力 / 钢铁产量 / 能源消耗 / 总人口 / 城市人口.

⚠️ 重要 caveat (防误读, 注入 prompt):
  CINC 由【人口 + 工业/能源体量】重度加权, **不等于 GDP, 也不等于军事投射力**.
  它会系统性【高估】人口与重工业大国 (中国/印度), 低估高人均/金融/科技强国.
  → CINC 反超 ≠ 综合国力反超; 只作"物质体量结构"参照, 不作单一国力裁决.

用途 (注入 intl_relations 派, 喂 power/tempo/echo):
  - echo : "守成霸权国 vs 新兴挑战者" 用真实国力份额量化 + 历史霸权转移参照
  - tempo: 国力此消彼长是几十年尺度 → 硬化"影响多久才显现"
  - power: 相对实力 = 议价权基础
"""
from __future__ import annotations
from typing import Any

# CINC 综合国力份额 (0–1), COW NMC v7, 主要大国 × 关键年份 (实测抽取)
_CINC: dict[str, dict[str, Any]] = {
    "US": {"name": "美国", "series": {1870: 0.099, 1900: 0.188, 1913: 0.220, 1938: 0.171, 1950: 0.284, 1970: 0.181, 1990: 0.141, 2000: 0.143, 2010: 0.148, 2022: 0.124}},
    "CN": {"name": "中国", "series": {1870: 0.171, 1900: 0.120, 1913: 0.096, 1938: 0.093, 1950: 0.118, 1970: 0.113, 1990: 0.112, 2000: 0.162, 2010: 0.209, 2022: 0.234}},
    "UK": {"name": "英国", "series": {1870: 0.242, 1900: 0.178, 1913: 0.113, 1938: 0.078, 1950: 0.061, 1970: 0.030, 1990: 0.025, 2000: 0.022, 2010: 0.016, 2022: 0.012}},
    "RU": {"name": "俄/苏", "series": {1870: 0.081, 1900: 0.109, 1913: 0.116, 1938: 0.164, 1950: 0.181, 1970: 0.171, 1990: 0.129, 2000: 0.051, 2010: 0.039, 2022: 0.038}},
    "DE": {"name": "德国", "series": {1870: 0.106, 1900: 0.132, 1913: 0.143, 1938: 0.154, 1990: 0.029, 2000: 0.026, 2010: 0.019, 2022: 0.015}},
    "FR": {"name": "法国", "series": {1870: 0.127, 1900: 0.075, 1913: 0.068, 1938: 0.046, 1950: 0.033, 1970: 0.024, 1990: 0.020, 2000: 0.019, 2010: 0.016, 2022: 0.011}},
    "JP": {"name": "日本", "series": {1870: 0.020, 1900: 0.029, 1913: 0.034, 1938: 0.059, 1970: 0.054, 1990: 0.051, 2000: 0.050, 2010: 0.037, 2022: 0.025}},
    "IN": {"name": "印度", "series": {1950: 0.050, 1970: 0.052, 1990: 0.060, 2000: 0.069, 2010: 0.080, 2022: 0.099}},
}

_LATEST_YEAR = 2022

# 关键词 → 焦点国 (用于挑"挑战者"那一极; 默认守成=美国)
_KEYWORD_COUNTRY: dict[str, str] = {
    "China": "CN", "Chinese": "CN", "中国": "CN", "tariff": "CN", "关税": "CN",
    "Russia": "RU", "Russian": "RU", "俄": "RU", "Ukraine": "RU", "乌克兰": "RU",
    "India": "IN", "Indian": "IN", "印度": "IN",
    "Japan": "JP", "日本": "JP",
    "Germany": "DE", "德国": "DE", "EU": "DE", "Europe": "DE",
}


def is_available() -> bool:
    return True


def _guess_challenger(keyword: str) -> str:
    for hint, iso2 in _KEYWORD_COUNTRY.items():
        if hint.lower() in keyword.lower():
            return iso2
    return "CN"  # 默认大国博弈对手 = 中国


def get_power_balance(keyword: str) -> dict[str, Any]:
    """返回当前国力排名 + 守成(美) vs 挑战者 轨迹 + 历史霸权转移参照."""
    challenger = _guess_challenger(keyword)
    # 当前 (2022) 排名
    ranking = sorted(
        ((c["name"], c["series"].get(_LATEST_YEAR)) for c in _CINC.values() if c["series"].get(_LATEST_YEAR) is not None),
        key=lambda x: x[1], reverse=True,
    )
    return {
        "challenger_iso2": challenger,
        "ranking": ranking,
        "incumbent": "US",
    }


def format_for_prompt(balance: dict[str, Any], keyword: str) -> str:
    """格式化国力格局供 intl_relations lens 注入."""
    if not balance:
        return ""
    challenger = balance.get("challenger_iso2", "CN")
    ranking = balance.get("ranking", [])
    inc = _CINC["US"]
    chal = _CINC.get(challenger, _CINC["CN"])

    def _traj(c: dict[str, Any]) -> str:
        s = c["series"]
        pts = [f"{y}={s[y]:.3f}" for y in (1950, 1990, 2000, 2022) if y in s]
        return "  ".join(pts)

    lines = [
        "",
        "---",
        "## 🌐 国力格局 (COW NMC v7 · CINC 综合国力份额 0–1)",
        "",
        "数据来源: Correlates of War, National Material Capabilities v7 (Singer 1987)",
        "CINC = 军费/兵力/钢铁/能源/总人口/城市人口 六项的全球份额均值.",
        "",
        f"### 当前 ({_LATEST_YEAR}) 主要大国 CINC 排名",
    ]
    for i, (name, v) in enumerate(ranking[:6], 1):
        lines.append(f"  {i}. {name} {v:.3f}")

    lines += [
        "",
        f"### 守成 vs 挑战 轨迹 (美国 vs {chal['name']})",
        f"  美国: {_traj(inc)}",
        f"  {chal['name']}: {_traj(chal)}",
        "",
        "### 历史霸权转移参照 (相对衰落都是几十年尺度)",
        f"  英国: 1870={_CINC['UK']['series'][1870]:.3f}(霸主) → 2022={_CINC['UK']['series'][2022]:.3f}, 一个世纪相对衰落",
        f"  美国: 1950={inc['series'][1950]:.3f}(峰值) → 2022={inc['series'][2022]:.3f}, 类似衰落轨迹",
        "",
        "⚠️ CINC caveat: 由【人口+工业/能源体量】重度加权, **不等于 GDP 或军事投射力**,",
        "  系统性高估人口/重工业大国 (中/印). CINC 反超 ≠ 综合国力反超.",
        "  只作物质体量结构参照, 不作单一国力裁决. 引用数字时须带此限定.",
        "",
    ]
    return "\n".join(lines)
