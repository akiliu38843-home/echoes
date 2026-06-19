"""②重跑 · 在 vintage-clean 选点上跑账本（复用 run_ledger.harvest，只换输入/输出）。

选题已去马后炮（vintage 催化）；答题输入仍为 revised 经济背景——按产品负责人定调
=有意实验条件（经济学家本就事后分析；revised vs 当时数 的差是被记录的研究维度），
**结果须标"改过数据上的推理表现，非实时预测能力"**。
"""
from __future__ import annotations

import json

from scripts.run_ledger import TARGETS, harvest

SEL = json.load(open("/tmp/hc_rerun/selected_dates_vintage.json"))
OUT = "/tmp/hc_rerun/ledger_raw_vintage.json"


def main():
    print(f"②重跑账本：vintage选点 {len(SEL)} × {len(TARGETS)} FX 对，每点4学派 RAG-on\n")
    rows, fails = [], 0
    for i, m in enumerate(SEL, 1):
        for t in TARGETS:
            try:
                r = harvest(m["date"], t, m)
            except Exception as e:
                fails += 1
                print(f"  [{i}/{len(SEL)}] {m['date']} {t:8s} ✗ {type(e).__name__}")
                continue
            rows += r
            print(f"  [{i}/{len(SEL)}] {m['date']} {t:8s} → {len(r)} 学派"
                  f"{'' if r else ' ·空(无价/无真值,零成本跳过)'}")
            json.dump(rows, open(OUT, "w"), ensure_ascii=False, indent=1)
    print(f"\n采集 {len(rows)} 行 | 失败跳过 {fails} → {OUT}")


if __name__ == "__main__":
    main()
