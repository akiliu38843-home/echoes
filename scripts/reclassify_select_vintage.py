"""②重跑 · 盲选 ~50（新 vintage 325 宇宙）。零-LLM。

照锁定预注册：盲于结果（只按局面/档/年代分层均匀抽，不看真实涨跌）；
档/局面阈值写死常数；先按年切（沉淀≤2013/验证>2013）再选；验证段补厚。
仅 CPI 正则加 [当时数] 兼容；其余逻辑与 reclassify_select.py 一致。
"""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict

H = json.load(open("/tmp/hc_rerun/catalyst_dates_vintage.json"))["hits"]


def regimes(reasons):
    out = []
    for r in reasons:
        m = re.search(r"政策利率周期\(Δ6m=([+-]?\d+\.?\d*)", r)
        if m:
            d = float(m.group(1))
            t = "重" if abs(d) >= 2.0 else "中" if abs(d) >= 1.0 else "轻"
            out.append(("宽松周期" if d < 0 else "紧缩周期", t))
        m = re.search(r"通胀加速(?:\[当时数\])?\(Δ3m=([+-]?\d+\.?\d*)", r)
        if m:
            d = float(m.group(1))
            t = "重" if abs(d) >= 3.0 else "中" if abs(d) >= 2.0 else "轻"
            out.append(("通胀冲击" if d > 0 else "通缩冲击", t))
    return out


pts = []
for rec in H:
    rs = regimes(rec["reasons"])
    if not rs:
        continue
    yr = int(rec["date"][:4])
    pts.append({"date": rec["date"], "regimes": rs,
                "split": "沉淀≤2013" if yr <= 2013 else "验证>2013"})

by_cell = defaultdict(list)
for p in pts:
    for reg, t in p["regimes"]:
        by_cell[(reg, t)].append(p)


def spread(lst, k):
    if not lst or k <= 0:
        return []
    return sorted(lst, key=lambda r: r["date"])[::max(1, len(lst) // k)][:k]


sel = {}
for cell in sorted(by_cell):
    for r in spread([x for x in by_cell[cell] if x["split"].startswith("沉淀")], 2):
        sel[r["date"]] = r
for cell in sorted(by_cell):
    for r in spread([x for x in by_cell[cell] if x["split"].startswith("验证")], 3):
        sel[r["date"]] = r

selected = sorted(sel.values(), key=lambda r: r["date"])
sp = Counter(r["split"] for r in selected)
reg = Counter(f"{a}{b}" for r in selected for a, b in r["regimes"])
print(f"新宇宙可分层点 {len(pts)} → 盲选 {len(selected)}")
print(f"沉淀≤2013={sp.get('沉淀≤2013',0)}  验证>2013={sp.get('验证>2013',0)}")
print("局面×档:", dict(sorted(reg.items())))
json.dump(selected, open("/tmp/hc_rerun/selected_dates_vintage.json", "w"),
          ensure_ascii=False, indent=1)
print("落盘 /tmp/hc_rerun/selected_dates_vintage.json")
