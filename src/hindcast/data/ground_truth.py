"""4 时点真实金价路径——回测用。

数据来自 WGC 历史价格 + Bloomberg/NYSE。T+5/T+20 是交易日口径。
"""

from __future__ import annotations


"""
Ground truth for backtest:
- GROUND_TRUTH: XAU/USD T+5/T+20 directional outcomes
- POLICY_RATE_GROUND_TRUTH: Fed's actual decision at next FOMC after each timepoint
"""


# Fed 在下次 FOMC（≤ 60 天内）的实际决议 — 公开 FOMC 历史
POLICY_RATE_GROUND_TRUTH: dict[str, dict] = {
    "1971-08-12": {
        "next_fomc_date": "1971-09-21",
        "action": "cut",
        "bps": 25,
        "note": "Burns Fed 在尼克松政治压力下继续宽松；Fed funds 从 5.5% 缓步降至 4.5% 年底",
    },
    "1973-10-05": {
        "next_fomc_date": "1973-10-16",
        "action": "hike",
        "bps": 50,
        "note": "石油危机后 Burns 加速紧缩；Fed funds 从 10.8% 升至 11.5%+",
    },
    "1979-10-05": {
        "next_fomc_date": "1979-10-06",   # Volcker shock 周末紧急会议
        "action": "hike",
        "bps": 100,
        "note": "Volcker Saturday Night Massacre 10/6：宣布新货币操作框架 + 大幅加息；Fed funds 数月内从 11% 飙至 17%",
    },
    "1992-09-15": {
        "next_fomc_date": "1992-10-06",
        "action": "hold",
        "bps": 0,
        "note": "Greenspan 在 ERM 危机期间维持 3% 不变；ERM 是欧洲事件不影响美国政策",
    },
    "2008-09-14": {
        "next_fomc_date": "2008-10-08",
        "action": "cut",
        "bps": 50,
        "note": "雷曼倒闭后协调降息 10/8（与 BOE/BOJ/ECB 联合），月底再降；Fed funds 从 2% 降至 1%",
    },
    "2018-03-21": {
        "next_fomc_date": "2018-03-21",   # 本日就是 FOMC
        "action": "hike",
        "bps": 25,
        "note": "Powell 主持的第一次 FOMC；按预期 +25 bps 至 1.75%",
    },
    "2020-02-28": {
        "next_fomc_date": "2020-03-03",   # 紧急 FOMC
        "action": "cut",
        "bps": 50,
        "note": "COVID 紧急降息 50bps；3/15 又紧急降 100bps 至 0%",
    },
    "2022-02-23": {
        "next_fomc_date": "2022-03-16",
        "action": "hike",
        "bps": 25,
        "note": "Fed 加息周期启动；首次 +25 bps 至 0.50%；之后 7 次连续大幅加息",
    },
    "2026-05-14": {
        "next_fomc_date": "2026-06-17",
        "action": "hold",
        "bps": 0,
        "note": "Today: 通胀回落但仍高 + Trump 施压降息 + Fed 独立性博弈中；6 月 FOMC 维持 4.25-4.50 不变（占位预测，非真实历史）",
    },
}


