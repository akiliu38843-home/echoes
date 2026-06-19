"""路径 #1 · CPI 修订污染量级实测（零-LLM，严按预注册）。

复刻 fred._yoy_pct + continuous._catalyst_asof 的 CPI 段，**只把数据源从
"revised-latest" 换成 ALFRED vintage(realtime_start=realtime_end=当日)**，
其余逻辑/阈值逐字不动（预注册 §1）。

预注册口径（AUTHORIZE + SCOPE_ADDENDUM，已冻结）：
- 分母 = CPI 承重催化点（reasons 含"通胀加速"）；纯利率/纯GPR 不入。
- 翻 = 用首发布 CPI 重算后 ①进出 ②档(轻/中/重) ③性质(通胀↔通缩) 任一变。
- 线 = 翻/判得了 ≤5% → GO(限范围,加注脚)；>5% → NO-GO 启 #2。
- 规矩A：取不到 vintage → "无法判定" 单列续挂，绝不并进干净。
- 规矩B：判得了的 N < 15 → 功效不足→悬置(翻率好看也不GO)。15=项目旧尺。
- B1：过线只报"过最低门槛+二项CI"，非"已证清白"。
- B2：333 主判；50 层 CPI 子集 <15 单独挂功效不足、不随 333 解挂。
- 333 层 GO/NO-GO 为准，50 层副报。逐点 before/after 表落盘可复核。
"""
from __future__ import annotations

import datetime as dt
import json
import math
import os
import re
import sys

import requests

CPI_DPP = 1.0          # _CAT_CPI_DPP（逐字）
ALFRED = "https://api.stlouisfed.org/fred/series/observations"
NOPROXY = {"http": None, "https": None}
SERIES = "CPIAUCSL"     # registry: us_cpi_yoy → CPIAUCSL (SA)


def _key() -> str:
    k = os.environ.get("FRED_API_KEY")
    if k:
        return k.strip()
    for p in ("/Users/a26976/Desktop/Hindcast-鉴往/04-graphrag-build/factual_rag/.env",):
        try:
            for line in open(p):
                if line.startswith("FRED_API_KEY="):
                    return line.split("=", 1)[1].strip().strip('"')
        except FileNotFoundError:
            pass
    raise SystemExit("FRED_API_KEY missing")


KEY = _key()


def _yoy_pct(observations: list[dict]) -> list[dict]:
    """逐字复刻 fred.py:_yoy_pct。"""
    by_date: dict[str, float] = {}
    parsed: list[tuple[dt.date, float | None]] = []
    for o in observations:
        try:
            d = dt.date.fromisoformat(o["date"])
        except Exception:
            continue
        v = o.get("value")
        try:
            fv = float(v) if v not in (".", None, "") else None
        except Exception:
            fv = None
        parsed.append((d, fv))
        if fv is not None:
            by_date[d.isoformat()] = fv
    out = []
    for d, fv in parsed:
        if fv is None:
            out.append({"date": d.isoformat(), "value": None}); continue
        target = d - dt.timedelta(days=365)
        bp = None
        for delta in range(0, 31):
            for sign in (-1, 1):
                key = (target + dt.timedelta(days=sign * delta)).isoformat()
                if key in by_date:
                    bp = by_date[key]; break
            if bp is not None:
                break
        if bp is None or bp == 0:
            out.append({"date": d.isoformat(), "value": None})
        else:
            out.append({"date": d.isoformat(), "value": round((fv / bp - 1) * 100, 4)})
    return out


def vintage_yoy_asof(asof: str) -> float | None:
    """ALFRED: CPIAUCSL 在 asof 当日已发布的 vintage → yoy at 最新 ref ≤ asof。
    复刻 value_at 的 'at-or-before' + _yoy_pct。取不到 → None(无法判定信号)。"""
    d = dt.date.fromisoformat(asof)
    obs_start = (d - dt.timedelta(days=600)).isoformat()
    params = {
        "series_id": SERIES, "api_key": KEY, "file_type": "json",
        "sort_order": "asc", "realtime_start": asof, "realtime_end": asof,
        "observation_start": obs_start, "observation_end": asof,
    }
    try:
        r = requests.get(ALFRED, params=params, timeout=30, proxies=NOPROXY)
        if r.status_code != 200:
            return None
        obs = r.json().get("observations", [])
    except Exception:
        return None
    yo = [x for x in _yoy_pct(obs) if x["value"] is not None
          and dt.date.fromisoformat(x["date"]) <= d]
    return yo[-1]["value"] if yo else None


def tier(absd: float) -> str:
    return "重" if absd >= 3.0 else "中" if absd >= 2.0 else "轻"


def shift(date: str, days: int) -> str:
    return (dt.date.fromisoformat(date) + dt.timedelta(days=days)).isoformat()


def wilson(k: int, n: int):
    if n == 0:
        return (0.0, 0.0)
    z = 1.96
    p = k / n
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return (max(0, c - h) * 100, min(1, c + h) * 100)


