"""学派命中率 + 缺陷洞察账本（17-ADR 首个产品产出）。

新产品形态下，这**不是成绩单，是研究台账**：忠实统计每个经济学派的方向命中率，
并给每个学派打"系统性失败模式"标签——这本身就是产品的交付物，且直接指出
"拟合修正层该优先修哪个学派"。

诚实纪律（17-ADR §4）：
- 数据源是 9 事件日志 → 必带"事件选择偏差"caveat（这些是手挑戏剧时点，分数偏高）
- 永远附诚实基线对照（永远猜该数据集最常见真实方向）
- 失败标签只描述"推理行为"，不冒充"准确率背书"

零 LLM：复用已有事件回测日志。
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Optional

# 事件块头： ========== 标签 (YYYY-MM-DD) [TARGET] ==========
_HDR = re.compile(r'=+\s*(.+?)\s*\((\d{4}-\d\d-\d\d)\)\s*\[([^\]]+)\]')
_SKIP = re.compile(r'=+\s*(.+?)\s*\((\d{4}-\d\d-\d\d)\)\s*—\s*跳过')
# 学派行：  school                 T+5: dir  T+20: dir
_ROW = re.compile(
    r'^\s*(austrian|monetarist|keynesian|rational_expectations)\s+'
    r'T\+5:\s*(up|down|flat)\s+T\+20:\s*(up|down|flat)')
# 连续平稳期内嵌真值行（17-ADR A）：  __GT__   T+5: dir  T+20: dir
# 它的存在 = 该块来自连续回测、当场用 factual_rag 算的真值 → 无事件选择偏差。
_GT_ROW = re.compile(
    r'^\s*__GT__\s+T\+5:\s*(up|down|flat|\?)\s+T\+20:\s*(up|down|flat|\?)')

_SCHOOLS = ("austrian", "monetarist", "keynesian", "rational_expectations")
_CN = {"austrian": "奥地利", "monetarist": "货币主义",
       "keynesian": "凯恩斯", "rational_expectations": "理性预期"}


def _gt_for(target: str) -> dict:
    from hindcast.data.ground_truth import (
        FX_GROUND_TRUTH, YIELD_GROUND_TRUTH, COMMODITY_GROUND_TRUTH,
        BRIDGE_GROUND_TRUTH,
    )
    # target → (GT dict, key in per-date dict)
    if target in ("USD/JPY", "USD/CNH", "EUR/USD"):
        return {d: v.get(target, {}) for d, v in FX_GROUND_TRUTH.items()}
    if target in ("US_2Y", "US_10Y"):
        return {d: v.get(target, {}) for d, v in YIELD_GROUND_TRUTH.items()}
    if target in ("CRUDE_OIL", "COPPER"):
        return {d: v.get(target, {}) for d, v in COMMODITY_GROUND_TRUTH.items()}
    if target in ("US_10Y_TIPS", "US_10Y_BEI", "DXY"):
        return {d: v.get(target, {}) for d, v in BRIDGE_GROUND_TRUTH.items()}
    return {}


def _parse(path: str):
    """→ list of {date, target, schools, gt_inline?}

    gt_inline 存在 ⇒ 该事件块来自连续平稳期回测（无事件选择偏差）。
    """
    events, cur = [], None
    for ln in open(path):
        if _SKIP.search(ln):
            cur = None
            continue
        h = _HDR.search(ln)
        if h:
            cur = {"date": h.group(2), "target": h.group(3), "schools": {}}
            events.append(cur)
            continue
        g = _GT_ROW.match(ln)
        if g and cur is not None:
            cur["gt_inline"] = {"T+5": g.group(1), "T+20": g.group(2)}
            continue
        m = _ROW.match(ln)
        if m and cur is not None:
            cur["schools"][m.group(1)] = {"T+5": m.group(2), "T+20": m.group(3)}
    return [e for e in events if e["schools"]]


def _actual(e: dict, gt: dict, H: str) -> Optional[str]:
    """该事件在 horizon H 的真实方向：优先内嵌真值（连续，无偏差），
    否则回退静态 GROUND_TRUTH 字典（老的 9 事件路径，行为不变）。"""
    gi = e.get("gt_inline")
    if gi is not None:
        d = gi.get(H)
        return d if d in ("up", "down", "flat") else None
    return gt.get(e["date"], {}).get(H, {}).get("dir")


def _baseline(actuals: list[str]) -> tuple[str, float]:
    """诚实基线：永远猜最常见真实方向，其命中率。"""
    c = defaultdict(int)
    for a in actuals:
        c[a] += 1
    if not c:
        return "?", 0.0
    best = max(c, key=c.get)
    return best, c[best] / len(actuals)


def build_ledger(logs: list[str]) -> None:
    # 收集 per (target,school,horizon) 的 (pred, actual) 对 + 聚合(多数票)对照
    by_target = defaultdict(lambda: {"events": [], "gt": {}})
    for lg in logs:
        for e in _parse(lg):
            t = e["target"]
            by_target[t]["events"].append(e)
    for t in by_target:
        by_target[t]["gt"] = _gt_for(t)

    all_evs = [e for blk in by_target.values() for e in blk["events"]]
    n_inline = sum(1 for e in all_evs if "gt_inline" in e)
    n_event = len(all_evs) - n_inline

    print("=" * 70)
    print("学派命中率 + 缺陷洞察账本   (17-ADR 首个产品产出 · 零 LLM)")
    print("=" * 70)
    if n_inline and not n_event:
        # 17-ADR A 达成：全部来自连续平稳期回测，真值当场算 → 无事件选择偏差
        print(f"✅ 数据源 = 连续平稳期回测 {n_inline} 个月度点（真值由 factual_rag 当场算）。")
        print("   **无事件选择偏差**——这正是 17-ADR §4 要求的、可据以谈'先修谁'的可信账本。")
        print("   （仍非准确率背书：账本的产品价值在刻画推理行为，不在绝对分数。）\n")
    elif n_inline and n_event:
        print(f"⚠️ 混合数据源：连续平稳期 {n_inline} 点（无偏差）+ 戏剧事件 {n_event} 点（有选择偏差）。")
        print("   下方未区分两者；要谈'先修谁'请只用纯连续日志（17-ADR §4）。\n")
    else:
        print(f"⚠️ 数据源 = {n_event} 个戏剧性事件日志：含**事件选择偏差**，绝对分数偏高，")
        print("   本账本价值在'刻画每个学派的推理行为与系统盲区'，非准确率背书。\n")

    fix_priority = []

    for target, blk in by_target.items():
        evs = blk["events"]
        gt = blk["gt"]
        # 过滤有可对照真值的事件（内嵌真值优先，否则静态字典）
        usable = [e for e in evs
                  if _actual(e, gt, "T+5") or _actual(e, gt, "T+20")]
        if not usable:
            print(f"[{target}] 无可对照 GT，跳过\n")
            continue
        n = len(usable)
        src = "连续月度点" if all("gt_inline" in e for e in usable) else "有 GT 的事件"
        print(f"━━━ {target}  ({n} 个{src}) ━━━")
        # 真实方向序列（用于诚实基线）
        for H in ("T+5", "T+20"):
            actuals = [_actual(e, gt, H) for e in usable]
            actuals = [a for a in actuals if a]
            base_dir, base_hit = _baseline(actuals)
            agg_dirs = []
            print(f"  [{H}]  真实方向分布 "
                  f"{ {d: actuals.count(d) for d in ('up','down','flat')} }  "
                  f"| 诚实基线='永远猜{base_dir}' {base_hit*100:.0f}%")
            for s in _SCHOOLS:
                preds = []
                hits = 0
                pn = 0
                for e in usable:
                    a = _actual(e, gt, H)
                    p = e["schools"].get(s, {}).get(H)
                    if a and p:
                        preds.append(p)
                        pn += 1
                        hits += (p == a)
                if pn == 0:
                    continue
                hr = hits / pn
                prof = {d: preds.count(d) for d in ("up", "down", "flat")}
                # —— 系统性失败标签（产品的"缺陷洞察"产出）——
                tags = []
                top = max(prof, key=prof.get)
                if prof[top] / pn >= 0.8:
                    tags.append(f"单调偏置(≥80%说{top})")
                if prof["flat"] == 0:
                    tags.append("从不说flat")
                if hr <= base_hit + 1e-9:
                    tags.append(f"≤诚实基线({base_hit*100:.0f}%)=无独立技能")
                marker = "  ⚠️" if tags else ""
                print(f"    {_CN[s]:<5}({s[:3]}) 命中 {hits}/{pn}={hr*100:>3.0f}%  "
                      f"画像{prof}  {' / '.join(tags) if tags else 'OK'}{marker}")
                fix_priority.append((target, H, s, hr, base_hit, tags))
        print()

    # —— 拟合修正层优先级（产品给自己的下一步）——
    print("=" * 70)
    print("拟合修正层·优先级线索（哪个学派最该先修）")
    print("=" * 70)
    drag = defaultdict(lambda: {"below_base": 0, "monotone": 0, "n": 0})
    for target, H, s, hr, bh, tags in fix_priority:
        d = drag[s]
        d["n"] += 1
        if hr <= bh + 1e-9:
            d["below_base"] += 1
        if any("单调偏置" in t for t in tags):
            d["monotone"] += 1
    for s in _SCHOOLS:
        d = drag[s]
        if d["n"]:
            print(f"  {_CN[s]:<5}: 受测 {d['n']} 项 | ≤基线 {d['below_base']} 项 "
                  f"| 单调偏置 {d['monotone']} 项")
    print("\n解读: '≤基线'多 = 该学派对'无关联猜测'没有改进，是拟合修正层的首要对象；")
    print("      '单调偏置'多 = 该学派缺对立 regime 的理论(如奥地利无横盘/无强USD理论)。")
    print("注: 仍是事件选择偏差下的画像；样本外验证前不得当作修正层有效性证据(17-ADR §4)。")