# 桥梁变量 ground truth (TIPS / BEI / DXY) — for XAU 集成预测
# TIPS 仅 1997+ 存在
BRIDGE_GROUND_TRUTH: dict[str, dict[str, dict]] = {
    "1971-08-12": {
        "DXY": {"T+5": {"dir": "down", "actual_bps": -250}, "T+20": {"dir": "down", "actual_bps": -700}},  # 弃锚后 USD 大贬
    },
    "1973-10-05": {
        "DXY": {"T+5": {"dir": "up", "actual_bps": 100}, "T+20": {"dir": "up", "actual_bps": 350}},
    },
    "1979-10-05": {
        "DXY": {"T+5": {"dir": "up", "actual_bps": 150}, "T+20": {"dir": "up", "actual_bps": 400}},  # Volcker 强势 USD
    },
    "1992-09-15": {
        "DXY": {"T+5": {"dir": "up", "actual_bps": 100}, "T+20": {"dir": "up", "actual_bps": 250}},  # ERM 后 USD 升
    },
    "2008-09-14": {
        "US_10Y_TIPS": {"T+5": {"dir": "down", "actual_bps": -25}, "T+20": {"dir": "down", "actual_bps": -50}},
        "US_10Y_BEI":  {"T+5": {"dir": "down", "actual_bps": -50}, "T+20": {"dir": "down", "actual_bps": -120}},
        "DXY": {"T+5": {"dir": "up", "actual_bps": 350}, "T+20": {"dir": "up", "actual_bps": 700}},  # flight to USD
    },
    "2018-03-21": {
        "US_10Y_TIPS": {"T+5": {"dir": "down", "actual_bps": -5}, "T+20": {"dir": "flat", "actual_bps": -2}},
        "US_10Y_BEI":  {"T+5": {"dir": "flat", "actual_bps": 3}, "T+20": {"dir": "down", "actual_bps": -10}},
        "DXY": {"T+5": {"dir": "down", "actual_bps": -50}, "T+20": {"dir": "down", "actual_bps": -150}},
    },
    "2020-02-28": {
        "US_10Y_TIPS": {"T+5": {"dir": "down", "actual_bps": -45}, "T+20": {"dir": "down", "actual_bps": -80}},
        "US_10Y_BEI":  {"T+5": {"dir": "down", "actual_bps": -25}, "T+20": {"dir": "down", "actual_bps": -65}},
        "DXY": {"T+5": {"dir": "down", "actual_bps": -120}, "T+20": {"dir": "up", "actual_bps": 350}},   # 初期 USD 跌后 flight up
    },
    "2022-02-23": {
        "US_10Y_TIPS": {"T+5": {"dir": "up", "actual_bps": 5}, "T+20": {"dir": "up", "actual_bps": 30}},
        "US_10Y_BEI":  {"T+5": {"dir": "up", "actual_bps": 15}, "T+20": {"dir": "up", "actual_bps": 35}},
        "DXY": {"T+5": {"dir": "up", "actual_bps": 100}, "T+20": {"dir": "up", "actual_bps": 350}},
    },
}


