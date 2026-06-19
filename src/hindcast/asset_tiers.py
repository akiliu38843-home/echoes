"""按资产类别·各用经济上正确单位·零 LLM 实测档位（17-ADR 档位设计）。

经济学常识落地（产品负责人 2026-05-16 纠正"别只拿汇率推广"后重做）：
- 汇率/黄金/商品 → log% ；利率 → Δ基点(bp) ；曲线 2s10s → bp 水平 + 倒挂占比
- 档位**全部锚在各资产自己的历史经验分位**（非正态 σ 倍数；商品尤其弃 √时间σ）
- **上行/下行分开**（非对称：股票/油下行肥尾），另出"峰谷振幅"两侧分位
- 每资产报数据起止 + N，自带覆盖度 caveat（够不到就如实，不外推）

一次 /state/asof 取回所有 level_2 资产 → 全量约 1148 次本地 HTTP，缓存复用。
"""
from __future__ import annotations

import datetime as _dt
import json
import math
import os
import statistics as _st
from typing import Optional

import requests

FACTUAL_RAG = "http://127.0.0.1:8002"
_NOPROXY = {"http": None, "https": None}
_CACHE = "/tmp/multiasset_weekly.json"
SPAN_START, SPAN_END = "2003-01-06", "2024-12-30"
HORIZONS = (1, 3, 6, 12, 24)

# var_id → (中文名, 单位类型)  单位类型: pct=log% / bp=利率基点
ASSETS = {
    "usdjpy_spot":  ("USD/JPY", "pct"),
    "eurusd_spot":  ("EUR/USD", "pct"),
    "dxy_index":    ("美元指数 DXY", "pct"),
    "xau_usd_spot": ("黄金 XAU", "pct"),
    "wti_crude":    ("WTI 原油", "pct"),
    "brent_crude":  ("Brent 原油", "pct"),
    "copper_lme":   ("LME 铜", "pct"),
    "us_2y_yield":  ("美债 2Y", "bp"),
    "us_10y_yield": ("美债 10Y", "bp"),
    "us_30y_yield": ("美债 30Y", "bp"),
}


def _mondays() -> list[str]:
    d = _dt.date.fromisoformat(SPAN_START)
    e = _dt.date.fromisoformat(SPAN_END)
    out = []
    while d <= e:
        out.append(d.isoformat())
        d += _dt.timedelta(days=7)
    return out


def fetch_all() -> dict[str, dict]:
    cache = json.load(open(_CACHE)) if os.path.exists(_CACHE) else {}
    weeks = _mondays()
    miss = [w for w in weeks if w not in cache]
    if miss:
        print(f"[fetch] {len(miss)}/{len(weeks)} 周点待抓 (缓存 {len(cache)})")
        for i, w in enumerate(miss):
            try:
                r = requests.get(f"{FACTUAL_RAG}/state/asof", params={"date": w},
                                 timeout=8, proxies=_NOPROXY)
                l2 = r.json().get("level_2", {}) if r.status_code == 200 else {}
                cache[w] = {k: (l2[k].get("value") if isinstance(l2.get(k), dict) else None)
                            for k in ASSETS}
            except Exception:
                cache[w] = {k: None for k in ASSETS}
            if (i + 1) % 100 == 0:
                json.dump(cache, open(_CACHE, "w")); print(f"  ...{i+1}/{len(miss)}")
        json.dump(cache, open(_CACHE, "w"))
    return {w: cache[w] for w in weeks if w in cache}


def _q(xs: list[float], p: float) -> float:
    if not xs:
        return float("nan")
    s = sorted(xs)
    return s[min(len(s) - 1, int(p * len(s)))]


def _series(data: dict, var: str):
    wk = [w for w in sorted(data) if data[w].get(var) is not None]
    return wk, [data[w][var] for w in wk], [_dt.date.fromisoformat(w) for w in wk]


