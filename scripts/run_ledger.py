"""per-entity 账本采集器（step 3 的 LLM 采集半，一次性烧、之后白嫖）。

复用 continuous.py 的无偏积木：build_state_asof / _actual_dir / _price，
+ fx.predict_fx（RAG-on，每学派带 reasoning）。只跑有干净无偏真值的
4 个 FX/黄金标的。每 (日期×标的) 落 4 学派各自方向+为什么+真值+幅度。

输出 raw JSON；分析(切片/拟合/基线)由 analyze_ledger.py 零-LLM 后处理。

用法:
  python scripts/run_ledger.py SMOKE          # 1 日期×1 标的冒烟
  python scripts/run_ledger.py FULL           # 全量 50×4
"""
from __future__ import annotations

import json
import sys

from hindcast.continuous import (
    _fr_state, _price, _shift, _actual_dir,
    build_state_asof, _PRICE_VAR, FLAT_PCT, HORIZON_DAYS,
)
from hindcast.fx import predict_fx

# predict_fx/FXVerdict 只认这 3 个 FX 对；XAU/USD 走另一路径(本轮不含, 如实推迟)
TARGETS = ["EUR/USD", "USD/JPY", "USD/CNH"]
SEL = json.load(open("/tmp/hc_rerun/selected_dates.json"))
OUT = "/tmp/hc_rerun/ledger_raw.json"


def harvest(date: str, target: str, meta: dict) -> list[dict]:
    fr0 = _fr_state(date)
    if fr0 is None:
        return []
    pvar = _PRICE_VAR[target]
    p0 = _price(fr0, pvar)
    if p0 is None:
        return []
    fr5 = _fr_state(_shift(date, HORIZON_DAYS["T+5"]))
    fr20 = _fr_state(_shift(date, HORIZON_DAYS["T+20"]))
    gt5, m5 = _actual_dir(p0, _price(fr5, pvar) if fr5 else None, FLAT_PCT["T+5"])
    gt20, m20 = _actual_dir(p0, _price(fr20, pvar) if fr20 else None, FLAT_PCT["T+20"])
    if gt5 == "?" or gt20 == "?":
        return []
    state = build_state_asof(date, fr0)
    fc = predict_fx(state, target)  # RAG-on（HINDCAST_USE_RAG=1）
    rows = []
    for v in fc.verdicts:
        if v._failed:
            continue
        rows.append({
            "date": date, "target": target,
            "split": meta["split"],
            "regimes": [f"{a}{b}" for a, b in meta["regimes"]],
            "school": v.school,
            "pred_t5": v.verdict["T+5"].dir,
            "pred_t20": v.verdict["T+20"].dir,
            "gt5": gt5, "gt20": gt20,
            "hit5": v.verdict["T+5"].dir == gt5,
            "hit20": v.verdict["T+20"].dir == gt20,
            "move5": round(m5, 2), "move20": round(m20, 2),
            "why": (v.attribution_note or v.reasoning or "")[:240],
        })
    return rows


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "SMOKE"
    if mode == "SMOKE":
        sel, tgts = SEL[:1], TARGETS[:1]
    else:
        sel, tgts = SEL, TARGETS
    print(f"[{mode}] 日期 {len(sel)} × 标的 {len(tgts)} = "
          f"{len(sel)*len(tgts)} 个 (日期,标的)，每个 4 学派\n")
    all_rows = []
    fails = 0
    for i, m in enumerate(sel, 1):
        for t in tgts:
            try:
                rows = harvest(m["date"], t, m)
            except Exception as e:  # 单点失败不崩整批
                fails += 1
                print(f"  [{i}/{len(sel)}] {m['date']} {t:8s} → ✗ {type(e).__name__}: {str(e)[:80]}")
                continue
            all_rows += rows
            tag = "✓" if rows else "·空(无价/无真值, 零成本跳过)"
            print(f"  [{i}/{len(sel)}] {m['date']} {t:8s} → {len(rows)} 学派 {tag}")
            json.dump(all_rows, open(OUT, "w"), ensure_ascii=False, indent=1)  # 增量落盘
    print(f"\n采集 {len(all_rows)} 行 | 失败跳过 {fails} → {OUT}")


if __name__ == "__main__":
    main()
