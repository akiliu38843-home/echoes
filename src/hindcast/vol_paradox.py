"""波动率悖论原型 · 结构-审慎 agent 的"先验真章"验证（17-ADR §5c.1 / 路径2）。

问题：异常低波动（明斯基/波动率悖论）能不能**事前**抬高"未来 H 月出现大幅异动"的概率？
做法（零 LLM，仅用 factual_rag 已有 usdjpy_spot 价格序列）：
  1. 周度抓 USD/JPY → 算 trailing 已实现波动率 → vs 其 5y 滚动基线 = "波动率缺口"
  2. 每个月度决策点 t：判 t 时点 vol 是否"异常低"（仅用 t 及之前信息，无未来泄漏）
  3. 标注未来 H∈{6,12,24}月内是否出现 ≥阈值 大涨/大跌（峰谷振幅，产品负责人定稿阈值）
  4. 诚实计分：条件概率 b = P(大异动 | 异常低波动) vs 无条件基率 a；提升 b−a；领先期
  5. §4 铁律：阈值在 TRAIN 段(2003–2013)定，命中率只在 HOLDOUT 段(2014–)报；
     另列"永远喊危险"(提升必为0)与"永远不喊"(=基率) 两个诚实基线对照

诚实边界：单标的、前瞻窗重叠(自相关，显著性被高估，已标注)、有效 N 小 → 只看方向性结论。
"""
from __future__ import annotations

import datetime as _dt
import json
import math
import os
import statistics as _stat
from typing import Optional

import requests

FACTUAL_RAG = "http://127.0.0.1:8002"
_NOPROXY = {"http": None, "https": None}
_CACHE = "/tmp/usdjpy_weekly_cache.json"

# 产品负责人 2026-05-16 定稿阈值（USD/JPY，峰谷振幅%）
THRESH = {6: 7.0, 12: 10.0, 24: 15.0}
HORIZONS = (6, 12, 24)

TRAIN_END = "2013-12-31"   # §4：异常低波动阈值只在此前定
SPAN_START = "2003-01-06"
SPAN_END = "2024-12-30"


def _fr_price(date: str) -> Optional[float]:
    try:
        r = requests.get(f"{FACTUAL_RAG}/state/asof", params={"date": date},
                          timeout=8, proxies=_NOPROXY)
        if r.status_code == 200:
            n = r.json().get("level_2", {}).get("usdjpy_spot")
            return n.get("value") if isinstance(n, dict) else None
    except Exception:
        return None
    return None


def _mondays(start: str, end: str) -> list[str]:
    d = _dt.date.fromisoformat(start)
    e = _dt.date.fromisoformat(end)
    d += _dt.timedelta(days=(7 - d.weekday()) % 7)  # 下一个周一
    out = []
    while d <= e:
        out.append(d.isoformat())
        d += _dt.timedelta(days=7)
    return out


def fetch_series() -> dict[str, float]:
    """周度 USD/JPY，带本地缓存（一次性，零 LLM，纯本地 HTTP）。"""
    cache = {}
    if os.path.exists(_CACHE):
        cache = json.load(open(_CACHE))
    weeks = _mondays(SPAN_START, SPAN_END)
    miss = [w for w in weeks if w not in cache]
    if miss:
        print(f"[fetch] {len(miss)}/{len(weeks)} 个新周点待抓 (已缓存 {len(cache)})")
        for i, w in enumerate(miss):
            p = _fr_price(w)
            if p is not None:
                cache[w] = p
            if (i + 1) % 50 == 0:
                json.dump(cache, open(_CACHE, "w"))
                print(f"  ... {i+1}/{len(miss)}")
        json.dump(cache, open(_CACHE, "w"))
    series = {w: cache[w] for w in weeks if w in cache}
    print(f"[fetch] 有效周点 {len(series)} / {len(weeks)}")
    return series


def _ann_vol(rets: list[float]) -> float:
    if len(rets) < 8:
        return float("nan")
    return _stat.pstdev(rets) * math.sqrt(52.0)