def analyze_asset(var: str, data: dict) -> None:
    name, unit = ASSETS[var]
    wk, px, wd = _series(data, var)
    if len(wk) < 200:
        print(f"\n━━━ {name} ({var}) ━━━  数据不足 N={len(wk)}，按设计留白（不外推）")
        return
    # σ_a：pct 用周对数收益年化%；含非正价(2020负油价)→log无定义, 改简单收益
    npos = sum(1 for v in px if v is not None and v <= 0)
    if unit == "pct":
        if npos:
            rr = [(px[i]-px[i-1])/px[i-1] for i in range(1, len(px)) if px[i-1] != 0]
        else:
            rr = [math.log(px[i]/px[i-1]) for i in range(1, len(px))
                  if px[i-1] > 0 and px[i] > 0]
        sig_a = _st.pstdev(rr) * math.sqrt(52) * 100
        sa_u = "%/yr"
    else:
        dl = [(px[i] - px[i-1]) * 100 for i in range(1, len(px))]
        sig_a = _st.pstdev(dl) * math.sqrt(52)
        sa_u = "bp/yr"

    dec = list(range(0, len(wk), 4))  # 月度决策点

    def moves(H: int):
        """→ (net[], drawdown[], runup[])  net/振幅: pct 用%，bp 用基点"""
        net, dd, ru = [], [], []
        for i in dec:
            end = wd[i] + _dt.timedelta(days=int(H * 30.44))
            fj = [j for j in range(i + 1, len(wk)) if wd[j] <= end]
            if len(fj) < max(4, H):
                continue
            p0 = px[i]; fwd = [px[j] for j in fj]
            if unit == "pct":
                if p0 <= 0:
                    continue
                net.append((fwd[-1] - p0) / p0 * 100)
                dd.append((p0 - min(fwd)) / p0 * 100)      # 最大跌幅(正数)
                ru.append((max(fwd) - p0) / p0 * 100)       # 最大涨幅
            else:
                net.append((fwd[-1] - p0) * 100)
                dd.append((p0 - min(fwd)) * 100)            # 最大下行 bp
                ru.append((max(fwd) - p0) * 100)            # 最大上行 bp
        return net, dd, ru

    u = "%" if unit == "pct" else "bp"
    print(f"\n━━━ {name} ({var})  单位:{u}  ━━━")
    if npos:
        flag = (f"   🛑含非正价{npos}个(如2020负油价)→log无定义,σ_a用简单收益; "
                "√时间σ彻底失效→商品必须独立框架(此即铁证)")
    elif var in ("wti_crude", "brent_crude", "copper_lme") or unit == "bp":
        flag = "   ⚠️商品/利率: √时间σ仅参考, 档位以实测分位为准"
    else:
        flag = ""
    print(f"  数据 {wk[0]}→{wk[-1]}  N周={len(wk)}  σ_a≈{sig_a:.1f}{sa_u}{flag}")
    print(f"  {'H':>3} | 净移动·跌侧(80/95/99) | 净移动·涨侧(80/95/99) | "
          f"峰谷跌(50/80/95/99) | 峰谷涨(50/80/95/99) | 肥尾比 99净/3σ_H")
    for H in HORIZONS:
        net, dd, ru = moves(H)
        if len(net) < 12:
            print(f"  {H:>3} | 前瞻数据不足 (N={len(net)})，留白")
            continue
        sH = sig_a * math.sqrt(H / 12)
        dn = [-x for x in net if x < 0]            # 跌幅(正)
        up = [x for x in net if x > 0]
        fat = (max(_q(dn, .99) if dn else 0, _q(up, .99) if up else 0) /
               (3 * sH)) if sH else float("nan")
        fmt = (lambda v: f"{v:5.1f}") if unit == "pct" else (lambda v: f"{v:5.0f}")
        print(f"  {H:>3} | {fmt(_q(dn,.80))}/{fmt(_q(dn,.95))}/{fmt(_q(dn,.99))} "
              f"| {fmt(_q(up,.80))}/{fmt(_q(up,.95))}/{fmt(_q(up,.99))} "
              f"| {fmt(_q(dd,.50))}/{fmt(_q(dd,.80))}/{fmt(_q(dd,.95))}/{fmt(_q(dd,.99))} "
              f"| {fmt(_q(ru,.50))}/{fmt(_q(ru,.80))}/{fmt(_q(ru,.95))}/{fmt(_q(ru,.99))} "
              f"| {fat:.2f}x")
    print("  档位读法: 横盘<50分位 · 小50-80 · 中80-95 · 大95-99 · 极端>99（各侧独立, 非对称）")


def analyze_curve(data: dict) -> None:
    """2s10s 曲线: bp 水平 + 倒挂占比 + Δ移动（阈值型信号, 非涨跌幅）。"""
    wk = [w for w in sorted(data)
          if data[w].get("us_10y_yield") is not None
          and data[w].get("us_2y_yield") is not None]
    if len(wk) < 200:
        print("\n━━━ 2s10s 曲线 ━━━ 数据不足，留白"); return
    sp = [(data[w]["us_10y_yield"] - data[w]["us_2y_yield"]) * 100 for w in wk]  # bp
    inv = sum(1 for s in sp if s < 0) / len(sp) * 100
    print(f"\n━━━ 2s10s 收益率曲线 (bp 水平, 阈值型) ━━━")
    print(f"  数据 {wk[0]}→{wk[-1]}  N={len(wk)}")
    print(f"  水平分位(bp): p5={_q(sp,.05):.0f} p25={_q(sp,.25):.0f} "
          f"中位={_q(sp,.50):.0f} p75={_q(sp,.75):.0f} p95={_q(sp,.95):.0f}")
    print(f"  **倒挂(<0bp)历史占比 = {inv:.0f}%**  →  曲线是'水平/穿越'信号(倒挂=衰退前兆),"
          f" 非'涨跌幅'档位；建议档: 深倒挂<{_q(sp,.05):.0f} / 倒挂<0 / 平 0~{_q(sp,.50):.0f}"
          f" / 陡>{_q(sp,.95):.0f}")


def run() -> None:
    data = fetch_all()
    if len(data) < 300:
        print("数据不足（factual_rag 在线？）"); return
    print("=" * 78)
    print("按资产类别·正确单位·零 LLM 实测档位  (锚定各资产自身历史经验分位, 非正态)")
    print("=" * 78)
    for var in ASSETS:
        analyze_asset(var, data)
    analyze_curve(data)
    print("\n" + "=" * 78)
    print("诚实边界: 档位=各资产自身历史实测分位(2003+,覆盖度随资产不同,已逐项标注);"
          " 股票大盘缺(等 RAG P2 us_equity_index, 不外推顶替); 前瞻窗重叠;"
          " 结论作'量级框架'非可交易点位。锁 ADR 前以本实测为准, 不用拍脑袋值。")


if __name__ == "__main__":
    run()
