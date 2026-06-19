"""4 个历史时点 14 变量结构状态快照。

MVP 内置 4 个，W2 扩到 8 个（加 1980 Volcker / 1992 ERM / 2018-19 贸易战 / 2020 COVID）。
数值来源详见 prototype-w3-hard-gate/structural_states.py。
"""

from __future__ import annotations

from hindcast.state import EventWindow, MacroEconomic, StructuralState


SNAPSHOTS: dict[str, StructuralState] = {
    "1971-08-12": StructuralState(
        as_of="1971-08-12",
        label="1971 Nixon Shock (pre)",
        values={
            "A1": 0.71, "A2": 0.06, "A3": -0.001, "A4": -200,
            "B1": 7.5, "B2": 0.02, "B3": 0.38,
            "C1": 0.18, "C2": 1.6, "C3": 0,
            "D1": 0.82, "D2": 0.00, "D3": 1.00,
            "E1": 0.00, "E2": 0.42,
        },
        # 1971 弃锚是"经济政策黑天鹅"——非地缘事件 GPR 不 spike，但政策事件信号充分
        # v0.5.1 修补：政治压力 dominant signals 显式标注
        event_window=EventWindow(
            gpr_30d_avg=1.5,
            gpr_30d_trend="stable",
            gpr_spike_recent=False,
            sdn_30d_count=0,
            cb_actions_30d=1,
            policy_event_imminent=True,
            economic_policy_signals=[
                "international_BoP_crisis",
                "dollar_run_accelerating",
                "gold_stock_depletion",
                "inflation_8pct_political_pressure",
                "fed_independence_compromised_by_nixon_pressure",   # 新：Burns 受 Nixon 政治压力
                "nixon_1972_election_year_dovish_bias",            # 新：选举年偏鸽
                "burns_publicly_pressured_to_cut",                 # 新：Nixon 公开施压降息
            ],
            notable_news_headlines=[
                "美元抛售压力加剧 - 法国/瑞士再度兑换美元为黄金",
                "尼克松周末（8/13-15）召集经济顾问 Camp David 会议",
                "Connally 财政部长公开暗示'重大政策变化'",
                "纽约 / 苏黎世金市单周抛售美元 ≥ $1.5b",
            ],
        ),
        # 1971 经济宏观：通胀高 + 失业上升 + Burns 已被尼克松施压降息
        macro=MacroEconomic(
            cpi_headline_yoy=4.4, core_pce_yoy=4.5, unemployment_rate=6.1, natural_unemployment=5.0,
            gdp_growth_qoq_annualized=3.4, output_gap_pct=-0.5,
            current_fed_funds_target=5.50, treasury_2y_yield=6.20, treasury_10y_yield=6.75,
            # 1971 中国文革后期, 计划经济封闭, 数据近无；日本布雷顿森林末期 350 yen 锚定
            cn_cpi_yoy=None, cn_policy_rate=None, cn_gdp_growth_yoy=7.0, cn_output_gap_pct=None,
            jp_cpi_yoy=6.1, jp_policy_rate=6.0, jp_gdp_growth_yoy=8.4, jp_output_gap_pct=2.0,
            usd_cnh_spot=None,           # 人民币离岸市场不存在
            usd_jpy_spot=357.0,          # 弃锚前固定汇率
            crude_oil_wti_usd=3.60,
            copper_lme_usd_t=1100,
            # TIPS 1997 才发行, 跳过
            dxy_index=120.0,             # Trade Weighted USD 1971-08 peak (1973=100 base)
        ),
    ),
    "1973-10-05": StructuralState(
        as_of="1973-10-05",
        label="1973 Oil Embargo (pre)",
        values={
            "A1": 0.78, "A2": 0.07, "A3": 0.001, "A4": -150,
            "B1": 7.0, "B2": 0.01, "B3": 0.34,
            "C1": 0.20, "C2": 1.4, "C3": 0,
            "D1": 0.78, "D2": 0.00, "D3": 0.95,
            "E1": 0.00, "E2": 0.40,
        },
        # 1973 Yom Kippur War 1973-10-06 爆发；GPR 在前 30 天已显著上升（中东紧张持续）
        event_window=EventWindow(
            gpr_30d_avg=2.5,
            gpr_30d_trend="rising",
            gpr_spike_recent=True,
            sdn_30d_count=0,
            cb_actions_30d=0,
            notable_news_headlines=[
                "中东军事调动加剧 - 以色列总动员（10/4-5）",
                "OPEC 维也纳会议宣布将于 10/16 重新评估油价",
                "Sadat 表态 - 阿拉伯国家'已准备好牺牲'",
            ],
        ),
        macro=MacroEconomic(
            cpi_headline_yoy=7.4, core_pce_yoy=5.2, unemployment_rate=4.6, natural_unemployment=5.0,
            gdp_growth_qoq_annualized=5.0, output_gap_pct=2.0,
            current_fed_funds_target=10.78, treasury_2y_yield=7.45, treasury_10y_yield=6.79,
            cn_cpi_yoy=None, cn_gdp_growth_yoy=8.0,
            jp_cpi_yoy=14.2, jp_policy_rate=5.5, jp_gdp_growth_yoy=8.0, jp_output_gap_pct=3.0,
            usd_jpy_spot=266.5,
            crude_oil_wti_usd=3.90,
            copper_lme_usd_t=1700,
            dxy_index=100.0,              # 1973 重定基准点
        ),
    ),
    "1979-10-05": StructuralState(
        as_of="1979-10-05",
        label="1979 Volcker Shock (pre)",
        values={
            "A1": 0.78, "A2": 0.07, "A3": 0.005, "A4": -100,
            "B1": 6.0, "B2": 0.02, "B3": 0.32,
            "C1": 0.22, "C2": 2.0, "C3": 0.5,
            "D1": 0.78, "D2": 0.00, "D3": 0.50,
            "E1": 0.00, "E2": 0.45,
        },
        # Volcker 1979-08 上任后立即放风新货币政策；通胀 13% 全民焦虑
        # 伊朗革命后中东风险持续；Soviet 阿富汗动员（12月入侵预兆）
        event_window=EventWindow(
            gpr_30d_avg=2.2,
            gpr_30d_trend="rising",
            gpr_spike_recent=False,
            sdn_30d_count=1,
            cb_actions_30d=2,
            notable_news_headlines=[
                "Volcker 公开表态'通胀必须以失业为代价控制'",
                "美元再度大跌 - 黄金现货突破 $400",
                "Tehran 大使馆事件（一个月后引爆）",
            ],
        ),
        # 1979-10: Volcker shock 前一日，通胀 12.2%，Fed funds 已升到 11.4%
        macro=MacroEconomic(
            cpi_headline_yoy=12.2, core_pce_yoy=9.5, unemployment_rate=6.0, natural_unemployment=6.0,
            gdp_growth_qoq_annualized=1.0, output_gap_pct=0.5,
            current_fed_funds_target=11.43, treasury_2y_yield=10.45, treasury_10y_yield=9.34,
            cn_gdp_growth_yoy=7.6,             # 改革开放初期
            jp_cpi_yoy=3.6, jp_policy_rate=5.25, jp_gdp_growth_yoy=5.8, jp_output_gap_pct=1.0,
            usd_jpy_spot=240.0,
            crude_oil_wti_usd=20.6,
            copper_lme_usd_t=2070,
            dxy_index=87.0,
        ),
    ),
    "1992-09-15": StructuralState(
        as_of="1992-09-15",
        label="1992 ERM Crisis (pre Black Wednesday)",
        values={
            "A1": 0.60, "A2": 0.06, "A3": -0.005, "A4": -50,
            "B1": 8.5, "B2": 0.045, "B3": 0.65,
            "C1": 0.25, "C2": 0.6, "C3": 0.2,
            "D1": 0.55, "D2": 0.00, "D3": 0.85,
            "E1": 0.00, "E2": 0.30,
        },
        # 1992 ERM 危机是货币危机 → USD 强势 → 黄金压制
        # v0.5.1 修补：加 USD 强势信号 + ERM 解体 policy event
        event_window=EventWindow(
            gpr_30d_avg=0.7,
            gpr_30d_trend="stable",
            gpr_spike_recent=False,
            sdn_30d_count=0,
            cb_actions_30d=6,                  # 升到 6，多国央行密集干预
            policy_event_imminent=True,         # ERM 解体在即
            economic_policy_signals=[
                "european_currency_crisis",
                "USD_safe_haven_strength",     # USD 避险升值
                "GBP_DEM_devaluation_pressure",
                "central_bank_intervention_intensifying",
            ],
            notable_news_headlines=[
                "意大利里拉 9/13 紧急贬值 7%",
                "英国央行已多次干预外汇市场（数十亿美元规模）",
                "Soros: 'ERM 是不可持续的'（公开表态）",
                "DXY 指数 9 月已涨 4% → USD 强势加剧黄金 USD 计价承压",
            ],
        ),
        # 1992-09 美国经济温和复苏期，Greenspan 已多次降息至 3% 附近
        macro=MacroEconomic(
            cpi_headline_yoy=3.0, core_pce_yoy=3.1, unemployment_rate=7.6, natural_unemployment=5.5,
            gdp_growth_qoq_annualized=4.0, output_gap_pct=-2.5,
            current_fed_funds_target=3.00, treasury_2y_yield=4.20, treasury_10y_yield=6.42,
            cn_cpi_yoy=6.4, cn_policy_rate=7.2, cn_gdp_growth_yoy=14.2, cn_output_gap_pct=2.0,
            jp_cpi_yoy=1.6, jp_policy_rate=3.25, jp_gdp_growth_yoy=1.0, jp_output_gap_pct=-1.0,
            usd_cnh_spot=5.55,
            usd_jpy_spot=121.5,
            crude_oil_wti_usd=21.7,
            copper_lme_usd_t=2400,
            dxy_index=85.0,                # 1992 USD 弱
        ),
    ),
    "2008-09-14": StructuralState(
        as_of="2008-09-14",
        label="2008 Lehman (pre)",
        values={
            "A1": 0.64, "A2": 0.06, "A3": -0.045, "A4": -250,
            "B1": 8.0, "B2": 0.03, "B3": 0.64,
            "C1": 0.58, "C2": 1.1, "C3": 0.2,
            "D1": 0.65, "D2": 0.02, "D3": 0.98,
            "E1": 0.00, "E2": 0.25,
        },
        # 2008 雷曼倒闭是金融事件——前 30 日 Bear Stearns 已倒（3月），Fannie/Freddie 接管（9/7）
        # GPR 平稳；金融市场动作密集
        event_window=EventWindow(
            gpr_30d_avg=1.1,
            gpr_30d_trend="stable",
            gpr_spike_recent=False,
            sdn_30d_count=0,
            cb_actions_30d=5,
            notable_news_headlines=[
                "9/7 美政府接管 Fannie Mae & Freddie Mac",
                "9/12 周末 Lehman 寻找买家失败（Barclays/BoA 退出）",
                "AIG 评级被降，市场担忧扩散",
            ],
        ),
        # 2008-09: 雷曼前，Fed funds 已从 5.25% 降到 2%
        macro=MacroEconomic(
            cpi_headline_yoy=5.4, core_pce_yoy=2.5, unemployment_rate=6.1, natural_unemployment=4.7,
            gdp_growth_qoq_annualized=-2.1, output_gap_pct=-2.0,
            current_fed_funds_target=2.00, treasury_2y_yield=2.07, treasury_10y_yield=3.72,
            cn_cpi_yoy=4.9, cn_policy_rate=7.20, cn_gdp_growth_yoy=9.5, cn_output_gap_pct=1.0,
            cn_pmi_manufacturing=51.2,
            jp_cpi_yoy=2.1, jp_policy_rate=0.50, jp_gdp_growth_yoy=0.5, jp_output_gap_pct=-0.5,
            eu_cpi_yoy=3.8, eu_policy_rate=4.25, eu_gdp_growth_yoy=0.6, eu_output_gap_pct=-0.5,
            usd_cnh_spot=6.84, usd_jpy_spot=104.8, eur_usd_spot=1.422,
            crude_oil_wti_usd=101.0,
            copper_lme_usd_t=7050,
            treasury_10y_tips_yield=1.85,
            breakeven_inflation_10y=1.87,
            dxy_index=79.0,                  # 2008-09 USD 弱
        ),
    ),
    "2018-03-21": StructuralState(
        as_of="2018-03-21",
        label="2018 US-China Trade War (pre Section 301)",
        values={
            "A1": 0.62, "A2": 0.20, "A3": -0.025, "A4": 300,
            "B1": 7.5, "B2": 0.05, "B3": 1.05,
            "C1": 0.95, "C2": 0.9, "C3": 0.5,
            "D1": 0.62, "D2": 0.05, "D3": 0.99,
            "E1": 0.10, "E2": 0.28,
        },
        # 2018 贸易战是政策事件——前 30 日 USTR 调查公开，关税已成新闻
        # v0.5.1 修补：priced-in 翻转 signals 显式标注
        event_window=EventWindow(
            gpr_30d_avg=1.1,
            gpr_30d_trend="rising",
            gpr_spike_recent=False,
            sdn_30d_count=3,
            cb_actions_30d=1,
            economic_policy_signals=[
                "tariff_announcement_priced_in_after_8_month_investigation",  # 新：USTR 2017-08 启动调查
                "fed_hike_path_priced_in_via_dot_plot",                       # 新：Powell hike 早已通过 dot plot 暗示
                "tariff_recession_fear_emerging_as_new_driver",              # 新：关税→衰退担忧→长端 yields down
            ],
            notable_news_headlines=[
                "USTR 完成 Section 301 调查报告（针对中国）— 已发酵 8 个月",
                "Trump 多次表态'对华关税势在必行' — 市场早已预期",
                "Powell 接任 Fed 主席（2/5），加息节奏已通过 dot plot 充分 priced-in",
                "Fed funds futures 已定价 2018 全年 3 次加息",
            ],
        ),
        # 2018-03: Powell 刚接任，Fed 处于加息周期中
        macro=MacroEconomic(
            cpi_headline_yoy=2.4, core_pce_yoy=1.9, unemployment_rate=4.0, natural_unemployment=4.5,
            gdp_growth_qoq_annualized=2.5, output_gap_pct=0.3,
            current_fed_funds_target=1.50, treasury_2y_yield=2.30, treasury_10y_yield=2.85,
            cn_cpi_yoy=2.1, cn_policy_rate=4.35, cn_gdp_growth_yoy=6.8, cn_output_gap_pct=0.0,
            cn_pmi_manufacturing=51.5,
            jp_cpi_yoy=1.5, jp_policy_rate=-0.10, jp_gdp_growth_yoy=2.4, jp_output_gap_pct=0.5,
            eu_cpi_yoy=1.3, eu_policy_rate=0.00, eu_gdp_growth_yoy=2.4, eu_output_gap_pct=0.2,
            usd_cnh_spot=6.31, usd_jpy_spot=106.3, eur_usd_spot=1.234,
            crude_oil_wti_usd=65.2,
            copper_lme_usd_t=6800,
            treasury_10y_tips_yield=0.78,
            breakeven_inflation_10y=2.07,
            dxy_index=89.5,                  # 2018-03 USD 中性
        ),
    ),
    "2020-02-28": StructuralState(
        as_of="2020-02-28",
        label="2020 COVID Crash (pre)",
        values={
            "A1": 0.60, "A2": 0.20, "A3": -0.025, "A4": 600,
            "B1": 7.0, "B2": 0.06, "B3": 1.10,
            "C1": 1.10, "C2": 1.5, "C3": 0.8,
            "D1": 0.60, "D2": 0.10, "D3": 0.99,
            "E1": 0.20, "E2": 0.30,
        },
        # 2020 COVID 前 30 日疫情已全球扩散；GPR spike；央行紧急动作密集
        event_window=EventWindow(
            gpr_30d_avg=1.8,
            gpr_30d_trend="rising",
            gpr_spike_recent=True,
            sdn_30d_count=2,
            cb_actions_30d=3,
            notable_news_headlines=[
                "WHO 2/25 提升 COVID 风险评级（high）",
                "意大利北部封城（2/22）, 韩国大邱封城",
                "美股 2/24 起连续暴跌 - VIX 突破 40",
                "Fed 主席 Powell 紧急表态准备行动",
            ],
        ),
        # 2020-02: COVID 爆发前夕，Fed funds 1.50-1.75
        macro=MacroEconomic(
            cpi_headline_yoy=2.3, core_pce_yoy=1.8, unemployment_rate=3.5, natural_unemployment=4.5,
            gdp_growth_qoq_annualized=2.1, output_gap_pct=0.5,
            current_fed_funds_target=1.625, treasury_2y_yield=1.13, treasury_10y_yield=1.13,
            cn_cpi_yoy=5.2, cn_policy_rate=4.05, cn_gdp_growth_yoy=6.0, cn_output_gap_pct=-1.0,
            cn_pmi_manufacturing=35.7,         # COVID 初期暴跌
            jp_cpi_yoy=0.4, jp_policy_rate=-0.10, jp_gdp_growth_yoy=-0.7, jp_output_gap_pct=-1.5,
            eu_cpi_yoy=1.2, eu_policy_rate=0.00, eu_gdp_growth_yoy=1.0, eu_output_gap_pct=0.1,
            usd_cnh_spot=7.01, usd_jpy_spot=107.9, eur_usd_spot=1.103,
            crude_oil_wti_usd=44.8,
            copper_lme_usd_t=5615,
            treasury_10y_tips_yield=-0.10,
            breakeven_inflation_10y=1.23,
            dxy_index=98.0,                  # COVID 前 USD 强
        ),
    ),
    "2022-02-23": StructuralState(
        as_of="2022-02-23",
        label="2022 Russia Sanctions (pre)",
        values={
            "A1": 0.59, "A2": 0.37, "A3": -0.035, "A4": 650,
            "B1": 7.0, "B2": 0.085, "B3": 1.20,
            "C1": 1.20, "C2": 2.0, "C3": 1.5,
            "D1": 0.58, "D2": 0.25, "D3": 0.99,
            "E1": 0.30, "E2": 0.32,
        },
        # 2022 俄乌前 30 日 - 俄军大规模集结边境已数月；GPR 持续 spike
        event_window=EventWindow(
            gpr_30d_avg=3.5,
            gpr_30d_trend="rising",
            gpr_spike_recent=True,
            sdn_30d_count=8,
            cb_actions_30d=2,
            notable_news_headlines=[
                "2/21 普京承认顿涅茨克/卢甘斯克独立",
                "美/英已开始制裁俄罗斯精英 + 部分银行",
                "俄军边境集结达 19 万人, 北约高度戒备",
                "拜登声明'入侵已经开始'",
            ],
        ),
        # 2022-02: 通胀 7.5% 创 40 年新高, Fed 即将开启加息周期
        macro=MacroEconomic(
            cpi_headline_yoy=7.5, core_pce_yoy=5.2, unemployment_rate=4.0, natural_unemployment=4.5,
            gdp_growth_qoq_annualized=6.9, output_gap_pct=1.0,
            current_fed_funds_target=0.125, treasury_2y_yield=1.55, treasury_10y_yield=1.97,
            cn_cpi_yoy=0.9, cn_policy_rate=3.70, cn_gdp_growth_yoy=4.8, cn_output_gap_pct=-0.5,
            cn_pmi_manufacturing=50.2,
            jp_cpi_yoy=0.5, jp_policy_rate=-0.10, jp_gdp_growth_yoy=0.7, jp_output_gap_pct=-0.5,
            eu_cpi_yoy=5.9, eu_policy_rate=0.00, eu_gdp_growth_yoy=4.6, eu_output_gap_pct=-0.5,
            usd_cnh_spot=6.32, usd_jpy_spot=115.0, eur_usd_spot=1.131,
            crude_oil_wti_usd=92.1,
            copper_lme_usd_t=9870,
            treasury_10y_tips_yield=-0.20,
            breakeven_inflation_10y=2.17,
            dxy_index=96.0,
        ),
    ),
    "2026-05-14": StructuralState(
        as_of="2026-05-14",
        label="Today (实时模拟基线)",
        # 数值依据 01-PRODUCT-DESIGN-v0.4.md §3.2.1 表格 "当前值 (2026-05)"
        # 由 IMF COFER / FRED / WGC / OFAC SDN / GPR / BIS / Correlates of War 等公开来源整理
        values={
            "A1": 0.58,    # USD 储备占比仍下降
            "A2": 0.28,    # QT 缩表至 28%
            "A3": -0.037,  # 经常项逆差
            "A4": 1100,    # 央行年购金量历史高位
            "B1": 6.5,     # Fed CBI 受 Trump 2.0 任命压力下降
            "B2": 0.062,   # 财政赤字结构性高位
            "B3": 1.24,    # 公共债务突破战时峰值
            "C1": 1.34,    # 中国 CINC 已超过美国
            "C2": 2.5,     # GPR 持续高位（俄乌+中东+中美科技战）
            "C3": 3.2,     # 武器化金融每月平均
            "D1": 0.54,    # USD 贸易计价缓降
            "D2": 0.30,    # 中俄~95% / 中沙~40% 平均
            "D3": 0.99,    # SWIFT 仍 99%，但 CIPS +60%/年
            "E1": 0.42,    # XAU-BTC 60日相关性
            "E2": 0.046,   # 中国央行金储占比（代表新兴市场）
        },
        # Today 2026-05-14：实时模拟基线——没有"刚发生大事件"，但持续高位 GPR / 武器化 / 中美摩擦
        event_window=EventWindow(
            gpr_30d_avg=2.5,
            gpr_30d_trend="stable",
            gpr_spike_recent=False,
            sdn_30d_count=4,
            cb_actions_30d=1,
            notable_news_headlines=[
                "持续高位 GPR（俄乌/中东/中美科技战）",
                "Fed 4 月议息维持利率不变, Trump 公开施压降息",
                "中沙本币结算占比扩至 40%+",
            ],
        ),
        # 2026-05 today: Trump 施压降息 + 通胀回落但仍高
        macro=MacroEconomic(
            cpi_headline_yoy=2.8, core_pce_yoy=2.6, unemployment_rate=4.1, natural_unemployment=4.5,
            gdp_growth_qoq_annualized=1.8, output_gap_pct=-0.5,
            current_fed_funds_target=4.375, treasury_2y_yield=3.85, treasury_10y_yield=4.30,
            cn_cpi_yoy=0.6, cn_policy_rate=3.10, cn_gdp_growth_yoy=4.7, cn_output_gap_pct=-1.0,
            cn_pmi_manufacturing=49.5,        # 中国通缩压力 + PMI 在荣枯线下
            jp_cpi_yoy=2.7, jp_policy_rate=0.50, jp_gdp_growth_yoy=0.6, jp_output_gap_pct=0.0,
            eu_cpi_yoy=2.2, eu_policy_rate=2.40, eu_gdp_growth_yoy=1.0, eu_output_gap_pct=-0.3,
            usd_cnh_spot=7.23, usd_jpy_spot=147.5, eur_usd_spot=1.09,
            crude_oil_wti_usd=72.5,
            copper_lme_usd_t=9450,
            treasury_10y_tips_yield=2.05,
            breakeven_inflation_10y=2.25,
            dxy_index=98.5,                  # today USD 略强
        ),
    ),
}


ALL_SNAPSHOTS = list(SNAPSHOTS.values())
