"""②第1步 · 接新管子重扫催化历史（零-LLM，只取数）。

忠实做法：地缘(GPR)+利率信号**原样复用现有 _catalyst_asof**（这俩本就不被
事后改写，无前视问题），**只把通胀信号换成读"当时公布的数"**（factual_rag.vintage，
即 #2 阶段1 建好的新管子）。改不到当时数的日期 → 标"无当时数"单列、**不拿改过的数
顶替**（规矩A）。产出"接新管子后"的新催化宇宙，与旧 333 对比。
"""
from __future__ import annotations

import json
import sys
from collections import Counter

# 跨包：hindcast(src) + factual_rag(04-graphrag-build)
sys.path.insert(0, "/Users/a26976/Desktop/Hindcast-鉴往/04-graphrag-build")

import hindcast.continuous as C
from hindcast.continuous import _catalyst_asof, _shift
from factual_rag.vintage import vintage_value_at

CPI_DPP = 1.0  # = _CAT_CPI_DPP，逐字不动

# memoize _fr_state（GPR/利率回看大量重叠），同原 scan
_FRC: dict = {}
_ORIG = C._fr_state


def _memo(d):
    if d not in _FRC:
        _FRC[d] = _ORIG(d)
    return _FRC[d]


C._fr_state = _memo


def months(s="1979-01", e="2026-05"):
    y, m = int(s[:4]), int(s[5:7])
    y1, m1 = int(e[:4]), int(e[5:7])
    while (y, m) <= (y1, m1):
        yield f"{y:04d}-{m:02d}-15"
        m += 1
        if m > 12:
            m, y = 1, y + 1


def cpi_vintage_reason(d: str):
    """→ (reason|None, status)。status: ok / 无当时数(规矩A,不顶替)。"""
    c0 = vintage_value_at("us_cpi_yoy", d)
    c3 = vintage_value_at("us_cpi_yoy", _shift(d, -90))
    if c0 is None or c3 is None:
        return None, "无当时数"
    dv = c0["value"] - c3["value"]
    if abs(dv) >= CPI_DPP:
        return f"通胀加速[当时数](Δ3m={dv:+.1f}pp)", "ok"
    return None, "ok"  # 有当时数但未触发


def main():
    hits, undet = [], []
    probed = 0
    for d in months():
        probed += 1
        fired0, reasons0 = _catalyst_asof(d)
        if reasons0 == ["no_data"]:
            continue
        gpr_rate = [r for r in reasons0 if "通胀加速" not in r]  # 原样保留地缘/利率
        cpi_r, st = cpi_vintage_reason(d)
        reasons = gpr_rate + ([cpi_r] if cpi_r else [])
        if st == "无当时数":
            undet.append(d)
        if not reasons:
            continue
        hits.append({"date": d, "reasons": reasons,
                     "cpi_status": st,
                     "by": ("CPI当时数" if cpi_r else "")
                           + ("+地缘/利率" if gpr_rate else "")})
        print(f"  {d}  {';'.join(reasons)}"
              + (f"   ⚠️CPI{st}" if st == "无当时数" else ""))

    json.dump({"hits": hits, "cpi_undetermined": undet},
              open("/tmp/hc_rerun/catalyst_dates_vintage.json", "w"),
              ensure_ascii=False, indent=1)

    old = json.load(open("/tmp/hc_rerun/catalyst_dates.json"))
    old_cpi = sum(1 for r in old if any("通胀加速" in x for x in r["reasons"]))
    new_cpi = sum(1 for h in hits if any("通胀加速" in x for x in h["reasons"]))
    print("\n" + "=" * 64)
    print(f"探针 {probed} 月")
    print(f"旧（读改过的数）催化点 {len(old)} | 其中 CPI 承重 {old_cpi}")
    print(f"新（读当时的数）催化点 {len(hits)} | 其中 CPI 承重 {new_cpi}")
    print(f"CPI'无当时数'(规矩A单列,不顶替): {len(undet)}")
    print(f"新宇宙信号构成: {dict(Counter(h['by'] for h in hits))}")
    print("落盘 /tmp/hc_rerun/catalyst_dates_vintage.json")


if __name__ == "__main__":
    main()