# FX 方向 ground truth (T+5 / T+20)
# dir=up 表示 USD 升值（USD/CNH 升 / USD/JPY 升）
#
# 阈值规则（基于汇率制度）:
#   USD/CNH (管制): |actual| < 0.5% → flat (PBoC 控制下的"日常波动")
#   USD/JPY (自由): |actual| < 0.3% → flat
FX_GROUND_TRUTH: dict[str, dict[str, dict]] = {
    "1971-08-12": {
        "USD/JPY": {"T+5": {"dir": "down", "actual_pct": -3.5}, "T+20": {"dir": "down", "actual_pct": -8.0}},
    },
    "1973-10-05": {
        "USD/JPY": {"T+5": {"dir": "up", "actual_pct": 1.2}, "T+20": {"dir": "up", "actual_pct": 4.0}},
    },
    "1979-10-05": {
        "USD/JPY": {"T+5": {"dir": "down", "actual_pct": -2.5}, "T+20": {"dir": "down", "actual_pct": -5.0}},
    },
    "1992-09-15": {
        # CNH 管制下 PBoC 维持 ~5.55 hard peg, 微小波动都算 flat
        "USD/CNH": {"T+5": {"dir": "flat", "actual_pct": 0.0}, "T+20": {"dir": "flat", "actual_pct": 0.1}},
        "USD/JPY": {"T+5": {"dir": "down", "actual_pct": -1.0}, "T+20": {"dir": "down", "actual_pct": -3.5}},
    },
    "2008-09-14": {
        # 雷曼后 PBoC 重定 hard peg ~6.83, 都 flat
        "USD/CNH": {"T+5": {"dir": "flat", "actual_pct": 0.1}, "T+20": {"dir": "flat", "actual_pct": -0.3}},
        "USD/JPY": {"T+5": {"dir": "down", "actual_pct": -5.5}, "T+20": {"dir": "down", "actual_pct": -8.0}},
        # EUR/USD: 雷曼初期 Fed/财政紧急行动 → USD 短暂走弱 EUR up; 随后 flight-to-USD 崩跌
        "EUR/USD": {"T+5": {"dir": "up", "actual_pct": 1.8}, "T+20": {"dir": "down", "actual_pct": -5.8}},
    },
    "2018-03-21": {
        # PBoC 反向中间价压制波动, T+5 -0.3% 在管制阈值内 → flat
        "USD/CNH": {"T+5": {"dir": "flat", "actual_pct": -0.3}, "T+20": {"dir": "flat", "actual_pct": 0.5}},
        "USD/JPY": {"T+5": {"dir": "down", "actual_pct": -0.8}, "T+20": {"dir": "down", "actual_pct": -1.5}},
        # EUR/USD: Powell 加息周期 vs ECB ZIRP, 但 20 日内尚未明显发散 → flat
        "EUR/USD": {"T+5": {"dir": "flat", "actual_pct": -0.2}, "T+20": {"dir": "flat", "actual_pct": 0.3}},
    },
    "2020-02-28": {
        # COVID 期间 PBoC 让 CNH 部分反映全球冲击, T+20 +2% 属于真实政策放手
        "USD/CNH": {"T+5": {"dir": "flat", "actual_pct": -0.5}, "T+20": {"dir": "up", "actual_pct": 2.0}},
        "USD/JPY": {"T+5": {"dir": "down", "actual_pct": -2.0}, "T+20": {"dir": "down", "actual_pct": -1.5}},
        # EUR/USD: Fed 紧急降息 150bps 快于 ECB(已 ZIRP) → USD 短期走弱 EUR up (中途 USD spike 后回升)
        "EUR/USD": {"T+5": {"dir": "up", "actual_pct": 2.3}, "T+20": {"dir": "up", "actual_pct": 1.0}},
    },
    "2022-02-23": {
        # 俄乌后小波动, 仍在管制阈值内
        "USD/CNH": {"T+5": {"dir": "flat", "actual_pct": -0.3}, "T+20": {"dir": "flat", "actual_pct": 0.5}},
        "USD/JPY": {"T+5": {"dir": "up", "actual_pct": 1.5}, "T+20": {"dir": "up", "actual_pct": 4.5}},
        # EUR/USD: 俄乌能源冲击击垮欧元区贸易条件 (与 USD/JPY 同期大涨同构) → EUR/USD down/down
        "EUR/USD": {"T+5": {"dir": "down", "actual_pct": -1.7}, "T+20": {"dir": "down", "actual_pct": -2.7}},
    },
}


