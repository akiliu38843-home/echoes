"""零-LLM 催化剂日期扫描器（拓宽测题 step 5 的前半）。

复用 continuous.py 的事前催化剂闸门 + factual_rag /state/asof + /events，
扫历史，只收"有变动"（catalyst 触发）的日期，按 5 族×3 档自动打标。
**不调任何学派、不烧 LLM。** 产出候选清单供产品负责人过目，点头后才跑账本。

用法:
  python scripts/scan_catalyst_dates.py 1979-01 2026-05    # 全量
  python scripts/scan_catalyst_dates.py 2007-01 2009-12     # 冒烟
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter

import requests

import hindcast.continuous as C
from hindcast.continuous import _catalyst_asof, _shift

FR = "http://127.0.0.1:8002"
NOPROXY = {"http": None, "https": None}

# memoize _fr_state —— catalyst 每点做 -90/-180/-365 回看，跨月大量重叠
_CACHE: dict = {}
_ORIG_FR = C._fr_state


def _memo_fr(date: str):
    if date not in _CACHE:
        _CACHE[date] = _ORIG_FR(date)
    return _CACHE[date]


C._fr_state = _memo_fr  # _catalyst_asof 调模块级 _fr_state，patch 之


def events_window(date: str, lookback: int = 30) -> list:
    start = _shift(date, -lookback)
    try:
        r = requests.get(f"{FR}/events",
                         params={"start": start, "end": date, "limit": 200},
                         timeout=15, proxies=NOPROXY)
        if r.status_code == 200:
            j = r.json()
            return j.get("events", []) if isinstance(j, dict) else (j or [])
    except Exception:
        pass
    return []


def classify(reasons: list[str], evs: list) -> tuple[str, str, dict]:
    """族 + 档 + 结构化来源标签计数。族来自催化剂(干净数字)+结构化源；
    档来自数字幅度。GDELT 原始标题只做辅助、不做权威（噪音）。"""
    src_tags: dict = {}
    for e in evs:
        src = e.get("source")
        for t in (e.get("tags") or []):
            src_tags.setdefault(src, Counter())[t] += 1
    all_tags = [t for e in evs for t in (e.get("tags") or [])]

    rate = next((r for r in reasons if "政策利率周期" in r), None)
    gpr = next((r for r in reasons if "GPR飙升" in r), None)
    cpi = next((r for r in reasons if "通胀加速" in r), None)

    fam = []
    if rate or "fed_fomc" in src_tags:
        fam.append("央行动作")
    if gpr or "geopolitical" in all_tags:
        fam.append("地缘-战争")
    if "ofac_actions" in src_tags or "sanctions" in all_tags:
        fam.append("制裁")
    if "ustr" in src_tags or any(t in all_tags for t in ("tariff", "trade_action")):
        fam.append("贸易-关税")
    if cpi or any(t in all_tags for t in ("fiscal_policy", "disaster")):
        fam.append("财政-危机")
    if not fam:
        fam = ["其他-数字催化"]

    mag = 0
    if rate:
        m = re.search(r"Δ6m=([+-]?\d+\.?\d*)", rate)
        if m:
            d = abs(float(m.group(1)))
            mag = max(mag, 3 if d >= 2.0 else 2 if d >= 1.0 else 1)
    if gpr:
        m = re.search(r"GPR飙升\((\d+\.?\d*)>(\d+\.?\d*)", gpr)
        if m and float(m.group(2)):
            ratio = float(m.group(1)) / float(m.group(2))
            mag = max(mag, 3 if ratio >= 2.5 else 2 if ratio >= 1.8 else 1)
    if cpi:
        m = re.search(r"Δ3m=([+-]?\d+\.?\d*)", cpi)
        if m:
            d = abs(float(m.group(1)))
            mag = max(mag, 3 if d >= 3.0 else 2 if d >= 2.0 else 1)
    tier = {0: "轻", 1: "轻", 2: "中", 3: "重"}[mag]
    flat_src = {k: dict(v) for k, v in src_tags.items()}
    return "/".join(fam), tier, flat_src


def months(s: str, e: str):
    y0, m0 = int(s[:4]), int(s[5:7])
    y1, m1 = int(e[:4]), int(e[5:7])
    y, m = y0, m0
    while (y, m) <= (y1, m1):
        yield f"{y:04d}-{m:02d}-15"
        m += 1
        if m > 12:
            m, y = 1, y + 1


def main():
    s = sys.argv[1] if len(sys.argv) > 1 else "1979-01"
    e = sys.argv[2] if len(sys.argv) > 2 else "2026-05"
    print(f"扫描 {s} → {e}（月度探针，零 LLM）\n" + "-" * 70)
    hits = []
    probed = 0
    for d in months(s, e):
        probed += 1
        fired, reasons = _catalyst_asof(d)
        if not fired or reasons == ["no_data"]:
            continue
        evs = events_window(d)
        fam, tier, srct = classify(reasons, evs)
        rec = {"date": d, "family": fam, "tier": tier,
               "reasons": reasons, "n_events": len(evs), "src_tags": srct}
        hits.append(rec)
        print(f"{d}  [{tier}] {fam:22s} ev={len(evs):3d}  {';'.join(reasons)}")

    print("\n" + "=" * 70)
    print(f"探针 {probed} 月 | 催化剂触发 {len(hits)} 点\n")
    fc = Counter((h["family"], h["tier"]) for h in hits)
    print("==== 族×档 分布（下选 ~30-50 跨格用）====")
    for k, v in sorted(fc.items()):
        print(f"  {k[0]:26s} {k[1]}  ×{v}")
    out = "/tmp/hc_rerun/catalyst_dates.json"
    json.dump(hits, open(out, "w"), ensure_ascii=False, indent=1)
    print(f"\n候选明细落盘: {out}")


if __name__ == "__main__":
    main()
