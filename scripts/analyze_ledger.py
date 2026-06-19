"""per-entity 账本后处理（零 LLM，可反复跑）。读 ledger_raw.json 出：

1. 4 学派各自及格率（全样本 + 仅验证段，按 子局面 切片，带 N）
2. "我们的理论 v1" = 极简拟合修正层：**仅用沉淀≤2013** 学"每个子局面信哪派"
   → **仅在验证>2013** 上打分（严守 17-ADR §4 样本外铁律）
3. 头条 = best-of(4 学派验证段 + 我们的理论验证段)
4. 诚实基线：永远flat / 多数类停摆钟 / 验证段最强单派
5. 灵敏度("好事件")：每 子局面×档 真实|涨跌幅|均值 + 方向一致性
"""
from __future__ import annotations

import collections
import json

D = json.load(open("/tmp/hc_rerun/ledger_raw.json"))
SCHOOLS = ["austrian", "keynesian", "monetarist", "rational_expectations"]
REGIME_OF = lambda s: s[:4] if s[:4] in ("宽松周期", "紧缩周期", "通胀冲击", "通缩冲击") else s[:4]


def base_regime(tag: str) -> str:
    for r in ("宽松周期", "紧缩周期", "通胀冲击", "通缩冲击"):
        if tag.startswith(r):
            return r
    return tag


def rate(rows, key):
    n = len(rows)
    return (sum(r[key] for r in rows) / n, n) if n else (0.0, 0)


print("=" * 72)
print(f"账本后处理 | {len(D)} 行 | 标的 {dict(collections.Counter(r['target'] for r in D))}")
print("=" * 72)

# ---------- 1. 4 学派各自及格率（全 + 仅验证），按子局面 ----------
hold = [r for r in D if r["split"].startswith("验证")]
train = [r for r in D if r["split"].startswith("沉淀")]
print(f"\n沉淀≤2013 {len(train)} 行 | 验证>2013 {len(hold)} 行\n")

print("【1】各学派 combined(T+5&T+20) 及格率")
print(f"{'学派':<22}{'全样本':>14}{'仅验证段':>16}")
for sch in SCHOOLS:
    a = [h for r in D if r["school"] == sch for h in (r["hit5"], r["hit20"])]
    v = [h for r in hold if r["school"] == sch for h in (r["hit5"], r["hit20"])]
    ra = sum(a) / len(a) * 100 if a else 0
    rv = sum(v) / len(v) * 100 if v else 0
    print(f"{sch:<22}{ra:>9.0f}% (N={len(a):<3}){rv:>9.0f}% (N={len(v)})")

# 按子局面 × 学派（仅验证段，combined）
print("\n【1b】仅验证段·按子局面 各学派 combined 及格率 (N=该格 horizon 数)")
regimes = ["宽松周期", "紧缩周期", "通胀冲击", "通缩冲击"]
hdr = "子局面".ljust(10) + "".join(s[:4].rjust(13) for s in SCHOOLS)
print(hdr)
for reg in regimes:
    line = reg.ljust(10)
    for sch in SCHOOLS:
        cell = [h for r in hold if r["school"] == sch
                and any(base_regime(t) == reg for t in r["regimes"])
                for h in (r["hit5"], r["hit20"])]
        line += (f"{sum(cell)/len(cell)*100:>6.0f}%(N{len(cell)})" if cell else f"{'—':>13}")
    print(line)

# ---------- 2. 我们的理论 v1：沉淀学规律 → 验证打分 ----------
print("\n【2】我们的理论 v1（沉淀≤2013 学'每子局面信哪派' → 验证>2013 样本外打分）")
fit = {}  # regime -> best school (by train combined)
for reg in regimes:
    best, bestr, bestn = None, -1, 0
    for sch in SCHOOLS:
        c = [h for r in train if r["school"] == sch
             and any(base_regime(t) == reg for t in r["regimes"])
             for h in (r["hit5"], r["hit20"])]
        if c and sum(c) / len(c) > bestr:
            best, bestr, bestn = sch, sum(c) / len(c), len(c)
    fit[reg] = best
    print(f"  沉淀段: {reg} → 信 {best or '(无沉淀数据,回退全局)'} "
          f"(沉淀命中 {bestr*100:.0f}% N={bestn})" if best else
          f"  沉淀段: {reg} → 无数据")

def school_rate(rows, sch):
    hs = [h for r in rows if r["school"] == sch for h in (r["hit5"], r["hit20"])]
    return (sum(hs) / len(hs)) if hs else 0.0


# 全局回退（沉淀段最强单派）
gtr = max(SCHOOLS, key=lambda s: school_rate(train, s))

ours = []
for r in hold:
    regs = [base_regime(t) for t in r["regimes"]]
    pick = next((fit[g] for g in regs if fit.get(g)), gtr)
    if r["school"] == pick:
        ours += [r["hit5"], r["hit20"]]
our_rate = sum(ours) / len(ours) * 100 if ours else 0
print(f"  → 我们的理论 v1 验证段 combined: {our_rate:.0f}% (N={len(ours)})")

# ---------- 3. 诚实基线（验证段）----------
flat = [(r["gt5"] == "flat") for r in hold] + [(r["gt20"] == "flat") for r in hold]
gts = [r["gt5"] for r in hold] + [r["gt20"] for r in hold]
maj = collections.Counter(gts).most_common(1)[0]
best_school_v = max(SCHOOLS, key=lambda s: school_rate(hold, s))
bsv = [h for r in hold if r["school"] == best_school_v for h in (r["hit5"], r["hit20"])]
print("\n【3】诚实基线（验证段）")
print(f"  永远猜flat:        {sum(flat)/len(flat)*100:.0f}%")
print(f"  停摆钟(永远猜'{maj[0]}'): {maj[1]/len(gts)*100:.0f}%")
print(f"  验证段最强单派({best_school_v[:4]}): {sum(bsv)/len(bsv)*100:.0f}%")
print(f"  我们的理论 v1:      {our_rate:.0f}%")
print(f"  头条 best-of:       {max(our_rate, sum(bsv)/len(bsv)*100):.0f}%  "
      f"(= max(我们理论, 验证最强单派))")

# ---------- 4. 灵敏度 / 好事件 ----------
print("\n【4】灵敏度图（'好事件'：|涨跌幅|大 + 方向一致 = 可学习）")
print(f"{'子局面×档':<14}{'点数':>5}{'|move5|均':>10}{'|move20|均':>11}{'方向一致性':>12}")
cells = collections.defaultdict(list)
for r in D:
    for t in r["regimes"]:
        cells[t].append(r)
for t in sorted(cells):
    rs = cells[t]
    am5 = sum(abs(x["move5"]) for x in rs) / len(rs)
    am20 = sum(abs(x["move20"]) for x in rs) / len(rs)
    gt = [x["gt5"] for x in rs] + [x["gt20"] for x in rs]
    cons = collections.Counter(gt).most_common(1)[0][1] / len(gt)
    star = " ★好事件" if (am20 >= 2.0 and cons >= 0.6) else ""
    print(f"{t:<14}{len(rs)//4:>5}{am5:>9.1f}%{am20:>10.1f}%{cons*100:>10.0f}%{star}")

print("\n" + "=" * 72)
print("注: N 小的格仅方向性参考(非统计)。USD/CNH 全程无数据 → 实为 JPY+EUR 两对。")
