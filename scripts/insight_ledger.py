"""归因地图 / 洞察账本（零-LLM）。读干净 vintage 账本：
每 事件局面×学派 → 准/不准 + N；揪出明显偏离同伴的格；
对偏离格打印该派在'对'vs'错'时它自己写的理由（人来看模式）。

诚实边界：N 小 → 逐条带日期可复查的'观察/线索'，非'认证规律'。
"""
from __future__ import annotations

import collections
import json

D = json.load(open("/tmp/hc_rerun/ledger_raw_vintage.json"))
SCHOOLS = ["austrian", "keynesian", "monetarist", "rational_expectations"]


def base(t):
    for r in ("宽松周期", "紧缩周期", "通胀冲击", "通缩冲击"):
        if t.startswith(r):
            return r
    return t


# 局面×学派 命中（combined t5+t20）
cell = collections.defaultdict(lambda: [0, 0])  # (reg,school)->[hit,tot]
rows_by = collections.defaultdict(list)
for r in D:
    for tg in r["regimes"]:
        rb = base(tg)
        for h in (r["hit5"], r["hit20"]):
            cell[(rb, r["school"])][0] += h
            cell[(rb, r["school"])][1] += 1
        rows_by[(rb, r["school"])].append(r)

regs = ["宽松周期", "紧缩周期", "通胀冲击", "通缩冲击"]
print("== 局面×学派 命中率（combined，N）==")
leads = []
for reg in regs:
    rates = {}
    for s in SCHOOLS:
        hit, tot = cell[(reg, s)]
        rates[s] = (hit / tot * 100 if tot else None, tot)
    line = reg + " | " + "  ".join(
        f"{s[:4]}={('%.0f%%' % rates[s][0]) if rates[s][0] is not None else '—'}(N{rates[s][1]})"
        for s in SCHOOLS)
    print(line)
    vals = [rates[s][0] for s in SCHOOLS if rates[s][0] is not None]
    if not vals:
        continue
    mean = sum(vals) / len(vals)
    for s in SCHOOLS:
        v, n = rates[s]
        if v is None or n < 8:
            continue
        if v - mean >= 12:
            leads.append((reg, s, v, n, "明显高于同伴"))
        elif mean - v >= 12:
            leads.append((reg, s, v, n, "明显低于同伴"))

print("\n== 偏离同伴的格（线索，非定论；N小仅方向性）==")
for reg, s, v, n, tag in leads:
    print(f"\n▶ {s} 在「{reg}」: {v:.0f}% (N={n}) — {tag}")
    rs = rows_by[(reg, s)]
    hits = [x for x in rs if x["hit5"] or x["hit20"]]
    miss = [x for x in rs if not (x["hit5"] or x["hit20"])]
    for label, lst in (("它判对时的理由", hits[:3]), ("它判错时的理由", miss[:3])):
        print(f"  {label}:")
        for x in lst:
            print(f"    {x['date']} {x['target']} 预测{x['pred_t5']}/{x['pred_t20']} "
                  f"真{x['gt5']}/{x['gt20']} :: {(x['why'] or '')[:120]}")

json.dump({"cell_rates": {f"{r}|{s}": cell[(r, s)] for r in regs for s in SCHOOLS},
           "leads": [(r, s, round(v, 1), n, t) for r, s, v, n, t in leads]},
          open("/tmp/hc_rerun/insight_ledger.json", "w"), ensure_ascii=False, indent=1)
print("\n落盘 /tmp/hc_rerun/insight_ledger.json")