def main():
    H = json.load(open("/tmp/hc_rerun/catalyst_dates.json"))
    SEL = {r["date"] for r in json.load(open("/tmp/hc_rerun/selected_dates.json"))}
    # 分母：CPI 承重点（reason 含 通胀加速）
    den = []
    for r in H:
        rs = r["reasons"]
        cpi = next((x for x in rs if "通胀加速" in x), None)
        if not cpi:
            continue
        m = re.search(r"Δ3m=([+-]?\d+\.?\d*)", cpi)
        if not m:
            continue
        d_orig = float(m.group(1))
        den.append({"date": r["date"], "d_orig": d_orig,
                    "fired_o": abs(d_orig) >= CPI_DPP,
                    "tier_o": tier(abs(d_orig)),
                    "reg_o": "通胀冲击" if d_orig > 0 else "通缩冲击",
                    "in50": r["date"] in SEL})
    print(f"分母(CPI承重)={len(den)}  其中下选50层={sum(x['in50'] for x in den)}")
    print("逐点实测中（ALFRED vintage，零LLM）…\n")

    rows, undet = [], []
    for i, x in enumerate(den, 1):
        c0 = vintage_yoy_asof(x["date"])
        c3 = vintage_yoy_asof(shift(x["date"], -90))
        if c0 is None or c3 is None:
            undet.append(x["date"])
            print(f"  [{i}/{len(den)}] {x['date']}  无法判定(ALFRED 空)")
            continue
        dv = round(c0 - c3, 4)
        fired_v = abs(dv) >= CPI_DPP
        tier_v = tier(abs(dv)) if fired_v else "—"
        reg_v = ("通胀冲击" if dv > 0 else "通缩冲击") if fired_v else "—"
        flip_io = fired_v != x["fired_o"]
        flip_tier = fired_v and x["fired_o"] and tier_v != x["tier_o"]
        flip_sign = fired_v and x["fired_o"] and reg_v != x["reg_o"]
        flip = bool(flip_io or flip_tier or flip_sign)
        rows.append({**x, "d_vint": dv, "fired_v": fired_v, "tier_v": tier_v,
                     "reg_v": reg_v, "flip": flip,
                     "flip_kind": ("进出" if flip_io else "") + ("档" if flip_tier else "")
                                  + ("性质" if flip_sign else "")})
        mark = f"⚠️翻({rows[-1]['flip_kind']})" if flip else "ok"
        print(f"  [{i}/{len(den)}] {x['date']}  orig Δ{x['d_orig']:+.1f}"
              f"({x['tier_o']}{x['reg_o'][:2]}) → vint Δ{dv:+.2f}"
              f"({tier_v}{reg_v[:2] if reg_v!='—' else '—'})  {mark}")

    det = len(rows)
    flips = sum(r["flip"] for r in rows)
    fr_all = flips / det * 100 if det else 0.0
    lo, hi = wilson(flips, det)
    s50 = [r for r in rows if r["in50"]]
    f50 = sum(r["flip"] for r in s50)
    fr50 = f50 / len(s50) * 100 if s50 else 0.0

    R = ["=" * 60, "路径 #1 结果（对照已冻结预注册）", "=" * 60,
         f"分母(CPI承重) {len(den)} | 判得了 {det} | 无法判定 {len(undet)}（单列续挂，不并入）",
         "",
         f"【333 主判层】翻 {flips}/{det} = {fr_all:.1f}%  Wilson95%CI[{lo:.1f}%,{hi:.1f}%]",
         f"【50 副报层】 翻 {f50}/{len(s50)} = {fr50:.1f}%  (N={len(s50)})",
         ""]
    # 规矩B + B1 + B2 + 5% 死线 自动判（不重谈）
    if det < 15:
        R.append(f"规矩B：判得了 {det} < 15(项目旧尺) → 功效不足→悬置/交回。不计 GO。")
    elif fr_all <= 5.0:
        R.append(f"333 翻率 {fr_all:.1f}% ≤ 5% 且 判得了 {det} ≥ 15 → **GO（限范围）**")
        R.append(f"  B1：仅报'过预注册最低门槛，N={det}，95%CI 上界 {hi:.1f}%'，非'已证清白'。")
        R.append(f"  范围限定：本 GO 仅覆盖 {det} 可查点；无法判定 {len(undet)} 个维持挂起单列。")
    else:
        R.append(f"333 翻率 {fr_all:.1f}% > 5% → **NO-GO**：该批作废，须启 #2 接真 vintage 重做。")
    # B2：50 层独立功效闸
    if len(s50) < 15:
        R.append(f"规矩B2：50 层 CPI 子集 N={len(s50)} < 15 → 该层单独'功效不足→悬置'，"
                 f"**不随 333 解挂**（局部不冒充整体）。")
    else:
        R.append(f"规矩B2：50 层 N={len(s50)} ≥15；翻率 {fr50:.1f}%（副报，GO/NO-GO 仍以 333 为准）。")
    if undet:
        R.append(f"\n无法判定单列（续挂、绝不计数）: {undet}")
    out = "\n".join(R)
    print("\n" + out)
    json.dump({"rows": rows, "undet": undet,
               "summary": {"den": len(den), "det": det, "flips": flips,
                           "fr333": fr_all, "ci": [lo, hi],
                           "n50": len(s50), "fr50": fr50}},
              open("/tmp/hc_rerun/cpi_contam.json", "w"), ensure_ascii=False, indent=1)
    open("/tmp/hc_rerun/cpi_contam_report.txt", "w").write(out)
    print("\n逐点表+判定 落盘: /tmp/hc_rerun/cpi_contam.json + _report.txt")


if __name__ == "__main__":
    main()
