"""路线 C：把已扫的 333 催化剂点重归类为"货币/通胀子局面"，分层下选 ~40。

零 HTTP、零 LLM——只读 /tmp/hc_rerun/catalyst_dates.json 里已存的带符号催化剂。
子局面: 宽松周期 / 紧缩周期 / 通胀冲击 / 通缩冲击  ×  档 轻/中/重
切分: 沉淀段 ≤2013 / 验证段 >2013（"我们的理论"那栏只用验证段算）。
"""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict

H = json.load(open("/tmp/hc_rerun/catalyst_dates.json"))


def regimes(reasons: list[str]) -> list[tuple[str, str]]:
    """→ [(子局面, 档)]，一个点可多局面（如宽松+通缩）。档由幅度定。"""
    out = []
    for r in reasons:
        m = re.search(r"政策利率周期\(Δ6m=([+-]?\d+\.?\d*)", r)
        if m:
            d = float(m.group(1))
            tier = "重" if abs(d) >= 2.0 else "中" if abs(d) >= 1.0 else "轻"
            out.append(("宽松周期" if d < 0 else "紧缩周期", tier))
        m = re.search(r"通胀加速\(Δ3m=([+-]?\d+\.?\d*)", r)
        if m:
            d = float(m.group(1))
            tier = "重" if abs(d) >= 3.0 else "中" if abs(d) >= 2.0 else "轻"
            out.append(("通胀冲击" if d > 0 else "通缩冲击", tier))
    return out


# 重归类
pts = []
for rec in H:
    rs = regimes(rec["reasons"])
    if not rs:
        continue
    yr = int(rec["date"][:4])
    pts.append({
        "date": rec["date"],
        "regimes": rs,
        "split": "沉淀≤2013" if yr <= 2013 else "验证>2013",
        "gpr_co": any("GPR飙升" in x for x in rec["reasons"]),
        "n_events": rec["n_events"],
    })

# 覆盖直方图（局面×档，多局面重复计）
cov = Counter()
for p in pts:
    for reg, t in p["regimes"]:
        cov[(reg, t)] += 1
print(f"重归类后可用点: {len(pts)}（来自 333 催化剂点）\n")
print("==== 子局面 × 档 覆盖 ====")
for k in sorted(cov):
    print(f"  {k[0]:6s} {k[1]}  ×{cov[k]}")

# 决策一(c)：沉淀段 ~24、验证段 ~20 独立分层取，验证段刻意补厚
by_cell = defaultdict(list)
for p in pts:
    for reg, t in p["regimes"]:
        by_cell[(reg, t)].append(p)

cells = sorted(by_cell)


def spread(lst, k):
    if not lst or k <= 0:
        return []
    step = max(1, len(lst) // k)
    return lst[::step][:k]


sel: dict[str, dict] = {}
# 沉淀段：每格取 ~2，目标 ~24
for cell in cells:
    rows = sorted([r for r in by_cell[cell] if r["split"].startswith("沉淀")],
                  key=lambda r: r["date"])
    for r in spread(rows, 2):
        sel[r["date"]] = r
# 验证段：每格取足，目标 ~20（点本就少，尽量多收，均匀跨年）
ho_sel: dict[str, dict] = {}
for cell in cells:
    rows = sorted([r for r in by_cell[cell] if r["split"].startswith("验证")],
                  key=lambda r: r["date"])
    for r in spread(rows, 3):
        ho_sel[r["date"]] = r
sel.update(ho_sel)

selected = sorted(sel.values(), key=lambda r: r["date"])
print(f"\n==== 分层下选 {len(selected)} 个候选（去重后）====")
sp = Counter(r["split"] for r in selected)
print(f"沉淀≤2013: {sp.get('沉淀≤2013',0)}   验证>2013: {sp.get('验证>2013',0)}\n")
for r in selected:
    rg = ",".join(f"{a}{b}" for a, b in r["regimes"])
    print(f"  {r['date']}  [{r['split']:8s}] {rg:22s}"
          f"{' +GPR' if r['gpr_co'] else ''}  ev={r['n_events']}")

json.dump(selected, open("/tmp/hc_rerun/selected_dates.json", "w"),
          ensure_ascii=False, indent=1)
print("\n候选清单落盘: /tmp/hc_rerun/selected_dates.json")