def analyze(series: dict[str, float]) -> None:
    weeks = sorted(series)
    px = [series[w] for w in weeks]
    n = len(weeks)
    # 周对数收益
    logret = [float("nan")] + [math.log(px[i] / px[i - 1]) for i in range(1, n)]

    TRAIL = 26          # 已实现波动率窗 ≈ 6 月
    BASE = 260          # 基线窗 ≈ 5 年
    rv = [float("nan")] * n
    for i in range(n):
        if i >= TRAIL:
            rv[i] = _ann_vol(logret[i - TRAIL + 1:i + 1])

    # 波动率缺口 z = (rv - 过去5y rv 均值) / 过去5y rv 标准差  —— 仅用过去信息
    z = [float("nan")] * n
    for i in range(n):
        hist = [rv[j] for j in range(max(0, i - BASE), i) if not math.isnan(rv[j])]
        if not math.isnan(rv[i]) and len(hist) >= 52:
            mu = _stat.mean(hist)
            sd = _stat.pstdev(hist) or 1e-9
            z[i] = (rv[i] - mu) / sd

    # —— 月度决策点（每 ~4 周取一个）——
    dec_idx = [i for i in range(n) if i % 4 == 0 and not math.isnan(z[i])]

    def fwd_big_move(i: int, months: int) -> Optional[bool]:
        """未来 months 月内峰谷振幅是否 ≥ 阈值（大涨或大跌任一）。"""
        end = _dt.date.fromisoformat(weeks[i]) + _dt.timedelta(days=int(months * 30.44))
        fwd = [px[j] for j in range(i + 1, n)
               if _dt.date.fromisoformat(weeks[j]) <= end]
        if len(fwd) < max(4, months):      # 前瞻数据不足 → 不计
            return None
        p0 = px[i]
        lo, hi = min(fwd), max(fwd)
        draw = (p0 - lo) / p0 * 100.0      # 最大下跌
        run = (hi - p0) / p0 * 100.0       # 最大上涨
        return (draw >= THRESH[months]) or (run >= THRESH[months])

    # 异常低波动阈值：TRAIN 段 z 分布的下三分位（§4：只用 train 定）
    train_z = [z[i] for i in dec_idx if weeks[i] <= TRAIN_END]
    train_z.sort()
    LOW_CUT = train_z[len(train_z) // 3] if train_z else -0.4
    print(f"\n[§4] 异常低波动阈值 z ≤ {LOW_CUT:+.2f} （仅用 TRAIN≤{TRAIN_END} 的 "
          f"{len(train_z)} 个决策点的下三分位定，HOLDOUT 不参与定阈）\n")

    def report(seg_name: str, pred):
        print(f"================= {seg_name} =================")
        for H in HORIZONS:
            pts = [(weeks[i], z[i], fwd_big_move(i, H)) for i in dec_idx if pred(weeks[i])]
            pts = [(w, zz, o) for w, zz, o in pts if o is not None]
            if not pts:
                continue
            tot = len(pts)
            base = sum(1 for _, _, o in pts if o) / tot
            lows = [(w, zz, o) for w, zz, o in pts if zz <= LOW_CUT]
            highs = [(w, zz, o) for w, zz, o in pts if zz >= 0.5]
            norms = [(w, zz, o) for w, zz, o in pts if LOW_CUT < zz < 0.5]
            def hit(g): return (sum(1 for _, _, o in g if o) / len(g), len(g)) if g else (float("nan"), 0)
            bl, nl = hit(lows); bn, nn = hit(norms); bh, nh = hit(highs)
            print(f"  H={H:>2}月  阈值≥{THRESH[H]:.0f}% | 无条件基率 a={base*100:4.0f}% (N={tot})")
            print(f"         异常低波动 b={bl*100:4.0f}% (N={nl})  → 提升 {(bl-base)*100:+5.1f}pp"
                  f"  | 正常 {bn*100:4.0f}%(N={nn}) | 高波动 {bh*100:4.0f}%(N={nh})")
        # 诚实基线
        print("  诚实基线: '永远喊危险'提升≡0(=基率) | '永远不喊'≡基率 → 信号须显著>0 才算真技能")

    report("TRAIN 段 (≤2013, 定阈用, 仅参考)", lambda w: w <= TRAIN_END)
    report("HOLDOUT 段 (>2013, §4 真考场)", lambda w: w > TRAIN_END)

    # 三次危机聚光：危机起点前 24 月内，异常低波动信号是否亮过
    print("\n========= 危机聚光（事前是否亮红灯）=========")
    for crisis, cdate in (("2008-09 雷曼", "2008-09-15"),
                          ("2018Q4 波动回归", "2018-10-01"),
                          ("2020-03 COVID", "2020-03-01")):
        c = _dt.date.fromisoformat(cdate)
        win = [(weeks[i], z[i]) for i in dec_idx
               if 0 <= (c - _dt.date.fromisoformat(weeks[i])).days <= 730]
        fired = [(w, zz) for w, zz in win if zz <= LOW_CUT]
        if fired:
            first = fired[0]
            lead = (c - _dt.date.fromisoformat(first[0])).days / 30.44
            print(f"  {crisis}: 危机前24月内异常低波动亮过 {len(fired)}/{len(win)} 次；"
                  f"最早 {first[0]} (z={first[1]:+.2f}) 提前 ~{lead:.0f} 月")
        else:
            print(f"  {crisis}: 危机前24月内**未**触发异常低波动（信号对该次无预警）")

    print("\n诚实边界: 单标的USD/JPY; 前瞻窗重叠→显著性高估; 有效N小; "
          "结论只作'方向性/有无信号', 非可交易概率。RAG 的 NFCI/VIX 到位后升级预测端。")


def run_prototype() -> None:
    s = fetch_series()
    if len(s) < 300:
        print("数据太少，无法分析（factual_rag 是否在线？）")
        return
    analyze(s)


if __name__ == "__main__":
    run_prototype()