# 大宗商品 ground truth (T+5 / T+20)
COMMODITY_GROUND_TRUTH: dict[str, dict[str, dict]] = {
    "1971-08-12": {
        "CRUDE_OIL": {"T+5": {"dir": "flat", "actual_pct": 1.0}, "T+20": {"dir": "up", "actual_pct": 3.0}},
        "COPPER":    {"T+5": {"dir": "flat", "actual_pct": 0.5}, "T+20": {"dir": "down", "actual_pct": -2.0}},
    },
    "1973-10-05": {
        "CRUDE_OIL": {"T+5": {"dir": "up", "actual_pct": 15.0}, "T+20": {"dir": "up", "actual_pct": 80.0}},  # OPEC 禁运
        "COPPER":    {"T+5": {"dir": "up", "actual_pct": 4.0}, "T+20": {"dir": "up", "actual_pct": 10.0}},
    },
    "1979-10-05": {
        "CRUDE_OIL": {"T+5": {"dir": "up", "actual_pct": 5.0}, "T+20": {"dir": "up", "actual_pct": 15.0}},
        "COPPER":    {"T+5": {"dir": "up", "actual_pct": 3.0}, "T+20": {"dir": "down", "actual_pct": -8.0}},  # Volcker 紧缩
    },
    "1992-09-15": {
        "CRUDE_OIL": {"T+5": {"dir": "down", "actual_pct": -2.0}, "T+20": {"dir": "down", "actual_pct": -4.0}},
        "COPPER":    {"T+5": {"dir": "down", "actual_pct": -1.5}, "T+20": {"dir": "down", "actual_pct": -3.5}},
    },
    "2008-09-14": {
        "CRUDE_OIL": {"T+5": {"dir": "down", "actual_pct": -10.0}, "T+20": {"dir": "down", "actual_pct": -25.0}},
        "COPPER":    {"T+5": {"dir": "down", "actual_pct": -8.0}, "T+20": {"dir": "down", "actual_pct": -30.0}},
    },
    "2018-03-21": {
        "CRUDE_OIL": {"T+5": {"dir": "up", "actual_pct": 1.5}, "T+20": {"dir": "up", "actual_pct": 4.5}},
        "COPPER":    {"T+5": {"dir": "down", "actual_pct": -2.0}, "T+20": {"dir": "down", "actual_pct": -3.5}},
    },
    "2020-02-28": {
        "CRUDE_OIL": {"T+5": {"dir": "down", "actual_pct": -15.0}, "T+20": {"dir": "down", "actual_pct": -55.0}},  # 历史最大暴跌
        "COPPER":    {"T+5": {"dir": "down", "actual_pct": -3.5}, "T+20": {"dir": "down", "actual_pct": -16.0}},
    },
    "2022-02-23": {
        "CRUDE_OIL": {"T+5": {"dir": "up", "actual_pct": 12.0}, "T+20": {"dir": "up", "actual_pct": 25.0}},  # 战争 + 制裁
        "COPPER":    {"T+5": {"dir": "up", "actual_pct": 5.0}, "T+20": {"dir": "down", "actual_pct": -3.0}},
    },
}


# US 2Y / 10Y 收益率方向 ground truth (T+5 / T+20 交易日)
# 数据来源：FRED DGS2 / DGS10 历史
YIELD_GROUND_TRUTH: dict[str, dict[str, dict]] = {
    "1971-08-12": {
        "US_2Y": {"T+5": {"dir": "down", "actual_bps": -30}, "T+20": {"dir": "down", "actual_bps": -50}},
        "US_10Y": {"T+5": {"dir": "down", "actual_bps": -15}, "T+20": {"dir": "down", "actual_bps": -30}},
    },
    "1973-10-05": {
        "US_2Y": {"T+5": {"dir": "up", "actual_bps": 25}, "T+20": {"dir": "up", "actual_bps": 60}},
        "US_10Y": {"T+5": {"dir": "up", "actual_bps": 15}, "T+20": {"dir": "up", "actual_bps": 35}},
    },
    "1979-10-05": {
        "US_2Y": {"T+5": {"dir": "up", "actual_bps": 100}, "T+20": {"dir": "up", "actual_bps": 250}},
        "US_10Y": {"T+5": {"dir": "up", "actual_bps": 60}, "T+20": {"dir": "up", "actual_bps": 150}},
    },
    "1992-09-15": {
        "US_2Y": {"T+5": {"dir": "down", "actual_bps": -15}, "T+20": {"dir": "down", "actual_bps": -20}},
        "US_10Y": {"T+5": {"dir": "down", "actual_bps": -10}, "T+20": {"dir": "flat", "actual_bps": -5}},
    },
    "2008-09-14": {
        "US_2Y": {"T+5": {"dir": "down", "actual_bps": -55}, "T+20": {"dir": "down", "actual_bps": -130}},
        "US_10Y": {"T+5": {"dir": "down", "actual_bps": -20}, "T+20": {"dir": "down", "actual_bps": -55}},
    },
    "2018-03-21": {
        "US_2Y": {"T+5": {"dir": "flat", "actual_bps": 3}, "T+20": {"dir": "down", "actual_bps": -8}},
        "US_10Y": {"T+5": {"dir": "down", "actual_bps": -5}, "T+20": {"dir": "down", "actual_bps": -10}},
    },
    "2020-02-28": {
        "US_2Y": {"T+5": {"dir": "down", "actual_bps": -55}, "T+20": {"dir": "down", "actual_bps": -85}},
        "US_10Y": {"T+5": {"dir": "down", "actual_bps": -55}, "T+20": {"dir": "down", "actual_bps": -55}},
    },
    "2022-02-23": {
        "US_2Y": {"T+5": {"dir": "up", "actual_bps": 25}, "T+20": {"dir": "up", "actual_bps": 70}},
        "US_10Y": {"T+5": {"dir": "up", "actual_bps": 15}, "T+20": {"dir": "up", "actual_bps": 45}},
    },
}


