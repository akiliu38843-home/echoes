"""结构状态变量类型 + 14 变量定义。

依据 01-PRODUCT-DESIGN-v0.4.md §3.2.1。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

__all__ = [
    "EventWindow", "MacroEconomic", "SCHOOLS", "School",
    "StructuralState", "StructuralVariable", "VARIABLES",
]

# ─── 4 经济派注册表 ───
# v0.5.7 refactor: SCHOOLS 现在从 disciplines registry 动态拿 (跨 18 个 import 点向后兼容).
# 旧硬编码 tuple 已搬到 disciplines/economics.py + @register, 单一真相源.
# School Literal 仍写死保证 pydantic + Linter 类型校验, 因为这条线我们的 4 经济派
# 名字不会变 (新学科是新 discipline, 不是新 economics lens).
from hindcast.disciplines import list_lens_ids

SCHOOLS = list_lens_ids("economics")
School = Literal["austrian", "monetarist", "keynesian", "rational_expectations"]

# 一致性自检 (import 期触发, 防 registry 漂移): 若有人意外往 economics 加/删 lens,
# SCHOOLS 立刻不一致, 这条断言会让 import 直接失败而非沉默崩溃后端 endpoint.
assert set(SCHOOLS) == {"austrian", "monetarist", "keynesian", "rational_expectations"}, (
    f"economics discipline lens 集合漂移: registry={SCHOOLS}; "
    f"如果是新增 economics lens, 请同步修改 School Literal 类型."
)


# ─── 14 变量元数据（id → 名称 + 流派依据 + 学派关注度⭐ 1-5）───
#
# school_relevance 来自 01 §3.2.2 ⭐ 表。
class StructuralVariable(BaseModel):
    id: str
    name: str
    school_relevance: dict[str, int] = Field(default_factory=dict)

    def stars(self, school: School) -> int:
        return self.school_relevance.get(school, 0)


VARIABLES: dict[str, StructuralVariable] = {
    "A1": StructuralVariable(
        id="A1",
        name="美元国际储备占比",
        school_relevance={"austrian": 5, "monetarist": 2, "keynesian": 2, "rational_expectations": 3},
    ),
    "A2": StructuralVariable(
        id="A2",
        name="美联储资产/GDP",
        school_relevance={"austrian": 5, "monetarist": 5, "keynesian": 3, "rational_expectations": 3},
    ),
    "A3": StructuralVariable(
        id="A3",
        name="美国经常项目逆差/GDP",
        school_relevance={"austrian": 4, "monetarist": 3, "keynesian": 4, "rational_expectations": 3},
    ),
    "A4": StructuralVariable(
        id="A4",
        name="全球央行年购金量(吨)",
        school_relevance={"austrian": 5, "monetarist": 2, "keynesian": 1, "rational_expectations": 3},
    ),
    "B1": StructuralVariable(
        id="B1",
        name="美联储 CBI 指数 (0-10)",
        school_relevance={"austrian": 5, "monetarist": 4, "keynesian": 3, "rational_expectations": 4},
    ),
    "B2": StructuralVariable(
        id="B2",
        name="美国财政赤字/GDP (滚动3年)",
        school_relevance={"austrian": 5, "monetarist": 3, "keynesian": 5, "rational_expectations": 3},
    ),
    "B3": StructuralVariable(
        id="B3",
        name="美国公共债务/GDP",
        school_relevance={"austrian": 5, "monetarist": 2, "keynesian": 2, "rational_expectations": 4},
    ),
    "C1": StructuralVariable(
        id="C1",
        name="中美 CINC 比 (中/美)",
        school_relevance={"austrian": 3, "monetarist": 1, "keynesian": 2, "rational_expectations": 3},
    ),
    "C2": StructuralVariable(
        id="C2",
        name="GPR 12 月滚动均值",
        school_relevance={"austrian": 4, "monetarist": 1, "keynesian": 2, "rational_expectations": 5},
    ),
    "C3": StructuralVariable(
        id="C3",
        name="武器化金融工具月均使用次数",
        school_relevance={"austrian": 5, "monetarist": 3, "keynesian": 2, "rational_expectations": 3},
    ),
    "D1": StructuralVariable(
        id="D1",
        name="美元在贸易计价中的占比",
        school_relevance={"austrian": 4, "monetarist": 5, "keynesian": 3, "rational_expectations": 4},
    ),
    "D2": StructuralVariable(
        id="D2",
        name="双边本币结算占比",
        school_relevance={"austrian": 4, "monetarist": 3, "keynesian": 2, "rational_expectations": 3},
    ),
    "D3": StructuralVariable(
        id="D3",
        name="SWIFT 在跨境支付占比",
        school_relevance={"austrian": 4, "monetarist": 4, "keynesian": 2, "rational_expectations": 3},
    ),
    "E1": StructuralVariable(
        id="E1",
        name="黄金-Bitcoin 60日相关性",
        school_relevance={"austrian": 2, "monetarist": 1, "keynesian": 1, "rational_expectations": 5},
    ),
    "E2": StructuralVariable(
        id="E2",
        name="全球央行黄金储备/总外储占比",
        school_relevance={"austrian": 5, "monetarist": 2, "keynesian": 2, "rational_expectations": 3},
    ),
}


# ─── EventWindow：前 30 天事件流摘要（ADR-003 路径 A）───
#
# 这是"现场可获取信号"——回测时点上**可观察**的事件流数据，
# 不是 LLM 训练数据记忆。让 LLM 看到"事件即将发生的先兆"。
class EventWindow(BaseModel):
    """前 30 天事件窗——"现场可观察信号"，非 LLM 训练数据记忆。

    ADR-003 §3.3 路径 A 数据载体。多类信号支持不同事件类型：
    - 地缘事件 → GPR spike + SDN
    - 货币政策事件 → cb_actions
    - 经济政策事件 (1971 弃锚类) → policy_event_imminent + economic_policy_signals
    """

    # 地缘信号
    gpr_30d_avg: float | None = None
    gpr_30d_trend: Literal["rising", "falling", "stable"] | None = None
    gpr_spike_recent: bool = False
    sdn_30d_count: int | None = None
    # 央行 / 货币政策信号
    cb_actions_30d: int | None = None
    # 经济政策事件信号（v0.5.1 新增——修 1971 Nixon 漏洞）
    policy_event_imminent: bool = False        # 重大经济政策决定即将出台（如 Camp David / G7 / FOMC）
    economic_policy_signals: list[str] = Field(default_factory=list)
    # 关键标题
    notable_news_headlines: list[str] = Field(default_factory=list)

    def is_event_window_active(self) -> bool:
        """是否有可识别事件信号——LLM 可据此判 exogenous_shock。

        v0.5.1 调整：policy_event_imminent 单独可激活；
        多源信号 ≥2 也可激活。"""
        if self.policy_event_imminent:
            return True
        signals = [
            self.gpr_spike_recent,
            (self.gpr_30d_trend == "rising"),
            (self.sdn_30d_count is not None and self.sdn_30d_count >= 5),
            (self.cb_actions_30d is not None and self.cb_actions_30d >= 2),
            len(self.economic_policy_signals) >= 2,
            len(self.notable_news_headlines) >= 2,
        ]
        return sum(s for s in signals if s) >= 2


# ─── MacroEconomic：宏观经济变量（货币政策预测必需）───
#
# Phase 1 新增：Fed funds rate 预测的必要输入。
# 单位规则：rates 用百分点（如 5.25 而非 0.0525）；gaps 是百分点差值。
class MacroEconomic(BaseModel):
    # 通胀 (US)
    cpi_headline_yoy: float | None = None     # CPI 同比 %（头条）
    core_pce_yoy: float | None = None         # 核心 PCE 同比 % (Fed 偏好的通胀)
    inflation_target: float = 2.0             # Fed 目标 %（默认 2）
    # 就业
    unemployment_rate: float | None = None    # U-3 %
    natural_unemployment: float = 4.5         # 自然失业率 u*（默认 4.5）
    nfp_3m_avg: int | None = None             # 近 3 月非农就业人均（千）
    # 产出
    gdp_growth_qoq_annualized: float | None = None  # 实际 GDP 季度环比年化 %
    output_gap_pct: float | None = None       # 产出缺口 % of 潜在 GDP
    # 政策利率
    current_fed_funds_target: float | None = None   # 当前联邦基金利率目标 %（区间中值）
    # Taylor Rule (1993 公式) — 实时算出
    taylor_implied_rate: float | None = None  # = r* + π + 0.5(π-π*) + 0.5(y_gap), r*=2, π*=2
    taylor_deviation: float | None = None     # = current_fed_funds_target - taylor_implied
    # 短端国债收益率（Phase 2 用）
    treasury_2y_yield: float | None = None
    treasury_10y_yield: float | None = None

    # ─── 桥梁变量（v0.5.4 Phase 2.5: 服务于 XAU 集成预测）───
    # 这些是 XAU 的核心直接驱动 (经典金价定价分解)
    treasury_10y_tips_yield: float | None = None      # FRED DFII10, 1997+ 才有
    breakeven_inflation_10y: float | None = None      # = 10Y nominal - TIPS = 通胀预期
    dxy_index: float | None = None                    # USD 综合指数 (Trade Weighted Dollar)

    # ─── 中国宏观（Phase 3 FX/Commodities 用）───
    cn_cpi_yoy: float | None = None
    cn_policy_rate: float | None = None              # PBoC 1Y LPR 或对应历史时期主要利率
    cn_gdp_growth_yoy: float | None = None
    cn_output_gap_pct: float | None = None
    cn_pmi_manufacturing: float | None = None        # 中国制造业 PMI（铜需求 proxy）

    # ─── 日本宏观（Phase 3）───
    jp_cpi_yoy: float | None = None
    jp_policy_rate: float | None = None              # BoJ 政策利率
    jp_gdp_growth_yoy: float | None = None
    jp_output_gap_pct: float | None = None

    # ─── 欧元区宏观（Phase 4c: EUR/USD）───
    eu_cpi_yoy: float | None = None
    eu_policy_rate: float | None = None              # ECB 主再融资利率
    eu_gdp_growth_yoy: float | None = None
    eu_output_gap_pct: float | None = None

    # ─── 外汇 + 商品当前价格（Phase 3）───
    usd_cnh_spot: float | None = None                # 离岸人民币
    usd_jpy_spot: float | None = None
    eur_usd_spot: float | None = None                # EUR/USD (报价: 1 EUR = X USD; ↑=EUR强USD弱)
    crude_oil_wti_usd: float | None = None           # WTI USD/桶
    copper_lme_usd_t: float | None = None            # LME 铜 USD/吨

    def inflation_gap(self) -> float | None:
        """π - π* (头条 CPI 减目标)。"""
        if self.cpi_headline_yoy is None:
            return None
        return self.cpi_headline_yoy - self.inflation_target

    def unemployment_gap(self) -> float | None:
        """u - u* （正值=失业高于自然率，需鸽派）。"""
        if self.unemployment_rate is None:
            return None
        return self.unemployment_rate - self.natural_unemployment

    def compute_taylor_implied(self) -> float | None:
        """Taylor (1993) 公式：i* = r* + π + 0.5(π - π*) + 0.5(y_gap)
        r* (real natural rate) 默认 2%，π* 默认 2%。"""
        if self.cpi_headline_yoy is None or self.output_gap_pct is None:
            return None
        r_star = 2.0
        pi_star = self.inflation_target
        pi = self.cpi_headline_yoy
        y_gap = self.output_gap_pct
        return r_star + pi + 0.5 * (pi - pi_star) + 0.5 * y_gap

    def compute_taylor_implied_cn(self) -> float | None:
        """中国 Taylor implied (用 2% target)."""
        if self.cn_cpi_yoy is None or self.cn_output_gap_pct is None:
            return None
        return 2.0 + self.cn_cpi_yoy + 0.5 * (self.cn_cpi_yoy - 2.0) + 0.5 * self.cn_output_gap_pct

    def compute_taylor_implied_jp(self) -> float | None:
        """日本 Taylor implied (用 1% target——BoJ 长期 2% 但实际容忍更低)."""
        if self.jp_cpi_yoy is None or self.jp_output_gap_pct is None:
            return None
        return 1.0 + self.jp_cpi_yoy + 0.5 * (self.jp_cpi_yoy - 2.0) + 0.5 * self.jp_output_gap_pct

    def us_cn_taylor_differential(self) -> float | None:
        """US - CN Taylor implied 差值（USD/CNH 预测核心信号）。正值→USD 升值压力。"""
        us = self.compute_taylor_implied()
        cn = self.compute_taylor_implied_cn()
        if us is None or cn is None:
            return None
        return us - cn

    def us_jp_taylor_differential(self) -> float | None:
        """US - JP Taylor implied 差值（USD/JPY 预测核心信号）。"""
        us = self.compute_taylor_implied()
        jp = self.compute_taylor_implied_jp()
        if us is None or jp is None:
            return None
        return us - jp

    def compute_taylor_implied_eu(self) -> float | None:
        """欧元区 Taylor implied (ECB 2% 目标, r*=2 与 US/CN 一致)。"""
        if self.eu_cpi_yoy is None or self.eu_output_gap_pct is None:
            return None
        return 2.0 + self.eu_cpi_yoy + 0.5 * (self.eu_cpi_yoy - 2.0) + 0.5 * self.eu_output_gap_pct

    def us_eu_taylor_differential(self) -> float | None:
        """US - EU Taylor implied 差值（EUR/USD 预测核心信号）。

        注意符号：差值 > 0 → Fed 更鹰 → USD 升值 → **EUR/USD 报价下行 (down)**
        （与 USD/JPY 相反：EUR/USD 的 dir=up 表示 EUR 升值/USD 贬值）。
        """
        us = self.compute_taylor_implied()
        eu = self.compute_taylor_implied_eu()
        if us is None or eu is None:
            return None
        return us - eu

    def compute_real_yield_proxy(self) -> float | None:
        """实际利率 proxy = 10Y nominal - core_pce_yoy (TIPS 不存在时备用)."""
        if self.treasury_10y_yield is None or self.core_pce_yoy is None:
            return None
        return self.treasury_10y_yield - self.core_pce_yoy

    def compute_bei_implied(self) -> float | None:
        """10Y BEI = 10Y nominal - 10Y TIPS (TIPS 存在时)."""
        if self.treasury_10y_yield is None or self.treasury_10y_tips_yield is None:
            return None
        return self.treasury_10y_yield - self.treasury_10y_tips_yield


# ─── StructuralState：单一时点结构状态快照 ───
class StructuralState(BaseModel):
    as_of: str                                # ISO date
    label: str                                # 可读标签
    values: dict[str, float]                  # var_id → value
    event_window: EventWindow | None = None   # 前 30 天事件流（ADR-003 路径 A）
    macro: MacroEconomic | None = None        # 宏观变量（Fed funds 预测必需）
    prior_section: str | None = None          # XAU prior 注入用 (v0.5.4)
    political_brief_section: str | None = None  # 第 5 派政治简报 (v0.5.6, 仅作为参考喂给 4 经济派)

    def format_for_prompt(self) -> str:
        lines = [
            f"# 结构状态快照 — {self.label} (as of {self.as_of})",
            "",
        ]

        # 政治简报置于结构数据之前 → 经济派先看到政治学派的独立判读, 再看数据
        # (仅在喂给 4 经济派时存在; 喂给政治派本身时此字段为 None, 避免自喂自)
        if self.political_brief_section:
            lines.append(self.political_brief_section)
            lines.append("")

        lines.extend([
            "## 14/15 结构变量（缓变，月/季度更新）",
            "| ID | 变量 | 当前值 |",
            "|---|---|---|",
        ])
        for var_id, var in VARIABLES.items():
            value = self.values.get(var_id, "N/A")
            lines.append(f"| {var_id} | {var.name} | {value} |")

        # Event window（如果有）
        if self.event_window is not None:
            ew = self.event_window
            lines.append("")
            lines.append("## 🌐 前 30 天事件窗（现场可观察信号，非模型记忆）")
            lines.append("")
            if ew.gpr_30d_avg is not None:
                trend_str = f"（趋势 {ew.gpr_30d_trend}）" if ew.gpr_30d_trend else ""
                spike_str = "  **⚠️ 7 日内 GPR spike**" if ew.gpr_spike_recent else ""
                lines.append(f"- **GPR 30 日均值**: {ew.gpr_30d_avg}{trend_str}{spike_str}")
            if ew.sdn_30d_count is not None:
                lines.append(f"- **OFAC SDN 30 日新增**: {ew.sdn_30d_count} 条")
            if ew.cb_actions_30d is not None:
                lines.append(f"- **主要央行 30 日重要动作**: {ew.cb_actions_30d} 次")
            if ew.policy_event_imminent:
                lines.append(f"- **⚠️ 重大经济政策事件即将出台**: 是（如 Camp David / G7 / FOMC 类）")
            if ew.economic_policy_signals:
                lines.append(f"- **经济政策事件信号**: {' · '.join(ew.economic_policy_signals)}")
            if ew.notable_news_headlines:
                lines.append("- **关键标题**:")
                for h in ew.notable_news_headlines:
                    lines.append(f"  - {h}")
            lines.append("")
            lines.append(f"**事件窗信号是否激活**: {'✅ 是 → 可判 exogenous_shock' if ew.is_event_window_active() else '❌ 否 → 应判 stochastic_noise/technical'}")

        # Macro economic block（如果有，Fed funds 预测必需）
        if self.macro is not None:
            m = self.macro
            lines.append("")
            lines.append("## 📐 宏观经济变量（货币政策预测）")
            lines.append("")
            inflation_gap = m.inflation_gap()
            unemployment_gap = m.unemployment_gap()
            implied = m.taylor_implied_rate if m.taylor_implied_rate is not None else m.compute_taylor_implied()
            deviation = (
                (m.current_fed_funds_target - implied)
                if (m.current_fed_funds_target is not None and implied is not None)
                else None
            )
            if m.cpi_headline_yoy is not None:
                lines.append(f"- **通胀 CPI YoY**: {m.cpi_headline_yoy:.1f}% (目标 {m.inflation_target}%) → **inflation gap {inflation_gap:+.1f} pp**")
            if m.core_pce_yoy is not None:
                lines.append(f"- **核心 PCE YoY**: {m.core_pce_yoy:.1f}%（Fed 偏好通胀指标）")
            if m.unemployment_rate is not None:
                lines.append(f"- **失业率 U-3**: {m.unemployment_rate:.1f}% (自然率 u*={m.natural_unemployment}%) → **unemployment gap {unemployment_gap:+.1f} pp**")
            if m.gdp_growth_qoq_annualized is not None:
                lines.append(f"- **实际 GDP 季度环比年化**: {m.gdp_growth_qoq_annualized:+.1f}%")
            if m.output_gap_pct is not None:
                lines.append(f"- **产出缺口**: {m.output_gap_pct:+.1f}% of 潜在 GDP")
            if m.current_fed_funds_target is not None:
                lines.append(f"- **当前联邦基金利率目标**: {m.current_fed_funds_target:.2f}%")
            if implied is not None:
                lines.append(f"- **🧮 Taylor Rule 隐含利率** (1993 公式 r*=2, π*=2)：**{implied:.2f}%**")
                if deviation is not None:
                    sign = "宽松" if deviation < 0 else ("中性" if abs(deviation) < 0.25 else "紧缩")
                    lines.append(f"  → 实际 - Taylor implied = **{deviation:+.2f} pp**（{sign}立场）")
            if m.treasury_2y_yield is not None:
                lines.append(f"- US 2Y 收益率: {m.treasury_2y_yield:.2f}%")
            if m.treasury_10y_yield is not None:
                lines.append(f"- US 10Y 收益率: {m.treasury_10y_yield:.2f}%")

            # 桥梁变量 (XAU 集成预测核心)
            if m.treasury_10y_tips_yield is not None:
                lines.append(f"- **🌉 US 10Y TIPS (实际利率)**: {m.treasury_10y_tips_yield:+.2f}%  ← XAU #1 inverse driver")
            bei = m.breakeven_inflation_10y if m.breakeven_inflation_10y is not None else m.compute_bei_implied()
            if bei is not None:
                lines.append(f"- **🌉 10Y BEI (通胀预期)**: {bei:.2f}%  ← XAU inflation hedge")
            if m.dxy_index is not None:
                lines.append(f"- **🌉 DXY 美元指数**: {m.dxy_index:.1f}  ← XAU USD 计价通道 (inverse)")

        # XAU prior section (用户已预测的桥梁变量, v0.5.4)
        if self.prior_section:
            lines.append("")
            lines.append(self.prior_section)

            # 中国 + 日本 macro（Phase 3）
            if m.cn_cpi_yoy is not None or m.jp_cpi_yoy is not None:
                lines.append("")
                lines.append("### 🇨🇳🇯🇵 中国/日本 macro（FX 派生变量预测必需）")
                if m.cn_cpi_yoy is not None:
                    cn_implied = m.compute_taylor_implied_cn()
                    lines.append(
                        f"- 🇨🇳 CN: CPI {m.cn_cpi_yoy:.1f}% / 政策利率 {m.cn_policy_rate}% / GDP {m.cn_gdp_growth_yoy}% / 产出 gap {m.cn_output_gap_pct}%"
                        + (f" / Taylor implied **{cn_implied:.2f}%**" if cn_implied else "")
                    )
                if m.cn_pmi_manufacturing is not None:
                    lines.append(f"  - PMI 制造业: {m.cn_pmi_manufacturing}（铜需求 proxy）")
                if m.jp_cpi_yoy is not None:
                    jp_implied = m.compute_taylor_implied_jp()
                    lines.append(
                        f"- 🇯🇵 JP: CPI {m.jp_cpi_yoy:.1f}% / 政策利率 {m.jp_policy_rate}% / GDP {m.jp_gdp_growth_yoy}% / 产出 gap {m.jp_output_gap_pct}%"
                        + (f" / Taylor implied **{jp_implied:.2f}%**" if jp_implied else "")
                    )

                # Taylor differential
                us_cn = m.us_cn_taylor_differential()
                us_jp = m.us_jp_taylor_differential()
                if us_cn is not None:
                    sign = "USD 升值压力" if us_cn > 1 else ("USD 贬值压力" if us_cn < -1 else "中性")
                    lines.append(f"- **🧮 US-CN Taylor differential: {us_cn:+.2f} pp** → {sign}（USD/CNH 预测核心信号）")
                if us_jp is not None:
                    sign = "USD 升值压力" if us_jp > 1 else ("USD 贬值压力" if us_jp < -1 else "中性")
                    lines.append(f"- **🧮 US-JP Taylor differential: {us_jp:+.2f} pp** → {sign}（USD/JPY 预测核心信号）")

            # FX + 商品当前价（Phase 3）
            if m.usd_cnh_spot or m.usd_jpy_spot or m.crude_oil_wti_usd or m.copper_lme_usd_t:
                lines.append("")
                lines.append("### 💱 当前 FX + 商品价格")
                if m.usd_cnh_spot:
                    lines.append(f"- USD/CNH: {m.usd_cnh_spot}")
                if m.usd_jpy_spot:
                    lines.append(f"- USD/JPY: {m.usd_jpy_spot}")
                if m.crude_oil_wti_usd:
                    lines.append(f"- WTI 原油: ${m.crude_oil_wti_usd}/桶")
                if m.copper_lme_usd_t:
                    lines.append(f"- LME 铜: ${m.copper_lme_usd_t}/吨")

        return "\n".join(lines)
