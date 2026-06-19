"""精算："事后诸葛亮" 当时数据 vs 今天修订数据，外加走偏的圆场。

输出 data/then_vs_now.json，前端只读它（零运行时 LLM）。
- structural_asof 仅本脚本调用（演示用近似锚点），**绝不接 live `build_state_asof`**。
- 圆场提示词硬约束：只反思过去 + 拿事后数据看的话哪儿会变；**禁前瞻预测/买卖/配置建议**（18-ADR）。
- 用法：PYTHONPATH=src .venv/bin/python scripts/build_then_vs_now.py [--only 2008-09-14] [--dry]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from copy import deepcopy

from hindcast.data import GROUND_TRUTH, SNAPSHOTS
from hindcast.llm import chat_text, get_client
from hindcast.predict import predict
from hindcast.schools import PROMPTS
from hindcast.state import StructuralState
from hindcast.structural_asof import PROVENANCE, coverage_note, struct_vals_asof

SCHOOL_ZH = {
    "austrian": "奥地利学派",
    "monetarist": "货币主义",
    "keynesian": "凯恩斯主义",
    "rational_expectations": "理性预期",
}

RATIONALIZE_TEMPLATE = """你是{school_label}。一段事后回看：

— 时间：{date}（{event}）
— 你**当时**手里数据下，对 XAU/USD 给的判断：T+5 = {dir5} / T+20 = {dir20}
— 真实后来发生：T+5 = {true5} / T+20 = {true20}
  → 你**没全猜对**（{miss_summary}）。
— 这些数据后来被官方反复修订，今天看是另一套数。

请在角色内**老实自圆其说**：
1) 当时数据下，你为什么会那样想？（讲清推理逻辑）
2) 如果当时拿到的是今天修订后的版本，你的判断**哪里会变**、为什么？

铁律（不可破）：
- **只反思过去 + 谈数据修订对过去观点的影响**；
- **绝不做任何新的前瞻预测、择时、买卖、配置建议**；
- 不许说"我其实是对的"——错就老实承认错；
- 4–6 句中文，保留学派一贯口气。
"""


def serialize_forecast(f) -> dict:
    return {
        "is_unanimous": f.is_unanimous,
        "is_split": f.is_split,
        "horizons": {
            h: {"direction": hf.dir, "vote_counts": hf.vote_counts}
            for h, hf in f.horizons.items()
        },
        "verdicts": [
            {
                "school": v.school,
                "verdict": {
                    h: {
                        "dir": hz.dir,
                        "range_pct": list(hz.range_pct) if hz.range_pct else None,
                    }
                    for h, hz in v.verdict.items()
                },
                "attribution_note": v.attribution_note,
                "reasoning": v.reasoning,
                "failed": v._failed,
            }
            for v in f.verdicts
        ],
        # v0.5.6: 第 5 派制度政治经济学派简报 (跑在前面, 喂给 4 经济派作可选参考)
        "political_brief": f.political_brief,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="只跑一个日期（验通用）")
    ap.add_argument("--dry", action="store_true", help="不调 LLM，看构造是否对")
    ap.add_argument("--out", default="src/hindcast/data/then_vs_now.json")
    args = ap.parse_args()

    client = None if args.dry else get_client()
    dates = [d for d in SNAPSHOTS if d != "2026-05-14"]
    if args.only:
        dates = [args.only] if args.only in SNAPSHOTS else []
        if not dates:
            print(f"未知日期 {args.only}")
            return 1

    out: dict = {}
    for date in dates:
        snap = SNAPSHOTS[date]
        print(f"\n── {date} · {snap.label} ──", flush=True)

        # Pass 1: vintage — 用 structural_asof 覆盖 SNAPSHOT 中匹配的键
        vintage_vals = struct_vals_asof(date)
        p1_values = {**snap.values, **vintage_vals}  # 只覆盖 asof 给出的；其余保留手搭
        p1_snap = StructuralState(
            as_of=snap.as_of,
            label=f"{snap.label} (vintage)",
            values=p1_values,
            macro=snap.macro,
        )
        # Pass 2: revised = 现成 SNAPSHOTS
        p2_snap = snap

        gt = GROUND_TRUTH.get(date, {})
        gt5 = (gt.get("T+5") or {}).get("dir", "?")
        gt20 = (gt.get("T+20") or {}).get("dir", "?")
        event = gt.get("event", snap.label)

        if args.dry:
            print(f"  vintage 覆盖 {len(vintage_vals)}/15 个结构变量; "
                  f"GT T+5={gt5}, T+20={gt20}; event={event}")
            print(f"  coverage_note: {coverage_note(date)[:120]}…")
            continue

        # 真跑（每 anchor 8 LLM 调用：2 passes × 4 schools）
        print("  Pass1 (vintage)…", end=" ", flush=True)
        f1 = predict(p1_snap, client=client)
        print(f"is_unanimous={f1.is_unanimous}")
        print("  Pass2 (revised)…", end=" ", flush=True)
        f2 = predict(p2_snap, client=client)
        print(f"is_unanimous={f2.is_unanimous}")

        rec = {
            "date": date,
            "event": event,
            "label": snap.label,
            "ground_truth": {"T+5": gt5, "T+20": gt20},
            "pass1_vintage": serialize_forecast(f1),
            "pass2_revised": serialize_forecast(f2),
            "vintage_meta": {
                "n_vars_overridden": len(vintage_vals),
                "vars": list(vintage_vals.keys()),
                "provenance": PROVENANCE,
                "coverage_note": coverage_note(date),
            },
            "rationalizations": {},
        }

        # 走偏的圆场（用 Pass1 verdict vs GT）
        for v in f1.verdicts:
            if v._failed:
                continue
            d5 = v.verdict["T+5"].dir
            d20 = v.verdict["T+20"].dir
            miss5 = (d5 != gt5) if gt5 != "?" else False
            miss20 = (d20 != gt20) if gt20 != "?" else False
            if not (miss5 or miss20):
                continue
            ms = ", ".join(
                ([f"T+5 给了 {d5}，实际 {gt5}"] if miss5 else [])
                + ([f"T+20 给了 {d20}，实际 {gt20}"] if miss20 else [])
            )
            prompt = RATIONALIZE_TEMPLATE.format(
                school_label=SCHOOL_ZH.get(v.school, v.school),
                date=date, event=event,
                dir5=d5, dir20=d20, true5=gt5, true20=gt20,
                miss_summary=ms,
            )
            # 系统提示 = 人格段（剥预测任务）
            persona = PROMPTS[v.school].split("任务：")[0].strip()
            print(f"  圆场 {v.school}…", end=" ", flush=True)
            text = chat_text(client, persona, prompt, max_tokens=350)
            rec["rationalizations"][v.school] = text
            print("ok" if not text.startswith("[") else "fail")

        out[date] = rec

    if args.dry:
        print("\n（--dry 干跑，未写出）")
        return 0

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"\n✓ saved {len(out)} anchors → {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