GROUND_TRUTH: dict[str, dict] = {
    "1971-08-12": {
        "event": "Nixon Shock (1971-08-15 announcement)",
        "base_price_usd_oz": 43.0,
        "T+5": {"dir": "up", "actual_pct": 6.0},
        "T+20": {"dir": "up", "actual_pct": 9.5},
    },
    "1973-10-05": {
        "event": "First Oil Embargo (1973-10-06 OPEC announcement)",
        "base_price_usd_oz": 100.0,
        "T+5": {"dir": "up", "actual_pct": 8.0},
        "T+20": {"dir": "up", "actual_pct": 15.0},
    },
    "1979-10-05": {
        "event": "Volcker Saturday Night Massacre (1979-10-06 new operating procedures)",
        "base_price_usd_oz": 385.0,
        "T+5": {"dir": "up", "actual_pct": 3.0},     # gold dipped初, 反弹至 ~$395
        "T+20": {"dir": "up", "actual_pct": 6.0},    # 持续上行至 ~$408（Iran/Afghanistan 加持）
    },
    "1992-09-15": {
        "event": "Black Wednesday — UK forced out of ERM (1992-09-16)",
        "base_price_usd_oz": 355.0,
        "T+5": {"dir": "down", "actual_pct": -2.5},  # USD 强势 → 金价小跌至 ~$346
        "T+20": {"dir": "flat", "actual_pct": -1.5}, # 维持低位 ~$350
    },
    "2008-09-14": {
        "event": "Lehman bankruptcy (2008-09-15)",
        "base_price_usd_oz": 787.0,
        "T+5": {"dir": "up", "actual_pct": 11.5},
        "T+20": {"dir": "flat", "actual_pct": -0.5},
    },
    "2018-03-21": {
        "event": "Trump Section 301 tariffs on China (2018-03-22)",
        "base_price_usd_oz": 1331.0,
        "T+5": {"dir": "flat", "actual_pct": -0.5},   # 关税影响初期被 USD 强势抵消
        "T+20": {"dir": "up", "actual_pct": 1.0},     # 缓慢上行 ~$1345
    },
    "2020-02-28": {
        "event": "COVID-19 global panic week (2020-02-28 onwards)",
        "base_price_usd_oz": 1564.0,
        "T+5": {"dir": "up", "actual_pct": 7.0},      # 反弹到 ~$1672（3/6）
        "T+20": {"dir": "up", "actual_pct": 3.4},     # 中间大跌后反弹到 ~$1617（3/27）
    },
    "2022-02-23": {
        "event": "Russia invasion + reserve freeze (2022-02-24/26)",
        "base_price_usd_oz": 1909.0,
        "T+5": {"dir": "up", "actual_pct": 4.5},
        "T+20": {"dir": "up", "actual_pct": 1.5},
    },
}
